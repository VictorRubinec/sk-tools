"""Testes unitários com mocks para o módulo de automação do navegador (Fase 3 - browser/)."""

from __future__ import annotations

import base64
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.card_generator.browser import (
    GeminiBrowserError,
    GeminiClient,
    GeminiGenerationTimeoutError,
    GeminiImageNotGeneratedError,
    GeminiPromptSubmissionError,
    GeminiSessionNotAuthenticatedError,
    STABILITY_ARGS,
    generate_card_image,
    get_chrome_context,
)
from tools.card_generator.core.config import AppConfig
from tools.card_generator.core.schema import CardInput


class TestBrowserExceptions(unittest.TestCase):
    """Testa a hierarquia de exceções dedicadas do pacote browser."""

    def test_exception_inheritance(self) -> None:
        """Todas as exceções específicas devem herdar de GeminiBrowserError."""
        subclasses = [
            GeminiSessionNotAuthenticatedError,
            GeminiPromptSubmissionError,
            GeminiGenerationTimeoutError,
            GeminiImageNotGeneratedError,
        ]
        for exc_cls in subclasses:
            with self.subTest(exception=exc_cls.__name__):
                self.assertTrue(issubclass(exc_cls, GeminiBrowserError))
                instance = exc_cls("Erro de teste")
                self.assertIsInstance(instance, GeminiBrowserError)


class TestBrowserSession(unittest.TestCase):
    """Testa a inicialização do contexto persistente do Chrome."""

    def test_get_chrome_context_uses_channel_and_stability_flags(self) -> None:
        """Deve configurar launch_persistent_context com channel='chrome' e flags de estabilidade."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            profile_dir = Path(tmp_dir) / "profile"
            config = AppConfig(
                base_dir=Path(tmp_dir),
                chrome_user_data_dir=profile_dir,
                chrome_executable_path=None,
                headless=False,
            )
            mock_pw = MagicMock()
            mock_ctx = MagicMock()
            mock_pw.chromium.launch_persistent_context.return_value = mock_ctx

            ctx = get_chrome_context(config=config, playwright=mock_pw)

            self.assertEqual(ctx, mock_ctx)
            self.assertTrue(profile_dir.is_dir())
            mock_pw.chromium.launch_persistent_context.assert_called_once()
            call_kwargs = mock_pw.chromium.launch_persistent_context.call_args.kwargs
            self.assertEqual(call_kwargs["user_data_dir"], str(profile_dir))
            self.assertEqual(call_kwargs["channel"], "chrome")
            self.assertFalse(call_kwargs["headless"])
            for flag in STABILITY_ARGS:
                self.assertIn(flag, call_kwargs["args"])

    def test_get_chrome_context_with_custom_executable_and_headless(self) -> None:
        """Deve usar executable_path quando configurado em AppConfig e respeitar headless=True."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            exe_path = Path(tmp_dir) / "chrome.exe"
            config = AppConfig(
                base_dir=Path(tmp_dir),
                chrome_executable_path=exe_path,
                headless=True,
            )
            mock_pw = MagicMock()
            get_chrome_context(config=config, playwright=mock_pw)

            call_kwargs = mock_pw.chromium.launch_persistent_context.call_args.kwargs
            self.assertEqual(call_kwargs["executable_path"], str(exe_path))
            self.assertNotIn("channel", call_kwargs)
            self.assertTrue(call_kwargs["headless"])


