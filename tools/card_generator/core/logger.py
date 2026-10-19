"""Configuração centralizada de logging e auditoria com Loguru."""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

from tools.card_generator.core.config import BASE_DIR, OUTPUT_DIR

LOGS_DIR: Path = OUTPUT_DIR / "logs"
LOG_FILE_PATH: Path = LOGS_DIR / "sk_tools_{time:YYYY-MM-DD}.log"


def setup_logger(
    console_level: str = "INFO",
    file_level: str = "DEBUG",
    log_to_file: bool = True,
) -> None:
    """Configura sinks do Loguru para terminal e arquivo de auditoria.

    Args:
        console_level: Nível mínimo de log para o console (ex: 'DEBUG', 'INFO').
        file_level: Nível mínimo de log gravado em arquivo (ex: 'DEBUG').
        log_to_file: Se `True`, ativa gravação rotativa no diretório de logs.
    """
    # Remove configurações padrão para evitar duplicação
    logger.remove()

    # Formato moderno e legível para o console
    console_format = (
        "<green>{time:HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
    )

    # 1. Sink de Console (Terminal)
    logger.add(
        sys.stderr,
        format=console_format,
        level=console_level,
        colorize=True,
        backtrace=True,
        diagnose=True,
    )

    # 2. Sink de Arquivo (Persistência e Auditoria)
    if log_to_file:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        file_format = (
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
            "{process.name}:{thread.name} | {name}:{function}:{line} - {message}"
        )
        logger.add(
            str(LOG_FILE_PATH),
            format=file_format,
            level=file_level,
            rotation="10 MB",
            retention="14 days",
            compression="zip",
            encoding="utf-8",
            enqueue=True,  # Thread-safe e multiprocesso
            backtrace=True,
            diagnose=True,
        )


# Inicializa automaticamente com os valores padrão
setup_logger()

__all__ = ["logger", "setup_logger", "LOGS_DIR", "BASE_DIR"]
