"""Testes unitários e de integração para imposição gráfica de cartas e pôsteres (tools/print_sheet/)."""

from __future__ import annotations

import re
import sys
import tempfile
import unittest
from pathlib import Path
from typing import List, Tuple

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import cli
from tools.card_generator.core.config import AppConfig
from tools.print_sheet import (
    CROP_LINE_WIDTH_MM,
    CROP_LINE_WIDTH_PX,
    DPI,
    MAX_CARDS_PER_SHEET,
    PAPER_SPECS,
    TCG_CARD_HEIGHT_MM,
    TCG_CARD_HEIGHT_PX,
    TCG_CARD_WIDTH_MM,
    TCG_CARD_WIDTH_PX,
    CardGridImposition,
    create_card_print_sheet,
    create_poster_print_sheet,
    create_poster_sheet,
    discover_card_images,
    get_registration_centers,
    normalize_paper_spec,
    render_poster_sheet_image,
)


def make_solid_card(
    color: Tuple[int, int, int],
    size: Tuple[int, int] = (TCG_CARD_WIDTH_PX, TCG_CARD_HEIGHT_PX),
) -> Image.Image:
    """Cria uma imagem sintética de carta TCG em cor sólida para inspeção exata de pixels."""
    return Image.new("RGB", size, color=color)


def count_pdf_pages(pdf_path: Path) -> int:
    """Lê a quantidade de páginas do PDF gerado via PyMuPDF (se disponível) ou estrutura interna PDF."""
    data = pdf_path.read_bytes()
    if not data.startswith(b"%PDF-"):
        raise ValueError("Arquivo não possui cabeçalho PDF válido (%PDF-).")

    try:
        import fitz  # type: ignore

        with fitz.open(pdf_path) as doc:
            return len(doc)
    except ImportError:
        pass

    # Fallback nativo: inspeciona /Type /Pages -> /Count N ou ocorrências de /Type /Page
    counts = [int(m) for m in re.findall(rb"/Count\s+(\d+)", data)]
    if counts:
        return max(counts)
    return len(re.findall(rb"/Type\s*/Page\b", data))


