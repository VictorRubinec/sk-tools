"""Interface de Linha de Comando (CLI) unificada do ecossistema Studio Kustom (sk-tools)."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import List, Optional, Sequence

from pydantic import ValidationError

from tools.background_expander.api import expand_background
from tools.background_expander.prompt_builder import (
    DEFAULT_BLEED_MM,
    calculate_bleed_pixels,
    normalize_expansion_mode,
)
from tools.card_generator.api import check_gemini_session as api_check_gemini_session
from tools.card_generator.browser.exceptions import GeminiBrowserError
from tools.card_generator.browser.session import get_chrome_context
from tools.card_generator.core.config import AppConfig, DEFAULT_CONFIG, INPUT_DIR
from tools.card_generator.core.logger import logger, setup_logger
from tools.card_generator.core.runner import CardGenerationRunner
from tools.card_generator.core.schema import CardInput, load_cards_from_file
from tools.upscaler.api import upscale_card_to_poster
from tools.upscaler.prompt_builder import normalize_target_format

CARD_GEN_COMMANDS = {"card-gen", "cards", "card"}
UPSCALE_COMMANDS = {"upscale", "poster", "up"}
EXPAND_COMMANDS = {"expand", "outpaint", "bg"}
ALL_SUBCOMMANDS = CARD_GEN_COMMANDS | UPSCALE_COMMANDS | EXPAND_COMMANDS


def _add_common_logging_arguments(parser: argparse.ArgumentParser) -> None:
    """Adiciona argumentos comuns de execução e logging em um parser."""
    parser.add_argument(
        "-r",
        "--retries",
        type=int,
        default=3,
        help="Número máximo de tentativas em caso de falha ou reprovação (padrão: 3).",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Executa o navegador em modo sem interface gráfica (headless=True).",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR"],
        help="Nível de detalhamento dos logs de console (padrão: INFO).",
    )
    parser.add_argument(
        "--no-file-log",
        action="store_true",
        help="Desativa a gravação persistente de logs em arquivo (output/logs/).",
    )


def _add_card_gen_arguments(parser: argparse.ArgumentParser) -> None:
    """Adiciona os argumentos da ferramenta `card-gen` em um parser/subparser."""
    parser.add_argument(
        "-i",
        "--input",
        type=str,
        default=str(INPUT_DIR / "sample_cards.json"),
        help="Caminho para arquivo JSON contendo uma ou mais cartas (padrão: input/sample_cards.json).",
    )
    parser.add_argument(
        "-c",
        "--card",
        type=str,
        default=None,
        help="JSON inline representando uma única carta para processamento imediato.",
    )
    parser.add_argument(
        "--check-session",
        action="store_true",
        help="Apenas verifica se a sessão do Google Gemini está autenticada e encerra.",
    )
    _add_common_logging_arguments(parser)


def _add_upscale_arguments(parser: argparse.ArgumentParser) -> None:
    """Adiciona os argumentos da ferramenta `upscale` em um subparser."""
    parser.add_argument(
        "--image",
        "-i",
        type=str,
        required=True,
        help="Caminho da imagem da carta original a ser convertida em poster.",
    )
    parser.add_argument(
        "--target",
        "-t",
        type=str,
        required=True,
        help="Formato alvo do poster a 300 DPI ('a4_v', 'a4_h', 'a3_v', 'a3_h').",
    )
    _add_common_logging_arguments(parser)


def _add_expand_arguments(parser: argparse.ArgumentParser) -> None:
    """Adiciona os argumentos da ferramenta `expand` em um subparser."""
    parser.add_argument(
        "--image",
        "-i",
        type=str,
        required=True,
        help="Caminho da imagem original para expansão de fundo (outpainting).",
    )
    parser.add_argument(
        "--mode",
        "-m",
        type=str,
        default="bleed_5mm",
        help="Modo de expansão de fundo ('bleed_5mm', 'horizontal', 'caneca', 'custom').",
    )
    parser.add_argument(
        "--bleed",
        "-b",
        type=float,
        default=DEFAULT_BLEED_MM,
        help="Milímetros de margem de sangria por borda a 300 DPI (padrão: 5.0).",
    )
    _add_common_logging_arguments(parser)


def build_arg_parser() -> argparse.ArgumentParser:
    """Constrói e retorna o parser de argumentos da CLI com suporte a subcomandos."""
    parser = argparse.ArgumentParser(
        prog="sk-tools",
        description=(
            "Suíte unificada de automação Studio Kustom (sk-tools). "
            "Inclui gerador de cartas (card-gen), upscaler de posters (upscale) e expansor de fundo (expand)."
        ),
    )
    _add_card_gen_arguments(parser)

    subparsers = parser.add_subparsers(
        dest="command",
        title="subcomandos disponíveis",
        description="Ferramentas encapsuladas do ecossistema sk-tools (padrão: card-gen).",
    )

    card_gen_parser = subparsers.add_parser(
        "card-gen",
        aliases=["cards", "card"],
        help="Gerador e validador automatizado de cartas TCG via Google Gemini Web.",
        description="Executa a geração e validação de cartas colecionáveis (TCG).",
    )
    _add_card_gen_arguments(card_gen_parser)

    upscale_parser = subparsers.add_parser(
        "upscale",
        aliases=["poster", "up"],
        help="Upscaler e redraw de cartas para posters 300 DPI (A4/A3 Vertical e Horizontal).",
        description="Realiza o redraw e super-resolução de uma carta para poster em 300 DPI.",
    )
    _add_upscale_arguments(upscale_parser)

    expand_parser = subparsers.add_parser(
        "expand",
        aliases=["outpaint", "bg"],
        help="Expansor generativo de fundo (outpainting) com sangria de 5mm a 300 DPI.",
        description="Estende o cenário ao redor da imagem mantendo o sujeito central preservado.",
    )
    _add_expand_arguments(expand_parser)

    return parser


def check_gemini_session(config: AppConfig) -> int:
    """Abre o navegador configurado, verifica o status de login no Gemini e retorna exit code."""
    authenticated = api_check_gemini_session(config)
    return 0 if authenticated else 1


def resolve_input_cards(args: argparse.Namespace) -> List[CardInput]:
    """Carrega a lista de cartas a partir de `--card` (JSON inline) ou `--input` (arquivo)."""
    if args.card:
        try:
            payload = json.loads(args.card)
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON inline inválido em --card: {exc}") from exc

        if isinstance(payload, list):
            return [CardInput.model_validate(item) for item in payload]
        if isinstance(payload, dict):
            return [CardInput.model_validate(payload)]
        raise ValueError("O JSON fornecido em --card deve ser um objeto ou lista.")

    return load_cards_from_file(Path(args.input))


def run_card_generator_cli(args: argparse.Namespace) -> int:
    """Executa o fluxo operacional do subcomando `card-gen`."""
    setup_logger(
        console_level=args.log_level,
        log_to_file=not args.no_file_log,
    )

    if args.retries < 1:
        logger.error("O argumento --retries deve ser maior ou igual a 1.")
        return 2

    config = replace(
        DEFAULT_CONFIG,
        headless=True if args.headless else DEFAULT_CONFIG.headless,
    )
    config.ensure_directories()

    if args.check_session:
        return check_gemini_session(config)

    logger.info("Iniciando SK-TOOLS [card-gen] | Gerador e Validador Automatizado de Cartas TCG")

    try:
        cards = resolve_input_cards(args)
    except (FileNotFoundError, ValueError, ValidationError) as exc:
        logger.error("Falha ao carregar dados das cartas: {}", exc)
        return 1

    logger.info(
        "Cartas carregadas: {} | Máx. Tentativas: {} | Headless: {}",
        len(cards),
        args.retries,
        config.headless,
    )

    runner = CardGenerationRunner()
    succeeded = 0
    failed = 0

    shared_context = get_chrome_context(config) if len(cards) > 1 else None
    try:
        for idx, card in enumerate(cards, start=1):
            logger.info(
                "[{}/{}] Processando carta: '{}' ({} - {})",
                idx,
                len(cards),
                card.titulo,
                card.tipo,
                card.estilo,
            )

            ok, output_path, validation = runner.process_card(
                card=card,
                config=config,
                max_retries=args.retries,
                context=shared_context,
            )

            if ok and output_path is not None and validation is not None:
                succeeded += 1
                logger.success(
                    "[{}/{}] Carta '{}' APROVADA ({}x{}px | Ratio: {:.2f}) -> {}",
                    idx,
                    len(cards),
                    card.titulo,
                    validation.width,
                    validation.height,
                    validation.aspect_ratio,
                    output_path,
                )
            else:
                failed += 1
                reasons = (
                    "; ".join(validation.errors)
                    if validation and validation.errors
                    else "Falha de comunicação/geração no navegador."
                )
                logger.error(
                    "[{}/{}] Carta '{}' REPROVADA após {} tentativa(s). Motivo: {}",
                    idx,
                    len(cards),
                    card.titulo,
                    args.retries,
                    reasons,
                )
    finally:
        if shared_context is not None:
            shared_context.close()

    logger.info(
        "Processamento finalizado | Total: {} | Sucesso: {} | Falhas: {}",
        len(cards),
        succeeded,
        failed,
    )

    return 0 if failed == 0 else 1


def run_upscale_cli(args: argparse.Namespace) -> int:
    """Executa o fluxo operacional do subcomando `upscale`."""
    setup_logger(
        console_level=args.log_level,
        log_to_file=not args.no_file_log,
    )

    if args.retries < 1:
        logger.error("O argumento --retries deve ser maior ou igual a 1.")
        return 2

    try:
        spec = normalize_target_format(args.target)
    except ValueError as exc:
        logger.error("Erro de parâmetro em --target: {}", exc)
        return 2

    config = replace(
        DEFAULT_CONFIG,
        headless=True if args.headless else DEFAULT_CONFIG.headless,
    )
    config.ensure_directories()

    logger.info(
        "Iniciando SK-TOOLS [upscale] | Imagem: '{}' -> Formato: {} ({}x{}px @ {} DPI)",
        args.image,
        spec.code,
        spec.width_px,
        spec.height_px,
        spec.dpi,
    )

    try:
        poster_path = upscale_card_to_poster(
            image_path=Path(args.image),
            target_format=spec.code,
            config=config,
            max_retries=args.retries,
        )
        logger.success("Poster gerado com sucesso em: {}", poster_path)
        return 0
    except (FileNotFoundError, ValueError, GeminiBrowserError) as exc:
        logger.error("Falha no upscaling para poster: {}", exc)
        return 1


def run_expand_cli(args: argparse.Namespace) -> int:
    """Executa o fluxo operacional do subcomando `expand` (outpainting)."""
    setup_logger(
        console_level=args.log_level,
        log_to_file=not args.no_file_log,
    )

    if args.retries < 1:
        logger.error("O argumento --retries deve ser maior ou igual a 1.")
        return 2

    try:
        spec = normalize_expansion_mode(args.mode)
        bleed_px = calculate_bleed_pixels(args.bleed)
    except ValueError as exc:
        logger.error("Erro de parâmetro em expand: {}", exc)
        return 2

    config = replace(
        DEFAULT_CONFIG,
        headless=True if args.headless else DEFAULT_CONFIG.headless,
    )
    config.ensure_directories()

    logger.info(
        "Iniciando SK-TOOLS [expand] | Imagem: '{}' | Modo: {} | Sangria: {:.1f}mm ({}px/borda @ 300 DPI)",
        args.image,
        spec.code,
        args.bleed,
        bleed_px,
    )

    try:
        expanded_path = expand_background(
            image_path=Path(args.image),
            mode=spec.code,
            bleed_mm=args.bleed,
            config=config,
            max_retries=args.retries,
        )
        logger.success("Imagem expandida gerada com sucesso em: {}", expanded_path)
        return 0
    except (FileNotFoundError, ValueError, GeminiBrowserError) as exc:
        logger.error("Falha na expansão de fundo: {}", exc)
        return 1


def _normalize_argv(argv: Sequence[str]) -> List[str]:
    """Insere o subcomando padrão `card-gen` quando nenhum subcomando explícito é informado."""
    args_list = list(argv)
    if not args_list:
        return ["card-gen"]
    first = args_list[0]
    if first in ("-h", "--help"):
        return args_list
    if first not in ALL_SUBCOMMANDS:
        return ["card-gen", *args_list]
    return args_list


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Ponto de entrada principal da CLI unificada."""
    parser = build_arg_parser()
    raw_argv = sys.argv[1:] if argv is None else list(argv)
    normalized_argv = _normalize_argv(raw_argv)
    args = parser.parse_args(normalized_argv)

    command = getattr(args, "command", None) or "card-gen"
    if command in CARD_GEN_COMMANDS:
        return run_card_generator_cli(args)
    if command in UPSCALE_COMMANDS:
        return run_upscale_cli(args)
    if command in EXPAND_COMMANDS:
        return run_expand_cli(args)

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
