"""HTML'den PDF (ADR-0012): Playwright ile Chromium, A4, JavaScript ve ağ kapalı.

Şablonlar yazı tiplerini gömülü taşır; dış kaynak istenirse istek iptal edilir. Sayfa altı
(kaynak, veri tarihi, sayfa numarası) Chromium'un `footer_template` özelliğiyle basılır.
"""

import re
from typing import Any

from kurgu_api.config import get_settings

PAGE = re.compile(rb"/Type\s*/Page(?![a-zA-Z])")
# Arka plan ağ trafiği (güncelleme, bileşen indirme) kapatılır; PDF üretimi çevrimdışıdır.
LAUNCH_ARGS = [
    "--disable-background-networking",
    "--disable-component-update",
    "--disable-default-apps",
    "--disable-sync",
    "--no-first-run",
    "--metrics-recording-only",
]


def page_count(pdf: bytes) -> int:
    return len(PAGE.findall(pdf))


async def _block(route: Any) -> None:
    if route.request.url.startswith(("data:", "about:")):
        await route.continue_()
    else:
        await route.abort()


async def render_pdf(html: str, footer: str) -> bytes:
    """Tek belge üretir. Tarayıcı her iş için açılıp kapanır (iş süresi < 15 sn, A-71)."""
    from playwright.async_api import async_playwright

    settings = get_settings()
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            executable_path=settings.kurgu_chromium_path or None, args=LAUNCH_ARGS
        )
        try:
            context = await browser.new_context(java_script_enabled=False, offline=True)
            page = await context.new_page()
            await page.route("**/*", _block)
            await page.set_content(html, wait_until="load")
            pdf: bytes = await page.pdf(
                format="A4",
                print_background=True,
                display_header_footer=True,
                header_template="<span></span>",
                footer_template=footer,
                margin={"top": "14mm", "bottom": "16mm", "left": "13mm", "right": "13mm"},
                prefer_css_page_size=True,
            )
        finally:
            await browser.close()
    return pdf
