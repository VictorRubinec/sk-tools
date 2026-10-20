"""Fachada Pública (API) do módulo de expansão generativa de fundo (tools/background_expander)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

from tools.background_expander.orchestrator import run_background_expansion_orchestration
from tools.background_expander.prompt_builder import DEFAULT_BLEED_MM
from tools.card_generator.core.config import AppConfig, DEFAULT_CONFIG


def expand_background(
    image_path: Union[str, Path],
    mode: str = "bleed_5mm",
    bleed_mm: float = DEFAULT_BLEED_MM,
    preserve_frame: bool = False,
    config: Optional[AppConfig] = None,
    max_retries: int = 3,
) -> Path:
    """Expande generativamente o cenário ao redor da imagem mantendo o sujeito central intacto.

    Args:
        image_path: Caminho para a imagem original.
        mode: Modo de expansão ('bleed_5mm', 'horizontal', 'caneca', 'custom').
        bleed_mm: Margem de sangria por borda em milímetros (padrão: 5.0 mm = 59 px a 300 DPI).
        preserve_frame: Se True, mantém a moldura decorativa fixa no centro e expande o cenário para fora dela.
        config: Configurações operacionais (`AppConfig`). Usa `DEFAULT_CONFIG` se omitido.
        max_retries: Número máximo de tentativas de geração e validação.

    Returns:
        `Path` apontando para a imagem expandida salva no diretório `output/`.
    """
    return run_background_expansion_orchestration(
        image_path=image_path,
        mode=mode,
        bleed_mm=bleed_mm,
        preserve_frame=preserve_frame,
        config=config or DEFAULT_CONFIG,
        max_retries=max_retries,
    )
