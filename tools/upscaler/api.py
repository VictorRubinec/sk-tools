"""Fachada Pública (API) do módulo de upscaling de cartas para posters (tools/upscaler)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

from tools.card_generator.core.config import AppConfig, DEFAULT_CONFIG
from tools.upscaler.orchestrator import run_upscale_orchestration


def upscale_card_to_poster(
    image_path: Union[str, Path],
    target_format: str,
    config: Optional[AppConfig] = None,
    max_retries: int = 3,
) -> Path:
    """Converte e amplia uma imagem de carta para um poster em alta resolução (300 DPI).

    Args:
        image_path: Caminho para a imagem original da carta.
        target_format: Formato de destino ('a4_v', 'a4_h', 'a3_v', 'a3_h').
        config: Configurações operacionais (`AppConfig`). Usa `DEFAULT_CONFIG` se omitido.
        max_retries: Número máximo de tentativas de geração e validação.

    Returns:
        `Path` apontando para o arquivo de poster gerado no diretório `output/`.
    """
    return run_upscale_orchestration(
        image_path=image_path,
        target_format=target_format,
        config=config or DEFAULT_CONFIG,
        max_retries=max_retries,
    )
