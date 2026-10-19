"""Script espião/mapeador de eventos e seletores da interface do Google Gemini.

Monitora em tempo real:
- Cliques em elementos (com seletores CSS sugeridos, atributos, aria-label, texto)
- Digitação / inputs na página
- Ações de copiar e colar (texto e arquivos)
- Adição dinâmica de inputs de arquivo e miniaturas no DOM
- Requisições de rede (Network requests e responses)
- Disparos de seletores de arquivos (filechooser)
- Salva um relatório estruturado em 'output/gemini_spy_log.jsonl'
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from playwright.sync_api import FileChooser, Page, Request, Response, sync_playwright

from browser.session import STABILITY_ARGS, resolve_user_data_dir
from core.config import DEFAULT_CONFIG

LOG_DIR = PROJECT_ROOT / "output"
LOG_FILE = LOG_DIR / "gemini_spy_log.jsonl"
SELECTORS_SUMMARY_FILE = LOG_DIR / "gemini_discovered_selectors.json"


def _format_timestamp() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def _append_log(entry: Dict[str, Any]) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# Código JavaScript que é injetado em toda página para capturar ações do usuário
INJECTED_SPY_JS = """
(() => {
    function getCssSelector(el) {
        if (!el || el.nodeType !== Node.ELEMENT_NODE) return '';
        if (el.id) return `#${el.id}`;

        const ariaLabel = el.getAttribute('aria-label');
        if (ariaLabel) {
            return `${el.tagName.toLowerCase()}[aria-label="${ariaLabel}"]`;
        }

        const dataTestId = el.getAttribute('data-test-id');
        if (dataTestId) {
            return `[data-test-id="${dataTestId}"]`;
        }

        let path = [];
        let curr = el;
        while (curr && curr.nodeType === Node.ELEMENT_NODE && path.length < 4) {
            let selector = curr.tagName.toLowerCase();
            if (curr.className && typeof curr.className === 'string') {
                const classes = curr.className.trim().split(/\\s+/).filter(c => c && !c.includes(':')).slice(0, 2);
                if (classes.length) selector += '.' + classes.join('.');
            }
            path.unshift(selector);
            if (curr.id || curr.tagName.toLowerCase() === 'body') break;
            curr = curr.parentElement;
        }
        return path.join(' > ');
    }

    function extractElementInfo(el) {
        if (!el || el.nodeType !== Node.ELEMENT_NODE) return null;
        
        const attrs = {};
        for (const attr of el.attributes || []) {
            attrs[attr.name] = attr.value;
        }

        const text = (el.innerText || el.textContent || '').trim().slice(0, 100);
        const ariaLabel = el.getAttribute('aria-label') || '';
        const role = el.getAttribute('role') || '';
        const tag = el.tagName.toLowerCase();

        return {
            tag: tag,
            id: el.id || '',
            className: typeof el.className === 'string' ? el.className.trim() : '',
            ariaLabel: ariaLabel,
            role: role,
            text: text,
            selector: getCssSelector(el),
            outerSnippet: (el.outerHTML || '').slice(0, 250),
            attributes: attrs
        };
    }

    // 1. Escuta de Cliques
    window.addEventListener('click', (event) => {
        const target = event.target;
        const info = extractElementInfo(target);
        if (window.__gemini_spy_event) {
            window.__gemini_spy_event({
                type: 'CLICK',
                element: info
            });
        }
    }, true);

    // 2. Escuta de Digitação / Inputs
    window.addEventListener('input', (event) => {
        const target = event.target;
        const info = extractElementInfo(target);
        const value = (target.value !== undefined ? target.value : (target.innerText || '')).slice(0, 150);
        if (window.__gemini_spy_event) {
            window.__gemini_spy_event({
                type: 'INPUT',
                value: value,
                element: info
            });
        }
    }, true);

    // 3. Escuta de Colagem (Paste)
    window.addEventListener('paste', (event) => {
        const target = event.target;
        const info = extractElementInfo(target);
        const clipboard = event.clipboardData;
        let pasteType = 'text';
        let itemsCount = 0;
        let preview = '';

        if (clipboard) {
            itemsCount = clipboard.items.length;
            if (clipboard.files && clipboard.files.length > 0) {
                pasteType = 'file/image';
                preview = `Arquivos: ${clipboard.files.length} (${Array.from(clipboard.files).map(f => f.name || f.type).join(', ')})`;
            } else {
                preview = (clipboard.getData('text') || '').slice(0, 150);
            }
        }

        if (window.__gemini_spy_event) {
            window.__gemini_spy_event({
                type: 'PASTE',
                pasteType: pasteType,
                preview: preview,
                element: info
            });
        }
    }, true);

    // 4. Observador de Mutações no DOM (detecta surgimento de input[type=file], imagens, menus)
    const observer = new MutationObserver((mutations) => {
        for (const m of mutations) {
            for (const node of m.addedNodes) {
                if (node.nodeType === Node.ELEMENT_NODE) {
                    const el = node;
                    // Detecta input de arquivo
                    if (el.tagName === 'INPUT' && el.type === 'file') {
                        if (window.__gemini_spy_event) {
                            window.__gemini_spy_event({
                                type: 'DOM_FILE_INPUT_ADDED',
                                element: extractElementInfo(el)
                            });
                        }
                    } else if (el.querySelector && el.querySelector('input[type="file"]')) {
                        const fileInp = el.querySelector('input[type="file"]');
                        if (window.__gemini_spy_event) {
                            window.__gemini_spy_event({
                                type: 'DOM_FILE_INPUT_ADDED',
                                element: extractElementInfo(fileInp)
                            });
                        }
                    }

                    // Detecta imagens renderizadas
                    if (el.tagName === 'IMG') {
                        if (window.__gemini_spy_event) {
                            window.__gemini_spy_event({
                                type: 'DOM_IMAGE_ADDED',
                                src: (el.src || '').slice(0, 100),
                                element: extractElementInfo(el)
                            });
                        }
                    }
                }
            }
        }
    });

    observer.observe(document.documentElement, {
        childList: true,
        subtree: true
    });
})();
"""


def main() -> int:
    profile_dir = resolve_user_data_dir(DEFAULT_CONFIG)
    url = DEFAULT_CONFIG.gemini_url

    print("=" * 70)
    print("      SK-TOOLS | Mapeador e Gravador de Interações do Gemini      ")
    print("=" * 70)
    print(f"[*] Perfil Chrome: {profile_dir}")
    print(f"[*] URL:           {url}")
    print(f"[*] Log em disco:  {LOG_FILE}")
    print("\n[INSTRUÇÃO]")
    print("1. O navegador abrirá agora.")
    print("2. Use o Gemini normalmente:")
    print("   - Clique no botão de upload / '+'")
    print("   - Anexe uma imagem")
    print("   - Digite um prompt")
    print("   - Clique em Enviar")
    print("   - Espere a resposta e imagem gerada")
    print("3. Toda ação, clique, seletor e resposta de rede aparecerão aqui no terminal.")
    print("4. Para encerrar, aperte [Ctrl + C] ou feche o navegador.")
    print("=" * 70 + "\n")

    discovered_selectors: Dict[str, list] = {
        "clicks": [],
        "inputs": [],
        "file_triggers": [],
        "images": [],
        "endpoints": [],
    }

    with sync_playwright() as pw:
        launch_kwargs = {
            "user_data_dir": str(profile_dir),
            "headless": False,
            "args": list(STABILITY_ARGS),
            "no_viewport": True,
            "channel": "chrome",
        }

        try:
            context = pw.chromium.launch_persistent_context(**launch_kwargs)
        except Exception as e:
            print(f"[ERRO AO ABRIR O CHROME]: {e}")
            print("\nSe houver outro Chrome aberto na pasta do perfil, feche-o com:")
            print("Stop-Process -Name chrome -Force -ErrorAction SilentlyContinue")
            return 1

        page: Page = context.pages[0] if context.pages else context.new_page()

        # Função de callback chamada pelo JavaScript injetado
        def handle_browser_event(data: Dict[str, Any]) -> None:
            ts = _format_timestamp()
            event_type = data.get("type", "UNKNOWN")
            el = data.get("element") or {}
            sel = el.get("selector", "")
            aria = el.get("ariaLabel", "")
            tag = el.get("tag", "")
            text = el.get("text", "")

            log_entry = {"timestamp": ts, **data}
            _append_log(log_entry)

            if event_type == "CLICK":
                desc = f"<{tag}>"
                if aria:
                    desc += f' aria-label="{aria}"'
                if text:
                    desc += f' text="{text[:30]}"'
                print(f"[{ts}] [CLIQUE] {desc}")
                print(f"       -> Seletor sugerido: {sel}")

                # Detecta se parece botão de upload ou adicionar
                if any(k in aria.lower() for k in ["adicionar", "upload", "anexar", "file", "arquivo", "+"]):
                    print(f"       ⭐ POSSÍVEL BOTÃO DE UPLOAD IDENTIFICADO: {sel} (aria-label: {aria})")
                    discovered_selectors["file_triggers"].append({"selector": sel, "aria": aria, "html": el.get("outerSnippet")})

                discovered_selectors["clicks"].append({"selector": sel, "aria": aria, "text": text})

            elif event_type == "INPUT":
                val = data.get("value", "")
                print(f"[{ts}] [DIGITAÇÃO] <{tag}> | Seletor: {sel}")
                print(f"       -> Conteúdo digitado: \"{val[:50]}\"")
                discovered_selectors["inputs"].append({"selector": sel, "aria": aria, "tag": tag})

            elif event_type == "PASTE":
                paste_type = data.get("pasteType", "")
                preview = data.get("preview", "")
                print(f"[{ts}] [COLAGEM/PASTE] Tipo: {paste_type} | {preview}")

            elif event_type == "DOM_FILE_INPUT_ADDED":
                print(f"\n[{ts}] 🎯 [DOM] NOVO INPUT DE ARQUIVO DETECTADO NO HTML!")
                print(f"       -> Seletor: {sel}")
                print(f"       -> HTML: {el.get('outerSnippet')}\n")
                discovered_selectors["file_triggers"].append({"type": "input[type=file]", "selector": sel, "element": el})

            elif event_type == "DOM_IMAGE_ADDED":
                src = data.get("src", "")
                if src and not src.startswith("data:image/svg"):
                    print(f"[{ts}] [IMAGEM CARREGADA] Seletor: {sel} | src: {src[:60]}...")
                    discovered_selectors["images"].append({"selector": sel, "src": src[:100]})

        # Expõe a função Python para o JavaScript da página
        page.expose_binding("__gemini_spy_event", lambda source, data: handle_browser_event(data))

        # Injeta o script espião
        page.add_init_script(INJECTED_SPY_JS)

        # 5. Monitora seletor de arquivos nativo do SO
        def on_file_chooser(chooser: FileChooser) -> None:
            ts = _format_timestamp()
            el = chooser.element
            print(f"\n[{ts}] 📂 [FILE CHOOSER NATIVO DISPARADO!]")
            print(f"       -> Múltiplos arquivos permitidos: {chooser.is_multiple}")
            _append_log({"timestamp": ts, "type": "FILE_CHOOSER", "multiple": chooser.is_multiple})

        page.on("filechooser", on_file_chooser)

        # 6. Monitora Network (Requisições e Respostas relevantes)
        def on_response(response: Response) -> None:
            url = response.url
            status = response.status
            content_type = response.headers.get("content-type", "")

            # Filtra apenas chamadas do Gemini que nos interessam (APIs, uploads, streaming de chat, imagens)
            is_gemini_api = any(
                k in url
                for k in [
                    "assistant.vertical",
                    "batchexecute",
                    "upload",
                    "generate",
                    "BardChatUi",
                    "image",
                    "blob:",
                ]
            )

            if is_gemini_api and status in (200, 204):
                ts = _format_timestamp()
                method = response.request.method
                short_url = url.split("?")[0]
                print(f"[{ts}] [NETWORK API] {method} {status} | {short_url}")
                _append_log({
                    "timestamp": ts,
                    "type": "NETWORK_RESPONSE",
                    "method": method,
                    "status": status,
                    "url": url,
                    "content_type": content_type,
                })
                discovered_selectors["endpoints"].append({"url": short_url, "method": method})

        page.on("response", on_response)

        # Navega para a URL
        print("[*] Abrindo o Gemini...")
        page.goto(url, wait_until="domcontentloaded")
        print("[*] Gemini aberto! Aguardando suas interações...\n")

        try:
            while True:
                # Mantém o script rodando enquanto o navegador estiver aberto
                if page.is_closed():
                    break
                time.sleep(1)
        except (KeyboardInterrupt, Exception):
            pass
        finally:
            print("\n[*] Encerrando sessão de monitoramento...")
            try:
                # Salva resumo de seletores descobertos
                with open(SELECTORS_SUMMARY_FILE, "w", encoding="utf-8") as sf:
                    json.dump(discovered_selectors, sf, indent=2, ensure_ascii=False)
                print(f"[*] Resumo de seletores salvo em: {SELECTORS_SUMMARY_FILE}")
                print(f"[*] Log completo salvo em:           {LOG_FILE}")
            except Exception:
                pass
            context.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
