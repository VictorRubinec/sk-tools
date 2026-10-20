"""Orquestrador do Criador de Arte para Caneca de Sublimação 11oz (tools/mug_artist/orchestrator.py)."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any, List, Optional, Sequence, Tuple, Union

from PIL import Image, ImageOps

from tools.background_expander.api import expand_background
from tools.card_generator.browser.exceptions import (
    GeminiImageNotGeneratedError,
    GeminiSessionNotAuthenticatedError,
)
from tools.card_generator.browser.gemini_client import GeminiClient
from tools.card_generator.browser.session import get_chrome_context
from tools.card_generator.core.config import AppConfig, BASE_DIR, DEFAULT_CONFIG
from tools.card_generator.core.logger import logger
from tools.mug_artist.color_engine import (
    DEFAULT_SATURATION_BOOST,
    apply_sublimation_compensation,
)
from tools.mug_artist.composer import (
    DEFAULT_MUG_SPEC,
    DPI,
    MugArtworkComposer,
    normalize_mug_mode,
)
from tools.mug_artist.prompt_builder import MugPromptBuilder
from tools.mug_artist.schema import MugInput
from tools.upscaler.validator import PosterImageValidator


def _resolve_image_path(image_path: Union[str, Path]) -> Path:
    """Resolve e valida a existência do caminho de uma imagem de entrada."""
    candidate = Path(image_path)
    resolved = candidate if candidate.is_file() else (BASE_DIR / candidate)
    if not resolved.is_file():
        raise FileNotFoundError(
            f"Imagem de entrada para arte de caneca não encontrada: {image_path}"
        )
    return resolved.resolve()


def _normalize_image_inputs(
    image_or_images: Union[str, Path, Image.Image, Sequence[Union[str, Path, Image.Image]]],
) -> List[Union[Path, Image.Image]]:
    """Normaliza a entrada única ou múltipla em uma lista validada de `Path` ou `Image.Image`."""
    if isinstance(image_or_images, (str, Path)):
        return [_resolve_image_path(image_or_images)]
    if isinstance(image_or_images, Image.Image):
        return [image_or_images]

    items = list(image_or_images)
    if not items:
        raise ValueError("Pelo menos uma imagem deve ser fornecida para gerar a arte da caneca.")

    normalized: List[Union[Path, Image.Image]] = []
    for item in items:
        if isinstance(item, Image.Image):
            normalized.append(item)
        else:
            normalized.append(_resolve_image_path(item))
    return normalized


def _derive_base_stem(inputs: Sequence[Union[Path, Image.Image]], mode_code: str) -> str:
    """Deriva o prefixo de nome de arquivo a partir das imagens de entrada."""
    first = inputs[0]
    first_stem = first.stem if isinstance(first, Path) else "mug_art"
    if mode_code == "dual_face" and len(inputs) >= 2 and isinstance(inputs[1], Path):
        second_stem = inputs[1].stem
        if second_stem != first_stem:
            return f"{first_stem}_{second_stem}"
    return first_stem


def _generate_mug_via_gemini(
    mug: MugInput,
    config: AppConfig,
    client: Optional[GeminiClient] = None,
    prompt_builder: Optional[MugPromptBuilder] = None,
    context: Optional[Any] = None,
) -> bytes:
    """Aciona o Gemini Web para gerar a imagem plana 2D da caneca e retorna os bytes brutos."""
    builder = prompt_builder or MugPromptBuilder()
    gemini_client = client or GeminiClient()

    logger.info(
        "Iniciando geração generativa de caneca | Tema: '{}' | Estilo: '{}' | Título: '{}'",
        mug.tema,
        mug.estilo,
        mug.titulo,
    )
    prompt_text = builder.build_prompt(mug)

    owns_context = context is None
    browser_context = get_chrome_context(config) if owns_context else context

    try:
        page = (
            browser_context.pages[0]
            if browser_context.pages
            else browser_context.new_page()
        )
        logger.debug("Navegando para {}", config.gemini_url)
        page.goto(config.gemini_url, wait_until="domcontentloaded")

        if not gemini_client.check_login_status(page):
            logger.error("Sessão não autenticada no Gemini")
            raise GeminiSessionNotAuthenticatedError(
                "Sessão do Google Gemini não está autenticada. "
                "Execute 'python scripts/setup_session.py' para realizar o login inicial."
            )

        if mug.imagens_referencia:
            ref_paths: list[Path] = []
            for p in mug.imagens_referencia:
                cand = Path(p)
                res = cand if cand.is_file() else (BASE_DIR / cand)
                ref_paths.append(res.resolve())

            logger.info("Digitando prompt de caneca no Gemini...")
            gemini_client.send_prompt(page, prompt_text, submit=False)
            logger.info("Anexando {} imagem(ns) de referência...", len(ref_paths))
            gemini_client.upload_reference_images(page, ref_paths)
            logger.info("Disparando envio do prompt com imagens...")
            gemini_client.submit_prompt(page)
        else:
            logger.info("Submetendo prompt de caneca ao Gemini...")
            gemini_client.send_prompt(page, prompt_text, submit=True)

        logger.info("Aguardando geração da arte (timeout: {}ms)...", config.timeout_ms)
        gemini_client.wait_for_generation_complete(page, timeout_ms=config.timeout_ms)

        logger.info("Extraindo binário da imagem gerada pelo Gemini...")
        image_bytes = gemini_client.extract_latest_generated_image(page)
        if not image_bytes:
            logger.error("Nenhum binário de imagem obtido para '{}'", mug.titulo)
            raise GeminiImageNotGeneratedError(
                "Nenhum conteúdo binário de imagem retornado pelo Gemini para a arte de caneca."
            )
        return image_bytes
    finally:
        if owns_context:
            logger.debug("Fechando contexto do navegador...")
            browser_context.close()


def conform_and_compensate_mug_image(
    image_bytes: bytes,
    saturation_boost: float = DEFAULT_SATURATION_BOOST,
) -> Image.Image:
    """Remove barras pretas, ajusta para 2598x1122px a 300 DPI e aplica compensação cromática.

    Args:
        image_bytes: Bytes brutos da imagem gerada pelo Gemini.
        saturation_boost: Fator de saturação Epson L110 (padrão: 1.18).

    Returns:
        Imagem Pillow RGB ajustada e compensada nas dimensões exatas de 2598x1122 a 300 DPI.
    """
    with Image.open(io.BytesIO(image_bytes)) as raw_img:
        rgb_img = raw_img.convert("RGB")

    # 1. Remove eventuais barras pretas periféricas (pillarbox/letterbox)
    cleaned_img = PosterImageValidator.trim_black_borders(rgb_img)

    # 2. Ajusta para 2598x1122 px exatos a 300 DPI com proporção preservada (center-crop cover)
    target_w = DEFAULT_MUG_SPEC.width_px
    target_h = DEFAULT_MUG_SPEC.height_px

    scale = max(target_w / cleaned_img.width, target_h / cleaned_img.height)
    new_w = int(round(cleaned_img.width * scale))
    new_h = int(round(cleaned_img.height * scale))

    scaled = cleaned_img.resize((new_w, new_h), resample=Image.Resampling.LANCZOS)
    left = max(0, (new_w - target_w) // 2)
    top = max(0, (new_h - target_h) // 2)
    cropped = scaled.crop((left, top, left + target_w, top + target_h))

    # 3. Aplica compensação cromática para impressora Epson L110
    compensated = apply_sublimation_compensation(cropped, saturation_boost=saturation_boost)
    compensated.info["dpi"] = (DPI, DPI)
    return compensated


def run_mug_artwork_orchestration(
    image_or_images: Optional[
        Union[MugInput, str, Path, Image.Image, Sequence[Union[str, Path, Image.Image]]]
    ] = None,
    mug_input: Optional[MugInput] = None,
    mode: str = "panoramic",
    text: Optional[str] = None,
    mirror_for_transfer: Optional[bool] = None,
    config: Optional[AppConfig] = None,
    output_path: Optional[Union[str, Path]] = None,
    saturation_boost: float = DEFAULT_SATURATION_BOOST,
    expand_with_ai: bool = False,
    max_retries: int = 3,
    composer: Optional[MugArtworkComposer] = None,
    client: Optional[GeminiClient] = None,
    prompt_builder: Optional[MugPromptBuilder] = None,
    context: Optional[Any] = None,
) -> Tuple[Path, Optional[Path]]:
    """Executa o fluxo completo de criação de arte para caneca 11oz (generativo ou composição).

    Se `mug_input` (ou `image_or_images: MugInput`) for fornecido:
      1. Aciona o Gemini Web via `GeminiClient` e `get_chrome_context(config)`.
      2. Remove eventuais barras pretas periféricas.
      3. Ajusta para os 2598x1122 px exatos a 300 DPI.
      4. Aplica a compensação cromática da Epson L110 (+18% de saturação).
      5. Salva `output/<slug>_mug_preview.png` e `output/<slug>_mug_transfer.png` (espelhado).

    Caso contrário (modo clássico com imagens existentes):
      Compõe localmente as cartas nas faces da caneca via Pillow.

    Args:
        image_or_images: Caminho/imagem clássica OU instância de `MugInput`.
        mug_input: Instância de `MugInput` para geração generativa completa.
        mode: Modo de layout para o fluxo clássico ('panoramic', 'dual_face', 'card_plus_text').
        text: Texto comemorativo para o fluxo clássico.
        mirror_for_transfer: Se True, gera versão espelhada horizontalmente para sublimação.
        config: Configuração operacional (`AppConfig`).
        output_path: Caminho customizado de saída.
        saturation_boost: Fator de compensação cromática (padrão: 1.18).
        expand_with_ai: Para o fluxo clássico, expande a carta com IA antes de compor.
        max_retries: Tentativas máximas.
        composer: Instância opcional de `MugArtworkComposer`.
        client: Instância opcional de `GeminiClient` (para injeção e testes).
        prompt_builder: Instância opcional de `MugPromptBuilder`.
        context: Contexto compartilhado do Chrome (para lote).

    Returns:
        Tupla `(caminho_transfer_espelhado, caminho_previa_normal)` ou `(caminho_previa, None)`.
    """
    active_config = config or DEFAULT_CONFIG
    active_config.ensure_directories()

    # Detecta se a entrada é um MugInput
    resolved_mug: Optional[MugInput] = None
    if isinstance(image_or_images, MugInput):
        resolved_mug = image_or_images
    elif mug_input is not None:
        resolved_mug = mug_input

    # =========================================================================
    # FLUXO 1: GERAÇÃO GENERATIVA VIA GEMINI WEB (MugInput)
    # =========================================================================
    if resolved_mug is not None:
        mirror_flag = (
            resolved_mug.espelhar_transfer
            if mirror_for_transfer is None
            else mirror_for_transfer
        )

        image_bytes = _generate_mug_via_gemini(
            mug=resolved_mug,
            config=active_config,
            client=client,
            prompt_builder=prompt_builder,
            context=context,
        )

        preview_img = conform_and_compensate_mug_image(
            image_bytes=image_bytes,
            saturation_boost=saturation_boost,
        )
        transfer_img = ImageOps.mirror(preview_img)
        transfer_img.info["dpi"] = (DPI, DPI)

        slug = resolved_mug.slug

        if output_path is not None:
            primary_target = Path(output_path)
            if primary_target.parent:
                primary_target.parent.mkdir(parents=True, exist_ok=True)
            primary_resolved = primary_target.resolve()

            if mirror_flag:
                transfer_path = primary_resolved
                preview_path = primary_resolved.with_name(
                    f"{primary_resolved.stem}_preview{primary_resolved.suffix or '.png'}"
                )
                transfer_img.save(transfer_path, format="PNG", dpi=(DPI, DPI))
                preview_img.save(preview_path, format="PNG", dpi=(DPI, DPI))
                logger.success(
                    "Arte generativa de caneca gerada | Transfer: '{}' | Prévia: '{}'",
                    transfer_path,
                    preview_path,
                )
                return transfer_path, preview_path

            preview_img.save(primary_resolved, format="PNG", dpi=(DPI, DPI))
            logger.success(
                "Arte generativa de caneca (sem espelhamento) gerada em: '{}'",
                primary_resolved,
            )
            return primary_resolved, None

        preview_path = (
            active_config.output_dir / f"{slug}_mug_preview.png"
        ).resolve()
        preview_img.save(preview_path, format="PNG", dpi=(DPI, DPI))

        if mirror_flag:
            transfer_path = (
                active_config.output_dir / f"{slug}_mug_transfer.png"
            ).resolve()
            transfer_img.save(transfer_path, format="PNG", dpi=(DPI, DPI))
            logger.success(
                "Arte de caneca 11oz gerada (2598x1122px @ 300 DPI) | Transfer: '{}' | Prévia: '{}'",
                transfer_path,
                preview_path,
            )
            return transfer_path, preview_path

        logger.success(
            "Arte de caneca 11oz (prévia normal) gerada em: '{}'",
            preview_path,
        )
        return preview_path, None

    # =========================================================================
    # FLUXO 2: COMPOSIÇÃO CLÁSSICA COM IMAGENS LOCAIS
    # =========================================================================
    if image_or_images is None:
        raise ValueError(
            "Informe um 'MugInput' ou pelo menos uma imagem ('image_or_images') para gerar a arte da caneca."
        )

    mode_spec = normalize_mug_mode(mode)
    inputs = _normalize_image_inputs(image_or_images)
    mirror_flag = True if mirror_for_transfer is None else mirror_for_transfer

    # Expansão generativa prévia opcional se carta for vertical no modo panorâmico
    if expand_with_ai and mode_spec.code == "panoramic" and isinstance(inputs[0], Path):
        src_path = inputs[0]
        with Image.open(src_path) as check_img:
            w, h = check_img.size
        if w < h * 1.8:
            logger.info(
                "Acionando tools.background_expander [modo=caneca] para expansão panorâmica de '{}'...",
                src_path.name,
            )
            expanded_path = expand_background(
                image_path=src_path,
                mode="caneca",
                config=active_config,
                max_retries=max_retries,
            )
            inputs[0] = expanded_path

    mug_composer = composer or MugArtworkComposer(spec=DEFAULT_MUG_SPEC)
    preview_img, transfer_img = mug_composer.compose(
        image_or_images=inputs,
        mode=mode_spec.code,
        text=text,
        apply_color_compensation=True,
        saturation_boost=saturation_boost,
    )

    base_stem = _derive_base_stem(inputs, mode_spec.code)

    if output_path is not None:
        primary_target = Path(output_path)
        if primary_target.parent:
            primary_target.parent.mkdir(parents=True, exist_ok=True)
        primary_resolved = primary_target.resolve()

        if mirror_flag:
            transfer_path = primary_resolved
            preview_path = primary_resolved.with_name(
                f"{primary_resolved.stem}_preview{primary_resolved.suffix or '.png'}"
            )
            transfer_img.save(transfer_path, format="PNG", dpi=(DPI, DPI))
            preview_img.save(preview_path, format="PNG", dpi=(DPI, DPI))
            logger.success(
                "Arte de caneca [{}] gerada | Transfer espelhado: '{}' | Prévia visual: '{}'",
                mode_spec.code,
                transfer_path,
                preview_path,
            )
            return transfer_path, preview_path

        preview_img.save(primary_resolved, format="PNG", dpi=(DPI, DPI))
        logger.success(
            "Arte de caneca [{}] (sem espelhamento) gerada em: '{}'",
            mode_spec.code,
            primary_resolved,
        )
        return primary_resolved, None

    preview_path = (
        active_config.output_dir / f"{base_stem}_mug_{mode_spec.code}_preview.png"
    ).resolve()
    preview_img.save(preview_path, format="PNG", dpi=(DPI, DPI))

    if mirror_flag:
        transfer_path = (
            active_config.output_dir / f"{base_stem}_mug_{mode_spec.code}_transfer.png"
        ).resolve()
        transfer_img.save(transfer_path, format="PNG", dpi=(DPI, DPI))
        logger.success(
            "Arte de caneca 11oz [{}] gerada ({}x{}px @ {} DPI) | Transfer: '{}' | Prévia: '{}'",
            mode_spec.code,
            DEFAULT_MUG_SPEC.width_px,
            DEFAULT_MUG_SPEC.height_px,
            DPI,
            transfer_path,
            preview_path,
        )
        return transfer_path, preview_path

    logger.success(
        "Arte de caneca 11oz [{}] (prévia normal) gerada em: '{}'",
        mode_spec.code,
        preview_path,
    )
    return preview_path, None