class TestCardGridGeometry(unittest.TestCase):
    """Testa a geometria rigorosa da grade 3x3 em A4/A3 Studio Kustom a 300 DPI."""

    def test_studio_kustom_physical_specs_at_300_dpi(self) -> None:
        """Verifica as dimensões exatas em mm e pixels de A4, A3 e Carta TCG a 300 DPI."""
        a4 = normalize_paper_spec("a4")
        self.assertEqual((a4.width_mm, a4.height_mm), (210.0, 300.0))
        self.assertEqual((a4.width_px, a4.height_px), (2480, 3543))
        self.assertAlmostEqual(a4.aspect_ratio, 1.429, delta=0.002)
        self.assertEqual(a4.dpi, 300)

        a3 = normalize_paper_spec("a3")
        self.assertEqual((a3.width_mm, a3.height_mm), (300.0, 420.0))
        self.assertEqual((a3.width_px, a3.height_px), (3543, 4960))
        self.assertAlmostEqual(a3.aspect_ratio, 1.400, delta=0.002)
        self.assertEqual(a3.dpi, 300)

        self.assertEqual((TCG_CARD_WIDTH_MM, TCG_CARD_HEIGHT_MM), (63.0, 88.0))
        self.assertEqual((TCG_CARD_WIDTH_PX, TCG_CARD_HEIGHT_PX), (744, 1039))
        self.assertEqual(DPI, 300)

    def test_a4_3x3_grid_margins_and_centering(self) -> None:
        """A grade 3x3 (189x264mm) em folha A4 (210x300mm) deve ter margens exatas de 10.5mm e 18.0mm."""
        imposition = CardGridImposition(paper="a4")

        self.assertEqual(imposition.rows, 3)
        self.assertEqual(imposition.cols, 3)
        self.assertEqual(imposition.max_cards, 9)

        # Geometria física em milímetros
        self.assertAlmostEqual(imposition.grid_width_mm, 189.0)
        self.assertAlmostEqual(imposition.grid_height_mm, 264.0)
        self.assertAlmostEqual(imposition.margin_x_mm, 10.5)
        self.assertAlmostEqual(imposition.margin_y_mm, 18.0)

        # Geometria digital em pixels a 300 DPI
        self.assertEqual(imposition.grid_width_px, 3 * 744)  # 2232 px
        self.assertEqual(imposition.grid_height_px, 3 * 1039)  # 3117 px
        self.assertEqual(imposition.margin_x_px, 124)  # (2480 - 2232) // 2
        self.assertEqual(imposition.margin_y_px, 213)  # (3543 - 3117) // 2

        slots = imposition.calculate_front_slots(9)
        self.assertEqual(len(slots), 9)

        # Slot (0, 0) deve iniciar exatamente na margem (124, 213)
        self.assertEqual((slots[0].row, slots[0].col), (0, 0))
        self.assertEqual((slots[0].x_px, slots[0].y_px), (124, 213))
        self.assertAlmostEqual(slots[0].x_mm, 10.5)
        self.assertAlmostEqual(slots[0].y_mm, 18.0)

        # Slot (2, 2) deve terminar exatamente em (2480 - 124, 3543 - 213) = (2356, 3330)
        last_slot = slots[8]
        self.assertEqual((last_slot.row, last_slot.col), (2, 2))
        self.assertEqual(
            last_slot.bbox,
            (124 + 2 * 744, 213 + 2 * 1039, 2480 - 124, 3543 - 213),
        )

    def test_invalid_card_count_or_paper_raises_value_error(self) -> None:
        """Deve rejeitar quantidades inválidas de cartas por folha (<1 ou >9) e papéis desconhecidos."""
        imposition = CardGridImposition(paper="a4")
        with self.assertRaises(ValueError):
            imposition.calculate_front_slots(0)
        with self.assertRaises(ValueError):
            imposition.calculate_front_slots(MAX_CARDS_PER_SHEET + 1)
        with self.assertRaises(ValueError):
            normalize_paper_spec("b5_invalido")


