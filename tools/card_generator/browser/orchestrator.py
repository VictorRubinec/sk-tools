"""Orquestrador de alto nível para geração e download de imagens de cartas no Gemini."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any, Optional

from tools.card_generator.browser.exceptions import (
    GeminiImageNotGeneratedError,
    GeminiSessionNotAuthenticatedError,
)
from tools.card_generator.browser.gemini_client import GeminiClient
from tools.card_generator.browser.session import get_chrome_context
from tools.card_generator.core.config import AppConfig, DEFAULT_CONFIG
from tools.card_generator.core.logger import logger
from tools.card_generator.core.schema import CardInput
from tools.card_generator.engine.prompt_builder import PromptBuilder


def _slugify_filename(text: str) -> str:
    """Converte um texto arbitrário em um identificador seguro para nome de arquivo."""
    normalized = (
        unicodedata.normalize("NFKD", text)
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )
    slug = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")
    return slug or "card"


def generate_card_image(
    card: CardInput,
    config: AppConfig = DEFAULT_CONFIG,
    client: Optional[GeminiClient] = None,
    prompt_builder: Optional[PromptBuilder] = None,
    context: Optional[Any] = None,
) -> Path:
    """Orquestra o fluxo ponta a ponta de geração de uma carta no Google Gemini.

    Monta o prompt estruturado, utiliza ou abre o contexto persistente do navegador,
    verifica o login, digita o prompt, cola imagens de referência (se houver),
    aguarda a geração, extrai o binário da imagem e salva em `config.output_dir`.

    Args:
        card: Instância validada de `CardInput`.
        config: Configurações da aplicação (`AppConfig`).
        client: Instância opcional de `GeminiClient` (útil para injeção em testes).
        prompt_builder: Instância opcional de `PromptBuilder`.
        context: Contexto de navegador existente (BrowserContext) para reaproveitamento em lote.

    Returns:
        `Path` apontando para a imagem salva no diretório `output/`.
    """
    builder = prompt_builder or PromptBuilder()
    gemini_client = client or GeminiClient()

    logger.info("Iniciando orquestração para carta: '{}' (Tipo: {}, Estilo: {})", card.titulo, card.tipo, card.estilo)
    prompt_text = builder.build_prompt(card)
    config.ensure_directories()

    owns_context = context is None
    browser_context = get_chrome_context(config) if owns_context else context

    try:
        page = browser_context.pages[0] if browser_context.pages else browser_context.new_page()
        logger.debug("Navegando para {}", config.gemini_url)
        page.goto(config.gemini_url, wait_until="domcontentloaded")

        if not gemini_client.check_login_status(page):
            logger.error("Sessão não autenticada no Gemini")
            raise GeminiSessionNotAuthenticatedError(
                "Sessão do Google Gemini não está autenticada. "
                "Execute 'python scripts/setup_session.py' para realizar o login inicial."
            )

        if card.imagens_referencia:
            ref_paths = [Path(p) for p in card.imagens_referencia]
            logger.info("Digitando prompt gerador no Gemini...")
            gemini_client.send_prompt(page, prompt_text, submit=False)
            logger.info("Anexando {} imagem(ns) de referência via paste...", len(ref_paths))
            gemini_client.upload_reference_images(page, ref_paths)
            logger.info("Disparando envio com prompt e imagem...")
            gemini_client.submit_prompt(page)
        else:
            logger.info("Submetendo prompt gerador ao Gemini...")
            gemini_client.send_prompt(page, prompt_text, submit=True)

        logger.info("Aguardando geração da imagem (timeout: {}ms)...", config.timeout_ms)
        gemini_client.wait_for_generation_complete(page, timeout_ms=config.timeout_ms)

        logger.info("Extraindo/baixando imagem gerada pelo Gemini...")
        image_bytes = gemini_client.extract_latest_generated_image(page)
        if not image_bytes:
            logger.error("Nenhum binário de imagem obtido para '{}'", card.titulo)
            raise GeminiImageNotGeneratedError(
                "Nenhum conteúdo binário de imagem retornado pelo Gemini."
            )

        filename = f"{_slugify_filename(card.tipo)}_{_slugify_filename(card.titulo)}.png"
        output_path = config.output_dir / filename
        output_path.write_bytes(image_bytes)
        size_kb = len(image_bytes) / 1024
        logger.success("Imagem salva com sucesso em: {} ({:.1f} KB)", output_path, size_kb)
        return output_path
    finally:
        if owns_context:
            logger.debug("Fechando contexto do navegador...")
            browser_context.close()
