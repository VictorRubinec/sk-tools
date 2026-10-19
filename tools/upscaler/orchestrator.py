"""Orquestrador de upscaling e conversão de cartas em posters 300 DPI via Google Gemini Web."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Union

from tools.card_generator.browser.exceptions import (
    GeminiGenerationTimeoutError,
    GeminiImageNotGeneratedError,
    GeminiPromptSubmissionError,
    GeminiSessionNotAuthenticatedError,
)
from tools.card_generator.browser.gemini_client import GeminiClient
from tools.card_generator.browser.session import get_chrome_context
from tools.card_generator.core.config import AppConfig, BASE_DIR, DEFAULT_CONFIG
from tools.card_generator.core.logger import logger
from tools.upscaler.prompt_builder import UpscalePromptBuilder, normalize_target_format
from tools.upscaler.validator import PosterImageValidator


def _resolve_source_image(image_path: Union[str, Path]) -> Path:
    """Resolve e valida a existência da imagem de origem em disco."""
    candidate = Path(image_path)
    resolved = candidate if candidate.is_file() else (BASE_DIR / candidate)
    if not resolved.is_file():
        raise FileNotFoundError(
            f"Imagem de origem para upscaling não encontrada: {image_path}"
        )
    return resolved.resolve()


def run_upscale_orchestration(
    image_path: Union[str, Path],
    target_format: str,
    config: Optional[AppConfig] = None,
    client: Optional[GeminiClient] = None,
    prompt_builder: Optional[UpscalePromptBuilder] = None,
    validator: Optional[PosterImageValidator] = None,
    context: Optional[Any] = None,
    max_retries: int = 3,
) -> Path:
    """Executa o fluxo de envio da carta original ao Gemini, redraw e validação 300 DPI.

    Args:
        image_path: Caminho para a imagem original da carta.
        target_format: Formato de poster alvo ('a4_v', 'a4_h', 'a3_v', 'a3_h').
        config: Configuração da aplicação (`AppConfig`).
        client: Cliente `GeminiClient` opcional (para injeção em testes).
        prompt_builder: Instância opcional de `UpscalePromptBuilder`.
        validator: Instância opcional de `PosterImageValidator`.
        context: Contexto persistente do navegador opcional.
        max_retries: Número máximo de tentativas de geração e validação.

    Returns:
        `Path` apontando para o poster final aprovado em `config.output_dir`.

    Raises:
        FileNotFoundError: Se a imagem de entrada não existir.
        ValueError: Se `target_format` ou `max_retries` forem inválidos.
        GeminiSessionNotAuthenticatedError: Se o navegador não estiver logado no Gemini.
        GeminiImageNotGeneratedError: Se após todas as tentativas o poster não for gerado/aprovado.
    """
    if max_retries < 1:
        raise ValueError("O parâmetro 'max_retries' deve ser maior ou igual a 1.")

    spec = normalize_target_format(target_format)
    source_path = _resolve_source_image(image_path)
    active_config = config or DEFAULT_CONFIG
    active_config.ensure_directories()

    gemini_client = client or GeminiClient()
    builder = prompt_builder or UpscalePromptBuilder()
    poster_validator = validator or PosterImageValidator()

    owns_context = context is None
    browser_context = get_chrome_context(active_config) if owns_context else context

    extra_instructions: Optional[str] = None
    last_errors: list[str] = []

    try:
        page = (
            browser_context.pages[0]
            if browser_context.pages
            else browser_context.new_page()
        )
        page.goto(active_config.gemini_url, wait_until="domcontentloaded")

        if not gemini_client.check_login_status(page):
            raise GeminiSessionNotAuthenticatedError(
                "Sessão do Google Gemini não está autenticada. "
                "Execute 'python scripts/setup_session.py' para realizar o login inicial."
            )

        for attempt in range(1, max_retries + 1):
            logger.info(
                "Iniciando upscaling de '{}' para {} ({}x{}px @ {} DPI) - Tentativa {}/{}",
                source_path.name,
                spec.code,
                spec.width_px,
                spec.height_px,
                spec.dpi,
                attempt,
                max_retries,
            )

            prompt_text = builder.build_prompt(
                target_format=spec.code,
                extra_instructions=extra_instructions,
            )

            try:
                gemini_client.send_prompt(page, prompt_text, submit=False)
                gemini_client.upload_reference_images(page, [source_path])
                gemini_client.submit_prompt(page)
                gemini_client.wait_for_generation_complete(
                    page, timeout_ms=active_config.timeout_ms
                )
                raw_poster_bytes = gemini_client.extract_latest_generated_image(page)
            except (
                GeminiImageNotGeneratedError,
                GeminiGenerationTimeoutError,
                GeminiPromptSubmissionError,
            ) as exc:
                logger.warning(
                    "Tentativa {}/{} de upscaling falhou no navegador: {}",
                    attempt,
                    max_retries,
                    exc,
                )
                last_errors = [str(exc)]
                extra_instructions = (
                    f"Gere obrigatoriamente a imagem completa em orientação {spec.orientation} "
                    f"para o formato {spec.label} ({spec.width_px}x{spec.height_px} px)."
                )
                continue

            if not raw_poster_bytes:
                last_errors = ["Nenhum binário de imagem retornado pelo Gemini."]
                continue

            conformed_bytes = poster_validator.conform_to_poster_spec(
                raw_poster_bytes, spec.code
            )
            validation = poster_validator.validate_poster(conformed_bytes, spec.code)

            if validation.is_valid:
                output_filename = f"{source_path.stem}_poster_{spec.code.lower()}.png"
                output_path = active_config.output_dir / output_filename
                output_path.write_bytes(conformed_bytes)
                logger.success(
                    "Poster {} gerado e validado com sucesso em '{}' ({}x{}px, ratio={:.3f})!",
                    spec.code,
                    output_path,
                    validation.width,
                    validation.height,
                    validation.aspect_ratio,
                )
                return output_path

            last_errors = list(validation.errors)
            logger.warning(
                "Poster reprovado na tentativa {}/{}: {}",
                attempt,
                max_retries,
                "; ".join(last_errors),
            )
            extra_instructions = (
                f"Corrija rigorosamente os seguintes problemas da tentativa anterior: "
                f"{' | '.join(last_errors)}."
            )

        raise GeminiImageNotGeneratedError(
            f"Falha ao gerar poster '{spec.code}' válido após {max_retries} tentativa(s). "
            f"Erros: {'; '.join(last_errors)}"
        )
    finally:
        if owns_context:
            browser_context.close()
