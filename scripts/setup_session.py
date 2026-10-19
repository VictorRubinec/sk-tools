"""Script utilitário para inicialização e autenticação manual da sessão do Google Gemini."""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from browser.gemini_client import GeminiClient
from browser.session import get_chrome_context, resolve_user_data_dir
from core.config import AppConfig, DEFAULT_CONFIG


def setup_interactive_session(config: AppConfig = DEFAULT_CONFIG) -> bool:
    """Abre o navegador em modo gráfico (headless=False) para login manual no Gemini.

    Args:
        config: Configuração base da aplicação.

    Returns:
        `True` se o login for detectado ao encerrar a verificação, `False` caso contrário.
    """
    interactive_config = replace(config, headless=False)
    profile_dir = resolve_user_data_dir(interactive_config)

    print("=== Configuração de Sessão Persistente do Google Gemini ===")
    print(f"Diretório de perfil: {profile_dir}")
    print(f"URL de destino:      {interactive_config.gemini_url}")

    context = get_chrome_context(interactive_config)
    client = GeminiClient()
    try:
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(interactive_config.gemini_url, wait_until="domcontentloaded")

        print(
            "\n[INSTRUÇÃO] Realize o login na sua conta Google na janela aberta do navegador."
        )
        input("Após concluir o login e visualizar a caixa de prompt do Gemini, pressione [ENTER] aqui no terminal...")

        is_authenticated = client.check_login_status(page)
        if is_authenticated:
            print("[SUCESSO] Sessão autenticada e salva com sucesso no perfil persistente.")
        else:
            print(
                "[AVISO] Não foi possível confirmar a caixa de prompt do Gemini. "
                "Verifique se o login foi concluído antes de executar a automação."
            )
        return is_authenticated
    finally:
        context.close()


def main() -> int:
    """Ponto de entrada CLI do utilitário de configuração de sessão."""
    parser = argparse.ArgumentParser(
        description="Abre o navegador com perfil persistente para login manual no Google Gemini."
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Apenas exibe as configurações do perfil sem aguardar input interativo.",
    )
    args = parser.parse_args()

    if args.check_only:
        profile_dir = resolve_user_data_dir(DEFAULT_CONFIG)
        print(f"Perfil persistente configurado em: {profile_dir}")
        return 0

    setup_interactive_session(DEFAULT_CONFIG)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
