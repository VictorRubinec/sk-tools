"""Fachada Pública (API) da ferramenta encapsulada de geração de cartas (card_generator)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from tools.card_generator.browser.gemini_client import GeminiClient
from tools.card_generator.browser.session import get_chrome_context
from tools.card_generator.core.config import AppConfig, DEFAULT_CONFIG
from tools.card_generator.core.logger import logger
from tools.card_generator.core.runner import CardGenerationRunner
from tools.card_generator.core.schema import CardInput
from tools.card_generator.validator.card_validator import ValidationResult


def generate_single_card(
    card: CardInput,
    config: Optional[AppConfig] = None,
    max_retries: int = 3,
) -> Tuple[bool, Optional[Path], Optional[ValidationResult]]:
    """Gera e valida uma única carta utilizando o motor do `card_generator`.

    Args:
        card: Instância validada de `CardInput`.
        config: Configurações operacionais (`AppConfig`). Usa `DEFAULT_CONFIG` se omitido.
        max_retries: Número máximo de tentativas de geração/validação.

    Returns:
        Tupla `(sucesso, caminho_da_imagem_aprovada, ultimo_resultado_de_validacao)`.
    """
    active_config = config or DEFAULT_CONFIG
    active_config.ensure_directories()
    runner = CardGenerationRunner()
    return runner.process_card(card=card, config=active_config, max_retries=max_retries)


def generate_batch_cards(
    cards: List[CardInput],
    config: Optional[AppConfig] = None,
    max_retries: int = 3,
) -> Dict[str, Any]:
    """Processa um lote de cartas reutilizando a sessão do navegador quando aplicável.

    Args:
        cards: Lista de instâncias de `CardInput`.
        config: Configurações operacionais (`AppConfig`). Usa `DEFAULT_CONFIG` se omitido.
        max_retries: Número máximo de tentativas por carta.

    Returns:
        Dicionário consolidado com estatísticas (`total`, `succeeded`, `failed`, `results`).
    """
    active_config = config or DEFAULT_CONFIG
    active_config.ensure_directories()
    runner = CardGenerationRunner()
    context = get_chrome_context(active_config)
    try:
        return runner.process_batch(
            cards=cards,
            config=active_config,
            max_retries=max_retries,
            context=context,
        )
    finally:
        context.close()


def check_gemini_session(config: Optional[AppConfig] = None) -> bool:
    """Verifica se a sessão do navegador está autenticada no Google Gemini.

    Args:
        config: Configurações operacionais (`AppConfig`). Usa `DEFAULT_CONFIG` se omitido.

    Returns:
        `True` se a sessão estiver autenticada, `False` caso contrário.
    """
    active_config = config or DEFAULT_CONFIG
    logger.info("Verificando status de autenticação da sessão no Google Gemini...")
    context = get_chrome_context(active_config)
    client = GeminiClient()
    try:
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(active_config.gemini_url, wait_until="domcontentloaded")
        authenticated = client.check_login_status(page)
        if authenticated:
            logger.success("Sessão AUTENTICADA e pronta para geração de cartas.")
        else:
            logger.warning(
                "Sessão NÃO AUTENTICADA. Execute 'python scripts/setup_session.py' para fazer login."
            )
        return authenticated
    finally:
        context.close()
