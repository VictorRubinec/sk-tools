"""Fachada Pública (API) do módulo de arte para caneca de sublimação 11oz (tools/mug_artist)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Sequence, Tuple, Union

from PIL import Image

from tools.card_generator.browser.gemini_client import GeminiClient
from tools.card_generator.core.config import AppConfig, DEFAULT_CONFIG
from tools.mug_artist.color_engine import DEFAULT_SATURATION_BOOST
from tools.mug_artist.orchestrator import run_mug_artwork_orchestration
from tools.mug_artist.prompt_builder import MugPromptBuilder
from tools.mug_artist.schema import MugInput


def create_mug_artwork(
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
    client: Optional[GeminiClient] = None,
    prompt_builder: Optional[MugPromptBuilder] = None,
    context: Optional[Any] = None,
) -> Tuple[Path, Optional[Path]]:
    """Cria a arte final para caneca de sublimação 11oz (220x95mm / 2598x1122px a 300 DPI).

    Suporta geração orientada a JSON via Gemini Web (quando fornecido `MugInput`) ou
    composição local com imagens de cartas existentes (via Pillow).

    Aplica compensação cromática de +18% de saturação para Epson L110 e gera a arte
    espelhada horizontalmente (`ImageOps.mirror`) para transfer térmico, além da prévia visual.

    Args:
        image_or_images: Instância de `MugInput`, caminho único ou sequência de caminhos de imagens.
        mug_input: Instância opcional de `MugInput` para geração generativa.
        mode: Modo de layout para o fluxo clássico ('panoramic', 'dual_face' ou 'card_plus_text').
        text: Texto comemorativo ou mensagem opcional (para `card_plus_text` clássico).
        mirror_for_transfer: Se True, gera o arquivo espelhado para transfer e a prévia visual.
        config: Configuração operacional (`AppConfig`). Usa `DEFAULT_CONFIG` se omitido.
        output_path: Caminho opcional de saída para o arquivo gerado.
        saturation_boost: Fator de compensação de saturação (padrão: 1.18).
        expand_with_ai: Se True, aciona `tools.background_expander` antes da composição panorâmica clássica.
        client: Cliente Gemini opcional para injeção.
        prompt_builder: Construtor de prompt opcional para injeção.
        context: Contexto compartilhado de navegador.

    Returns:
        Tupla `(caminho_arte_transfer_espelhada, caminho_previa_visual)`.
    """
    return run_mug_artwork_orchestration(
        image_or_images=image_or_images,
        mug_input=mug_input,
        mode=mode,
        text=text,
        mirror_for_transfer=mirror_for_transfer,
        config=config or DEFAULT_CONFIG,
        output_path=output_path,
        saturation_boost=saturation_boost,
        expand_with_ai=expand_with_ai,
        client=client,
        prompt_builder=prompt_builder,
        context=context,
    )


def generate_mug_artwork(
    mug: MugInput,
    config: Optional[AppConfig] = None,
    client: Optional[GeminiClient] = None,
    prompt_builder: Optional[MugPromptBuilder] = None,
    context: Optional[Any] = None,
    output_path: Optional[Union[str, Path]] = None,
    saturation_boost: float = DEFAULT_SATURATION_BOOST,
) -> Tuple[Path, Optional[Path]]:
    """Gera a arte de caneca orientada a parâmetros JSON utilizando o Google Gemini Web.

    Args:
        mug: Instância validada de `MugInput`.
        config: Configuração operacional (`AppConfig`).
        client: Instância de `GeminiClient` para injeção e mocks.
        prompt_builder: Instância de `MugPromptBuilder` para injeção e mocks.
        context: Contexto de navegador persistente.
        output_path: Caminho de saída customizado.
        saturation_boost: Fator de saturação Epson L110 (padrão: 1.18).

    Returns:
        Tupla `(caminho_transfer_espelhado, caminho_previa_normal)`.
    """
    return run_mug_artwork_orchestration(
        mug_input=mug,
        config=config or DEFAULT_CONFIG,
        client=client,
        prompt_builder=prompt_builder,
        context=context,
        output_path=output_path,
        saturation_boost=saturation_boost,
    )
