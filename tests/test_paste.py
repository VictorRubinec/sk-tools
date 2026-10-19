from playwright.sync_api import sync_playwright

def test_paste_synthetic_file():
    html = """
    <div id="box" contenteditable="true"></div>
    <script>
    document.getElementById("box").addEventListener("paste", (e) => {
        if (e.clipboardData && e.clipboardData.files.length > 0) {
            document.body.setAttribute("data-pasted", e.clipboardData.files[0].name);
        }
    });
    </script>
    """
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        page = b.new_page()
        page.set_content(html)
        js = """
        (name) => {
            const dt = new DataTransfer();
            dt.items.add(new File([new Uint8Array([1, 2, 3])], name, { type: 'image/png' }));
            const el = document.getElementById('box');
            el.focus();
            el.dispatchEvent(new ClipboardEvent('paste', {
                bubbles: true,
                cancelable: true,
                composed: true,
                clipboardData: dt
            }));
        }
        """
        page.evaluate(js, "carta.png")
        page.wait_for_timeout(100)
        attr = page.locator("body").get_attribute("data-pasted")
        assert attr == "carta.png"
        b.close()
