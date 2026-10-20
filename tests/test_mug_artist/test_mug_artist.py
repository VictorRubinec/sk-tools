"""Testes unitários e de integração para o módulo de canecas 11oz (tools/mug_artist/)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from typing import Tuple
from unittest.mock import patch

from PIL import Image, ImageEnhance, ImageOps

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import cli
from tools.card_generator.core.config import AppConfig
from tools.mug_artist import (
    CENTER_FACE_CENTER_X_PX,
    DEFAULT_MUG_SPEC,
    DEFAULT_SATURATION_BOOST,
    DPI,
    HANDLE_MARGIN_MM,
    HANDLE_MARGIN_PX,
    LEFT_FACE_CENTER_X_PX,
    MUG_CAPACITY_ML,
    MUG_CAPACITY_OZ,
    MUG_CENTER_Y_PX,
    MUG_HEIGHT_MM,
    MUG_HEIGHT_PX,
    MUG_SIZE_PX,
    MUG_WIDTH_MM,
    MUG_WIDTH_PX,
    RIGHT_FACE_CENTER_X_PX,
    MugArtworkComposer,
    apply_sublimation_compensation,
    create_mug_artwork,
    mirror_for_sublimation,
    mm_to_px,
    normalize_mug_mode,
    run_mug_artwork_orchestration,
)


def make_test_card(
    color: Tuple[int, int, int],
    size: Tuple[int, int] = (744, 1039),
) -> Image.Image:
    """Cria uma carta sintética de cor sólida nas dimensões nominais TCG (744x1039 px)."""
    return Image.new("RGB", size, color=color)


class TestStudioKustomMug11ozSpecs(unittest.TestCase):
    """Valida os parâmetros físicos e geométricos rigorosos da Caneca 11oz / 325ml a 300 DPI."""

    def test_mug_11oz_exact_dimensions_and_face_centers_at_300_dpi(self) -> None:
        """Largura 220mm (2598px), altura 95mm (1122px), faces em 650/1299/1948px e alça 10mm (118px)."""
        self.assertEqual(DPI, 300)
        self.assertEqual(MUG_CAPACITY_OZ, 11)
        self.assertEqual(MUG_CAPACITY_ML, 325)

        self.assertEqual((MUG_WIDTH_MM, MUG_HEIGHT_MM), (220.0, 95.0))
        self.assertEqual(mm_to_px(220.0, 300), 2598)
        self.assertEqual(mm_to_px(95.0, 300), 1122)
        self.assertEqual((MUG_WIDTH_PX, MUG_HEIGHT_PX), (2598, 1122))
        self.assertEqual(MUG_SIZE_PX, (2598, 1122))

        # Margem de segurança da alça: 10mm = 118px em cada extremidade
        self.assertEqual(HANDLE_MARGIN_MM, 10.0)
        self.assertEqual(mm_to_px(10.0, 300), 118)
        self.assertEqual(HANDLE_MARGIN_PX, 118)
        self.assertEqual(DEFAULT_MUG_SPEC.usable_left_x_px, 118)
        self.assertEqual(DEFAULT_MUG_SPEC.usable_right_x_px, 2598 - 118)
        self.assertEqual(DEFAULT_MUG_SPEC.usable_width_px, 2598 - 236)

        # Centros das faces úteis: Esquerda (25% = 650px), Centro (50% = 1299px), Direita (75% = 1948px)
        self.assertEqual(LEFT_FACE_CENTER_X_PX, 650)
        self.assertEqual(CENTER_FACE_CENTER_X_PX, 1299)
        self.assertEqual(RIGHT_FACE_CENTER_X_PX, 1948)
        self.assertEqual(MUG_CENTER_Y_PX, 561)

    def test_normalize_mug_mode_and_aliases(self) -> None:
        """Deve reconhecer os modos panoramic, dual_face e card_plus_text e rejeitar inválidos."""
        self.assertEqual(normalize_mug_mode("panoramic").code, "panoramic")
        self.assertEqual(normalize_mug_mode("panoramico").code, "panoramic")
        self.assertEqual(normalize_mug_mode("dual_face").code, "dual_face")
        self.assertEqual(normalize_mug_mode("dual-face").code, "dual_face")
        self.assertEqual(normalize_mug_mode("card_plus_text").code, "card_plus_text")
        self.assertEqual(normalize_mug_mode("text").code, "card_plus_text")

        with self.assertRaises(ValueError):
            normalize_mug_mode("")
        with self.assertRaises(ValueError):
            normalize_mug_mode("modo_inexistente")


class TestSublimationColorEngine(unittest.TestCase):
    """Testa o motor de compensação cromática (+18% saturação) para Epson L110 Sublimática."""

    def test_apply_sublimation_compensation_boosts_saturation_by_18_percent(self) -> None:
        """Deve aplicar exatamente ImageEnhance.Color com fator 1.18 sem estourar highlights."""
        self.assertAlmostEqual(DEFAULT_SATURATION_BOOST, 1.18)

        base_color = (190, 90, 60)
        src_img = Image.new("RGB", (120, 120), color=base_color)
        # Adiciona área de highlight branco puro (255, 255, 255) para garantir não-estouro
        for x in range(20):
            for y in range(20):
                src_img.putpixel((x, y), (255, 255, 255))

        compensated = apply_sublimation_compensation(src_img, saturation_boost=1.18)
        expected = ImageEnhance.Color(src_img).enhance(1.18)

        self.assertEqual(compensated.size, (120, 120))
        self.assertEqual(compensated.mode, "RGB")

        # O pixel colorido deve coincidir exatamente com PIL.ImageEnhance.Color(1.18)
        comp_px = compensated.getpixel((60, 60))
        exp_px = expected.getpixel((60, 60))
        self.assertEqual(comp_px, exp_px)

        # A diferença entre canal máximo e mínimo (saturação cromática) deve ter aumentado
        orig_chroma = max(base_color) - min(base_color)
        new_chroma = max(comp_px) - min(comp_px)
        self.assertGreater(new_chroma, orig_chroma)

        # Highlights brancos (255, 255, 255) permanecem intactos sem estourar
        self.assertEqual(compensated.getpixel((5, 5)), (255, 255, 255))

    def test_color_engine_preserves_rgba_and_validates_inputs(self) -> None:
        """Deve preservar canal alfa em imagens RGBA e rejeitar parâmetros inválidos."""
        rgba_img = Image.new("RGBA", (40, 40), color=(180, 70, 90, 128))
        out_rgba = apply_sublimation_compensation(rgba_img, saturation_boost=1.18)
        self.assertEqual(out_rgba.mode, "RGBA")
        self.assertEqual(out_rgba.getpixel((20, 20))[3], 128)

        with self.assertRaises(ValueError):
            apply_sublimation_compensation(rgba_img, saturation_boost=0.0)
        with self.assertRaises(ValueError):
            apply_sublimation_compensation(rgba_img, saturation_boost=-0.5)
        with self.assertRaises(TypeError):
            apply_sublimation_compensation("nao_e_imagem")  # type: ignore[arg-type]


class TestMugComposerLayoutsAndMirroring(unittest.TestCase):
    """Testa a composição dos layouts panoramic, dual_face, card_plus_text e espelhamento."""

    def setUp(self) -> None:
        self.composer = MugArtworkComposer()

    def test_compose_panoramic_positions_card_in_center_and_fills_2598x1122(self) -> None:
        """No modo panoramic, a arte deve ter 2598x1122px e a carta posicionada em X=1299px."""
        card_color = (200, 50, 50)
        card = make_test_card(card_color)

        preview_raw = self.composer.compose_panoramic(card)
        self.assertEqual(preview_raw.size, (2598, 1122))
        self.assertEqual(preview_raw.info.get("dpi"), (300, 300))

        # No centro da Face Centro (X=1299, Y=561), deve estar a cor exata da carta
        self.assertEqual(
            preview_raw.getpixel((CENTER_FACE_CENTER_X_PX, MUG_CENTER_Y_PX)),
            card_color,
        )

    def test_compose_dual_face_positions_left_and_right_faces_and_mirrors_for_transfer(self) -> None:
        """No modo dual_face, carta 1 fica em X=650 e carta 2 em X=1948; no transfer elas invertem."""
        left_color = (210, 40, 40)
        right_color = (40, 90, 210)
        card_left = make_test_card(left_color)
        card_right = make_test_card(right_color)

        # Sem compensação cromática para verificar mapeamento exato de cores e espelhamento
        preview_img, transfer_img = self.composer.compose(
            [card_left, card_right],
            mode="dual_face",
            apply_color_compensation=False,
        )

        self.assertEqual(preview_img.size, (2598, 1122))
        self.assertEqual(transfer_img.size, (2598, 1122))

        # Na prévia visual (orientação normal):
        # Face Esquerda (X=650, Y=561) -> left_color
        # Face Direita (X=1948, Y=561) -> right_color
        self.assertEqual(
            preview_img.getpixel((LEFT_FACE_CENTER_X_PX, MUG_CENTER_Y_PX)),
            left_color,
        )
        self.assertEqual(
            preview_img.getpixel((RIGHT_FACE_CENTER_X_PX, MUG_CENTER_Y_PX)),
            right_color,
        )

        # Na arte de transfer (espelhada via ImageOps.mirror):
        # O pixel (x, y) do transfer é exatamente (2598 - 1 - x, y) da prévia
        expected_mirror = ImageOps.mirror(preview_img)
        self.assertEqual(
            transfer_img.getpixel((LEFT_FACE_CENTER_X_PX, MUG_CENTER_Y_PX)),
            expected_mirror.getpixel((LEFT_FACE_CENTER_X_PX, MUG_CENTER_Y_PX)),
        )
        self.assertEqual(
            transfer_img.getpixel((LEFT_FACE_CENTER_X_PX, MUG_CENTER_Y_PX)),
            right_color,
        )
        self.assertEqual(
            transfer_img.getpixel((RIGHT_FACE_CENTER_X_PX, MUG_CENTER_Y_PX)),
            left_color,
        )

    def test_compose_dual_face_duplicates_single_card_when_only_one_given(self) -> None:
        """Se apenas 1 carta for passada para dual_face, deve duplicá-la em ambas as faces."""
        card_color = (60, 180, 90)
        single_card = make_test_card(card_color)

        preview_img, _ = self.composer.compose(
            single_card,
            mode="dual_face",
            apply_color_compensation=False,
        )
        self.assertEqual(
            preview_img.getpixel((LEFT_FACE_CENTER_X_PX, MUG_CENTER_Y_PX)),
            card_color,
        )
        self.assertEqual(
            preview_img.getpixel((RIGHT_FACE_CENTER_X_PX, MUG_CENTER_Y_PX)),
            card_color,
        )

    def test_compose_card_plus_text_renders_card_left_and_text_panel_right(self) -> None:
        """No modo card_plus_text, a carta fica na Face Esquerda (650px) e o texto na Direita (1948px)."""
        card_color = (180, 60, 140)
        card = make_test_card(card_color)

        preview_img, transfer_img = self.composer.compose(
            card,
            mode="card_plus_text",
            text="Parabéns pelo seu dia!\nEdição Especial Studio Kustom",
            apply_color_compensation=False,
        )
        self.assertEqual(preview_img.size, (2598, 1122))
        self.assertEqual(transfer_img.size, (2598, 1122))

        # Face esquerda contém a carta original
        self.assertEqual(
            preview_img.getpixel((LEFT_FACE_CENTER_X_PX, MUG_CENTER_Y_PX)),
            card_color,
        )
        # Face direita contém o painel comemorativo (cor diferente do fundo da carta)
        self.assertNotEqual(
            preview_img.getpixel((RIGHT_FACE_CENTER_X_PX, MUG_CENTER_Y_PX)),
            card_color,
        )


class TestMugArtistOrchestratorAndCLI(unittest.TestCase):
    """Testa a fachada pública create_mug_artwork, orquestrador e subcomando CLI 'mug'."""

    def test_create_mug_artwork_generates_transfer_and_preview_files_at_300_dpi(self) -> None:
        """Deve salvar o arquivo de transfer espelhado e o arquivo de prévia visual em 2598x1122."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            config = AppConfig(
                base_dir=tmp_path,
                input_dir=tmp_path / "input",
                output_dir=tmp_path / "output",
            )

            c1 = tmp_path / "carta_fogo.png"
            c2 = tmp_path / "carta_agua.png"
            make_test_card((220, 60, 40)).save(c1, format="PNG")
            make_test_card((40, 100, 220)).save(c2, format="PNG")

            transfer_path, preview_path = create_mug_artwork(
                image_or_images=[c1, c2],
                mode="dual_face",
                mirror_for_transfer=True,
                config=config,
            )

            self.assertIsNotNone(preview_path)
            assert preview_path is not None
            self.assertTrue(transfer_path.is_file())
            self.assertTrue(preview_path.is_file())

            with Image.open(transfer_path) as t_img, Image.open(preview_path) as p_img:
                self.assertEqual(t_img.size, (2598, 1122))
                self.assertEqual(p_img.size, (2598, 1122))

                # Verifica que o arquivo transfer é o espelho horizontal exato da prévia
                mirrored_p = mirror_for_sublimation(p_img)
                self.assertEqual(
                    t_img.getpixel((LEFT_FACE_CENTER_X_PX, MUG_CENTER_Y_PX)),
                    mirrored_p.getpixel((LEFT_FACE_CENTER_X_PX, MUG_CENTER_Y_PX)),
                )
                self.assertEqual(
                    t_img.getpixel((RIGHT_FACE_CENTER_X_PX, MUG_CENTER_Y_PX)),
                    mirrored_p.getpixel((RIGHT_FACE_CENTER_X_PX, MUG_CENTER_Y_PX)),
                )

    def test_orchestrator_connects_with_background_expander_when_expand_with_ai_enabled(self) -> None:
        """Quando expand_with_ai=True no modo panoramic, deve acionar expand_background(mode='caneca')."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            config = AppConfig(base_dir=tmp_path, output_dir=tmp_path / "output")

            src_card = tmp_path / "carta_vertical.png"
            make_test_card((150, 80, 200)).save(src_card, format="PNG")

            expanded_mock_path = tmp_path / "carta_vertical_expanded.png"
            Image.new("RGB", (2598, 1122), color=(150, 80, 200)).save(
                expanded_mock_path, format="PNG"
            )

            with patch(
                "tools.mug_artist.orchestrator.expand_background",
                return_value=expanded_mock_path,
            ) as mock_expand:
                transfer_path, preview_path = run_mug_artwork_orchestration(
                    image_or_images=src_card,
                    mode="panoramic",
                    mirror_for_transfer=True,
                    config=config,
                    expand_with_ai=True,
                )
                mock_expand.assert_called_once()
                self.assertTrue(transfer_path.is_file())
                self.assertIsNotNone(preview_path)

    def test_cli_mug_subcommand_and_aliases(self) -> None:
        """Deve executar 'mug' (e aliases 'caneca', 'mug-art') nos modos panoramic e dual_face."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            c1 = tmp_path / "sua_carta.png"
            c2 = tmp_path / "carta2.png"
            make_test_card((200, 90, 50)).save(c1, format="PNG")
            make_test_card((50, 160, 210)).save(c2, format="PNG")

            # 1. python cli.py mug --image output/sua_carta.png --mode panoramic --mirror
            out_pano = tmp_path / "caneca_panoramica.png"
            code1 = cli.main(
                [
                    "mug",
                    "--image",
                    str(c1),
                    "--mode",
                    "panoramic",
                    "--mirror",
                    "--output",
                    str(out_pano),
                    "--no-file-log",
                ]
            )
            self.assertEqual(code1, 0)
            self.assertTrue(out_pano.is_file())
            preview_pano = tmp_path / "caneca_panoramica_preview.png"
            self.assertTrue(preview_pano.is_file())

            with Image.open(out_pano) as img_out:
                self.assertEqual(img_out.size, (2598, 1122))

            # 2. python cli.py mug --images output/carta1.png output/carta2.png --mode dual_face --mirror
            out_dual = tmp_path / "caneca_dual.png"
            code2 = cli.main(
                [
                    "mug",
                    "--images",
                    str(c1),
                    str(c2),
                    "--mode",
                    "dual_face",
                    "--mirror",
                    "--output",
                    str(out_dual),
                    "--no-file-log",
                ]
            )
            self.assertEqual(code2, 0)
            self.assertTrue(out_dual.is_file())

            # 3. Aliases 'caneca' e 'mug-art' com card_plus_text e --no-mirror
            for alias in ("caneca", "mug-art"):
                with self.subTest(alias=alias):
                    out_alias = tmp_path / f"out_{alias}.png"
                    code_alias = cli.main(
                        [
                            alias,
                            "-i",
                            str(c1),
                            "-m",
                            "card_plus_text",
                            "--text",
                            "Feliz Aniversário!",
                            "--no-mirror",
                            "-o",
                            str(out_alias),
                            "--no-file-log",
                        ]
                    )
                    self.assertEqual(code_alias, 0)
                    self.assertTrue(out_alias.is_file())

    def test_cli_mug_returns_error_on_invalid_arguments(self) -> None:
        """Deve retornar código de erro quando faltar imagem ou o modo for inválido."""
        self.assertEqual(cli.main(["mug", "--mode", "panoramic", "--no-file-log"]), 2)
        self.assertEqual(
            cli.main(["mug", "--image", "inexistente.png", "--mode", "modo_x", "--no-file-log"]),
            2,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
