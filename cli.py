"""Interface de Linha de Comando (CLI) unificada do ecossistema sk-tools."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import List, Optional, Sequence

from pydantic import ValidationError

from browser.gemini_client import GeminiClient
from browser.session import get_chrome_context
from core.config import AppConfig, DEFAULT_CONFIG, INPUT_DIR
from core.logger import logger, setup_logger
from core.runner import CardGenerationRunner
from core.schema import CardInput, load_cards_from_file


def build_arg_parser() -> argparse.ArgumentParser:
    """Constrói e retorna o parser de argumentos da CLI."""
    parser = argparse.ArgumentParser(
        prog="sk-tools",
        description=(
            "Automatizador de geração e validação de cartas colecionáveis (TCG) "
            "via Google Gemini Web e Playwright."
        ),
    )
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
        "-r",
        "--retries",
        type=int,
        default=3,
        help="Número máximo de tentativas por carta em caso de falha ou reprovação (padrão: 3).",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Executa o navegador em modo sem interface gráfica (headless=True).",
    )
    parser.add_argument(
        "--check-session",
        action="store_true",
        help="Apenas verifica se a sessão do Google Gemini está autenticada e encerra.",
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
    return parser


def check_gemini_session(config: AppConfig) -> int:
    """Abre o navegador configurado, verifica o status de login no Gemini e encerra."""
    logger.info("Verificando status de autenticação da sessão no Google Gemini...")
    context = get_chrome_context(config)
    client = GeminiClient()
    try:
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(config.gemini_url, wait_until="domcontentloaded")
        authenticated = client.check_login_status(page)
        if authenticated:
            logger.success("Sessão AUTENTICADA e pronta para geração de cartas.")
            return 0
        logger.warning(
            "Sessão NÃO AUTENTICADA. Execute 'python scripts/setup_session.py' para fazer login."
        )
        return 1
    finally:
        context.close()


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


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Ponto de entrada principal da CLI unificada."""
    parser = build_arg_parser()
    args = parser.parse_args(argv)

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

    logger.info("Iniciando SK-TOOLS | Gerador e Validador Automatizado de Cartas TCG")

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

    context = get_chrome_context(config)
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
                card=card, config=config, max_retries=args.retries, context=context
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
        context.close()

    logger.info(
        "Processamento finalizado | Total: {} | Sucesso: {} | Falhas: {}",
        len(cards),
        succeeded,
        failed,
    )

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
