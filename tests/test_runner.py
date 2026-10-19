"""Testes unitários para o motor de retentativas (core/runner.py) e CLI (cli.py)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import cli
from browser.exceptions import GeminiImageNotGeneratedError
from core.config import AppConfig
from core.runner import CardGenerationRunner
from core.schema import CardInput
from tests.test_validator import create_synthetic_image_bytes


class TestCardGenerationRunner(unittest.TestCase):
    """Suíte de testes para CardGenerationRunner cobrindo retentativas e validação."""

    def setUp(self) -> None:
        """Prepara carta de exemplo para os testes."""
        self.sample_card = CardInput(
            tipo="Magic",
            estilo="Fullart",
            titulo="Fênix Solar",
            descricao="Ave de fogo renascendo das cinzas.",
            cores="Vermelho",
        )

    def test_success_on_first_attempt(self) -> None:
        """Deve aprovar na 1ª tentativa quando a imagem gerada é válida."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            config = AppConfig(base_dir=tmp_path, output_dir=tmp_path)
            call_count = 0

            def fake_generator(card: CardInput, config: AppConfig) -> Path:
                nonlocal call_count
                call_count += 1
                out_file = config.output_dir / "card_ok.png"
                out_file.write_bytes(create_synthetic_image_bytes(750, 1050))
                return out_file

            runner = CardGenerationRunner(generator_fn=fake_generator)
            ok, path, validation = runner.process_card(
                self.sample_card, config=config, max_retries=3
            )

            self.assertTrue(ok)
            self.assertEqual(call_count, 1)
            self.assertIsNotNone(path)
            self.assertTrue(path.is_file())  # type: ignore[union-attr]
            self.assertIsNotNone(validation)
            self.assertTrue(validation.is_valid)  # type: ignore[union-attr]

    def test_success_after_one_validation_failure_retry(self) -> None:
        """Deve apagar a imagem inválida da 1ª tentativa, reforçar o prompt e aprovar na 2ª."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            config = AppConfig(base_dir=tmp_path, output_dir=tmp_path)
            received_cards: list[CardInput] = []

            def fake_generator(card: CardInput, config: AppConfig) -> Path:
                received_cards.append(card)
                attempt_num = len(received_cards)
                out_file = config.output_dir / f"attempt_{attempt_num}.png"
                if attempt_num == 1:
                    # 1ª tentativa gera imagem pequena inválida (200x300)
                    out_file.write_bytes(create_synthetic_image_bytes(200, 300))
                else:
                    # 2ª tentativa gera imagem válida (750x1050)
                    out_file.write_bytes(create_synthetic_image_bytes(750, 1050))
                return out_file

            runner = CardGenerationRunner(generator_fn=fake_generator)
            ok, path, validation = runner.process_card(
                self.sample_card, config=config, max_retries=3
            )

            self.assertTrue(ok)
            self.assertEqual(len(received_cards), 2)
            # O arquivo inválido da tentativa 1 deve ter sido apagado do disco
            self.assertFalse((tmp_path / "attempt_1.png").exists())
            self.assertTrue((tmp_path / "attempt_2.png").is_file())
            self.assertEqual(path, tmp_path / "attempt_2.png")
            self.assertIn("REFORÇO DE QUALIDADE", received_cards[1].descricao or "")
            self.assertIsNotNone(validation)
            self.assertTrue(validation.is_valid)  # type: ignore[union-attr]

    def test_success_after_browser_exception_retry(self) -> None:
        """Deve capturar GeminiImageNotGeneratedError na 1ª tentativa e ter sucesso na 2ª."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            config = AppConfig(base_dir=tmp_path, output_dir=tmp_path)
            attempts = 0

            def fake_generator(card: CardInput, config: AppConfig) -> Path:
                nonlocal attempts
                attempts += 1
                if attempts == 1:
                    raise GeminiImageNotGeneratedError("Nenhuma imagem retornada.")
                out_file = config.output_dir / "recovered.png"
                out_file.write_bytes(create_synthetic_image_bytes(750, 1050))
                return out_file

            runner = CardGenerationRunner(generator_fn=fake_generator)
            ok, path, _ = runner.process_card(
                self.sample_card, config=config, max_retries=3
            )

            self.assertTrue(ok)
            self.assertEqual(attempts, 2)
            self.assertIsNotNone(path)

    def test_exhausts_max_retries_when_validation_fails_repeatedly(self) -> None:
        """Deve retornar (False, None, validation) quando todas as tentativas falharem."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            config = AppConfig(base_dir=tmp_path, output_dir=tmp_path)
            attempts = 0

            def fake_generator(card: CardInput, config: AppConfig) -> Path:
                nonlocal attempts
                attempts += 1
                out_file = config.output_dir / f"bad_{attempts}.png"
                # Sempre gera imagem monocromática preta inválida
                out_file.write_bytes(
                    create_synthetic_image_bytes(750, 1050, monochrome_color=(0, 0, 0))
                )
                return out_file

            runner = CardGenerationRunner(generator_fn=fake_generator)
            ok, path, validation = runner.process_card(
                self.sample_card, config=config, max_retries=3
            )

            self.assertFalse(ok)
            self.assertIsNone(path)
            self.assertEqual(attempts, 3)
            self.assertIsNotNone(validation)
            self.assertFalse(validation.is_valid)  # type: ignore[union-attr]
            # Nenhum arquivo inválido deve restar no diretório
            for idx in range(1, 4):
                self.assertFalse((tmp_path / f"bad_{idx}.png").exists())

    def test_process_batch_statistics_and_cli_execution(self) -> None:
        """Deve consolidar estatísticas no process_batch e validar a CLI com --card."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            config = AppConfig(base_dir=tmp_path, output_dir=tmp_path)

            def fake_generator(card: CardInput, config: AppConfig) -> Path:
                out_file = config.output_dir / f"{card.titulo}.png"
                out_file.write_bytes(create_synthetic_image_bytes(750, 1050))
                return out_file

            runner = CardGenerationRunner(generator_fn=fake_generator)
            cards = [
                self.sample_card,
                CardInput(tipo="Pokemon", estilo="Normal", titulo="Pikachu"),
            ]
            summary = runner.process_batch(cards, config=config, max_retries=2)
            self.assertEqual(summary["total"], 2)
            self.assertEqual(summary["succeeded"], 2)
            self.assertEqual(summary["failed"], 0)
            self.assertEqual(len(summary["results"]), 2)

            # Testa invocação da CLI com --card mockando o CardGenerationRunner.process_card
            inline_json = json.dumps(
                {"tipo": "One Piece", "estilo": "Fullart", "titulo": "Shanks"}
            )
            valid_result = runner.validator.validate_image(
                create_synthetic_image_bytes(750, 1050)
            )
            with patch.object(
                CardGenerationRunner,
                "process_card",
                return_value=(True, tmp_path / "shanks.png", valid_result),
            ):
                exit_code = cli.main(["--card", inline_json, "--retries", "2", "--headless"])
                self.assertEqual(exit_code, 0)

    def test_cli_logging_options(self) -> None:
        """Verifica se os argumentos --log-level e --no-file-log são aceitos corretamente pela CLI."""
        inline_json = json.dumps(
            {"tipo": "Pokemon", "estilo": "Normal", "titulo": "Bulbasaur"}
        )
        runner = CardGenerationRunner()
        valid_result = runner.validator.validate_image(
            create_synthetic_image_bytes(750, 1050)
        )
        with patch.object(
            CardGenerationRunner,
            "process_card",
            return_value=(True, Path("dummy.png"), valid_result),
        ):
            exit_code = cli.main([
                "--card", inline_json,
                "--retries", "1",
                "--log-level", "DEBUG",
                "--no-file-log",
                "--headless",
            ])
            self.assertEqual(exit_code, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