class TestHorizontalDuplexMirroring(unittest.TestCase):
    """Testa rigorosamente o espelhamento horizontal do verso (coluna 0 <-> coluna 2)."""

    def test_back_slots_invert_columns_in_every_row(self) -> None:
        """Na página 2 (Verso), a coluna 0 da frente deve virar coluna 2, 1->1 e 2->0 em todas as linhas."""
        imposition = CardGridImposition(paper="a4")
        front_slots = imposition.calculate_front_slots(9)
        back_slots = imposition.calculate_back_slots(9)

        for idx in range(9):
            f_slot = front_slots[idx]
            b_slot = back_slots[idx]

            # Mesma linha vertical
            self.assertEqual(f_slot.row, b_slot.row)
            self.assertEqual(f_slot.y_px, b_slot.y_px)

            # Coluna espelhada: 0 -> 2, 1 -> 1, 2 -> 0
            expected_back_col = 2 - f_slot.col
            self.assertEqual(b_slot.col, expected_back_col)

            # A coordenada X da carta na coluna c na frente deve ser idêntica à coordenada X
            # da carta na coluna (2 - c) no verso
            partner_front_slot = imposition.get_slot(f_slot.row * 3 + expected_back_col, is_back=False)
            self.assertEqual(b_slot.x_px, partner_front_slot.x_px)

    def test_rendered_duplex_sheets_pixel_exact_column_mirroring(self) -> None:
        """Verifica nos pixels renderizados que a carta da coluna 0 na frente casa com a coluna 2 no verso."""
        imposition = CardGridImposition(paper="a4")

        # 9 cores distintas para identificar inequivocamente cada carta (0 a 8)
        palette: List[Tuple[int, int, int]] = [
            (220, 20, 60),    # Carta 0 (Linha 0, Col 0 na frente -> Linha 0, Col 2 no verso)
            (30, 144, 255),   # Carta 1 (Linha 0, Col 1 na frente -> Linha 0, Col 1 no verso)
            (50, 205, 50),    # Carta 2 (Linha 0, Col 2 na frente -> Linha 0, Col 0 no verso)
            (255, 165, 0),    # Carta 3 (Linha 1, Col 0 na frente -> Linha 1, Col 2 no verso)
            (138, 43, 226),   # Carta 4 (Linha 1, Col 1 na frente -> Linha 1, Col 1 no verso)
            (0, 206, 209),    # Carta 5 (Linha 1, Col 2 na frente -> Linha 1, Col 0 no verso)
            (255, 20, 147),   # Carta 6 (Linha 2, Col 0 na frente -> Linha 2, Col 2 no verso)
            (184, 134, 11),   # Carta 7 (Linha 2, Col 1 na frente -> Linha 2, Col 1 no verso)
            (70, 130, 180),   # Carta 8 (Linha 2, Col 2 na frente -> Linha 2, Col 0 no verso)
        ]

        fronts = [make_solid_card(color) for color in palette]
        backs = [make_solid_card(color) for color in palette]

        front_page, back_page = imposition.render_duplex_sheets(fronts, backs, draw_marks=True)
        self.assertEqual(front_page.size, (2480, 3543))
        self.assertEqual(back_page.size, (2480, 3543))

        front_slots = imposition.calculate_front_slots(9)
        for row in range(3):
            slot_col0 = front_slots[row * 3 + 0]
            slot_col1 = front_slots[row * 3 + 1]
            slot_col2 = front_slots[row * 3 + 2]

            # Na frente: col 0 tem cor[row*3+0], col 1 tem cor[row*3+1], col 2 tem cor[row*3+2]
            self.assertEqual(front_page.getpixel(slot_col0.center_px), palette[row * 3 + 0])
            self.assertEqual(front_page.getpixel(slot_col1.center_px), palette[row * 3 + 1])
            self.assertEqual(front_page.getpixel(slot_col2.center_px), palette[row * 3 + 2])

            # No verso: a posição física da col 2 recebe o verso da carta da col 0 da frente!
            self.assertEqual(
                back_page.getpixel(slot_col2.center_px),
                front_page.getpixel(slot_col0.center_px),
            )
            # A posição física da col 0 no verso recebe o verso da carta da col 2 da frente!
            self.assertEqual(
                back_page.getpixel(slot_col0.center_px),
                front_page.getpixel(slot_col2.center_px),
            )
            # A coluna central (col 1) permanece no centro!
            self.assertEqual(
                back_page.getpixel(slot_col1.center_px),
                front_page.getpixel(slot_col1.center_px),
            )

    def test_single_card_front_col0_renders_at_back_col2(self) -> None:
        """Se houver apenas 1 carta (col 0 na frente), seu verso deve ser impresso na col 2 do verso."""
        imposition = CardGridImposition(paper="a4")
        front_card = make_solid_card((200, 40, 40))
        shared_back = make_solid_card((40, 80, 200))

        front_page, back_page = imposition.render_duplex_sheets([front_card], shared_back)
        slot_col0 = imposition.get_slot(0, is_back=False)
        slot_col2 = imposition.get_slot(2, is_back=False)

        self.assertEqual(front_page.getpixel(slot_col0.center_px), (200, 40, 40))
        self.assertEqual(front_page.getpixel(slot_col2.center_px), (255, 255, 255))

        # No verso, a col 0 fica em branco e a col 2 recebe o verso azul!
        self.assertEqual(back_page.getpixel(slot_col0.center_px), (255, 255, 255))
        self.assertEqual(back_page.getpixel(slot_col2.center_px), (40, 80, 200))


