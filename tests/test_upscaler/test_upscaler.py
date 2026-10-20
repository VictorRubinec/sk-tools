"""Testes unitários para o módulo de upscaling de posters 300 DPI (tools/upscaler/)."""

from __future__ import annotations

import io
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Tuple
from unittest.mock import MagicMock, patch

from PIL import Image, ImageDraw

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import cli
from tools.card_generator.browser.exceptions import (
    GeminiImageNotGeneratedError,
    GeminiSessionNotAuthenticatedError,
)
from tools.card_generator.browser.gemini_client import GeminiClient
from tools.card_generator.core.config import AppConfig
from tools.upscaler import (
    POSTER_FORMATS,
    PosterImageValidator,
    UpscalePromptBuilder,
    normalize_target_format,
    run_upscale_orchestration,
    upscale_card_to_poster,
)


def create_synthetic_poster_bytes(
    width: int,
    height: int,
    monochrome_color: Tuple[int, int, int] | None = None,
) -> bytes:
    """Sintetiza uma imagem PNG em memória nas dimensões especificadas."""
    if monochrome_color is not None:
        img = Image.new("RGB", (width, height), color=monochrome_color)
    else:
        img = Image.new("RGB", (width, height), color=(30, 50, 100))
        draw = ImageDraw.Draw(img)
        draw.rectangle(
            [width // 10, height // 10, (width * 9) // 10, height // 2],
            fill=(230, 150, 50),
            outline=(255, 255, 255),
        )
        draw.ellipse(
            [width // 4, height // 2, (width * 3) // 4, (height * 9) // 10],
            fill=(50, 200, 140),
        )
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestStudioKustomPosterSpecs(unittest.TestCase):
    """Verifica os parâmetros físicos rigorosos de 300 DPI da Studio Kustom."""

    def test_all_four_formats_dimensions_and_ratios(self) -> None:
        """Deve validar exatamente os mm, pixels e aspect ratios de A4_V, A4_H, A3_V e A3_H."""
        expected = {
            "A4_V": (210, 300, 2480, 3543, 1.429, "vertical"),
            "A4_H": (300, 210, 3543, 2480, 0.700, "horizontal"),
            "A3_V": (300, 420, 3543, 4960, 1.400, "vertical"),
            "A3_H": (420, 300, 4960, 3543, 0.714, "horizontal"),
        }
        for code, (w_mm, h_mm, w_px, h_px, ratio, orient) in expected.items():
            with self.subTest(format=code):
                spec = normalize_target_format(code.lower())
                self.assertEqual(spec.code, code)
                self.assertEqual(spec.width_mm, w_mm)
                self.assertEqual(spec.height_mm, h_mm)
                self.assertEqual(spec.width_px, w_px)
                self.assertEqual(spec.height_px, h_px)
                self.assertEqual(spec.orientation, orient)
                self.assertEqual(spec.dpi, 300)
                self.assertAlmostEqual(spec.aspect_ratio, ratio, places=2)

    def test_invalid_target_format_raises_value_error(self) -> None:
        """Deve rejeitar formatos desconhecidos ou vazios."""
        with self.assertRaises(ValueError):
            normalize_target_format("")
        with self.assertRaises(ValueError):
            normalize_target_format("a5_v")


class TestUpscalePromptBuilder(unittest.TestCase):
    """Testa a construção de prompts de redraw e super-resolução."""

    def setUp(self) -> None:
        self.builder = UpscalePromptBuilder()

    def test_build_prompt_for_each_format(self) -> None:
        """Deve incluir preservação de fisionomia, traços nítidos, 300 DPI e dimensões do formato."""
        for code, spec in POSTER_FORMATS.items():
            with self.subTest(format=code):
                prompt = self.builder.build_prompt(code.lower())
                self.assertIn(spec.code, prompt)
                self.assertIn(f"{spec.width_px}x{spec.height_px}", prompt)
                self.assertIn("300 DPI", prompt)
                self.assertIn("fisionomia", prompt.lower())
                self.assertIn("traços nítidos", prompt.lower())
                self.assertIn("ruídos digitais", prompt.lower())
                self.assertIn("pillarbox", prompt.lower())
                self.assertIn("letterbox", prompt.lower())

    def test_build_prompt_with_extra_instructions(self) -> None:
        """Deve anexar instruções complementares quando fornecidas."""
        prompt = self.builder.build_prompt(
            "a3_h", extra_instructions="Mantenha a iluminação dourada no fundo."
        )
        self.assertIn("Mantenha a iluminação dourada no fundo.", prompt)
        self.assertIn("4960x3543", prompt)


class TestPosterImageValidator(unittest.TestCase):
    """Testa o validador de posters 300 DPI com imagens sintetizadas via Pillow."""

    def setUp(self) -> None:
        self.validator = PosterImageValidator()

    def test_validates_exact_300dpi_posters(self) -> None:
        """Deve aprovar posters que atingem a resolução e orientação de cada formato."""
        for code, spec in POSTER_FORMATS.items():
            with self.subTest(format=code):
                poster_bytes = create_synthetic_poster_bytes(
                    spec.width_px, spec.height_px
                )
                res = self.validator.validate_poster(poster_bytes, code)
                self.assertTrue(res.is_valid, f"Erros inesperados em {code}: {res.errors}")
                self.assertEqual(res.width, spec.width_px)
                self.assertEqual(res.height, spec.height_px)

    def test_rejects_wrong_orientation_and_low_resolution(self) -> None:
        """Deve reprovar poster horizontal quando solicitado A4_V e reprovar baixa resolução."""
        # Orientação invertida (horizontal enviada para A4_V)
        inverted_bytes = create_synthetic_poster_bytes(3543, 2480)
        res_inv = self.validator.validate_poster(inverted_bytes, "a4_v")
        self.assertFalse(res_inv.is_valid)
        self.assertTrue(any("Orientação incompatível" in e for e in res_inv.errors))

        # Resolução insuficiente para A3_V (ex: 750x1050 quando exige 3543x4960)
        low_res_bytes = create_synthetic_poster_bytes(750, 1050)
        res_low = self.validator.validate_poster(low_res_bytes, "a3_v")
        self.assertFalse(res_low.is_valid)
        self.assertTrue(any("Resolução insuficiente" in e for e in res_low.errors))

    def test_conform_to_poster_spec_scales_valid_image_to_300dpi(self) -> None:
        """Deve escalonar imagem válida gerada pelo Gemini (ex: 1000x1400) para 2480x3543 (A4_V)."""
        raw_gemini_img = create_synthetic_poster_bytes(1000, 1400)
        conformed = self.validator.conform_to_poster_spec(raw_gemini_img, "a4_v")
        res = self.validator.validate_poster(conformed, "a4_v")
        self.assertTrue(res.is_valid)
        self.assertEqual((res.width, res.height), (2480, 3543))

    def test_trim_black_borders_removes_pillarboxing_and_letterboxing(self) -> None:
        """Deve detectar e remover barras pretas artificiais simuladas nas laterais."""
        # Imagem 1000x1400 com 50px de barra preta à esquerda e 50px à direita
        base_img = Image.new("RGB", (900, 1400), color=(180, 100, 50))
        letterboxed = Image.new("RGB", (1000, 1400), color=(0, 0, 0))
        letterboxed.paste(base_img, (50, 0))

        trimmed = PosterImageValidator.trim_black_borders(letterboxed, threshold=20)
        self.assertEqual(trimmed.size, (900, 1400))

    def test_conform_to_poster_spec_removes_black_bars_and_covers_target(self) -> None:
        """Deve eliminar barras pretas e preencher a área do poster sem faixas pretas residuais."""
        # Cria imagem com barras pretas nas bordas
        inner_img = Image.new("RGB", (800, 1200), color=(200, 120, 40))
        draw = ImageDraw.Draw(inner_img)
        draw.ellipse([200, 200, 600, 1000], fill=(50, 200, 100))

        bar_img = Image.new("RGB", (900, 1200), color=(0, 0, 0))
        bar_img.paste(inner_img, (50, 0))
        buf = io.BytesIO()
        bar_img.save(buf, format="PNG")

        conformed = self.validator.conform_to_poster_spec(buf.getvalue(), "a4_v")
        res = self.validator.validate_poster(conformed, "a4_v")
        self.assertTrue(res.is_valid)
        self.assertEqual((res.width, res.height), (2480, 3543))

        # Confirma que os cantos e margens externas do poster conformed não são pretos
        with Image.open(io.BytesIO(conformed)) as out_img:
            # Colunas da extrema esquerda e direita devem ter cor do conteúdo (não preto)
            left_pixel = out_img.getpixel((0, out_img.height // 2))
            right_pixel = out_img.getpixel((out_img.width - 1, out_img.height // 2))
            self.assertGreater(sum(left_pixel), 60)
            self.assertGreater(sum(right_pixel), 60)


class TestUpscalerOrchestratorAndCLI(unittest.TestCase):
    """Testa o fluxo orquestrado de upscaling com mocks do Gemini e integração na CLI."""

    @patch("tools.upscaler.orchestrator.get_chrome_context")
    def test_upscale_card_to_poster_full_flow(
        self, mock_get_context: MagicMock
    ) -> None:
        """Deve enviar a carta anexa ao Gemini, baixar o poster e salvar em 300 DPI no output/."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            src_card = tmp_path / "luffy_gear5.png"
            src_card.write_bytes(create_synthetic_poster_bytes(750, 1050))

            config = AppConfig(
                base_dir=tmp_path,
                input_dir=tmp_path / "input",
                output_dir=tmp_path / "output",
            )

            mock_context = MagicMock()
            mock_page = MagicMock()
            mock_context.pages = [mock_page]
            mock_get_context.return_value = mock_context

            mock_client = MagicMock(spec=GeminiClient)
            mock_client.check_login_status.return_value = True
            # Simula o Gemini retornando uma imagem vertical de alta definição
            mock_client.extract_latest_generated_image.return_value = (
                create_synthetic_poster_bytes(1400, 2000)
            )

            poster_path = run_upscale_orchestration(
                image_path=src_card,
                target_format="a4_v",
                config=config,
                client=mock_client,
                max_retries=2,
            )

            self.assertTrue(poster_path.is_file())
            self.assertEqual(poster_path.name, "luffy_gear5_poster_a4_v.png")

            validator = PosterImageValidator()
            val_res = validator.validate_poster(poster_path, "a4_v")
            self.assertTrue(val_res.is_valid)
            self.assertEqual((val_res.width, val_res.height), (2480, 3543))

            mock_client.upload_reference_images.assert_called_once_with(
                mock_page, [src_card.resolve()]
            )
            mock_client.submit_prompt.assert_called_once_with(mock_page)
            mock_context.close.assert_called_once()

    @patch("tools.upscaler.orchestrator.get_chrome_context")
    def test_upscale_raises_when_not_authenticated(
        self, mock_get_context: MagicMock
    ) -> None:
        """Deve lançar GeminiSessionNotAuthenticatedError quando a sessão não estiver logada."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            src_card = tmp_path / "card.png"
            src_card.write_bytes(create_synthetic_poster_bytes(750, 1050))

            config = AppConfig(base_dir=tmp_path, output_dir=tmp_path / "output")
            mock_context = MagicMock()
            mock_context.pages = [MagicMock()]
            mock_get_context.return_value = mock_context

            mock_client = MagicMock(spec=GeminiClient)
            mock_client.check_login_status.return_value = False

            with self.assertRaises(GeminiSessionNotAuthenticatedError):
                run_upscale_orchestration(
                    image_path=src_card,
                    target_format="a3_v",
                    config=config,
                    client=mock_client,
                )
            mock_context.close.assert_called_once()

    def test_cli_upscale_subcommand_and_aliases(self) -> None:
        """Deve aceitar o subcomando 'upscale' e seus aliases 'poster' e 'up' na CLI."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            src_card = tmp_path / "carta_original.png"
            src_card.write_bytes(create_synthetic_poster_bytes(750, 1050))
            expected_out = tmp_path / "carta_original_poster_a4_v.png"

            with patch(
                "cli.upscale_card_to_poster", return_value=expected_out
            ) as mock_upscale:
                for cmd in ["upscale", "poster", "up"]:
                    with self.subTest(command=cmd):
                        exit_code = cli.main(
                            [
                                cmd,
                                "--image",
                                str(src_card),
                                "--target",
                                "a4_v",
                                "--no-file-log",
                                "--headless",
                            ]
                        )
                        self.assertEqual(exit_code, 0)
                self.assertEqual(mock_upscale.call_count, 3)

            # Testa invocação direta da fachada upscale_card_to_poster
            with patch(
                "tools.upscaler.api.run_upscale_orchestration",
                return_value=expected_out,
            ) as mock_orch:
                res_path = upscale_card_to_poster(src_card, "a3_h")
                self.assertEqual(res_path, expected_out)
                mock_orch.assert_called_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)
