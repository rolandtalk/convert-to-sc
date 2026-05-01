from __future__ import annotations

import asyncio
from pathlib import Path

from app.config import settings

REAL_CHART_SELECTOR = 'img[alt="SharpCharts Chart"][src*="/c-sc/sc?"]'


def chart_url(symbol: str) -> str:
    return f"{settings.chart_site_base_url.rstrip('/')}/h-sc/ui?s={symbol}"


def _safe_filename(symbol: str) -> str:
    return "".join(ch for ch in symbol.upper() if ch.isalnum() or ch in {"-", "_", "."}) or "chart"


class ChartCaptureClient:
    def __init__(self) -> None:
        try:
            from playwright.async_api import TimeoutError as PlaywrightTimeoutError
            from playwright.async_api import async_playwright
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                "Playwright is not installed or browsers are not available. Install Playwright and Chromium for chart capture."
            ) from exc

        self._playwright_error = PlaywrightTimeoutError
        self._async_playwright = async_playwright

    async def _wait_for_chart_image(self, page) -> object:
        chart = page.locator(REAL_CHART_SELECTOR)
        await chart.wait_for(state="visible", timeout=settings.chart_capture_timeout_ms)
        await page.wait_for_function(
            f"""
            () => {{
              const img = document.querySelector({REAL_CHART_SELECTOR!r});
              if (!img) return false;
              const width = Number(img.naturalWidth || 0);
              const height = Number(img.naturalHeight || 0);
              const src = String(img.currentSrc || img.src || "");
              return img.complete
                && width > 300
                && height > 180
                && src.length > 0
                && src.includes("/c-sc/sc?");
            }}
            """,
            timeout=settings.chart_capture_timeout_ms,
        )
        return chart

    async def _capture_async(self, run_key: str, symbol: str, output_dir: Path) -> dict[str, str]:
        output_dir.mkdir(parents=True, exist_ok=True)
        url = chart_url(symbol)
        filename = f"{run_key}-{_safe_filename(symbol)}.png"
        image_path = output_dir / filename

        async with self._async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                headless=True,
                args=["--disable-dev-shm-usage"],
            )
            try:
                page = await browser.new_page(
                    viewport={
                        "width": settings.chart_capture_viewport_width,
                        "height": settings.chart_capture_viewport_height,
                    }
                )
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=settings.chart_capture_timeout_ms)
                    await page.wait_for_load_state("load", timeout=settings.chart_capture_timeout_ms)
                    try:
                        chart = await self._wait_for_chart_image(page)
                        await chart.screenshot(path=str(image_path))
                    except self._playwright_error:
                        await page.screenshot(path=str(image_path), full_page=False)
                except self._playwright_error as exc:
                    raise RuntimeError(f"Timed out while capturing {symbol}.") from exc
            finally:
                await browser.close()

        return {
            "symbol": symbol,
            "source_url": url,
            "image_filename": filename,
        }

    def capture(self, run_key: str, symbol: str, output_dir: Path) -> dict[str, str]:
        return asyncio.run(self._capture_async(run_key, symbol, output_dir))


def capture_symbol_chart(run_key: str, symbol: str, output_dir: Path) -> dict[str, str]:
    client = ChartCaptureClient()
    return client.capture(run_key, symbol, output_dir)


def capture_symbol_charts(run_key: str, symbols: list[str], output_dir: Path) -> list[dict[str, str]]:
    client = ChartCaptureClient()
    return [client.capture(run_key, symbol, output_dir) for symbol in symbols]
