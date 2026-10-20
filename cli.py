"""Interface de Linha de Comando (CLI) unificada do ecossistema Studio Kustom (sk-tools)."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import List, Optional, Sequence, Union

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
from tools.mug_artist.api import create_mug_artwork
from tools.mug_artist.composer import DEFAULT_MUG_SPEC, normalize_mug_mode
from tools.mug_artist.orchestrator import run_mug_artwork_orchestration
from tools.mug_artist.schema import MugInput, load_mugs_from_file
from tools.order_planner.orchestrator import run_order_by_id
from tools.order_planner.scanner import (
    DEFAULT_ORDERS_ROOT,
    discover_orders,
    find_order_by_id,
)
from tools.order_planner.schema import normalize_product_route
from tools.print_sheet.api import (
    create_card_print_sheet,
    create_poster_print_sheet,
    discover_card_images,
)
from tools.print_sheet.card_grid import normalize_paper_spec
from tools.upscaler.api import upscale_card_to_poster
from tools.upscaler.prompt_builder import normalize_target_format

CARD_GEN_COMMANDS = {"card-gen", "cards", "card"}
UPSCALE_COMMANDS = {"upscale", "poster", "up"}
EXPAND_COMMANDS = {"expand", "outpaint", "bg"}
SHEET_COMMANDS = {"sheet", "print-sheet", "folha", "imposition"}
MUG_COMMANDS = {"mug", "caneca", "mug-art"}
ORDER_COMMANDS = {"order", "pedidos", "planner"}
ALL_SUBCOMMANDS = (
    CARD_GEN_COMMANDS
    | UPSCALE_COMMANDS
    | EXPAND_COMMANDS
    | SHEET_COMMANDS
    | MUG_COMMANDS
    | ORDER_COMMANDS
)


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
    parser.add_argument(
        "--preserve-frame",
        "--frame",
        "-f",
        action="store_true",
        help="Mantém a moldura ornamental fixa no centro e expande o cenário de fundo para fora dela.",
    )
    _add_common_logging_arguments(parser)


def _add_sheet_arguments(parser: argparse.ArgumentParser) -> None:
    """Adiciona os argumentos da ferramenta `sheet` (imposição gráfica PDF) em um subparser."""
    parser.add_argument(
        "--cards",
        nargs="+",
        type=str,
        default=None,
        help="Lista de caminhos das imagens da frente das cartas (ex: output/carta1.png output/carta2.png).",
    )
    parser.add_argument(
        "--cards-dir",
        type=str,
        default=None,
        help="Diretório contendo as imagens da frente das cartas (ex: output/).",
    )
    parser.add_argument(
        "--back",
        nargs="+",
        type=str,
        default=None,
        help="Caminho da imagem de verso padrão único ou lista de versos individuais.",
    )
    parser.add_argument(
        "--poster",
        type=str,
        default=None,
        help="Caminho da imagem do pôster para imposição centralizada com marcas de corte.",
    )
    parser.add_argument(
        "--paper",
        "-p",
        type=str,
        default="super_a4",
        help="Formato físico da folha ('super_a4', 'a4' ou 'a3' a 300 DPI). Padrão: super_a4.",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        help="Caminho do arquivo PDF de saída.",
    )
    _add_common_logging_arguments(parser)


def _add_mug_arguments(parser: argparse.ArgumentParser) -> None:
    """Adiciona os argumentos da ferramenta `mug` (arte de caneca 11oz) em um subparser."""
    parser.add_argument(
        "-i",
        "--input",
        type=str,
        default=None,
        help="Caminho para arquivo JSON de canecas (ex: input/sample_mugs.json) ou caminho de imagem.",
    )
    parser.add_argument(
        "--mug",
        type=str,
        default=None,
        help="JSON inline representando uma única caneca para processamento imediato.",
    )
    parser.add_argument(
        "--image",
        type=str,
        default=None,
        help="Caminho de uma imagem única para montagem local de arte da caneca.",
    )
    parser.add_argument(
        "--images",
        nargs="+",
        type=str,
        default=None,
        help="Lista de caminhos de imagens para arte de caneca (ex: output/carta1.png output/carta2.png).",
    )
    parser.add_argument(
        "--mode",
        "-m",
        type=str,
        default="panoramic",
        help="Modo de layout da caneca ('panoramic', 'dual_face' ou 'card_plus_text'). Padrão: panoramic.",
    )
    parser.add_argument(
        "--text",
        type=str,
        default=None,
        help="Texto comemorativo ou mensagem para a outra face (modo 'card_plus_text').",
    )
    parser.add_argument(
        "--mirror",
        dest="mirror",
        action="store_true",
        default=True,
        help="Gera a arte espelhada horizontalmente para prensa de sublimação (padrão: True).",
    )
    parser.add_argument(
        "--no-mirror",
        dest="mirror",
        action="store_false",
        help="Desativa o espelhamento horizontal (gera apenas a arte em orientação normal).",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        help="Caminho opcional do arquivo PNG de saída.",
    )
    _add_common_logging_arguments(parser)


def _add_order_arguments(parser: argparse.ArgumentParser) -> None:
    """Adiciona os argumentos da ferramenta `order` (planejador e esteira de pedidos) em um subparser."""
    parser.add_argument(
        "--scan",
        action="store_true",
        help="Lista pedidos pendentes (ignorando pastas '- ok') e arquivos detectados.",
    )
    parser.add_argument(
        "--plan",
        action="store_true",
        help="Exibe a rota produtiva e a fila de tarefas planejada para o pedido informado em --id.",
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="Executa a fila de ferramentas e avalia todos os Quality Gates para o pedido em --id.",
    )
    parser.add_argument(
        "--id",
        dest="order_id",
        type=str,
        default=None,
        help="Identificador do pedido alvo (ex: 176).",
    )
    parser.add_argument(
        "--route",
        type=str,
        default=None,
        help="Força explicitamente a rota de produção ('upscale_only', 'poster_full', 'card_tcg', 'mug_11oz').",
    )
    parser.add_argument(
        "--mark-ok",
        action="store_true",
        help="Renomeia a pasta do pedido para '<numero> - ok' após aprovação em todos os Quality Gates.",
    )
    parser.add_argument(
        "--orders-root",
        "--root",
        dest="orders_root",
        type=str,
        default=str(DEFAULT_ORDERS_ROOT),
        help="Diretório raiz dos pedidos da Studio Kustom.",
    )
    _add_common_logging_arguments(parser)


def build_arg_parser() -> argparse.ArgumentParser:
    """Constrói e retorna o parser de argumentos da CLI com suporte a subcomandos."""
    parser = argparse.ArgumentParser(
        prog="sk-tools",
        description=(
            "Suíte unificada de automação Studio Kustom (sk-tools). "
            "Inclui gerador de cartas (card-gen), upscaler de posters (upscale), "
            "expansor de fundo (expand), imposição gráfica PDF (sheet), criador de canecas (mug) "
            "e planejador de pedidos (order)."
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

    sheet_parser = subparsers.add_parser(
        "sheet",
        aliases=["print-sheet", "folha", "imposition"],
        help="Imposição gráfica em PDF 300 DPI para grade de cartas 3x3 (duplex espelhado) e pôsteres.",
        description="Gera folhas de impressão PDF a 300 DPI com marcas de corte e cruzes de registro.",
    )
    _add_sheet_arguments(sheet_parser)

    mug_parser = subparsers.add_parser(
        "mug",
        aliases=["caneca", "mug-art"],
        help="Criador de arte para caneca de sublimação 11oz (220x95mm / 2598x1122px a 300 DPI).",
        description=(
            "Gera artes de caneca 11oz com compensação cromática (+18% saturação Epson L110), "
            "prévia visual e versão espelhada para transfer térmico."
        ),
    )
    _add_mug_arguments(mug_parser)

    order_parser = subparsers.add_parser(
        "order",
        aliases=["pedidos", "planner"],
        help="Planejador e orquestrador da esteira de pedidos com Quality Gates determinísticos.",
        description="Varre pedidos pendentes, planeja filas de tarefas por rota e executa Quality Gates.",
    )
    _add_order_arguments(order_parser)

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

    preserve_frame = getattr(args, "preserve_frame", False)
    logger.info(
        "Iniciando SK-TOOLS [expand] | Imagem: '{}' | Modo: {} | Sangria: {:.1f}mm ({}px/borda @ 300 DPI) | Preservar Moldura: {}",
        args.image,
        spec.code,
        args.bleed,
        bleed_px,
        preserve_frame,
    )

    try:
        expanded_path = expand_background(
            image_path=Path(args.image),
            mode=spec.code,
            bleed_mm=args.bleed,
            preserve_frame=preserve_frame,
            config=config,
            max_retries=args.retries,
        )
        logger.success("Imagem expandida gerada com sucesso em: {}", expanded_path)
        return 0
    except (FileNotFoundError, ValueError, GeminiBrowserError) as exc:
        logger.error("Falha na expansão de fundo: {}", exc)
        return 1


def run_sheet_cli(args: argparse.Namespace) -> int:
    """Executa o fluxo operacional do subcomando `sheet` (imposição gráfica PDF)."""
    setup_logger(
        console_level=args.log_level,
        log_to_file=not args.no_file_log,
    )

    try:
        paper_spec = normalize_paper_spec(args.paper)
    except ValueError as exc:
        logger.error("Erro de parâmetro em --paper: {}", exc)
        return 2

    config = DEFAULT_CONFIG
    config.ensure_directories()
    output_pdf = Path(args.output) if args.output else None

    if args.poster:
        if args.cards or args.cards_dir:
            logger.error("Não combine --poster com --cards ou --cards-dir no mesmo comando.")
            return 2

        logger.info(
            "Iniciando SK-TOOLS [sheet] (Pôster) | Imagem: '{}' | Papel: {} ({}x{}px @ {} DPI)",
            args.poster,
            paper_spec.code,
            paper_spec.width_px,
            paper_spec.height_px,
            paper_spec.dpi,
        )
        try:
            pdf_path = create_poster_print_sheet(
                poster_image=Path(args.poster),
                paper=paper_spec.code,
                output_pdf=output_pdf,
                config=config,
            )
            logger.success("Folha de impressão de pôster gerada em: {}", pdf_path)
            return 0
        except (FileNotFoundError, ValueError) as exc:
            logger.error("Falha ao gerar folha de pôster: {}", exc)
            return 1

    if not args.cards and not args.cards_dir:
        logger.error(
            "Informe --cards, --cards-dir (para grade de cartas) ou --poster (para folha de pôster)."
        )
        return 2

    if not args.back:
        logger.error("O argumento --back é obrigatório para gerar folha duplex de cartas.")
        return 2

    back_list = [Path(b) for b in args.back]
    back_input = back_list[0] if len(back_list) == 1 else back_list

    try:
        if args.cards_dir:
            front_paths = discover_card_images(args.cards_dir, exclude_paths=back_list)
        else:
            front_paths = [Path(c) for c in args.cards]

        logger.info(
            "Iniciando SK-TOOLS [sheet] (Cartas Duplex) | Cartas: {} | Papel: {} ({}x{}px @ {} DPI)",
            len(front_paths),
            paper_spec.code,
            paper_spec.width_px,
            paper_spec.height_px,
            paper_spec.dpi,
        )
        pdf_path = create_card_print_sheet(
            front_images=front_paths,
            back_image=back_input,
            paper=paper_spec.code,
            output_pdf=output_pdf,
            config=config,
        )
        logger.success("Folha de impressão duplex de cartas gerada em: {}", pdf_path)
        return 0
    except (FileNotFoundError, ValueError) as exc:
        logger.error("Falha ao gerar folha de cartas: {}", exc)
        return 1


def _process_generative_mugs(
    mugs: List[MugInput],
    config: AppConfig,
    output_path: Optional[Path] = None,
    max_retries: int = 3,
) -> int:
    """Processa uma lista de especificações de caneca via Google Gemini Web."""
    logger.info(
        "Iniciando SK-TOOLS [mug] (Geração Generativa Gemini) | Total de canecas: {} | Headless: {}",
        len(mugs),
        config.headless,
    )

    succeeded = 0
    failed = 0
    shared_context = get_chrome_context(config) if len(mugs) > 1 else None

    try:
        for idx, mug in enumerate(mugs, start=1):
            logger.info(
                "[{}/{}] Gerando arte de caneca: '{}' (Tema: {}, Estilo: {})",
                idx,
                len(mugs),
                mug.titulo,
                mug.tema,
                mug.estilo,
            )
            out_target = output_path if len(mugs) == 1 else None
            try:
                transfer_path, preview_path = run_mug_artwork_orchestration(
                    mug_input=mug,
                    config=config,
                    context=shared_context,
                    output_path=out_target,
                    max_retries=max_retries,
                )
                succeeded += 1
                logger.success(
                    "[{}/{}] Caneca '{}' CONCLUÍDA | Transfer: '{}' | Prévia: '{}'",
                    idx,
                    len(mugs),
                    mug.titulo,
                    transfer_path,
                    preview_path,
                )
            except Exception as exc:
                failed += 1
                logger.error(
                    "[{}/{}] Falha ao gerar caneca '{}': {}",
                    idx,
                    len(mugs),
                    mug.titulo,
                    exc,
                )
    finally:
        if shared_context is not None:
            shared_context.close()

    logger.info(
        "Processamento de canecas finalizado | Total: {} | Sucesso: {} | Falhas: {}",
        len(mugs),
        succeeded,
        failed,
    )
    return 0 if failed == 0 else 1


def run_mug_cli(args: argparse.Namespace) -> int:
    """Executa o fluxo operacional do subcomando `mug` (arte de caneca 11oz)."""
    setup_logger(
        console_level=args.log_level,
        log_to_file=not args.no_file_log,
    )

    config = replace(
        DEFAULT_CONFIG,
        headless=True if args.headless else DEFAULT_CONFIG.headless,
    )
    config.ensure_directories()
    output_path = Path(args.output) if args.output else None

    # 1. Modo JSON inline: --mug
    if getattr(args, "mug", None):
        try:
            payload = json.loads(args.mug)
        except json.JSONDecodeError as exc:
            logger.error("JSON inline inválido em --mug: {}", exc)
            return 2

        try:
            if isinstance(payload, list):
                mugs = [MugInput.model_validate(item) for item in payload]
            elif isinstance(payload, dict):
                mugs = [MugInput.model_validate(payload)]
            else:
                raise ValueError("O JSON fornecido em --mug deve ser um objeto ou lista.")
        except (ValueError, ValidationError) as exc:
            logger.error("Falha ao validar especificação da caneca: {}", exc)
            return 2

        return _process_generative_mugs(mugs, config, output_path, args.retries)

    # 2. Modo arquivo ou imagem via --input / -i
    input_arg = getattr(args, "input", None)
    if input_arg:
        input_lower = input_arg.lower()
        if input_lower.endswith(".json"):
            try:
                mugs = load_mugs_from_file(Path(input_arg))
            except (FileNotFoundError, ValueError, ValidationError) as exc:
                logger.error("Falha ao carregar arquivo de canecas: {}", exc)
                return 1

            return _process_generative_mugs(mugs, config, output_path, args.retries)

        # Se for imagem passada via -i / --input (compatibilidade clássica)
        image_arg = input_arg
    else:
        image_arg = getattr(args, "image", None)

    # 3. Modo clássico local com imagens Pillow: --image / --images (ou -i caminho_de_imagem)
    images_arg = getattr(args, "images", None)

    if not image_arg and not images_arg:
        logger.error(
            "Informe --input com arquivo JSON (ou --mug com JSON inline) "
            "ou --image/--images para composição local de caneca."
        )
        return 2

    if image_arg and images_arg:
        logger.error("Informe apenas uma imagem (--image) ou lista (--images), não ambos simultaneamente.")
        return 2

    try:
        mode_spec = normalize_mug_mode(args.mode)
    except ValueError as exc:
        logger.error("Erro de parâmetro em --mode: {}", exc)
        return 2

    image_input: Union[Path, List[Path]]
    if images_arg:
        image_input = [Path(p) for p in images_arg]
    else:
        image_input = Path(image_arg)

    logger.info(
        "Iniciando SK-TOOLS [mug] (Composição Local) | Modo: {} | Caneca 11oz ({}x{}px @ {} DPI) | Espelhar Transfer: {}",
        mode_spec.code,
        DEFAULT_MUG_SPEC.width_px,
        DEFAULT_MUG_SPEC.height_px,
        DEFAULT_MUG_SPEC.dpi,
        args.mirror,
    )

    try:
        transfer_path, preview_path = create_mug_artwork(
            image_or_images=image_input,
            mode=mode_spec.code,
            text=args.text,
            mirror_for_transfer=args.mirror,
            config=config,
            output_path=output_path,
        )
        logger.success(
            "Arte de caneca concluída | Principal: '{}' | Prévia: '{}'",
            transfer_path,
            preview_path,
        )
        return 0
    except (FileNotFoundError, ValueError, GeminiBrowserError) as exc:
        logger.error("Falha ao gerar arte de caneca: {}", exc)
        return 1


def run_order_cli(args: argparse.Namespace) -> int:
    """Executa o fluxo operacional do subcomando `order` (`pedidos`, `planner`)."""
    setup_logger(
        console_level=args.log_level,
        log_to_file=not args.no_file_log,
    )

    orders_root = Path(getattr(args, "orders_root", str(DEFAULT_ORDERS_ROOT)))
    raw_route = getattr(args, "route", None)
    route_override = None
    if raw_route:
        try:
            route_override = normalize_product_route(raw_route)
        except ValueError as exc:
            logger.error("Erro em --route: {}", exc)
            return 2

    scan_mode = getattr(args, "scan", False)
    plan_mode = getattr(args, "plan", False)
    run_mode = getattr(args, "run", False)
    order_id = getattr(args, "order_id", None)
    mark_ok = getattr(args, "mark_ok", False)

    if not scan_mode and not plan_mode and not run_mode:
        logger.error("Informe uma ação para o planejador de pedidos: --scan, --plan ou --run.")
        return 2

    if scan_mode:
        try:
            orders = discover_orders(orders_root=orders_root, route_override=route_override)
        except FileNotFoundError as exc:
            logger.error("Falha na varredura de pedidos: {}", exc)
            return 1

        logger.info(
            "SK-TOOLS [order --scan] | Diretório: '{}' | Pedidos pendentes: {}",
            orders_root,
            len(orders),
        )
        for job in orders:
            file_names = ", ".join(p.name for p in job.customer_files) or "(nenhum arquivo)"
            print(
                f"[{job.order_id}] Rota: {job.route.value} | Arquivos ({len(job.customer_files)}): {file_names}"
            )
        return 0

    if plan_mode and not run_mode:
        if not order_id:
            logger.error("O argumento --id <ID> é obrigatório para --plan.")
            return 2
        try:
            job = find_order_by_id(
                order_id=order_id,
                orders_root=orders_root,
                route_override=route_override,
            )
        except (FileNotFoundError, ValueError) as exc:
            logger.error("Falha ao planejar pedido '{}': {}", order_id, exc)
            return 1

        logger.info(
            "SK-TOOLS [order --plan] | Pedido: {} | Rota: {} | Diretório: {}",
            job.order_id,
            job.route.value,
            job.order_dir,
        )
        print(f"Pedido: {job.order_id} | Rota: {job.route.value} | Status: {job.status}")
        print(f"Arquivos do Cliente ({len(job.customer_files)}):")
        for f in job.customer_files:
            print(f"  - {f.name}")
        print(f"Fila de Tarefas ({len(job.tasks)} etapa(s)):")
        for task in job.tasks:
            print(
                f"  [{task.step_number}] {task.tool_name}: {task.action_description} "
                f"| Gate: {task.gate_criterion} | Status: {task.status}"
            )
        return 0

    # run_mode
    config = replace(
        DEFAULT_CONFIG,
        headless=True if args.headless else DEFAULT_CONFIG.headless,
    )
    config.ensure_directories()

    if order_id:
        target_ids = [order_id]
    else:
        try:
            pending_jobs = discover_orders(orders_root=orders_root, route_override=route_override)
            target_ids = [j.order_id for j in pending_jobs]
        except Exception as exc:
            logger.error("Falha ao descobrir pedidos pendentes: {}", exc)
            return 1

    if not target_ids:
        logger.info("Nenhum pedido pendente para processar em '{}'.", orders_root)
        return 0

    logger.info("Iniciando execução da fila de produção: {} pedido(s)...", len(target_ids))
    success_count = 0
    fail_count = 0

    for tid in target_ids:
        logger.info(">>> [Pedido {}] Processando...", tid)
        try:
            report = run_order_by_id(
                order_id=tid,
                orders_root=orders_root,
                route_override=route_override,
                mark_ok=mark_ok,
                config=config,
                max_retries=args.retries,
            )
            if report.passed:
                success_count += 1
                print(
                    f"Pedido {report.order_job.order_id} CONCLUÍDO ({report.order_job.route.value}) -> {report.dossie_path}"
                )
            else:
                fail_count += 1
                logger.error("Pedido '{}' REPROVADO nos Quality Gates (Status: {}).", tid, report.order_job.status)
        except Exception as exc:
            fail_count += 1
            logger.error("Falha ao executar pedido '{}': {}", tid, exc)

    logger.info("Fila finalizada: {} pedido(s) concluído(s), {} falha(s).", success_count, fail_count)
    return 0 if fail_count == 0 else 1


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
    if command in SHEET_COMMANDS:
        return run_sheet_cli(args)
    if command in MUG_COMMANDS:
        return run_mug_cli(args)
    if command in ORDER_COMMANDS:
        return run_order_cli(args)

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
