"""Exceções dedicadas para o módulo de automação web do Google Gemini."""

from __future__ import annotations


class GeminiBrowserError(Exception):
    """Exceção base para todos os erros de automação do navegador no Gemini."""


class GeminiSessionNotAuthenticatedError(GeminiBrowserError):
    """Disparada quando a sessão do navegador não está autenticada no Google Gemini."""


class GeminiPromptSubmissionError(GeminiBrowserError):
    """Disparada quando ocorre falha ao preencher ou submeter o prompt na interface."""


class GeminiGenerationTimeoutError(GeminiBrowserError):
    """Disparada quando o tempo limite é excedido aguardando a geração pela IA."""


class GeminiImageNotGeneratedError(GeminiBrowserError):
    """Disparada quando a resposta da IA termina sem conter uma imagem gerada."""
