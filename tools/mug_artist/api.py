"""Fachada Pública (API) do módulo de arte para caneca de sublimação 11oz (tools/mug_artist)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence, Tuple, Union

from PIL import Image

from tools.card_generator.core.config import AppConfig, DEFAULT_CONFIG
from tools.mug_artist.color_engine import DEFAULT_SATURATION_BOOST
from tools.mug_artist.orchestrator import run_mug_artwork_orchestration


def create_mug_artwork(
    image_or_images: Union[
        str, Path, Image.Image, Sequence[Union[str, Path, Image.Image]]
    ],
    mode: str = "panoramic",
    text: Optional[str] = None,
    mirror_for_transfer: bool = True,
    config: Optional[AppConfig] = None,
    output_path: Optional[Union[str, Path]] = None,
    saturation_boost: float = DEFAULT_SATURATION_BOOST,
    expand_with_ai: bool = False,
) -> Tuple[Path, Optional[Path]]:
    """Cria a arte final para caneca de sublimação 11oz (220x95mm / 2598x1122px a 300 DPI).

    Aplica compensação cromática de +18% de saturação para Epson L110 e gera a arte
    espelhada horizontalmente (`ImageOps.mirror`) para transfer térmico, além da prévia visual.

    Args:
        image_or_images: Caminho único ou sequência de caminhos das cartas/imagens.
        mode: Modo de layout ('panoramic', 'dual_face' ou 'card_plus_text'). Padrão: 'panoramic'.
        text: Texto comemorativo ou mensagem opcional (para `card_plus_text`).
        mirror_for_transfer: Se True (padrão), gera o arquivo espelhado para transfer e a prévia visual.
        config: Configuração operacional (`AppConfig`). Usa `DEFAULT_CONFIG` se omitido.
        output_path: Caminho opcional de saída para o arquivo gerado.
        saturation_boost: Fator de compensação de saturação (padrão: 1.18).
        expand_with_ai: Se True, aciona `tools.background_expander` antes da composição panorâmica.

    Returns:
        Tupla `(caminho_arte_transfer_espelhada, caminho_previa_visual)`.
    """
    return run_mug_artwork_orchestration(
        image_or_images=image_or_images,
        mode=mode,
        text=text,
        mirror_for_transfer=mirror_for_transfer,
        config=config or DEFAULT_CONFIG,
        output_path=output_path,
        saturation_boost=saturation_boost,
        expand_with_ai=expand_with_ai,
    )
