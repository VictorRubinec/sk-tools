"""Testes unitários para validação do schema CardInput, AppConfig e utilitários de carga."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.config import AppConfig, BASE_DIR, DEFAULT_CONFIG, INPUT_DIR
from core.schema import CardInput, load_cards_from_file


class TestCardInputSchema(unittest.TestCase):
    """Suíte de testes para o modelo Pydantic CardInput e AppConfig."""

    def test_valid_standard_types_and_styles(self) -> None:
        """Deve aceitar todos os tipos padrão ('Magic', 'Pokemon', 'Yu-Gi-Oh!', 'One Piece')."""
        standard_types = ["Magic", "Pokemon", "Yu-Gi-Oh!", "One Piece"]
        styles = ["Normal", "Fullart", "Alternative"]

        for card_type in standard_types:
            for style in styles:
                card = CardInput(
                    tipo=card_type,
                    estilo=style,
                    titulo="Carta de Teste",
                )
                self.assertEqual(card.tipo, card_type)
                self.assertEqual(card.estilo, style)
                self.assertEqual(card.titulo, "Carta de Teste")
                self.assertTrue(card.is_standard_type)
                self.assertIsNone(card.descricao)
                self.assertIsNone(card.texto_adicional)
                self.assertIsNone(card.cores)
                self.assertIsNone(card.imagens_referencia)

    def test_case_insensitive_normalization_for_known_types_and_styles(self) -> None:
        """Deve normalizar variações de caixa e grafia para tipos e estilos padrão."""
        card = CardInput(
            tipo="  yugioh ",
            estilo=" full art ",
            titulo="  Dragão Branco de Olhos Azuis  ",
        )
        self.assertEqual(card.tipo, "Yu-Gi-Oh!")
        self.assertEqual(card.estilo, "Fullart")
        self.assertEqual(card.titulo, "Dragão Branco de Olhos Azuis")
        self.assertTrue(card.is_standard_type)

    def test_custom_type_and_custom_style_accepted(self) -> None:
        """Deve permitir tipos de jogos e estilos customizados desde que não vazios."""
        card = CardInput(
            tipo="Flesh and Blood",
            estilo="Cold Foil Marvel",
            titulo="Prism, Sculptor of Arc Light",
            descricao="Anjo luminoso em biblioteca arcana.",
            texto_adicional="Hero - Light Illusionist",
            cores=["Luz", "Amarelo"],
        )
        self.assertEqual(card.tipo, "Flesh and Blood")
        self.assertEqual(card.estilo, "Cold Foil Marvel")
        self.assertFalse(card.is_standard_type)
        self.assertEqual(card.cores, ["Luz", "Amarelo"])
        self.assertEqual(card.cores_lista, ["Luz", "Amarelo"])

    def test_cores_accepts_string_or_list_of_strings(self) -> None:
        """Deve validar 'cores' tanto como string única quanto como lista de strings."""
        card_str = CardInput(
            tipo="Magic",
            estilo="Normal",
            titulo="Raio",
            cores="Vermelho",
        )
        self.assertEqual(card_str.cores, "Vermelho")
        self.assertEqual(card_str.cores_lista, ["Vermelho"])

        card_list = CardInput(
            tipo="Magic",
            estilo="Fullart",
            titulo="Contramágica Absoluta",
            cores=[" Azul ", " Branco "],
        )
        self.assertEqual(card_list.cores, ["Azul", "Branco"])
        self.assertEqual(card_list.cores_lista, ["Azul", "Branco"])

    def test_imagens_referencia_valid_and_invalid_paths(self) -> None:
        """Deve validar se 'imagens_referencia' contém arquivos existentes e rejeitar inexistentes."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            ref_img = Path(tmp_dir) / "ref1.png"
            ref_img.write_bytes(b"\x89PNG\r\n\x1a\n")

            card_valid = CardInput(
                tipo="Magic",
                estilo="Fullart",
                titulo="Mago com Referência",
                imagens_referencia=[str(ref_img)],
            )
            self.assertEqual(card_valid.imagens_referencia, [str(ref_img)])

            # Arquivo inexistente em disco deve falhar na validação
            with self.assertRaises(ValidationError):
                CardInput(
                    tipo="Magic",
                    estilo="Fullart",
                    titulo="Mago Inválido",
                    imagens_referencia=[str(Path(tmp_dir) / "nao_existe.png")],
                )

            # Tipos inválidos (ex: string solta ou inteiro dentro da lista) devem falhar
            with self.assertRaises(ValidationError):
                CardInput.model_validate(
                    {
                        "tipo": "Magic",
                        "estilo": "Normal",
                        "titulo": "Carta",
                        "imagens_referencia": str(ref_img),
                    }
                )
            with self.assertRaises(ValidationError):
                CardInput.model_validate(
                    {
                        "tipo": "Magic",
                        "estilo": "Normal",
                        "titulo": "Carta",
                        "imagens_referencia": [123],
                    }
                )

    def test_app_config_chrome_and_gemini_attributes(self) -> None:
        """Deve validar os novos atributos de configuração em AppConfig."""
        self.assertEqual(DEFAULT_CONFIG.gemini_url, "https://gemini.google.com/app")
        self.assertTrue(hasattr(DEFAULT_CONFIG, "chrome_user_data_dir"))
        self.assertTrue(hasattr(DEFAULT_CONFIG, "chrome_executable_path"))

        with patch.dict(
            os.environ,
            {
                "SK_CHROME_USER_DATA_DIR": "C:/ChromeProfile",
                "SK_CHROME_EXECUTABLE_PATH": "C:/Program Files/Google/Chrome/Application/chrome.exe",
                "SK_GEMINI_URL": "https://gemini.google.com/app",
            },
            clear=False,
        ):
            custom_cfg = AppConfig()
            self.assertEqual(custom_cfg.chrome_user_data_dir, Path("C:/ChromeProfile"))
            self.assertEqual(
                custom_cfg.chrome_executable_path,
                Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
            )
            self.assertEqual(custom_cfg.gemini_url, "https://gemini.google.com/app")

    def test_rejects_empty_or_whitespace_required_fields(self) -> None:
        """Deve rejeitar strings vazias ou apenas espaços em 'tipo', 'estilo' e 'titulo'."""
        invalid_payloads = [
            {"tipo": "", "estilo": "Normal", "titulo": "Carta"},
            {"tipo": "   ", "estilo": "Normal", "titulo": "Carta"},
            {"tipo": "Magic", "estilo": "", "titulo": "Carta"},
            {"tipo": "Magic", "estilo": "   ", "titulo": "Carta"},
            {"tipo": "Magic", "estilo": "Normal", "titulo": ""},
            {"tipo": "Magic", "estilo": "Normal", "titulo": "   "},
        ]
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(ValidationError):
                    CardInput.model_validate(payload)

    def test_rejects_missing_required_fields(self) -> None:
        """Deve lançar ValidationError quando campos obrigatórios forem omitidos."""
        with self.assertRaises(ValidationError):
            CardInput.model_validate({"tipo": "Magic", "estilo": "Normal"})
        with self.assertRaises(ValidationError):
            CardInput.model_validate({"tipo": "Magic", "titulo": "Carta"})
        with self.assertRaises(ValidationError):
            CardInput.model_validate({"estilo": "Normal", "titulo": "Carta"})

    def test_rejects_invalid_types_and_extra_fields(self) -> None:
        """Deve rejeitar tipos primitivos incorretos e campos não declarados no schema."""
        with self.assertRaises(ValidationError):
            CardInput.model_validate(
                {"tipo": 123, "estilo": "Normal", "titulo": "Carta"}
            )
        with self.assertRaises(ValidationError):
            CardInput.model_validate(
                {"tipo": "Magic", "estilo": "Normal", "titulo": "Carta", "cores": 999}
            )
        with self.assertRaises(ValidationError):
            CardInput.model_validate(
                {
                    "tipo": "Magic",
                    "estilo": "Normal",
                    "titulo": "Carta",
                    "cores": ["Azul", ""],
                }
            )
        with self.assertRaises(ValidationError):
            CardInput.model_validate(
                {
                    "tipo": "Magic",
                    "estilo": "Normal",
                    "titulo": "Carta",
                    "campo_inexistente": "valor",
                }
            )

    def test_load_sample_cards_file(self) -> None:
        """Deve carregar e validar o arquivo de exemplo input/sample_cards.json."""
        sample_file = INPUT_DIR / "sample_cards.json"
        self.assertTrue(sample_file.is_file(), "O arquivo sample_cards.json deve existir.")
        cards = load_cards_from_file(sample_file)
        self.assertEqual(len(cards), 4)
        self.assertTrue(all(isinstance(c, CardInput) for c in cards))
        # Verifica que o arquivo de exemplo contempla cartas com e sem imagens_referencia
        self.assertIsNotNone(cards[0].imagens_referencia)
        self.assertIsNone(cards[1].imagens_referencia)

    def test_load_single_card_json_and_error_handling(self) -> None:
        """Deve carregar JSON com objeto único e tratar arquivos inexistentes."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            single_json = Path(tmp_dir) / "single.json"
            single_json.write_text(
                '{"tipo": "Pokemon", "estilo": "Fullart", "titulo": "Pikachu"}',
                encoding="utf-8",
            )
            cards = load_cards_from_file(single_json)
            self.assertEqual(len(cards), 1)
            self.assertEqual(cards[0].titulo, "Pikachu")

            with self.assertRaises(FileNotFoundError):
                load_cards_from_file(Path(tmp_dir) / "nao_existe.json")

    def test_project_directory_structure_exists(self) -> None:
        """Verifica se toda a estrutura de diretórios exigida na Fase 1 está presente."""
        DEFAULT_CONFIG.ensure_directories()
        required_dirs = ["core", "engine", "browser", "validator", "input", "output"]
        for folder in required_dirs:
            dir_path = BASE_DIR / folder
            self.assertTrue(
                dir_path.is_dir(), f"O diretório obrigatório '{folder}/' não existe."
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
