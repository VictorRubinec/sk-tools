"""Orquestrador do Criador de Arte para Caneca de Sublimação 11oz (tools/mug_artist/orchestrator.py)."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Sequence, Tuple, Union

from PIL import Image

from tools.background_expander.api import expand_background
from tools.card_generator.core.config import AppConfig, BASE_DIR, DEFAULT_CONFIG
from tools.card_generator.core.logger import logger
from tools.mug_artist.color_engine import DEFAULT_SATURATION_BOOST
from tools.mug_artist.composer import (
    DEFAULT_MUG_SPEC,
    DPI,
    MugArtworkComposer,
    normalize_mug_mode,
)


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


def run_mug_artwork_orchestration(
    image_or_images: Union[str, Path, Image.Image, Sequence[Union[str, Path, Image.Image]]],
    mode: str = "panoramic",
    text: Optional[str] = None,
    mirror_for_transfer: bool = True,
    config: Optional[AppConfig] = None,
    output_path: Optional[Union[str, Path]] = None,
    saturation_boost: float = DEFAULT_SATURATION_BOOST,
    expand_with_ai: bool = False,
    max_retries: int = 3,
    composer: Optional[MugArtworkComposer] = None,
) -> Tuple[Path, Optional[Path]]:
    """Executa o fluxo completo de composição cromática e montagem de arte para caneca 11oz.

    Conecta opcionalmente com `tools.background_expander` (modo `caneca`) caso `expand_with_ai=True`
    para expandir generativamente cartas verticais antes da composição panorâmica.

    Args:
        image_or_images: Caminho único ou sequência de caminhos/imagens das cartas.
        mode: Modo de layout ('panoramic', 'dual_face', 'card_plus_text').
        text: Texto comemorativo opcional (para o modo `card_plus_text`).
        mirror_for_transfer: Se True (padrão), gera tanto a arte espelhada (`ImageOps.mirror`)
            para prensa sublimática quanto a prévia visual normal.
        config: Configuração operacional (`AppConfig`).
        output_path: Caminho customizado opcional para salvar o arquivo principal.
        saturation_boost: Fator de compensação de saturação para Epson L110 (padrão: 1.18).
        expand_with_ai: Se True, aciona `expand_background(..., mode='caneca')` via Gemini Web
            quando a carta precisar de outpainting panorâmico.
        max_retries: Máximo de tentativas caso `expand_with_ai=True`.
        composer: Instância opcional de `MugArtworkComposer`.

    Returns:
        Tupla `(caminho_arte_transfer_espelhada, caminho_previa_visual)` quando
        `mirror_for_transfer=True`, ou `(caminho_previa_visual, None)` quando
        `mirror_for_transfer=False`.
    """
    mode_spec = normalize_mug_mode(mode)
    inputs = _normalize_image_inputs(image_or_images)

    active_config = config or DEFAULT_CONFIG
    active_config.ensure_directories()

    # Se solicitado outpainting generativo no modo panorâmico e a entrada for arquivo vertical
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

        if mirror_for_transfer:
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

    if mirror_for_transfer:
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
