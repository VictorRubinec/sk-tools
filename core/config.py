"""Configurações globais e diretórios base do projeto sk-tools."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

BASE_DIR: Path = Path(__file__).resolve().parent.parent
INPUT_DIR: Path = BASE_DIR / "input"
OUTPUT_DIR: Path = BASE_DIR / "output"


def _optional_path_from_env(env_var: str) -> Optional[Path]:
    """Lê uma variável de ambiente e converte para Path se não for vazia."""
    raw_value = os.getenv(env_var, "").strip()
    return Path(raw_value) if raw_value else None


@dataclass(frozen=True)
class AppConfig:
    """Configurações operacionais da aplicação."""

    base_dir: Path = field(default=BASE_DIR)
    input_dir: Path = field(default=INPUT_DIR)
    output_dir: Path = field(default=OUTPUT_DIR)
    headless: bool = field(
        default_factory=lambda: os.getenv("SK_HEADLESS", "false").lower() == "true"
    )
    timeout_ms: int = field(
        default_factory=lambda: int(os.getenv("SK_TIMEOUT_MS", "60000"))
    )
    chrome_user_data_dir: Optional[Path] = field(
        default_factory=lambda: _optional_path_from_env("SK_CHROME_USER_DATA_DIR")
    )
    chrome_executable_path: Optional[Path] = field(
        default_factory=lambda: _optional_path_from_env("SK_CHROME_EXECUTABLE_PATH")
    )
    gemini_url: str = field(
        default_factory=lambda: os.getenv(
            "SK_GEMINI_URL", "https://gemini.google.com/app"
        )
    )

    def ensure_directories(self) -> None:
        """Garante a existência dos diretórios de entrada e saída."""
        self.input_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)


DEFAULT_CONFIG = AppConfig()
