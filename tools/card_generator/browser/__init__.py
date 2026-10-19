"""Pacote browser responsável pela automação web com Playwright."""

from tools.card_generator.browser.exceptions import (
    GeminiBrowserError,
    GeminiGenerationTimeoutError,
    GeminiImageNotGeneratedError,
    GeminiPromptSubmissionError,
    GeminiSessionNotAuthenticatedError,
)
from tools.card_generator.browser.gemini_client import GeminiClient
from tools.card_generator.browser.orchestrator import generate_card_image
from tools.card_generator.browser.session import (
    DEFAULT_VIEWPORT,
    STABILITY_ARGS,
    get_chrome_context,
    resolve_user_data_dir,
)

__all__ = [
    "DEFAULT_VIEWPORT",
    "GeminiBrowserError",
    "GeminiClient",
    "GeminiGenerationTimeoutError",
    "GeminiImageNotGeneratedError",
    "GeminiPromptSubmissionError",
    "GeminiSessionNotAuthenticatedError",
    "STABILITY_ARGS",
    "generate_card_image",
    "get_chrome_context",
    "resolve_user_data_dir",
]
