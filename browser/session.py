"""Gerenciador de sessão e perfil persistente do navegador com Playwright."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from playwright.sync_api import BrowserContext, Playwright, sync_playwright

from core.config import AppConfig, DEFAULT_CONFIG

DEFAULT_VIEWPORT: Dict[str, int] = {"width": 1440, "height": 900}
STABILITY_ARGS: List[str] = [
    "--disable-blink-features=AutomationControlled",
    "--start-maximized",
]


def resolve_user_data_dir(config: AppConfig) -> Path:
    """Resolve e garante a existência do diretório de perfil persistente do Chrome."""
    profile_dir = (
        config.chrome_user_data_dir
        if config.chrome_user_data_dir is not None
        else (config.base_dir / ".chrome_profile")
    )
    profile_dir.mkdir(parents=True, exist_ok=True)
    return profile_dir


def get_chrome_context(
    config: AppConfig = DEFAULT_CONFIG,
    playwright: Optional[Playwright] = None,
) -> BrowserContext:
    """Inicia e retorna um contexto persistente do Chromium/Chrome configurado.

    Args:
        config: Instância de `AppConfig` contendo parâmetros de execução.
        playwright: Instância opcional do Playwright já iniciada. Caso omitida,
            `sync_playwright().start()` será invocado e encerrado junto ao contexto.

    Returns:
        `BrowserContext` persistente pronto para navegação.
    """
    owns_playwright = playwright is None
    pw_instance: Playwright = (
        sync_playwright().start() if owns_playwright else playwright  # type: ignore[assignment]
    )

    user_data_dir = resolve_user_data_dir(config)

    launch_kwargs: Dict[str, Any] = {
        "user_data_dir": str(user_data_dir),
        "headless": config.headless,
        "args": list(STABILITY_ARGS),
    }

    if config.headless:
        launch_kwargs["viewport"] = dict(DEFAULT_VIEWPORT)
    else:
        launch_kwargs["no_viewport"] = True

    if config.chrome_executable_path is not None:
        launch_kwargs["executable_path"] = str(config.chrome_executable_path)
    else:
        launch_kwargs["channel"] = "chrome"

    try:
        context = pw_instance.chromium.launch_persistent_context(**launch_kwargs)
    except Exception:
        if owns_playwright:
            pw_instance.stop()
        raise

    if owns_playwright:
        original_close = context.close

        def _close_with_playwright(*args: Any, **kwargs: Any) -> None:
            try:
                original_close(*args, **kwargs)
            finally:
                pw_instance.stop()

        try:
            setattr(context, "close", _close_with_playwright)
        except Exception:
            pass

    return context
