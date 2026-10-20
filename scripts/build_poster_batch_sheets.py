"""Monta e compila as 9 folhas A3 com marcas de corte dos pôsteres (Pedidos 170, 172, 173, 175, 177 e 178)."""

from __future__ import annotations

import sys
from pathlib import Path
from PIL import Image

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from tools.print_sheet.pdf_builder import render_poster_sheet_image, save_pages_to_pdf
from tools.card_generator.core.logger import logger, setup_logger

ROOT = Path(r"D:\Desktop\Studio Kustom\04 - Pedidos e Historico\Pedidos")


def get_poster_batch() -> dict[str, list[tuple[str, Path, bool]]]:
    """Retorna o dicionário de pedidos mapeando para a lista de tuplas (identificador, caminho, precisa_rotacionar)."""
    return {
        "170": [
            ("170", ROOT / "170" / "poster_170_A3_300dpi_poster_a3_v_expanded.png", False),
        ],
        "172": [
            ("172_1", ROOT / "172" / "br-11134231-820lm-muco2soiwem850_poster_a3_v_expanded.png", False),
            ("172_2", ROOT / "172" / "br-11134231-820m7-muco2soiv01s7c_poster_a3_v_expanded.png", False),
        ],
        "173": [
            ("173", ROOT / "173" / "br-11134231-820lx-mudiq6avwn42ae_poster_a3_v_expanded.png", False),
        ],
        "175": [
            ("175", ROOT / "175" / "br-11134231-820lz-muhynsrey9s382_poster_a3_v_expanded.png", False),
        ],
        "177": [
            ("177_1", ROOT / "177" / "br-11134231-820lw-mui0ux3lwrgi9f_poster_a3_v_expanded.png", False),
            ("177_2", ROOT / "177" / "br-11134231-820m8-mui0ux3kuu4je6_poster_a3_v_expanded.png", False),
            ("177_3", ROOT / "177" / "br-11134231-820mf-mui0ux3m0z5u2d_poster_a3_v_expanded.png", False),
        ],
        "178": [
            ("178", ROOT / "178" / "br-11134231-820ls-mufsit7yp1xdd1_poster_a3_h_expanded.png", True),
        ],
    }


def render_poster_page(img_path: Path, rotate_90: bool) -> Image.Image:
    im = Image.open(img_path)
    if rotate_90:
        im = im.rotate(90, expand=True)
    sheet, _ = render_poster_sheet_image(im, paper="a3", margin_mm=10.0, draw_marks=True)
    return sheet


def main():
    setup_logger(console_level="INFO", log_to_file=True)
    logger.info("Iniciando compilação do lote consolidado de pôsteres A3...")

    batch = get_poster_batch()
    all_pages: list[Image.Image] = []
    total_posters = sum(len(items) for items in batch.values())
    logger.info("Total de pedidos: {} | Total de pôsteres: {}", len(batch), total_posters)

    for order_id, poster_items in batch.items():
        order_pages: list[Image.Image] = []
        for label, img_path, rot in poster_items:
            logger.info("Renderizando [Pedido {} / Arte {}]: '{}' (rotacionar={})...", order_id, label, img_path.name, rot)
            sheet = render_poster_page(img_path, rotate_90=rot)
            order_pages.append(sheet)
            all_pages.append(sheet)

        # Atualiza o PDF individual de cada pedido com todas as suas páginas
        order_pdf = ROOT / order_id / f"pedido_{order_id}_poster_a3.pdf"
        save_pages_to_pdf(order_pages, output_pdf=order_pdf, dpi=300)
        logger.success("[Pedido {}] PDF individual atualizado ({} página(s)): '{}'", order_id, len(order_pages), order_pdf.name)

    # Compila o Master PDF de Pôsteres
    master_pdf = ROOT / "impressao_lote_completo_posters_a3.pdf"
    logger.info("Gerando Master PDF Consolidado de Pôsteres: '{}'...", master_pdf.name)
    save_pages_to_pdf(all_pages, output_pdf=master_pdf, dpi=300)
    logger.success("Master PDF de Pôsteres gerado com sucesso ({} páginas @ 300 DPI): '{}'", len(all_pages), master_pdf)


if __name__ == "__main__":
    main()