class TestCropMarksAndRegistration(unittest.TestCase):
    """Testa as marcas de corte finas (0.25mm / 3px) e as 4 cruzes de registro nos cantos."""

    def test_crop_marks_and_registration_crosses_are_drawn_in_black(self) -> None:
        """Deve desenhar traços pretos (0,0,0) de 3px nas linhas de corte e nas 4 cruzes de registro."""
        self.assertAlmostEqual(CROP_LINE_WIDTH_MM, 0.25)
        self.assertEqual(CROP_LINE_WIDTH_PX, 3)

        imposition = CardGridImposition(paper="a4")
        sheet = imposition.render_front_sheet([make_solid_card((120, 180, 240))], draw_marks=True)

        # Verifica as 4 cruzes de registro nos cantos da folha
        for cx, cy in get_registration_centers(
            sheet.size,
            corner_offset_px=(imposition.margin_x_px // 2, imposition.margin_y_px // 2),
        ):
            self.assertEqual(sheet.getpixel((cx, cy)), (0, 0, 0))

        # Verifica as marcas de corte verticais no topo (cantos externos e canais de separação)
        sample_y_top = imposition.margin_y_px - 20
        for x in imposition.vertical_cut_lines_px():
            self.assertEqual(sheet.getpixel((x, sample_y_top)), (0, 0, 0))

        # Verifica as marcas de corte horizontais na margem esquerda
        sample_x_left = imposition.margin_x_px - 20
        for y in imposition.horizontal_cut_lines_px():
            self.assertEqual(sheet.getpixel((sample_x_left, y)), (0, 0, 0))


class TestPDFBuilderAndPosters(unittest.TestCase):
    """Testa a geração de PDFs multipágina em 300 DPI para cartas duplex e folhas de pôster A4/A3."""

    def test_create_card_print_sheet_generates_2_page_duplex_pdf(self) -> None:
        """Deve gerar um arquivo PDF válido com 2 páginas (Frente e Verso) para até 9 cartas."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            config = AppConfig(
                base_dir=tmp_path,
                input_dir=tmp_path / "input",
                output_dir=tmp_path / "output",
            )

            front_paths: List[Path] = []
            for idx in range(9):
                p = tmp_path / f"carta_{idx + 1}.png"
                make_solid_card((20 * idx, 100, 200)).save(p, format="PNG")
                front_paths.append(p)

            back_path = tmp_path / "VersoPadrao.png"
            make_solid_card((30, 30, 90)).save(back_path, format="PNG")

            out_pdf = tmp_path / "output" / "folha_cartas_a4.pdf"
            result_path = create_card_print_sheet(
                front_images=front_paths,
                back_image=back_path,
                paper="a4",
                output_pdf=out_pdf,
                config=config,
            )

            self.assertEqual(result_path, out_pdf.resolve())
            self.assertTrue(result_path.is_file())
            self.assertGreater(result_path.stat().st_size, 10_000)
            self.assertEqual(count_pdf_pages(result_path), 2)

    def test_create_poster_print_sheet_a4_and_a3(self) -> None:
        """Deve gerar folhas de pôster centralizadas em A4 (2480x3543) e A3 (3543x4960) com marcas de corte."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            config = AppConfig(base_dir=tmp_path, output_dir=tmp_path / "output")

            poster_src = tmp_path / "poster_arte.png"
            Image.new("RGB", (1600, 2200), color=(180, 60, 90)).save(poster_src, format="PNG")

            for paper_code, expected_size in [("a4", (2480, 3543)), ("a3", (3543, 4960))]:
                with self.subTest(paper=paper_code):
                    rendered_img, bbox = render_poster_sheet_image(poster_src, paper=paper_code)
                    self.assertEqual(rendered_img.size, expected_size)
                    # Verifica centralização simétrica na folha
                    left, top, right, bottom = bbox
                    self.assertAlmostEqual(left, expected_size[0] - right, delta=1)
                    self.assertAlmostEqual(top, expected_size[1] - bottom, delta=1)

                    pdf_out = tmp_path / "output" / f"poster_{paper_code}.pdf"
                    pdf_path = create_poster_print_sheet(
                        poster_image=poster_src,
                        paper=paper_code,
                        output_pdf=pdf_out,
                        config=config,
                    )
                    self.assertTrue(pdf_path.is_file())
                    self.assertEqual(count_pdf_pages(pdf_path), 1)


class TestPrintSheetCLI(unittest.TestCase):
    """Testa o subcomando 'sheet' (e aliases 'print-sheet', 'folha', 'imposition') na CLI."""

    def test_cli_sheet_cards_and_cards_dir_and_poster(self) -> None:
        """Deve executar 'sheet' via CLI para lista de cartas, diretório de cartas e pôster."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            cards_dir = tmp_path / "cards_out"
            cards_dir.mkdir(parents=True, exist_ok=True)

            c1 = cards_dir / "carta1.png"
            c2 = cards_dir / "carta2.png"
            verso = cards_dir / "VersoPadrao.png"
            make_solid_card((210, 50, 50)).save(c1, format="PNG")
            make_solid_card((50, 210, 50)).save(c2, format="PNG")
            make_solid_card((40, 40, 120)).save(verso, format="PNG")

            # 1. Subcomando 'sheet' com --cards explícito
            pdf_cards = tmp_path / "explicit_cards.pdf"
            code1 = cli.main(
                [
                    "sheet",
                    "--cards",
                    str(c1),
                    str(c2),
                    "--back",
                    str(verso),
                    "--paper",
                    "a4",
                    "--output",
                    str(pdf_cards),
                    "--no-file-log",
                ]
            )
            self.assertEqual(code1, 0)
            self.assertTrue(pdf_cards.is_file())
            self.assertEqual(count_pdf_pages(pdf_cards), 2)

            # 2. Alias 'folha' com --cards-dir (deve excluir VersoPadrao.png automaticamente)
            discovered = discover_card_images(cards_dir, exclude_paths=[verso])
            self.assertEqual(len(discovered), 2)

            pdf_dir = tmp_path / "dir_cards.pdf"
            code2 = cli.main(
                [
                    "folha",
                    "--cards-dir",
                    str(cards_dir),
                    "--back",
                    str(verso),
                    "--paper",
                    "a4",
                    "-o",
                    str(pdf_dir),
                    "--no-file-log",
                ]
            )
            self.assertEqual(code2, 0)
            self.assertTrue(pdf_dir.is_file())
            self.assertEqual(count_pdf_pages(pdf_dir), 2)

            # 3. Aliases 'print-sheet' e 'imposition' com --poster
            for alias in ("print-sheet", "imposition"):
                with self.subTest(alias=alias):
                    pdf_poster = tmp_path / f"poster_{alias}.pdf"
                    code_p = cli.main(
                        [
                            alias,
                            "--poster",
                            str(c1),
                            "--paper",
                            "a4",
                            "-o",
                            str(pdf_poster),
                            "--no-file-log",
                        ]
                    )
                    self.assertEqual(code_p, 0)
                    self.assertTrue(pdf_poster.is_file())
                    self.assertEqual(count_pdf_pages(pdf_poster), 1)

    def test_cli_sheet_returns_error_on_invalid_arguments(self) -> None:
        """Deve retornar exit code != 0 quando faltar --back ou papel for inválido."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            c1 = tmp_path / "c1.png"
            make_solid_card((100, 100, 100)).save(c1, format="PNG")

            # Sem --back ao informar --cards
            self.assertEqual(
                cli.main(["sheet", "--cards", str(c1), "--no-file-log"]),
                2,
            )
            # Papel inválido
            self.assertEqual(
                cli.main(["sheet", "--poster", str(c1), "--paper", "papel_x", "--no-file-log"]),
                2,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
