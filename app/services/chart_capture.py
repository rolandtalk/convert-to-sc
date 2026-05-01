from __future__ import annotations

from pathlib import Path
from app.config import settings


def chart_url(symbol: str) -> str:
    return f"{settings.chart_site_base_url.rstrip('/')}/h-sc/ui?s={symbol}"


def _safe_filename(symbol: str) -> str:
    return "".join(ch for ch in symbol.upper() if ch.isalnum() or ch in {"-", "_", "."}) or "chart"


class ChartCaptureClient:
    def __init__(self) -> None:
        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except Exception as exc:  # pragma: no cover - dependency/runtime issue
            raise RuntimeError(
                "Playwright is not installed or browsers are not available. Install Playwright and Chromium for chart capture."
            ) from exc

        self._playwright_error = PlaywrightTimeoutError
        self._sync_playwright = sync_playwright
        self._playwright_context = None
        self._browser = None
        self._page = None

    def __enter__(self) -> "ChartCaptureClient":
        self._playwright_context = self._sync_playwright().start()
        self._browser = self._playwright_context.chromium.launch(
            headless=True,
            args=["--disable-dev-shm-usage"],
        )
        self._page = self._browser.new_page(
            viewport={
                "width": settings.chart_capture_viewport_width,
                "height": settings.chart_capture_viewport_height,
            }
        )
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._browser:
            self._browser.close()
        if self._playwright_context:
            self._playwright_context.stop()

    def capture(self, run_key: str, symbol: str, output_dir: Path) -> dict[str, str]:
        output_dir.mkdir(parents=True, exist_ok=True)
        url = chart_url(symbol)
        filename = f"{run_key}-{_safe_filename(symbol)}.png"
        image_path = output_dir / filename

        try:
            self._page.goto(url, wait_until="domcontentloaded", timeout=settings.chart_capture_timeout_ms)
            self._page.wait_for_load_state("load", timeout=settings.chart_capture_timeout_ms)
            chart = self._page.locator('img[alt="SharpCharts Chart"]')
            if chart.count() != 1:
                raise RuntimeError(f"Expected one chart image for {symbol}, found {chart.count()}.")
            chart.wait_for(state="visible", timeout=settings.chart_capture_timeout_ms)
            chart.screenshot(path=str(image_path))
        except self._playwright_error as exc:
            raise RuntimeError(f"Timed out while capturing {symbol}.") from exc

        return {
            "symbol": symbol,
            "source_url": url,
            "image_filename": filename,
        }


def capture_symbol_chart(run_key: str, symbol: str, output_dir: Path) -> dict[str, str]:
    with ChartCaptureClient() as client:
        return client.capture(run_key, symbol, output_dir)


def capture_symbol_charts(run_key: str, symbols: list[str], output_dir: Path) -> list[dict[str, str]]:
    try:
        captures: list[dict[str, str]] = []
        with ChartCaptureClient() as client:
            for symbol in symbols:
                captures.append(client.capture(run_key, symbol, output_dir))
        return captures
    except Exception:
        raise
