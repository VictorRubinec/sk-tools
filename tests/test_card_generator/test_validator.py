"""Testes unitários para o validador de imagens de cartas (Fase 4 - validator/)."""

from __future__ import annotations

import io
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Tuple

from PIL import Image, ImageDraw

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.card_generator.validator import CardImageValidator, ValidationResult


def create_synthetic_image_bytes(
    width: int,
    height: int,
    monochrome_color: Tuple[int, int, int] | None = None,
) -> bytes:
    """Sintetiza uma imagem PNG em memória (rica em cores ou monocromática)."""
    if monochrome_color is not None:
        img = Image.new("RGB", (width, height), color=monochrome_color)
    else:
        img = Image.new("RGB", (width, height), color=(25, 45, 95))
        draw = ImageDraw.Draw(img)
        draw.rectangle(
            [width // 8, height // 8, (width * 7) // 8, height // 2],
            fill=(220, 140, 40),
            outline=(255, 255, 255),
        )
        draw.ellipse(
            [width // 4, height // 2, (width * 3) // 4, (height * 7) // 8],
            fill=(60, 190, 130),
        )

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


class TestCardImageValidator(unittest.TestCase):
    """Suíte de testes para CardImageValidator com imagens sintetizadas via Pillow."""

    def setUp(self) -> None:
        """Instancia o validador padrão antes de cada teste."""
        self.validator = CardImageValidator()

    def test_valid_image_passes_all_checks(self) -> None:
        """Deve aprovar uma imagem vertical 750x1050px (ratio 1.40) com riqueza cromática."""
        img_bytes = create_synthetic_image_bytes(750, 1050)
        result = self.validator.validate_image(img_bytes)

        self.assertIsInstance(result, ValidationResult)
        self.assertTrue(result.is_valid)
        self.assertEqual(result.width, 750)
        self.assertEqual(result.height, 1050)
        self.assertAlmostEqual(result.aspect_ratio, 1.40, places=2)
        self.assertEqual(result.errors, [])

    def test_rejects_insufficient_dimensions(self) -> None:
        """Deve reprovar imagens com dimensões abaixo do mínimo (ex: 200x300 px)."""
        img_bytes = create_synthetic_image_bytes(200, 300)
        result = self.validator.validate_image(img_bytes)

        self.assertFalse(result.is_valid)
        self.assertEqual(result.width, 200)
        self.assertEqual(result.height, 300)
        self.assertTrue(
            any("Dimensões insuficientes" in err for err in result.errors),
            f"Esperado erro de dimensões insuficientes em {result.errors}",
        )

    def test_rejects_horizontal_orientation(self) -> None:
        """Deve reprovar imagens com orientação horizontal (ex: 1050x750 px)."""
        img_bytes = create_synthetic_image_bytes(1050, 750)
        result = self.validator.validate_image(img_bytes)

        self.assertFalse(result.is_valid)
        self.assertEqual(result.width, 1050)
        self.assertEqual(result.height, 750)
        self.assertTrue(
            any("Orientação inválida" in err for err in result.errors),
            f"Esperado erro de orientação horizontal em {result.errors}",
        )

    def test_rejects_monochrome_black_or_white_images(self) -> None:
        """Deve reprovar imagens totalmente pretas ou totalmente brancas (monocromáticas)."""
        for label, color in [("preta", (0, 0, 0)), ("branca", (255, 255, 255))]:
            with self.subTest(color=label):
                img_bytes = create_synthetic_image_bytes(
                    750, 1050, monochrome_color=color
                )
                result = self.validator.validate_image(img_bytes)
                self.assertFalse(result.is_valid)
                self.assertTrue(
                    any("monocromática ou vazia" in err for err in result.errors),
                    f"Esperado erro de imagem monocromática ({label}) em {result.errors}",
                )

    def test_rejects_corrupted_bytes_and_validates_file_path(self) -> None:
        """Deve reprovar bytes corrompidos e aceitar caminho de arquivo válido em disco."""
        corrupted = self.validator.validate_image(b"NOT_A_VALID_PNG_FILE")
        self.assertFalse(corrupted.is_valid)
        self.assertTrue(len(corrupted.errors) > 0)

        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "valid_card.png"
            file_path.write_bytes(create_synthetic_image_bytes(750, 1050))
            valid_from_disk = self.validator.validate_image(file_path)
            self.assertTrue(valid_from_disk.is_valid)


if __name__ == "__main__":
    unittest.main(verbosity=2)
