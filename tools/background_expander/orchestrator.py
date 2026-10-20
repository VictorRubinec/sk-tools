"""Orquestrador de expansão generativa de fundo (outpainting) via Google Gemini Web."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Tuple, Union

from PIL import Image

from tools.background_expander.prompt_builder import (
    DEFAULT_BLEED_MM,
    BackgroundExpansionPromptBuilder,
    calculate_expanded_dimensions,
    normalize_expansion_mode,
)
from tools.background_expander.validator import ExpandedImageValidator
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


def _resolve_source_image(image_path: Union[str, Path]) -> Tuple[Path, Tuple[int, int]]:
    """Resolve o caminho da imagem original e lê suas dimensões `(width, height)`."""
    candidate = Path(image_path)
    resolved = candidate if candidate.is_file() else (BASE_DIR / candidate)
    if not resolved.is_file():
        raise FileNotFoundError(
            f"Imagem de origem para expansão de fundo não encontrada: {image_path}"
        )
    full_path = resolved.resolve()
    with Image.open(full_path) as img:
        base_size = img.size
    return full_path, base_size


def run_background_expansion_orchestration(
    image_path: Union[str, Path],
    mode: str = "bleed_5mm",
    bleed_mm: float = DEFAULT_BLEED_MM,
    preserve_frame: bool = False,
    config: Optional[AppConfig] = None,
    client: Optional[GeminiClient] = None,
    prompt_builder: Optional[BackgroundExpansionPromptBuilder] = None,
    validator: Optional[ExpandedImageValidator] = None,
    context: Optional[Any] = None,
    custom_size: Optional[Tuple[int, int]] = None,
    max_retries: int = 3,
) -> Path:
    """Executa o fluxo completo de outpainting no Gemini, download nativo e validação 300 DPI.

    Args:
        image_path: Caminho para a imagem original.
        mode: Modo de expansão ('bleed_5mm', 'horizontal', 'caneca', 'custom').
        bleed_mm: Milímetros de margem de sangria por borda (padrão: 5.0 mm = 59 px a 300 DPI).
        preserve_frame: Se True, mantém a moldura decorativa fixa no centro e expande apenas o fundo para fora.
        config: Configuração da aplicação (`AppConfig`).
        client: Cliente `GeminiClient` opcional (para injeção em testes).
        prompt_builder: Instância opcional de `BackgroundExpansionPromptBuilder`.
        validator: Instância opcional de `ExpandedImageValidator`.
        context: Contexto persistente do navegador opcional.
        custom_size: Dimensões alvo opcionais para o modo `custom`.
        max_retries: Número máximo de tentativas de geração e validação.

    Returns:
        `Path` apontando para a imagem expandida salva em `config.output_dir`.
    """
    if max_retries < 1:
        raise ValueError("O parâmetro 'max_retries' deve ser maior ou igual a 1.")

    spec = normalize_expansion_mode(mode)
    source_path, base_size = _resolve_source_image(image_path)
    target_w, target_h, bleed_px = calculate_expanded_dimensions(
        base_width=base_size[0],
        base_height=base_size[1],
        mode=spec.code,
        bleed_mm=bleed_mm,
        custom_size=custom_size,
    )

    active_config = config or DEFAULT_CONFIG
    active_config.ensure_directories()

    gemini_client = client or GeminiClient()
    builder = prompt_builder or BackgroundExpansionPromptBuilder()
    img_validator = validator or ExpandedImageValidator()

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
                "Iniciando expansão de fundo [{}] de '{}' ({}x{}px -> {}x{}px, sangria={}px/borda) - Tentativa {}/{}",
                spec.code,
                source_path.name,
                base_size[0],
                base_size[1],
                target_w,
                target_h,
                bleed_px,
                attempt,
                max_retries,
            )

            prompt_text = builder.build_prompt(
                mode=spec.code,
                bleed_mm=bleed_mm,
                base_size=base_size,
                custom_size=custom_size,
                extra_instructions=extra_instructions,
                preserve_frame=preserve_frame,
            )

            try:
                gemini_client.send_prompt(page, prompt_text, submit=False)
                gemini_client.upload_reference_images(page, [source_path])
                gemini_client.submit_prompt(page)
                gemini_client.wait_for_generation_complete(
                    page, timeout_ms=active_config.timeout_ms
                )
                raw_expanded_bytes = gemini_client.extract_latest_generated_image(page)
            except (
                GeminiImageNotGeneratedError,
                GeminiGenerationTimeoutError,
                GeminiPromptSubmissionError,
            ) as exc:
                logger.warning(
                    "Tentativa {}/{} de expansão de fundo falhou no navegador: {}",
                    attempt,
                    max_retries,
                    exc,
                )
                last_errors = [str(exc)]
                extra_instructions = (
                    f"Expanda obrigatoriamente o cenário de fundo para FORA da moldura existente sem alterar o sujeito central, "
                    f"preenchendo toda a área até {target_w}x{target_h} pixels sem barras pretas e sem esticar a moldura."
                    if preserve_frame
                    else f"Expanda obrigatoriamente o cenário de fundo sem alterar o personagem central, "
                    f"preenchendo toda a área até {target_w}x{target_h} pixels sem barras pretas."
                )
                continue

            if not raw_expanded_bytes:
                last_errors = ["Nenhum binário de imagem retornado pelo Gemini."]
                continue

            conformed_bytes = img_validator.conform_expanded_image(
                raw_bytes=raw_expanded_bytes,
                base_size=base_size,
                mode=spec.code,
                bleed_mm=bleed_mm,
                custom_size=custom_size,
            )
            validation = img_validator.validate_expanded_image(
                image_path_or_bytes=conformed_bytes,
                base_size=base_size,
                mode=spec.code,
                bleed_mm=bleed_mm,
                custom_size=custom_size,
            )

            if validation.is_valid:
                output_filename = f"{source_path.stem}_expanded.png"
                output_path = active_config.output_dir / output_filename
                output_path.write_bytes(conformed_bytes)
                logger.success(
                    "Imagem expandida ({}) gerada e validada com sucesso em '{}' ({}x{}px, sangria={}px/borda)!",
                    spec.code,
                    output_path,
                    validation.width,
                    validation.height,
                    validation.bleed_px,
                )
                return output_path

            last_errors = list(validation.errors)
            logger.warning(
                "Imagem expandida reprovada na tentativa {}/{}: {}",
                attempt,
                max_retries,
                "; ".join(last_errors),
            )
            extra_instructions = (
                f"Corrija rigorosamente os problemas da tentativa anterior: "
                f"{' | '.join(last_errors)}."
            )

        raise GeminiImageNotGeneratedError(
            f"Falha ao expandir o fundo ('{spec.code}') após {max_retries} tentativa(s). "
            f"Erros: {'; '.join(last_errors)}"
        )
    finally:
        if owns_context:
            browser_context.close()
