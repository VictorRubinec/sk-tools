"""Compilador de folhas de imposição gráfica (Cartas Duplex e Pôsteres) em PDF 300 DPI."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Sequence, Tuple, Union

from PIL import Image, ImageOps

from tools.card_generator.core.config import AppConfig, DEFAULT_CONFIG
from tools.card_generator.core.logger import logger
from tools.print_sheet.card_grid import (
    DPI,
    MAX_CARDS_PER_SHEET,
    CardGridImposition,
    PaperSpec,
    load_image_rgb,
    mm_to_px,
    normalize_paper_spec,
)
from tools.print_sheet.crop_marks import apply_sheet_marks

DEFAULT_POSTER_MARGIN_MM: float = 10.0


def save_pages_to_pdf(
    pages: Sequence[Image.Image],
    output_pdf: Union[str, Path],
    dpi: int = DPI,
) -> Path:
    """Salva uma sequência de imagens PIL como um único documento PDF multipágina em 300 DPI."""
    if not pages:
        raise ValueError("A lista de páginas para geração do PDF não pode ser vazia.")

    out_path = Path(output_pdf)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    rgb_pages = [page.convert("RGB") for page in pages]
    first_page, remaining_pages = rgb_pages[0], rgb_pages[1:]

    first_page.save(
        out_path,
        format="PDF",
        resolution=float(dpi),
        save_all=True,
        append_images=remaining_pages,
    )
    return out_path.resolve()


def render_poster_sheet_image(
    poster_path: Union[str, Path, Image.Image],
    paper: str = "a4",
    margin_mm: float = DEFAULT_POSTER_MARGIN_MM,
    draw_marks: bool = True,
) -> Tuple[Image.Image, Tuple[int, int, int, int]]:
    """Renderiza 1 pôster centralizado na folha A4/A3 (300 DPI) com marcas de corte e cruzes de registro."""
    spec: PaperSpec = normalize_paper_spec(paper)
    poster_img = load_image_rgb(poster_path)

    sheet_w, sheet_h = spec.width_px, spec.height_px
    margin_px = max(0, mm_to_px(margin_mm, spec.dpi)) if margin_mm > 0 else 0

    max_poster_w = max(1, sheet_w - 2 * margin_px)
    max_poster_h = max(1, sheet_h - 2 * margin_px)

    # Ajusta o pôster preservando a área útil centralizada na folha
    fitted_poster = ImageOps.contain(
        poster_img,
        (max_poster_w, max_poster_h),
        method=Image.Resampling.LANCZOS,
    )
    pw, ph = fitted_poster.size
    left = (sheet_w - pw) // 2
    top = (sheet_h - ph) // 2
    bbox = (left, top, left + pw, top + ph)

    canvas = Image.new("RGB", (sheet_w, sheet_h), color=(255, 255, 255))
    canvas.paste(fitted_poster, (left, top))

    if draw_marks:
        apply_sheet_marks(canvas, rect_bbox=bbox)

    return canvas, bbox


def build_card_sheet_pdf(
    front_images: Sequence[Union[str, Path, Image.Image]],
    back_image: Union[str, Path, Image.Image, Sequence[Union[str, Path, Image.Image]]],
    paper: str = "super_a4",
    output_pdf: Optional[Union[str, Path]] = None,
    config: Optional[AppConfig] = None,
    draw_marks: bool = True,
) -> Path:
    """Compila frentes e versos espelhados de cartas TCG em 1 único PDF multipágina a 300 DPI."""
    if not front_images:
        raise ValueError("A lista de imagens de frente ('front_images') não pode ser vazia.")

    cfg = config or DEFAULT_CONFIG
    cfg.ensure_directories()

    imposition = CardGridImposition(paper=paper)
    total_cards = len(front_images)

    # Normaliza a lista de versos para o total de cartas (suporta 1 verso único ou N versos individuais)
    if isinstance(back_image, (str, Path, Image.Image)):
        all_backs: List[Union[str, Path, Image.Image]] = [back_image for _ in range(total_cards)]
    else:
        back_seq = list(back_image)
        if not back_seq:
            raise ValueError("A lista de imagens de verso ('back_image') não pode ser vazia.")
        if len(back_seq) == 1:
            all_backs = [back_seq[0] for _ in range(total_cards)]
        elif len(back_seq) == total_cards:
            all_backs = back_seq
        else:
            raise ValueError(
                f"Quantidade de versos ({len(back_seq)}) incompatível com a quantidade de frentes ({total_cards})."
            )

    pages: List[Image.Image] = []
    for start_idx in range(0, total_cards, MAX_CARDS_PER_SHEET):
        chunk_fronts = front_images[start_idx : start_idx + MAX_CARDS_PER_SHEET]
        chunk_backs = all_backs[start_idx : start_idx + MAX_CARDS_PER_SHEET]
        front_page, back_page = imposition.render_duplex_sheets(
            front_images=chunk_fronts,
            back_image=chunk_backs,
            draw_marks=draw_marks,
        )
        pages.extend([front_page, back_page])

    if output_pdf is None:
        first_stem = (
            Path(front_images[0]).stem
            if isinstance(front_images[0], (str, Path))
            else "cards"
        )
        output_pdf = cfg.output_dir / f"{first_stem}_sheet_{imposition.paper_spec.code.lower()}.pdf"

    saved_path = save_pages_to_pdf(pages, output_pdf=output_pdf, dpi=imposition.dpi)
    logger.info(
        "Folha de cartas duplex gerada em PDF ({} página(s) @ {} DPI): {}",
        len(pages),
        imposition.dpi,
        saved_path,
    )
    return saved_path


def create_poster_sheet(
    poster_path: Union[str, Path, Image.Image],
    paper: str = "a4",
    output_pdf: Optional[Union[str, Path]] = None,
    config: Optional[AppConfig] = None,
    margin_mm: float = DEFAULT_POSTER_MARGIN_MM,
    draw_marks: bool = True,
) -> Path:
    """Gera uma folha de impressão PDF (300 DPI) com 1 pôster centralizado e marcas de corte."""
    cfg = config or DEFAULT_CONFIG
    cfg.ensure_directories()

    spec = normalize_paper_spec(paper)
    sheet_img, _ = render_poster_sheet_image(
        poster_path=poster_path,
        paper=spec.code,
        margin_mm=margin_mm,
        draw_marks=draw_marks,
    )

    if output_pdf is None:
        stem = Path(poster_path).stem if isinstance(poster_path, (str, Path)) else "poster"
        output_pdf = cfg.output_dir / f"{stem}_sheet_{spec.code.lower()}.pdf"

    saved_path = save_pages_to_pdf([sheet_img], output_pdf=output_pdf, dpi=spec.dpi)
    logger.info(
        "Folha de pôster {} ({}x{}px @ {} DPI) gerada em PDF: {}",
        spec.code,
        spec.width_px,
        spec.height_px,
        spec.dpi,
        saved_path,
    )
    return saved_path
