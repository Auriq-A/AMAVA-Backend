"""Local Playwright browser transport (no Bright Data).

Falls back from ScrapingBrowserSession when BRIGHTDATA_USE=false.
Requires: pip install playwright && playwright install chromium

Good for: development, testing, sites that don't block headless browsers.
Not good for: sites that detect/block bots — use ScrapingBrowserSession for those.
"""
from __future__ import annotations

from ..config import ScraperConfig
from ..exceptions import ScraperConfigError, TransportError
from .scraping_browser import _PlaywrightSessionBase

# Realistic desktop Chrome UA so SPAs don't treat us as a bot.
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Init script that hides the most common automation tells. Many SPAs (avasam
# included) run anti-bot/analytics scripts that detect headless Chrome and
# refuse to render the app otherwise. This masks the standard fingerprints
# (the WebGL renderer string is the biggest headless giveaway).
_STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
window.chrome = window.chrome || { runtime: {} };
Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
try { Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8}); } catch (e) {}
try { Object.defineProperty(navigator, 'deviceMemory', {get: () => 8}); } catch (e) {}
// permissions.query reports 'denied' for notifications under headless — normalize it.
try {
  const _q = window.navigator.permissions && window.navigator.permissions.query;
  if (_q) {
    window.navigator.permissions.query = (p) =>
      p && p.name === 'notifications'
        ? Promise.resolve({ state: Notification.permission })
        : _q(p);
  }
} catch (e) {}
// WebGL vendor/renderer: headless reports 'Google SwiftShader' — spoof a real GPU.
try {
  const _gp = WebGLRenderingContext.prototype.getParameter;
  WebGLRenderingContext.prototype.getParameter = function (p) {
    if (p === 37445) return 'Intel Inc.';                 // UNMASKED_VENDOR_WEBGL
    if (p === 37446) return 'Intel Iris OpenGL Engine';   // UNMASKED_RENDERER_WEBGL
    return _gp.call(this, p);
  };
  if (window.WebGL2RenderingContext) {
    const _gp2 = WebGL2RenderingContext.prototype.getParameter;
    WebGL2RenderingContext.prototype.getParameter = function (p) {
      if (p === 37445) return 'Intel Inc.';
      if (p === 37446) return 'Intel Iris OpenGL Engine';
      return _gp2.call(this, p);
    };
  }
} catch (e) {}
"""


class LocalBrowserSession(_PlaywrightSessionBase):
    """Launches a local Chromium instance instead of connecting to Bright Data."""

    name = "local_browser"

    def __init__(self, config: ScraperConfig) -> None:
        # No require_browser() call — no Bright Data credentials needed.
        super().__init__(config)

    async def __aenter__(self) -> "LocalBrowserSession":
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:  # pragma: no cover
            raise ScraperConfigError(
                "playwright is not installed. Run:\n"
                "  pip install playwright\n"
                "  playwright install chromium"
            ) from exc

        self._pw = await async_playwright().start()
        try:
            self._browser = await self._pw.chromium.launch(
                headless=self._config.local_browser_headless,
                args=[
                    # Drops the "Chrome is being controlled by automated test
                    # software" flag and the navigator.webdriver=true signal.
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ],
            )
        except Exception as exc:  # noqa: BLE001
            await self._cleanup()
            raise TransportError(
                f"Could not launch local Chromium: {exc}\n"
                "Run 'playwright install chromium' to download the browser."
            ) from exc

        await self._finish_context_setup()
        return self

    def _context_options(self) -> dict:
        return {
            "user_agent": _USER_AGENT,
            "viewport": {"width": 1366, "height": 900},
            "locale": "en-US",
        }

    async def _apply_stealth(self) -> None:
        await self._context.add_init_script(_STEALTH_JS)
