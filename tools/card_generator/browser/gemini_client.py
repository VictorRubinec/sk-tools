"""Cliente de automação com seletores semânticos e resilientes para o Google Gemini Web."""

from __future__ import annotations

import base64
import io
import re
import time
from pathlib import Path
from typing import List, Optional, Sequence, Union

from PIL import Image
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from tools.card_generator.browser.exceptions import (
    GeminiBrowserError,
    GeminiGenerationTimeoutError,
    GeminiImageNotGeneratedError,
    GeminiPromptSubmissionError,
)
from tools.card_generator.core.config import BASE_DIR
from tools.card_generator.core.logger import logger


class GeminiClient:
    """Encapsula as interações de interface web com o Google Gemini via Playwright."""

    SIGN_IN_SELECTOR: str = (
        'a[href*="ServiceLogin"], '
        'button:has-text("Fazer login"), '
        'a:has-text("Fazer login"), '
        'button:has-text("Sign in"), '
        'a:has-text("Sign in")'
    )

    PROMPT_BOX_SELECTOR: str = (
        'rich-textarea div[contenteditable="true"], '
        'div[contenteditable="true"][role="textbox"], '
        'textarea[aria-label*="prompt" i], '
        'div[contenteditable="true"], '
        '[role="textbox"]'
    )

    SEND_BUTTON_SELECTOR: str = (
        'button[aria-label*="Enviar" i], '
        'button[aria-label*="Send" i], '
        'button.send-button'
    )

    STOP_GENERATION_SELECTOR: str = (
        'button[aria-label*="Parar" i], '
        'button[aria-label*="Stop" i], '
        'button.stop-button, '
        '[aria-busy="true"]'
    )

    FILE_INPUT_SELECTOR: str = 'input[type="file"]'

    UPLOAD_TRIGGER_SELECTOR: str = (
        'button[aria-label*="Carregar" i], '
        'button[aria-label*="Adicionar" i], '
        'button[aria-label*="Upload" i], '
        'button[aria-label*="Add" i]'
    )

    UPLOAD_THUMBNAIL_SELECTOR: str = (
        'uploader-file-preview, '
        'img.gem-attachment-style-img, '
        'img[alt="attachment"], '
        '.file-preview-chip, '
        'img[src^="blob:"], '
        'img[src^="data:image"], '
        '[data-test-id*="image-preview"], '
        '.file-preview, '
        'mat-chip, '
        'button[aria-label*="remover" i]'
    )

    GENERATED_IMAGE_SELECTOR: str = (
        'model-response img:not([src*="googleusercontent.com/a/"]):not([class*="avatar"]), '
        'message-content:not(user-query *) img:not([src*="googleusercontent.com/a/"]):not([class*="avatar"]), '
        '.model-response-text img:not([src*="googleusercontent.com/a/"]):not([class*="avatar"]), '
        'img[alt*="Gerada" i], '
        'img[alt*="Generated" i], '
        '.image-container img, '
        'div[data-test-id*="image"] img'
    )

    DOWNLOAD_BUTTON_SELECTOR: str = (
        '[data-test-id="download-generated-image-button"] button, '
        '[data-test-id="download-generated-image-button"], '
        'button[aria-label="Baixar imagem no tamanho original"], '
        'button[aria-label*="tamanho original" i], '
        'button[aria-label*="download" i], '
        'button[aria-label*="baixar" i], '
        'a[download]'
    )

    def check_login_status(self, page: Page, timeout_ms: int = 15000) -> bool:
        """Verifica se a página do Gemini está autenticada e pronta para uso.

        Detecta a ausência de botões visíveis de 'Fazer login' / 'Sign in' e
        aguarda a presença e visibilidade da caixa de texto de prompt.
        """
        deadline = time.time() + (timeout_ms / 1000.0)
        while True:
            try:
                sign_in_btn = page.locator(self.SIGN_IN_SELECTOR)
                if sign_in_btn.count() > 0 and sign_in_btn.first.is_visible():
                    return False

                prompt_box = page.locator(self.PROMPT_BOX_SELECTOR)
                if prompt_box.count() > 0 and prompt_box.first.is_visible():
                    return True
            except PlaywrightError:
                pass

            if time.time() >= deadline:
                break
            try:
                page.wait_for_timeout(500)
            except PlaywrightError:
                break

        return False

    def _paste_images_to_chat(
        self, page: Page, resolved_files: Sequence[Path]
    ) -> None:
        """Injeta imagens diretamente no chat simulando evento de colar (ClipboardEvent e nativo)."""
        files_payload = []
        for file_path in resolved_files:
            raw_data = file_path.read_bytes()
            b64_data = base64.b64encode(raw_data).decode("ascii")
            suffix = file_path.suffix.lower()
            mime = (
                "image/png"
                if suffix in (".png", "")
                else ("image/jpeg" if suffix in (".jpg", ".jpeg") else "image/webp")
            )
            files_payload.append({
                "name": file_path.name,
                "mimeType": mime,
                "base64": b64_data,
            })

        # Garante permissões de área de transferência no contexto
        try:
            page.context.grant_permissions(["clipboard-read", "clipboard-write"])
        except Exception:
            pass

        # Localiza e foca a caixa de prompt antes de colar
        prompt_loc = page.locator(self.PROMPT_BOX_SELECTOR).first
        try:
            if prompt_loc.count() > 0 and prompt_loc.is_visible():
                prompt_loc.click()
                page.wait_for_timeout(300)
        except Exception:
            pass

        # 1. Tenta via Clipboard API nativo + Control+V (evento confiável isTrusted: true)
        js_native_clipboard = """
        async (files) => {
            try {
                for (const f of files) {
                    const bin = atob(f.base64);
                    const bytes = new Uint8Array(bin.length);
                    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
                    const blob = new Blob([bytes], { type: f.mimeType });
                    const imgBitmap = await createImageBitmap(blob);
                    const canvas = document.createElement("canvas");
                    canvas.width = imgBitmap.width;
                    canvas.height = imgBitmap.height;
                    const ctx = canvas.getContext("2d");
                    ctx.drawImage(imgBitmap, 0, 0);
                    const pngBlob = await new Promise(r => canvas.toBlob(r, "image/png"));
                    await navigator.clipboard.write([
                        new ClipboardItem({ "image/png": pngBlob })
                    ]);
                }
                return true;
            } catch (e) {
                return false;
            }
        }
        """
        written_to_clipboard = False
        try:
            written_to_clipboard = bool(page.evaluate(js_native_clipboard, files_payload))
        except Exception:
            written_to_clipboard = False

        if written_to_clipboard:
            try:
                if prompt_loc.count() > 0 and prompt_loc.is_visible():
                    prompt_loc.click()
                page.keyboard.press("Control+v")
                page.wait_for_timeout(1000)
            except Exception:
                pass
        else:
            # 2. Como fallback quando navigator.clipboard não estiver disponível:
            # dispara evento synthetic ClipboardEvent
            js_paste = """
            (files) => {
                const targets = [
                    document.activeElement,
                    document.querySelector('rich-textarea div[contenteditable="true"]'),
                    document.querySelector('rich-textarea'),
                    document.querySelector('chat-window'),
                    document.body,
                    document
                ].filter(Boolean);

                for (const f of files) {
                    const bin = atob(f.base64);
                    const bytes = new Uint8Array(bin.length);
                    for (let i = 0; i < bin.length; i++) {
                        bytes[i] = bin.charCodeAt(i);
                    }
                    const fileObj = new File([bytes], f.name, { type: f.mimeType });

                    for (const t of targets) {
                        const dt = new DataTransfer();
                        dt.items.add(fileObj);
                        const pasteEv = new ClipboardEvent("paste", {
                            bubbles: true,
                            cancelable: true,
                            composed: true,
                            clipboardData: dt
                        });
                        t.dispatchEvent(pasteEv);
                    }
                }
                return true;
            }
            """
            try:
                page.evaluate(js_paste, files_payload)
            except Exception:
                pass

    def upload_reference_images(
        self, page: Page, image_paths: Sequence[Union[str, Path]]
    ) -> None:
        """Cola imagens de referência diretamente no chat e aguarda o carregamento do anexo."""
        if not image_paths:
            return

        resolved_files: List[Path] = []
        for raw_path in image_paths:
            candidate = Path(raw_path)
            resolved = candidate if candidate.is_file() else (BASE_DIR / candidate)
            if not resolved.is_file():
                raise FileNotFoundError(
                    f"Imagem de referência não encontrada para upload: {raw_path}"
                )
            resolved_files.append(resolved.resolve())

        try:
            logger.info(f"Colando {len(resolved_files)} imagem(ns) de referência no chat...")
            self._paste_images_to_chat(page, resolved_files)

            # Aguarda a miniatura aparecer ou um tempo seguro de processamento
            try:
                thumbnail = page.locator(self.UPLOAD_THUMBNAIL_SELECTOR)
                thumbnail.first.wait_for(state="visible", timeout=12000)
                logger.success("Imagem de referência anexada com sucesso no chat!")
                page.wait_for_timeout(2000)
            except Exception:
                logger.warning("Miniatura demorou a aparecer, aguardando buffer de colagem...")
                page.wait_for_timeout(4000)

        except (PlaywrightError, PlaywrightTimeoutError, Exception) as exc:
            logger.error(f"Erro ao anexar imagens de referência: {exc}")
            raise GeminiPromptSubmissionError(
                f"Falha ao anexar imagens de referência no Gemini: {exc}"
            ) from exc

    def submit_prompt(self, page: Page) -> None:
        """Dispara o envio do prompt atual (botão enviar ou tecla Enter)."""
        try:
            prompt_box = page.locator(self.PROMPT_BOX_SELECTOR).first
            send_btn = page.locator(self.SEND_BUTTON_SELECTOR)
            if send_btn.count() > 0 and send_btn.first.is_visible():
                send_btn.first.click()
            else:
                prompt_box.press("Enter")
            logger.debug("Prompt disparado com sucesso.")
        except Exception as exc:
            logger.error(f"Erro ao disparar envio do prompt: {exc}")
            raise GeminiPromptSubmissionError(
                f"Não foi possível enviar o prompt ao Gemini: {exc}"
            ) from exc

    def send_prompt(
        self,
        page: Page,
        prompt_text: str,
        image_paths: Optional[Sequence[Union[str, Path]]] = None,
        submit: bool = True,
    ) -> None:
        """Insere o prompt na área de texto editável e aciona o envio.

        Se `submit=False`, apenas digita o texto na caixa sem clicar em enviar,
        permitindo anexar/colar imagens antes de disparar o envio com `submit_prompt()`.
        """
        if not isinstance(prompt_text, str) or not prompt_text.strip():
            raise GeminiPromptSubmissionError("O texto do prompt não pode ser vazio.")

        try:
            logger.info("Digitando prompt no Gemini...")
            logger.debug(f"Prompt ({len(prompt_text)} caracteres): {prompt_text[:150]}...")
            prompt_box = page.locator(self.PROMPT_BOX_SELECTOR).first
            prompt_box.wait_for(state="visible", timeout=15000)
            prompt_box.click()
            prompt_box.fill(prompt_text)
            page.wait_for_timeout(600)

            # Se houver imagens de referência fornecidas diretamente, anexa agora
            if image_paths:
                logger.info(f"Anexando {len(image_paths)} imagem(ns) de referência via colagem...")
                self.upload_reference_images(page, image_paths)

            if submit:
                logger.info("Disparando envio da mensagem...")
                self.submit_prompt(page)
        except (PlaywrightError, PlaywrightTimeoutError, Exception) as exc:
            if isinstance(exc, GeminiPromptSubmissionError):
                raise
            logger.error(f"Erro ao digitar prompt: {exc}")
            raise GeminiPromptSubmissionError(
                f"Não foi possível digitar ou enviar o prompt ao Gemini: {exc}"
            ) from exc

    def wait_for_generation_complete(
        self, page: Page, timeout_ms: int = 90000
    ) -> None:
        """Aguarda a conclusão completa da resposta da IA e da imagem gerada.

        Monitora o indicador de parada e o surgimento efetivo da imagem renderizada,
        evitando encerramento prematuro em mensagens intermediárias como 'Criando sua imagem'.
        """
        logger.info(f"Aguardando geração do Gemini (timeout: {timeout_ms}ms)...")
        stop_locator = page.locator(self.STOP_GENERATION_SELECTOR)

        try:
            # Aguarda brevemente o início do estado de geração
            try:
                stop_locator.first.wait_for(
                    state="visible", timeout=min(5000, timeout_ms)
                )
            except PlaywrightTimeoutError:
                pass

            # Monitora o desaparecimento do botão de parada dentro do limite de timeout_ms
            stop_locator.first.wait_for(state="hidden", timeout=timeout_ms)
        except (PlaywrightTimeoutError, TimeoutError) as exc:
            raise GeminiGenerationTimeoutError(
                f"Tempo limite de {timeout_ms}ms excedido aguardando a geração do Gemini."
            ) from exc
        except PlaywrightError as exc:
            raise GeminiBrowserError(
                f"Erro inesperado enquanto aguardava geração do Gemini: {exc}"
            ) from exc

        # Fase 2: Aguarda especificamente o surgimento da imagem gerada
        start_time = time.time()
        max_image_wait_sec = min(75.0, timeout_ms / 1000.0)

        while (time.time() - start_time) < max_image_wait_sec:
            has_image = False
            try:
                has_image = page.evaluate("""() => {
                    const selector = 'model-response img, message-content:not(user-query *) img, .image-container img, div[data-test-id*="image"] img';
                    const imgs = Array.from(document.querySelectorAll(selector));
                    for (const img of imgs) {
                        const src = img.src || '';
                        if (src.includes('/a/') || src.includes('googleusercontent.com/a/') || (img.className && String(img.className).includes('avatar'))) {
                            continue;
                        }
                        if (img.closest('user-query, .user-query, header, nav, button[aria-label*="Conta"], button[aria-label*="Account"]')) {
                            continue;
                        }
                        const w = img.naturalWidth || img.clientWidth || img.width || 0;
                        const h = img.naturalHeight || img.clientHeight || img.height || 0;
                        if (w > 128 && h > 128 && img.complete) {
                            return true;
                        }
                    }
                    return false;
                }""")
            except Exception:
                has_image = True

            if has_image:
                logger.success("Card com imagem gerada detectado! Aguardando estabilização...")
                page.wait_for_timeout(6000)
                return

            # Verifica se há texto de carregamento ativo ("Criando sua imagem", etc.)
            is_still_generating = False
            try:
                is_still_generating = page.evaluate("""() => {
                    const text = (document.querySelector('model-response, message-content:not(user-query *)')?.innerText || '').toLowerCase();
                    return text.includes('criando sua imagem') || text.includes('gerando imagem') || text.includes('creating image') || text.includes('generating image');
                }""")
            except Exception:
                is_still_generating = False

            if not is_still_generating and (time.time() - start_time) > 8.0:
                break

            logger.debug("Imagem ainda sendo processada pelo Gemini, aguardando...")
            page.wait_for_timeout(1500)

    @staticmethod
    def _trim_screenshot_borders(raw_bytes: bytes) -> bytes:
        """Remove barras pretas periféricas caso o screenshot capture padding/pillarboxing do DOM."""
        try:
            with Image.open(io.BytesIO(raw_bytes)) as img:
                rgb_img = img.convert("RGB")
                gray = rgb_img.convert("L")
                thresh = gray.point(lambda p: 255 if p > 20 else 0)
                bbox = thresh.getbbox()
                if not bbox:
                    return raw_bytes
                left, top, right, bottom = bbox
                max_w = int(rgb_img.width * 0.25)
                max_h = int(rgb_img.height * 0.25)
                crop_left = left if left <= max_w else 0
                crop_top = top if top <= max_h else 0
                crop_right = right if (rgb_img.width - right) <= max_w else rgb_img.width
                crop_bottom = bottom if (rgb_img.height - bottom) <= max_h else rgb_img.height
                if crop_left > 0 or crop_top > 0 or crop_right < rgb_img.width or crop_bottom < rgb_img.height:
                    cropped = rgb_img.crop((crop_left, crop_top, crop_right, crop_bottom))
                    buf = io.BytesIO()
                    cropped.save(buf, format="PNG")
                    return buf.getvalue()
                return raw_bytes
        except Exception:
            return raw_bytes

    def extract_latest_generated_image(self, page: Page) -> Optional[bytes]:
        """Localiza e baixa o arquivo original da última imagem gerada na conversa.

        Prioriza o download direto do arquivo em alta resolução (via botão nativo de download
        ou fetch do blob/URL) em vez de capturar print/screenshot da tela.

        Raises:
            GeminiImageNotGeneratedError: Se nenhuma imagem válida for encontrada na resposta.
        """
        try:
            images = page.locator(self.GENERATED_IMAGE_SELECTOR)
            count = images.count()
            if count == 0:
                raise GeminiImageNotGeneratedError(
                    "A resposta do Gemini foi concluída, mas nenhuma tag <img> foi gerada."
                )

            # Itera de trás para frente buscando a última imagem gerada que não seja avatar/ícone
            target_img = None
            for idx in reversed(range(count)):
                cand = images.nth(idx)
                try:
                    eval_res = cand.evaluate("""(img) => {
                        const src = img.src || '';
                        if (src.includes('/a/') || src.includes('googleusercontent.com/a/') || (img.className && String(img.className).includes('avatar'))) {
                            return false;
                        }
                        if (img.closest('user-query, .user-query, header, nav, button[aria-label*="Conta"], button[aria-label*="Account"]')) {
                            return false;
                        }
                        const w = img.naturalWidth || img.clientWidth || img.width || 0;
                        const h = img.naturalHeight || img.clientHeight || img.height || 0;
                        if (w > 0 && h > 0 && (w <= 128 || h <= 128)) {
                            return false;
                        }
                        return true;
                    }""")
                    if eval_res is True or (eval_res and not isinstance(eval_res, bool)):
                        target_img = cand
                        break
                except Exception:
                    if target_img is None:
                        target_img = cand

            if target_img is None:
                target_img = images.last

            src = target_img.get_attribute("src") or ""

            # 1. Estratégia Prioritária: Download Nativo do arquivo original via botão
            try:
                logger.info("Localizando botão de download nativo no card da imagem...")
                target_img.scroll_into_view_if_needed()
                target_img.hover()
                img_container = page.locator(".image-container, model-response").last
                if img_container.count() > 0:
                    img_container.hover()

                page.wait_for_timeout(600)

                download_btn = page.locator(self.DOWNLOAD_BUTTON_SELECTOR).last
                if download_btn.count() > 0:
                    logger.info("Acionando botão de download nativo do Gemini...")
                    with page.expect_download(timeout=12000) as download_info:
                        download_btn.click(force=True)
                    download = download_info.value
                    temp_path = download.path()
                    if temp_path and Path(temp_path).exists():
                        downloaded_bytes = Path(temp_path).read_bytes()
                        if downloaded_bytes and len(downloaded_bytes) > 1024:
                            logger.success(
                                f"Download nativo concluído com sucesso ({len(downloaded_bytes):,} bytes)!"
                            )
                            return downloaded_bytes
            except Exception as exc:
                logger.debug(f"Download nativo via botão não completou: {exc}")

            # 2. Se for data:image/base64, decodifica diretamente
            if src.startswith("data:image/") and "," in src:
                _, b64_data = src.split(",", 1)
                raw_bytes = base64.b64decode(b64_data)
                if raw_bytes:
                    return raw_bytes

            # 3. Estratégia de Download via Fetch no contexto da página (para URLs e blobs)
            if src:
                try:
                    b64_from_fetch = page.evaluate("""async (url) => {
                        const res = await fetch(url);
                        const blob = await res.blob();
                        return new Promise((resolve, reject) => {
                            const reader = new FileReader();
                            reader.onloadend = () => resolve(reader.result);
                            reader.onerror = reject;
                            reader.readAsDataURL(blob);
                        });
                    }""", src)
                    if b64_from_fetch and "," in b64_from_fetch:
                        _, b64_clean = b64_from_fetch.split(",", 1)
                        data = base64.b64decode(b64_clean)
                        if data and len(data) > 1024:
                            return data
                except Exception:
                    pass

            # 4. Estratégia de Download HTTP direto via Playwright Request
            if src.startswith("http://") or src.startswith("https://"):
                urls_to_try = [src]
                if "=s" in src and "googleusercontent.com" in src:
                    high_res_url = re.sub(r"=s\d+", "=s0", src)
                    if high_res_url != src:
                        urls_to_try.insert(0, high_res_url)

                for u in urls_to_try:
                    try:
                        response = page.request.get(u)
                        if response.ok:
                            body = response.body()
                            if body and len(body) > 1024:
                                return body
                    except Exception:
                        pass

            # 5. Fallback para screenshot apenas se todas as tentativas de download falharem
            screenshot_bytes = target_img.screenshot(type="png")
            if isinstance(screenshot_bytes, bytes) and len(screenshot_bytes) > 0:
                logger.warning(
                    "Download direto indisponível; utilizando fallback de screenshot com remoção de bordas DOM."
                )
                return self._trim_screenshot_borders(screenshot_bytes)

            raise GeminiImageNotGeneratedError(
                "A imagem gerada foi localizada no DOM, mas não foi possível extrair seus bytes."
            )
        except GeminiImageNotGeneratedError:
            raise
        except (PlaywrightError, Exception) as exc:
            raise GeminiImageNotGeneratedError(
                f"Falha ao extrair a imagem gerada da resposta do Gemini: {exc}"
            ) from exc
