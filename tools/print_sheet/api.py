"""Fachada Pública (API) do módulo de imposição gráfica (tools/print_sheet)."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Sequence, Union

from tools.card_generator.core.config import AppConfig, DEFAULT_CONFIG
from tools.print_sheet.pdf_builder import build_card_sheet_pdf, create_poster_sheet

SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def discover_card_images(
    cards_dir: Union[str, Path],
    exclude_paths: Optional[Sequence[Union[str, Path]]] = None,
) -> List[Path]:
    """Localiza imagens de cartas ordenadas alfabeticamente em um diretório, ignorando o arquivo de verso."""
    dir_path = Path(cards_dir)
    if not dir_path.is_dir():
        raise FileNotFoundError(f"Diretório de cartas não encontrado: {dir_path}")

    excluded_resolved = {
        Path(p).resolve() for p in (exclude_paths or []) if p is not None and Path(p).exists()
    }

    found: List[Path] = []
    for item in sorted(dir_path.iterdir()):
        if (
            item.is_file()
            and item.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS
            and item.resolve() not in excluded_resolved
        ):
            found.append(item)

    if not found:
        raise ValueError(f"Nenhuma imagem de carta encontrada no diretório: {dir_path}")
    return found


def create_card_print_sheet(
    front_images: List[Union[str, Path]],
    back_image: Union[str, Path, List[Union[str, Path]]],
    paper: str = "super_a4",
    output_pdf: Optional[Path] = None,
    config: Optional[AppConfig] = None,
) -> Path:
    """Gera uma folha de impressão PDF (300 DPI) duplex com grade 3x3 de cartas e verso espelhado com sangria.

    Args:
        front_images: Lista de caminhos das imagens da frente das cartas.
        back_image: Caminho único para verso compartilhado ou lista de caminhos para versos individuais.
        paper: Formato do papel ('super_a4', 'a4' ou 'a3'). Padrão: 'super_a4'.
        output_pdf: Caminho opcional de destino do arquivo PDF.
        config: Configuração operacional (`AppConfig`). Usa `DEFAULT_CONFIG` se omitido.

    Returns:
        `Path` apontando para o PDF multipágina gerado.
    """
    return build_card_sheet_pdf(
        front_images=front_images,
        back_image=back_image,
        paper=paper,
        output_pdf=output_pdf,
        config=config or DEFAULT_CONFIG,
    )


def create_poster_print_sheet(
    poster_image: Union[str, Path],
    paper: str = "a4",
    output_pdf: Optional[Path] = None,
    config: Optional[AppConfig] = None,
) -> Path:
    """Gera uma folha de impressão PDF (300 DPI) com 1 pôster centralizado e marcas de corte.

    Args:
        poster_image: Caminho da imagem do pôster.
        paper: Formato do papel ('a4' ou 'a3'). Padrão: 'a4'.
        output_pdf: Caminho opcional de destino do arquivo PDF.
        config: Configuração operacional (`AppConfig`). Usa `DEFAULT_CONFIG` se omitido.

    Returns:
        `Path` apontando para o PDF gerado.
    """
    return create_poster_sheet(
        poster_path=poster_image,
        paper=paper,
        output_pdf=output_pdf,
        config=config or DEFAULT_CONFIG,
    )
