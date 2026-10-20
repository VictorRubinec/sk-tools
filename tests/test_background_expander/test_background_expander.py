"""Testes unitários para o módulo de expansão de fundo / outpainting (tools/background_expander/)."""

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
from tools.background_expander import (
    EXPANSION_MODES,
    BackgroundExpansionPromptBuilder,
    ExpandedImageValidator,
    calculate_bleed_pixels,
    calculate_expanded_dimensions,
    expand_background,
    normalize_expansion_mode,
    run_background_expansion_orchestration,
)
from tools.card_generator.browser.exceptions import GeminiSessionNotAuthenticatedError
from tools.card_generator.browser.gemini_client import GeminiClient
from tools.card_generator.core.config import AppConfig


def create_synthetic_expanded_bytes(
    width: int,
    height: int,
    black_border_px: int = 0,
    monochrome_color: Tuple[int, int, int] | None = None,
) -> bytes:
    """Sintetiza uma imagem PNG em memória, opcionalmente com barras pretas periféricas."""
    if monochrome_color is not None:
        img = Image.new("RGB", (width, height), color=monochrome_color)
    else:
        img = Image.new("RGB", (width, height), color=(35, 65, 115))
        draw = ImageDraw.Draw(img)
        draw.rectangle(
            [width // 6, height // 6, (width * 5) // 6, height // 2],
            fill=(235, 155, 55),
            outline=(255, 255, 255),
        )
        draw.ellipse(
            [width // 4, height // 2, (width * 3) // 4, (height * 5) // 6],
            fill=(55, 205, 145),
        )
        if black_border_px > 0:
            # Desenha barras pretas laterais (pillarboxing)
            draw.rectangle([0, 0, black_border_px, height], fill=(0, 0, 0))
            draw.rectangle(
                [width - black_border_px, 0, width, height], fill=(0, 0, 0)
            )

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestBleedAndDimensionsCalculation(unittest.TestCase):
    """Testa o cálculo rigoroso de sangria (5mm a 300 DPI = 59px) e dimensões expandidas."""

    def test_5mm_bleed_at_300_dpi_equals_59px(self) -> None:
        """5mm a 300 DPI deve corresponder exatamente a 59 pixels por borda."""
        self.assertEqual(calculate_bleed_pixels(5.0, 300), 59)
        self.assertEqual(calculate_bleed_pixels(0.0, 300), 0)

        with self.assertRaises(ValueError):
            calculate_bleed_pixels(-1.0, 300)
        with self.assertRaises(ValueError):
            calculate_bleed_pixels(5.0, 0)

    def test_calculate_expanded_dimensions_for_all_modes(self) -> None:
        """Verifica o cálculo das dimensões finais para bleed_5mm, horizontal, caneca e custom."""
        # 1. bleed_5mm em uma carta 750x1050 adiciona 59px em cada uma das 4 bordas (+118px)
        w, h, bleed = calculate_expanded_dimensions(750, 1050, mode="bleed_5mm", bleed_mm=5.0)
        self.assertEqual(bleed, 59)
        self.assertEqual(w, 750 + 118)
        self.assertEqual(h, 1050 + 118)

        # 2. horizontal e caneca devem produzir orientação estritamente horizontal (w > h)
        for mode in ["horizontal", "caneca"]:
            with self.subTest(mode=mode):
                hw, hh, hbleed = calculate_expanded_dimensions(750, 1050, mode=mode, bleed_mm=5.0)
                self.assertEqual(hbleed, 59)
                self.assertGreater(hw, hh)
                self.assertEqual(hh, 1050 + 118)

        # 3. custom com dimensões específicas
        cw, ch, cbleed = calculate_expanded_dimensions(
            750, 1050, mode="custom", bleed_mm=5.0, custom_size=(2000, 2000)
        )
        self.assertEqual((cw, ch, cbleed), (2118, 2118, 59))


class TestBackgroundExpansionPromptBuilder(unittest.TestCase):
    """Testa a geração de prompts de outpainting para todos os modos de expansão."""

    def setUp(self) -> None:
        self.builder = BackgroundExpansionPromptBuilder()

    def test_build_prompt_for_all_expansion_modes(self) -> None:
        """Deve incluir preservação do sujeito, 59px/borda, continuidade de fundo e restrições negativas."""
        for mode_code in EXPANSION_MODES:
            with self.subTest(mode=mode_code):
                prompt = self.builder.build_prompt(
                    mode=mode_code,
                    bleed_mm=5.0,
                    base_size=(750, 1050),
                )
                self.assertIn(mode_code, prompt)
                self.assertIn("59 px", prompt)
                self.assertIn("300 DPI", prompt)
                self.assertIn("não devem ser alterados", prompt.lower())
                self.assertIn("ambiente de fundo", prompt.lower())
                self.assertIn("sem barras pretas", prompt.lower())
                self.assertIn("sem cortes no personagem", prompt.lower())

    def test_build_prompt_with_preserve_frame(self) -> None:
        """Deve incluir instruções rigorosas de preservação de moldura e sangria externa."""
        prompt = self.builder.build_prompt(
            mode="bleed_5mm",
            bleed_mm=5.0,
            base_size=(1024, 1536),
            preserve_frame=True,
        )
        self.assertIn("PRESERVAÇÃO DE MOLDURA E SANGRIA EXTERNA", prompt)
        self.assertIn("moldura decorativa deve permanecer fixa", prompt.lower())
        self.assertIn("vazar e continuar organicamente para fora da moldura", prompt.lower())
        self.assertIn("não redesenhe ou estique a moldura ornamental", prompt.lower())

    def test_invalid_mode_raises_value_error(self) -> None:
        """Deve rejeitar modos de expansão desconhecidos."""
        with self.assertRaises(ValueError):
            normalize_expansion_mode("modo_invalido")


class TestExpandedImageValidator(unittest.TestCase):
    """Testa a validação dimensional e detecção de barras pretas em imagens expandidas."""

    def setUp(self) -> None:
        self.validator = ExpandedImageValidator()

    def test_approves_valid_expanded_image_with_5mm_bleed(self) -> None:
        """Deve aprovar imagem sem barras pretas e com as dimensões exatas (750+118 x 1050+118)."""
        valid_bytes = create_synthetic_expanded_bytes(868, 1168)
        result = self.validator.validate_expanded_image(
            valid_bytes, base_size=(750, 1050), mode="bleed_5mm", bleed_mm=5.0
        )
        self.assertTrue(result.is_valid, f"Erros inesperados: {result.errors}")
        self.assertFalse(result.has_black_borders)
        self.assertEqual(result.bleed_px, 59)
        self.assertEqual((result.width, result.height), (868, 1168))

    def test_rejects_image_with_black_borders(self) -> None:
        """Deve detectar e reprovar imagens que contenham barras pretas periféricas (pillarbox)."""
        bordered_bytes = create_synthetic_expanded_bytes(868, 1168, black_border_px=40)
        result = self.validator.validate_expanded_image(
            bordered_bytes, base_size=(750, 1050), mode="bleed_5mm", bleed_mm=5.0
        )
        self.assertFalse(result.is_valid)
        self.assertTrue(result.has_black_borders)
        self.assertTrue(any("Barras pretas" in err for err in result.errors))

    def test_rejects_insufficient_dimensions_and_wrong_orientation(self) -> None:
        """Deve reprovar imagem menor que a sangria exigida ou vertical no modo horizontal."""
        small_bytes = create_synthetic_expanded_bytes(750, 1050)
        res_small = self.validator.validate_expanded_image(
            small_bytes, base_size=(750, 1050), mode="bleed_5mm", bleed_mm=5.0
        )
        self.assertFalse(res_small.is_valid)
        self.assertTrue(any("Dimensões insuficientes" in err for err in res_small.errors))

        vertical_bytes = create_synthetic_expanded_bytes(868, 1168)
        res_horiz = self.validator.validate_expanded_image(
            vertical_bytes, base_size=(750, 1050), mode="horizontal", bleed_mm=5.0
        )
        self.assertFalse(res_horiz.is_valid)
        self.assertTrue(any("Orientação incompatível" in err for err in res_horiz.errors))

    def test_conform_expanded_image_trims_black_bars_and_fits_target(self) -> None:
        """Deve remover barras pretas e ajustar a imagem para as dimensões exatas com sangria."""
        raw_with_bars = create_synthetic_expanded_bytes(1000, 1300, black_border_px=50)
        conformed = self.validator.conform_expanded_image(
            raw_with_bars, base_size=(750, 1050), mode="bleed_5mm", bleed_mm=5.0
        )
        res = self.validator.validate_expanded_image(
            conformed, base_size=(750, 1050), mode="bleed_5mm", bleed_mm=5.0
        )
        self.assertTrue(res.is_valid)
        self.assertFalse(res.has_black_borders)
        self.assertEqual((res.width, res.height), (868, 1168))


class TestBackgroundExpanderOrchestratorAndCLI(unittest.TestCase):
    """Testa o orquestrador de outpainting com mocks e o subcomando 'expand' na CLI."""

    @patch("tools.background_expander.orchestrator.get_chrome_context")
    def test_run_background_expansion_orchestration_full_flow(
        self, mock_get_context: MagicMock
    ) -> None:
        """Deve conectar ao Gemini, enviar imagem e prompt de outpainting, baixar e salvar _expanded.png."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            src_card = tmp_path / "charizard_vmax.png"
            src_card.write_bytes(create_synthetic_expanded_bytes(750, 1050))

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
            mock_client.extract_latest_generated_image.return_value = (
                create_synthetic_expanded_bytes(900, 1200)
            )

            out_path = run_background_expansion_orchestration(
                image_path=src_card,
                mode="bleed_5mm",
                bleed_mm=5.0,
                config=config,
                client=mock_client,
                max_retries=2,
            )

            self.assertTrue(out_path.is_file())
            self.assertEqual(out_path.name, "charizard_vmax_expanded.png")

            validator = ExpandedImageValidator()
            val = validator.validate_expanded_image(
                out_path, base_size=(750, 1050), mode="bleed_5mm", bleed_mm=5.0
            )
            self.assertTrue(val.is_valid)
            self.assertEqual((val.width, val.height), (868, 1168))

            mock_client.upload_reference_images.assert_called_once_with(
                mock_page, [src_card.resolve()]
            )
            mock_client.submit_prompt.assert_called_once_with(mock_page)
            mock_context.close.assert_called_once()

    @patch("tools.background_expander.orchestrator.get_chrome_context")
    def test_orchestrator_raises_when_not_authenticated(
        self, mock_get_context: MagicMock
    ) -> None:
        """Deve disparar GeminiSessionNotAuthenticatedError quando a sessão não estiver logada."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            src_card = tmp_path / "card.png"
            src_card.write_bytes(create_synthetic_expanded_bytes(750, 1050))

            config = AppConfig(base_dir=tmp_path, output_dir=tmp_path / "output")
            mock_context = MagicMock()
            mock_context.pages = [MagicMock()]
            mock_get_context.return_value = mock_context

            mock_client = MagicMock(spec=GeminiClient)
            mock_client.check_login_status.return_value = False

            with self.assertRaises(GeminiSessionNotAuthenticatedError):
                run_background_expansion_orchestration(
                    image_path=src_card,
                    mode="bleed_5mm",
                    config=config,
                    client=mock_client,
                )
            mock_context.close.assert_called_once()

    def test_cli_expand_subcommand_and_aliases(self) -> None:
        """Deve aceitar o subcomando 'expand' e seus aliases 'outpaint' e 'bg' na CLI."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            src_card = tmp_path / "sua_carta.png"
            src_card.write_bytes(create_synthetic_expanded_bytes(750, 1050))
            expected_out = tmp_path / "sua_carta_expanded.png"

            with patch(
                "cli.expand_background", return_value=expected_out
            ) as mock_expand:
                for cmd in ["expand", "outpaint", "bg"]:
                    with self.subTest(command=cmd):
                        exit_code = cli.main(
                            [
                                cmd,
                                "--image",
                                str(src_card),
                                "--mode",
                                "bleed_5mm",
                                "--bleed",
                                "5.0",
                                "--no-file-log",
                                "--headless",
                            ]
                        )
                        self.assertEqual(exit_code, 0)
                self.assertEqual(mock_expand.call_count, 3)

            with patch(
                "tools.background_expander.api.run_background_expansion_orchestration",
                return_value=expected_out,
            ) as mock_orch:
                res_path = expand_background(src_card, mode="caneca", bleed_mm=5.0)
                self.assertEqual(res_path, expected_out)
                mock_orch.assert_called_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)