class TestGeminiClientUnits(unittest.TestCase):
    """Testa os métodos de interação do GeminiClient utilizando mocks do Playwright."""

    def setUp(self) -> None:
        """Instancia o cliente e uma página mockada antes de cada teste."""
        self.client = GeminiClient()
        self.page = MagicMock()

    def test_check_login_status_authenticated(self) -> None:
        """Deve retornar True quando não há botão de login e a caixa de prompt está visível."""
        sign_in_loc = MagicMock()
        sign_in_loc.count.return_value = 0

        prompt_loc = MagicMock()
        prompt_loc.count.return_value = 1
        prompt_loc.first.is_visible.return_value = True

        def locator_side_effect(selector: str) -> MagicMock:
            if selector == self.client.SIGN_IN_SELECTOR:
                return sign_in_loc
            return prompt_loc

        self.page.locator.side_effect = locator_side_effect
        self.assertTrue(self.client.check_login_status(self.page))

    def test_check_login_status_unauthenticated_when_signin_visible(self) -> None:
        """Deve retornar False quando o botão 'Fazer login' estiver visível."""
        sign_in_loc = MagicMock()
        sign_in_loc.count.return_value = 1
        sign_in_loc.first.is_visible.return_value = True

        self.page.locator.return_value = sign_in_loc
        self.assertFalse(self.client.check_login_status(self.page))

    def test_upload_reference_images_success(self) -> None:
        """Deve injetar o evento de colar imagem via page.evaluate e aguardar a miniatura."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            img_path = Path(tmp_dir) / "ref.png"
            img_path.write_bytes(b"\x89PNG\r\n\x1a\n")

            thumb_loc = MagicMock()
            thumb_loc.count.return_value = 1
            thumb_loc.first.is_visible.return_value = True
            self.page.locator.return_value = thumb_loc

            self.client.upload_reference_images(self.page, [img_path])

            self.page.evaluate.assert_called_once()
            call_args = self.page.evaluate.call_args
            payload = call_args[0][1]
            self.assertEqual(len(payload), 1)
            self.assertEqual(payload[0]["name"], "ref.png")
            thumb_loc.first.wait_for.assert_called_once_with(
                state="visible", timeout=12000
            )

    def test_send_prompt_success_and_error_handling(self) -> None:
        """Deve preencher o prompt e clicar no botão de envio, ou disparar GeminiPromptSubmissionError."""
        prompt_loc = MagicMock()
        send_btn_loc = MagicMock()
        send_btn_loc.count.return_value = 1
        send_btn_loc.first.is_visible.return_value = True

        def locator_side_effect(selector: str) -> MagicMock:
            if selector == self.client.PROMPT_BOX_SELECTOR:
                return prompt_loc
            return send_btn_loc

        self.page.locator.side_effect = locator_side_effect

        self.client.send_prompt(self.page, "Gere uma carta de Magic")
        prompt_loc.first.fill.assert_called_once_with("Gere uma carta de Magic")
        send_btn_loc.first.click.assert_called_once()

        # Prompt vazio deve disparar GeminiPromptSubmissionError
        with self.assertRaises(GeminiPromptSubmissionError):
            self.client.send_prompt(self.page, "   ")

        # Falha do Playwright ao preencher deve disparar GeminiPromptSubmissionError
        prompt_loc.first.fill.side_effect = PlaywrightError("DOM detached")
        with self.assertRaises(GeminiPromptSubmissionError):
            self.client.send_prompt(self.page, "Prompt válido")

    def test_wait_for_generation_complete_success_and_timeout(self) -> None:
        """Deve aguardar o botão de parada desaparecer e converter timeout em GeminiGenerationTimeoutError."""
        stop_loc = MagicMock()
        self.page.locator.return_value = stop_loc

        self.client.wait_for_generation_complete(self.page, timeout_ms=45000)
        stop_loc.first.wait_for.assert_called_with(state="hidden", timeout=45000)

        # Simula TimeoutError na espera de ocultação do botão de parada
        stop_loc.first.wait_for.side_effect = [
            None,
            PlaywrightTimeoutError("Timeout waiting for hidden"),
        ]
        with self.assertRaises(GeminiGenerationTimeoutError):
            self.client.wait_for_generation_complete(self.page, timeout_ms=1000)

    def test_extract_latest_generated_image_success_and_missing_error(self) -> None:
        """Deve extrair os bytes da última imagem ou lançar GeminiImageNotGeneratedError se ausente."""
        expected_bytes = b"\x89PNG\r\n\x1a\nFAKE_IMAGE_DATA"
        b64_src = "data:image/png;base64," + base64.b64encode(expected_bytes).decode(
            "ascii"
        )

        img_loc = MagicMock()
        img_loc.count.return_value = 2
        img_loc.nth.return_value = img_loc.last
        img_loc.last.get_attribute.return_value = b64_src
        self.page.locator.return_value = img_loc

        extracted = self.client.extract_latest_generated_image(self.page)
        self.assertEqual(extracted, expected_bytes)

        # Caso nenhuma imagem tenha sido gerada (count == 0)
        img_loc.count.return_value = 0
        with self.assertRaises(GeminiImageNotGeneratedError):
            self.client.extract_latest_generated_image(self.page)


class TestBrowserOrchestrator(unittest.TestCase):
    """Testa o fluxo ponta a ponta do orquestrador generate_card_image com mocks."""

    @patch("tools.card_generator.browser.orchestrator.get_chrome_context")
    def test_generate_card_image_full_flow(
        self, mock_get_context: MagicMock
    ) -> None:
        """Deve orquestrar sessão, upload, prompt, espera, extração e salvamento em disco."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            ref_img = tmp_path / "ref.png"
            ref_img.write_bytes(b"\x89PNG\r\n\x1a\n")

            config = AppConfig(
                base_dir=tmp_path,
                input_dir=tmp_path / "input",
                output_dir=tmp_path / "output",
                timeout_ms=30000,
            )
            card = CardInput(
                tipo="Magic",
                estilo="Fullart",
                titulo="Dragão Ancestral",
                imagens_referencia=[str(ref_img)],
            )

            mock_context = MagicMock()
            mock_page = MagicMock()
            mock_context.pages = [mock_page]
            mock_get_context.return_value = mock_context

            mock_client = MagicMock(spec=GeminiClient)
            mock_client.check_login_status.return_value = True
            mock_client.extract_latest_generated_image.return_value = (
                b"\x89PNG\r\n\x1a\nGENERATED"
            )

            saved_path = generate_card_image(
                card=card, config=config, client=mock_client
            )

            self.assertTrue(saved_path.is_file())
            self.assertEqual(saved_path.read_bytes(), b"\x89PNG\r\n\x1a\nGENERATED")
            mock_client.check_login_status.assert_called_once_with(mock_page)
            mock_client.upload_reference_images.assert_called_once()
            mock_client.send_prompt.assert_called_once()
            mock_client.wait_for_generation_complete.assert_called_once_with(
                mock_page, timeout_ms=30000
            )
            mock_context.close.assert_called_once()

    @patch("tools.card_generator.browser.orchestrator.get_chrome_context")
    def test_generate_card_image_raises_when_not_authenticated(
        self, mock_get_context: MagicMock
    ) -> None:
        """Deve disparar GeminiSessionNotAuthenticatedError e fechar o contexto se não logado."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            config = AppConfig(
                base_dir=tmp_path,
                input_dir=tmp_path / "input",
                output_dir=tmp_path / "output",
            )
            card = CardInput(
                tipo="Pokemon",
                estilo="Normal",
                titulo="Mewtwo",
            )

            mock_context = MagicMock()
            mock_context.pages = [MagicMock()]
            mock_get_context.return_value = mock_context

            mock_client = MagicMock(spec=GeminiClient)
            mock_client.check_login_status.return_value = False

            with self.assertRaises(GeminiSessionNotAuthenticatedError):
                generate_card_image(card=card, config=config, client=mock_client)

            mock_context.close.assert_called_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)
