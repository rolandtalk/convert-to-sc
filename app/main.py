from __future__ import annotations

import csv
import io
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from celery.result import AsyncResult
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.celery_app import celery_app
from app.config import settings
from app.db import (
    create_saved_list,
    create_convert_run,
    delete_watchlist_symbol,
    fetch_picks,
    get_convert_run,
    get_saved_list,
    init_db,
    latest_run,
    latest_runs,
    list_convert_runs,
    list_convert_symbols,
    list_saved_list_symbols,
    list_saved_lists,
    list_watchlist_symbols,
    upsert_watchlist_symbol,
)
from app.jobs import shutdown_scheduler, start_scheduler
from app.tasks import build_convert_run_key, capture_convert_run_task, run_convert_capture, run_sctr_pipeline_task
from app.services.symbol_extract import extract_symbols
from app.services.ticker_universe import validate_symbol_candidates
from app.services.vision_extract import extract_symbols_from_image_data


BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
ARTIFACTS_DIR = settings.screenshot_output_dir


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    start_scheduler()
    yield
    shutdown_scheduler()


app = FastAPI(title="Convert to SC", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/artifacts", StaticFiles(directory=ARTIFACTS_DIR), name="artifacts")


class ExtractRequest(BaseModel):
    text: str = Field(default="")


class ConvertRunRequest(BaseModel):
    text: str = Field(default="")
    symbols: list[str] = Field(default_factory=list)


class ValidateSymbolsRequest(BaseModel):
    candidates: list[str] = Field(default_factory=list)


class WatchlistRequest(BaseModel):
    symbol: str = Field(default="")
    source_url: str = Field(default="")
    image_path: str = Field(default="")


class SavedListRequest(BaseModel):
    name: str = Field(default="")
    run_id: int


class ImageExtractRequest(BaseModel):
    image_data_url: str = Field(default="")


def _queue_task(task, *args, inline_runner=None, **kwargs) -> dict:
    if settings.run_tasks_inline:
        if inline_runner is None:
            raise RuntimeError("Inline runner is required when RUN_TASKS_INLINE=true.")
        result = inline_runner(*args, **kwargs)
        return {"mode": "inline", "task_id": f"inline-{uuid4()}", "result": result}

    try:
        async_result = task.delay(*args, **kwargs)
        return {"mode": "queued", "task_id": async_result.id, "result": None}
    except Exception:
        if inline_runner is None:
            raise
        result = inline_runner(*args, **kwargs)
        return {"mode": "inline-fallback", "task_id": f"inline-{uuid4()}", "result": result}


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/watchlist", response_class=HTMLResponse)
def watchlist_page():
    return """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta name="theme-color" content="#07111f" />
    <title>Convert to SC Watch List</title>
    <style>
      :root {
        --paper: #f8f4ea;
        --ink: #1d1a16;
        --muted: #6f6657;
        --line: rgba(77, 67, 49, 0.14);
        --line-strong: rgba(77, 67, 49, 0.28);
        --blue: #375f8c;
        --red: #8a3b34;
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        min-height: 100vh;
        color: var(--ink);
        font-family: "Iowan Old Style", "Palatino Linotype", Georgia, serif;
        background:
          linear-gradient(180deg, rgba(255,255,255,0.55), rgba(255,255,255,0.1)),
          linear-gradient(180deg, #d8d2c7 0%, #cbc4b7 100%);
      }
      .shell {
        max-width: 1080px;
        margin: 0 auto;
        padding:
          calc(22px + env(safe-area-inset-top, 0px))
          calc(18px + env(safe-area-inset-right, 0px))
          calc(40px + env(safe-area-inset-bottom, 0px))
          calc(18px + env(safe-area-inset-left, 0px));
      }
      .topbar {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        margin-bottom: 14px;
      }
      .back,
      .button {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-height: 48px;
        padding: 0 18px;
        border-radius: 999px;
        border: 1px solid var(--line-strong);
        color: var(--ink);
        text-decoration: none;
        background: rgba(255,255,255,0.52);
        cursor: pointer;
        font: inherit;
      }
      .hero {
        padding: 18px;
        border-radius: 8px;
        border: 1px solid rgba(89, 78, 59, 0.18);
        background:
          linear-gradient(180deg, rgba(255,255,255,0.65), rgba(255,255,255,0)),
          var(--paper);
        box-shadow: 0 22px 50px rgba(77, 67, 49, 0.18);
      }
      h1 {
        margin: 0;
        font-size: 1.35rem;
        line-height: 1.1;
      }
      .status,
      .meta {
        color: var(--muted);
        line-height: 1.6;
      }
      .list {
        display: grid;
        gap: 8px;
        margin-top: 14px;
      }
      .card {
        display: grid;
        grid-template-columns: 110px minmax(0, 1fr) auto;
        align-items: center;
        gap: 12px;
        padding: 10px 12px;
        border-radius: 4px;
        border: 1px solid var(--line);
        background: rgba(255,255,255,0.52);
      }
      .symbol {
        margin: 0;
        font-family: "SFMono-Regular", Menlo, Monaco, Consolas, monospace;
        font-size: 1rem;
      }
      .remove {
        border-color: rgba(138,59,52,0.22);
        color: var(--red);
        min-height: 38px;
        padding: 0 14px;
      }
      .links {
        display: flex;
        gap: 12px;
        flex-wrap: nowrap;
      }
      .action-link {
        border: 0;
        padding: 0;
        background: transparent;
        color: var(--blue);
        text-decoration: underline;
        white-space: nowrap;
        cursor: pointer;
        font: inherit;
      }
      .row-meta {
        display: flex;
        align-items: center;
        gap: 14px;
        min-width: 0;
        flex-wrap: nowrap;
        overflow: hidden;
      }
      .added-date {
        white-space: nowrap;
        font-size: 0.92rem;
      }
      .page-head {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        padding-bottom: 10px;
        border-bottom: 1px solid var(--line);
      }
      .empty {
        margin-top: 14px;
        padding: 18px;
        border: 1px solid var(--line);
        background: rgba(255,255,255,0.42);
        color: var(--muted);
      }
      @media (max-width: 720px) {
        .shell {
          padding:
            calc(12px + env(safe-area-inset-top, 0px))
            calc(12px + env(safe-area-inset-right, 0px))
            calc(28px + env(safe-area-inset-bottom, 0px))
            calc(12px + env(safe-area-inset-left, 0px));
        }
        .card {
          grid-template-columns: 84px minmax(0, 1fr) auto;
          gap: 10px;
          padding: 8px 10px;
        }
        .page-head {
          align-items: flex-start;
          flex-direction: column;
        }
        .symbol {
          font-size: 0.92rem;
        }
        .added-date,
        .links a {
          font-size: 0.82rem;
        }
        .remove {
          min-height: 32px;
          padding: 0 10px;
          font-size: 0.82rem;
        }
      }
    </style>
  </head>
  <body>
    <div class="shell">
      <div class="topbar">
        <a class="back" href="/" onclick="if (window.history.length > 1) { event.preventDefault(); window.history.back(); }">Back</a>
      </div>
      <section class="hero">
        <div class="page-head">
          <h1>Watch List</h1>
        </div>
        <div id="watchList" class="list"></div>
      </section>
    </div>
    <script>
      function escapeHtml(value) {
        return String(value)
          .replaceAll("&", "&amp;")
          .replaceAll("<", "&lt;")
          .replaceAll(">", "&gt;")
          .replaceAll('"', "&quot;")
          .replaceAll("'", "&#039;");
      }

      function formatDate(value) {
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return value || "";
        return date.toLocaleDateString(undefined, {
          year: "2-digit",
          month: "2-digit",
          day: "2-digit"
        });
      }

      async function loadWatchList() {
        const response = await fetch("/api/watchlist");
        const json = await response.json();
        if (json.status !== "ok") throw new Error(json.detail || "Failed to load watch list");

        const container = document.getElementById("watchList");
        if (!json.items.length) {
          container.innerHTML = `<div class="empty">No watched symbols yet. Use <strong>+ Watch</strong> from the combined chart page to save names here.</div>`;
          return;
        }

        container.innerHTML = json.items.map((item) => `
          <article class="card">
            <h2 class="symbol">${escapeHtml(item.symbol)}</h2>
            <div class="row-meta meta">
              <span class="added-date">Added ${escapeHtml(formatDate(item.added_at))}</span>
              <div class="links">
                ${item.source_url ? `<button type="button" class="action-link" data-open-url="${escapeHtml(item.source_url)}">Source</button>` : ""}
                ${item.image_url ? `<button type="button" class="action-link" data-open-url="${escapeHtml(item.image_url)}">PNG</button>` : ""}
              </div>
            </div>
            <div>
              <button class="button remove" data-symbol="${escapeHtml(item.symbol)}">Remove</button>
            </div>
          </article>
        `).join("");

        for (const button of container.querySelectorAll("[data-symbol]")) {
          button.onclick = async () => {
            const symbol = button.getAttribute("data-symbol");
            const removeResponse = await fetch(`/api/watchlist/${encodeURIComponent(symbol)}`, { method: "DELETE" });
            const removeJson = await removeResponse.json();
            if (removeJson.status !== "ok") throw new Error(removeJson.detail || "Failed to remove symbol");
            await loadWatchList();
          };
        }

        for (const button of container.querySelectorAll("[data-open-url]")) {
          button.onclick = () => {
            const url = button.getAttribute("data-open-url");
            if (url) {
              window.location.href = url;
            }
          };
        }
      }

      loadWatchList().catch((error) => {
        document.getElementById("watchList").innerHTML = `<div class="empty">${escapeHtml(error.message)}</div>`;
      });
    </script>
  </body>
</html>
"""


@app.get("/saved-lists", response_class=HTMLResponse)
def saved_lists_page():
    return """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta name="theme-color" content="#07111f" />
    <title>Convert to SC Saved Lists</title>
    <style>
      :root {
        --paper: #f8f4ea;
        --ink: #1d1a16;
        --muted: #6f6657;
        --line: rgba(77, 67, 49, 0.14);
        --line-strong: rgba(77, 67, 49, 0.28);
        --blue: #375f8c;
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        min-height: 100vh;
        color: var(--ink);
        font-family: "Iowan Old Style", "Palatino Linotype", Georgia, serif;
        background:
          linear-gradient(180deg, rgba(255,255,255,0.55), rgba(255,255,255,0.1)),
          linear-gradient(180deg, #d8d2c7 0%, #cbc4b7 100%);
      }
      .shell {
        max-width: 1080px;
        margin: 0 auto;
        padding:
          calc(22px + env(safe-area-inset-top, 0px))
          calc(18px + env(safe-area-inset-right, 0px))
          calc(40px + env(safe-area-inset-bottom, 0px))
          calc(18px + env(safe-area-inset-left, 0px));
      }
      .topbar {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        margin-bottom: 14px;
      }
      .back {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-height: 48px;
        padding: 0 18px;
        border-radius: 999px;
        border: 1px solid var(--line-strong);
        color: var(--ink);
        text-decoration: none;
        background: rgba(255,255,255,0.52);
      }
      .hero {
        padding: 18px;
        border-radius: 8px;
        border: 1px solid rgba(89, 78, 59, 0.18);
        background:
          linear-gradient(180deg, rgba(255,255,255,0.65), rgba(255,255,255,0)),
          var(--paper);
        box-shadow: 0 22px 50px rgba(77, 67, 49, 0.18);
      }
      h1 {
        margin: 0;
        font-size: 1.35rem;
        line-height: 1.1;
      }
      .list {
        display: grid;
        gap: 10px;
        margin-top: 14px;
      }
      .row {
        display: grid;
        grid-template-columns: minmax(0, 1.2fr) auto;
        gap: 12px;
        padding: 12px 14px;
        border: 1px solid var(--line);
        border-radius: 4px;
        background: rgba(255,255,255,0.52);
      }
      .row-link {
        display: block;
        color: inherit;
        text-decoration: none;
      }
      .row-link:hover .row {
        border-color: var(--line-strong);
        background: rgba(255,255,255,0.66);
      }
      .row h2 {
        margin: 0;
        font-size: 1rem;
      }
      .meta {
        margin-top: 4px;
        color: var(--muted);
        line-height: 1.5;
      }
      .symbols {
        margin-top: 6px;
        font-family: "SFMono-Regular", Menlo, Monaco, Consolas, monospace;
        font-size: 0.92rem;
        color: var(--blue);
      }
      .empty {
        margin-top: 14px;
        padding: 18px;
        border: 1px solid var(--line);
        background: rgba(255,255,255,0.42);
        color: var(--muted);
      }
      @media (max-width: 720px) {
        .row {
          grid-template-columns: 1fr;
        }
      }
    </style>
  </head>
  <body>
    <div class="shell">
      <div class="topbar">
        <a class="back" href="/" onclick="if (window.history.length > 1) { event.preventDefault(); window.history.back(); }">Back</a>
      </div>
      <section class="hero">
        <h1>Saved Lists</h1>
        <div id="savedLists" class="list"></div>
      </section>
    </div>
    <script>
      function escapeHtml(value) {
        return String(value)
          .replaceAll("&", "&amp;")
          .replaceAll("<", "&lt;")
          .replaceAll(">", "&gt;")
          .replaceAll('"', "&quot;")
          .replaceAll("'", "&#039;");
      }

      function formatDate(value) {
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return value || "";
        return date.toLocaleDateString(undefined, {
          year: "numeric",
          month: "2-digit",
          day: "2-digit"
        });
      }

      async function loadSavedLists() {
        const response = await fetch("/api/saved-lists");
        const json = await response.json();
        if (json.status !== "ok") throw new Error(json.detail || "Failed to load saved lists");

        const container = document.getElementById("savedLists");
        if (!json.items.length) {
          container.innerHTML = `<div class="empty">No saved sheets yet. Use the <strong>Save</strong> box on a combined results page to keep a sheet locally.</div>`;
          return;
        }

        container.innerHTML = json.items.map((item) => `
          <a class="row-link" href="/results/${escapeHtml(String(item.run_id || ""))}">
            <article class="row">
              <div>
                <h2>${escapeHtml(item.name)}</h2>
                <div class="meta">${escapeHtml(formatDate(item.created_at))} · ${escapeHtml(String(item.symbol_count || 0))} symbols</div>
                <div class="symbols">${escapeHtml(item.symbols || "")}</div>
              </div>
              <div class="meta">Run #${escapeHtml(String(item.run_id || ""))}</div>
            </article>
          </a>
        `).join("");
      }

      loadSavedLists().catch((error) => {
        document.getElementById("savedLists").innerHTML = `<div class="empty">${escapeHtml(error.message)}</div>`;
      });
    </script>
  </body>
</html>
"""


@app.get("/results/{run_id}", response_class=HTMLResponse)
def results_page(run_id: int):
    return f"""
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta name="theme-color" content="#07111f" />
    <title>Convert to SC Results</title>
    <style>
      :root {{
        --bg: #d6d1c5;
        --paper: #f8f4ea;
        --paper-edge: #e5decd;
        --ink: #1d1a16;
        --muted: #6f6657;
        --line: rgba(77, 67, 49, 0.14);
        --line-strong: rgba(77, 67, 49, 0.28);
        --blue: #375f8c;
        --green: #35684a;
        --amber: #9a6d1a;
        --red: #8a3b34;
      }}
      * {{ box-sizing: border-box; }}
      body {{
        margin: 0;
        min-height: 100vh;
        color: var(--ink);
        font-family: "Iowan Old Style", "Palatino Linotype", Georgia, serif;
        background:
          linear-gradient(180deg, rgba(255,255,255,0.55), rgba(255,255,255,0.1)),
          linear-gradient(180deg, #d8d2c7 0%, #cbc4b7 100%);
      }}
      .shell {{
        max-width: 1280px;
        margin: 0 auto;
        padding:
          calc(22px + env(safe-area-inset-top, 0px))
          calc(18px + env(safe-area-inset-right, 0px))
          calc(40px + env(safe-area-inset-bottom, 0px))
          calc(18px + env(safe-area-inset-left, 0px));
      }}
      .topbar {{
        display: flex;
        align-items: center;
        justify-content: flex-start;
        margin-bottom: 14px;
      }}
      .back {{
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-height: 48px;
        padding: 0 18px;
        border-radius: 999px;
        border: 1px solid var(--line-strong);
        color: var(--ink);
        text-decoration: none;
        background: rgba(255,255,255,0.52);
      }}
      .hero {{
        position: relative;
        overflow: hidden;
        padding: 34px;
        border-radius: 8px;
        border: 1px solid rgba(89, 78, 59, 0.18);
        background:
          linear-gradient(180deg, rgba(255,255,255,0.65), rgba(255,255,255,0)),
          var(--paper);
        box-shadow:
          0 2px 0 rgba(88, 76, 57, 0.05),
          0 22px 50px rgba(77, 67, 49, 0.18);
      }}
      .status {{
        color: var(--muted);
        margin-top: 8px;
      }}
      .summary {{
        display: grid;
        grid-template-columns: minmax(140px, 0.8fr) minmax(0, 2.6fr);
        gap: 12px;
        margin-top: 20px;
      }}
      .summary-card {{
        padding: 14px 16px;
        border: 1px solid var(--line);
        border-radius: 6px;
        background: rgba(255,255,255,0.42);
      }}
      .summary-label {{
        color: var(--muted);
        font-size: 0.88rem;
      }}
      .summary-value {{
        margin-top: 6px;
        font-size: 1.45rem;
        font-family: "SFMono-Regular", Menlo, Monaco, Consolas, monospace;
      }}
      .saved-list-name {{
        margin-top: 6px;
        font-size: 1.2rem;
        line-height: 1.25;
        font-weight: 600;
        word-break: normal;
        overflow-wrap: anywhere;
      }}
      .saved-list-head {{
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 16px;
      }}
      .saved-list-copy {{
        min-width: 0;
        flex: 1;
      }}
      .save-panel {{
        min-width: 260px;
      }}
      .save-panel.hidden {{
        display: none;
      }}
      .save-row {{
        display: flex;
        align-items: center;
        gap: 10px;
        margin-top: 10px;
      }}
      .save-input {{
        flex: 1;
        min-width: 0;
        min-height: 44px;
        padding: 0 12px;
        border: 1px solid var(--line-strong);
        border-radius: 999px;
        background: rgba(255,255,255,0.65);
        color: var(--ink);
        font: inherit;
      }}
      .save-button {{
        min-width: 44px;
        min-height: 44px;
        border: 1px solid rgba(53,104,74,0.2);
        border-radius: 999px;
        background: rgba(53,104,74,0.08);
        color: var(--green);
        cursor: pointer;
        font: inherit;
        font-size: 1.3rem;
        line-height: 1;
      }}
      .save-note {{
        margin-top: 8px;
        color: var(--muted);
        font-size: 0.9rem;
        min-height: 20px;
      }}
      .grid {{
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 22px;
        margin-top: 26px;
      }}
      .card {{
        overflow: hidden;
        border-radius: 4px;
        border: 1px solid var(--line);
        background: rgba(255,255,255,0.52);
        box-shadow: inset 0 1px 0 rgba(255,255,255,0.45);
      }}
      .card img {{
        display: block;
        width: 100%;
        height: auto;
        background: #ffffff;
        border-bottom: 1px solid var(--line);
      }}
      .card-body {{
        padding: 16px 18px 18px;
      }}
      .symbol {{
        font-family: "SFMono-Regular", Menlo, Monaco, Consolas, monospace;
        font-size: 1.25rem;
        margin: 0 0 8px;
      }}
      .meta {{
        color: var(--muted);
        word-break: break-word;
      }}
      .links {{
        display: flex;
        gap: 12px;
        flex-wrap: wrap;
        margin-top: 14px;
      }}
      .links a {{
        color: var(--blue);
        text-decoration: none;
      }}
      .links a:hover {{
        text-decoration: underline;
      }}
      .badge {{
        display: inline-flex;
        align-items: center;
        justify-content: center;
        padding: 7px 10px;
        border-radius: 999px;
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        border: 1px solid transparent;
      }}
      .ok {{ color: var(--green); background: rgba(53,104,74,0.09); border-color: rgba(53,104,74,0.16); }}
      .running {{ color: var(--blue); background: rgba(55,95,140,0.08); border-color: rgba(55,95,140,0.16); }}
      .failed {{ color: var(--red); background: rgba(138,59,52,0.08); border-color: rgba(138,59,52,0.16); }}
      .queued {{ color: var(--amber); background: rgba(154,109,26,0.08); border-color: rgba(154,109,26,0.16); }}
      .watch-btn {{
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-height: 40px;
        padding: 0 16px;
        border-radius: 999px;
        border: 1px solid rgba(53,104,74,0.18);
        background: rgba(53,104,74,0.08);
        color: var(--green);
        font: inherit;
        cursor: pointer;
      }}
      .watch-btn.saved {{
        background: rgba(55,95,140,0.08);
        border-color: rgba(55,95,140,0.18);
        color: var(--blue);
      }}
      .empty-card {{
        padding: 28px;
        border-radius: 4px;
        border: 1px solid var(--line);
        background: rgba(255,255,255,0.42);
        color: var(--muted);
      }}
      .card-head {{
        display:flex;
        align-items:flex-start;
        justify-content:space-between;
        gap:12px;
        padding-bottom: 12px;
        border-bottom: 1px dashed var(--line);
      }}
      @media (max-width: 720px) {{
        .shell {{
          padding:
            calc(12px + env(safe-area-inset-top, 0px))
            calc(12px + env(safe-area-inset-right, 0px))
            calc(28px + env(safe-area-inset-bottom, 0px))
            calc(12px + env(safe-area-inset-left, 0px));
        }}
        .topbar {{
          align-items: flex-start;
        }}
        .summary {{
          grid-template-columns: 1fr;
        }}
        .saved-list-head {{
          flex-direction: column;
          gap: 12px;
        }}
        .saved-list-copy,
        .save-panel {{
          width: 100%;
          min-width: 0;
        }}
        .saved-list-name {{
          font-size: 1rem;
        }}
        .save-row {{
          flex-wrap: wrap;
        }}
        .grid {{
          grid-template-columns: 1fr;
        }}
      }}
    </style>
  </head>
  <body>
    <div class="shell">
      <div class="topbar">
        <a class="back" href="/" onclick="if (window.history.length > 1) {{ event.preventDefault(); window.history.back(); }}">Go Back to Home</a>
      </div>
      <section class="hero">
        <div id="runStatus" class="status">Preparing screenshots...</div>
        <div class="summary">
          <div class="summary-card">
            <div class="summary-label">Run</div>
            <div id="summaryRun" class="summary-value">#{run_id}</div>
          </div>
          <div class="summary-card">
            <div class="saved-list-head">
              <div class="saved-list-copy">
                <div class="summary-label">Saved List Name</div>
                <div id="summarySavedName" class="saved-list-name">Not saved yet</div>
              </div>
              <div id="savePanel" class="save-panel">
                <div class="summary-label">Save</div>
                <div class="save-row">
                  <span>Save:</span>
                    <input id="saveSheetName" class="save-input" placeholder="Sheet name" list="savedSheetNames" />
                  <button id="saveSheetBtn" class="save-button" type="button">+</button>
                </div>
              </div>
            </div>
            <div id="saveSheetNote" class="save-note"></div>
            <datalist id="savedSheetNames"></datalist>
          </div>
        </div>
        <div id="cards" class="grid"></div>
      </section>
    </div>
    <script>
      const runId = {run_id};
      let pollHandle = null;
      let watchedSymbols = new Set();
      let savedLists = [];

      function badgeClass(status) {{
        if (status === "ok" || status === "ready") return "badge ok";
        if (status === "running") return "badge running";
        if (status === "failed") return "badge failed";
        return "badge queued";
      }}

      function escapeHtml(value) {{
        return String(value)
          .replaceAll("&", "&amp;")
          .replaceAll("<", "&lt;")
          .replaceAll(">", "&gt;")
          .replaceAll('"', "&quot;")
          .replaceAll("'", "&#039;");
      }}

      async function loadWatchedSymbols() {{
        const response = await fetch("/api/watchlist");
        const json = await response.json();
        if (json.status !== "ok") throw new Error(json.detail || "Failed to load watched symbols");
        watchedSymbols = new Set((json.items || []).map((item) => item.symbol));
      }}

      async function loadSavedLists() {{
        const response = await fetch("/api/saved-lists");
        const json = await response.json();
        if (json.status !== "ok") throw new Error(json.detail || "Failed to load saved lists");
        savedLists = json.items || [];
      }}

      async function addToWatch(symbol, sourceUrl, imagePath) {{
        const response = await fetch("/api/watchlist", {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify({{
            symbol,
            source_url: sourceUrl || "",
            image_path: imagePath || ""
          }})
        }});
        const json = await response.json();
        if (json.status !== "ok") throw new Error(json.detail || "Failed to add symbol to watch list");
        watchedSymbols.add(symbol);
      }}

      async function saveCurrentSheet() {{
        const input = document.getElementById("saveSheetName");
        const note = document.getElementById("saveSheetNote");
        const name = (input.value || "").trim();
        if (!name) {{
          note.textContent = "Enter a name first.";
          input.focus();
          return;
        }}
        note.textContent = "Saving...";
        const response = await fetch("/api/saved-lists", {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify({{ name, run_id: runId }})
        }});
        const json = await response.json();
        if (json.status !== "ok") throw new Error(json.detail || "Failed to save sheet");
        note.textContent = `Saved as ${{json.name}}.`;
        input.value = "";
      }}

      async function loadRun() {{
        await loadWatchedSymbols();
        await loadSavedLists();
        const response = await fetch(`/api/convert/runs/${{runId}}`);
        const json = await response.json();
        if (json.status !== "ok") throw new Error(json.detail || "Failed to load run");
        const matchedSavedList = savedLists.find((item) => Number(item.run_id || 0) === Number(runId));
        const savePanel = document.getElementById("savePanel");

        document.getElementById("summaryRun").textContent = `#${{json.run.id}}`;
        document.getElementById("summarySavedName").textContent = matchedSavedList?.name || "Not saved yet";
        savePanel.classList.toggle("hidden", Boolean(matchedSavedList?.name));
        document.getElementById("runStatus").textContent =
          json.run.status === "ok"
            ? "All captured charts are combined below."
            : json.run.status === "failed"
              ? (json.run.error_message || "This run failed before completion.")
              : "Generating charts. This page will update automatically.";
        document.getElementById("savedSheetNames").innerHTML = savedLists.map((item) => `<option value="${{escapeHtml(item.name)}}"></option>`).join("");

        const cards = document.getElementById("cards");
        if (!json.symbols.length) {{
          cards.innerHTML = `<div class="empty-card">No chart cards are ready yet. This page will keep updating until the capture run finishes.</div>`;
          return;
        }}

        cards.innerHTML = json.symbols.map((item) => `
          <article class="card">
            ${{item.image_url ? `<img src="${{item.image_url}}" alt="${{item.symbol}} chart" />` : `<div class="card-body"><div class="${{badgeClass(item.status)}}">${{escapeHtml(item.status)}}</div></div>`}}
            <div class="card-body">
              <div class="card-head">
                <h2 class="symbol">${{escapeHtml(item.symbol)}}</h2>
                ${{
                  item.status === "ready"
                    ? `<button class="watch-btn ${{watchedSymbols.has(item.symbol) ? "saved" : ""}}" data-watch-symbol="${{escapeHtml(item.symbol)}}" data-watch-source="${{escapeHtml(item.source_url || "")}}" data-watch-image="${{escapeHtml(item.image_path || "")}}">${{watchedSymbols.has(item.symbol) ? "Watching" : "+ Watch"}}</button>`
                    : `<span class="${{badgeClass(item.status)}}">${{escapeHtml(item.status)}}</span>`
                }}
              </div>
              <div class="meta" style="margin-top:12px;">${{escapeHtml(item.source_url || item.error_message || "Waiting for capture")}}</div>
              <div class="links">
                ${{item.image_url ? `<a href="${{item.image_url}}" target="_blank" rel="noreferrer">Open PNG</a>` : ""}}
                ${{item.source_url ? `<a href="${{item.source_url}}" target="_blank" rel="noreferrer">Open source chart</a>` : ""}}
              </div>
            </div>
          </article>
        `).join("");

        for (const button of cards.querySelectorAll("[data-watch-symbol]")) {{
          button.onclick = async () => {{
            const symbol = button.getAttribute("data-watch-symbol");
            const sourceUrl = button.getAttribute("data-watch-source") || "";
            const imagePath = button.getAttribute("data-watch-image") || "";
            try {{
              await addToWatch(symbol, sourceUrl, imagePath);
              button.textContent = "Watching";
              button.classList.add("saved");
            }} catch (error) {{
              document.getElementById("runStatus").textContent = error.message;
            }}
          }};
        }}

        const saveButton = document.getElementById("saveSheetBtn");
        if (saveButton) {{
          saveButton.onclick = () => {{
            saveCurrentSheet().catch((error) => {{
              document.getElementById("saveSheetNote").textContent = error.message;
            }});
          }};
        }}

        if (json.run.status === "ok" || json.run.status === "failed") {{
          if (pollHandle) {{
            clearInterval(pollHandle);
            pollHandle = null;
          }}
        }}
      }}

      pollHandle = setInterval(() => {{
        loadRun().catch((error) => {{
          document.getElementById("runStatus").textContent = error.message;
        }});
      }}, 1500);

      loadRun().catch((error) => {{
        document.getElementById("runStatus").textContent = error.message;
      }});
    </script>
  </body>
</html>
"""


@app.exception_handler(RuntimeError)
async def runtime_error_handler(_, exc: RuntimeError):
    return JSONResponse(status_code=500, content={"status": "error", "detail": str(exc)})


@app.get("/healthz")
def healthz():
    return {
        "status": "ok",
        "app": "convert-to-sc",
        "artifacts_dir": str(ARTIFACTS_DIR),
        "sqlite_path": str(settings.sqlite_path),
        "run_tasks_inline": settings.run_tasks_inline,
    }


@app.get("/api/config/status")
def api_config_status():
    return {
        "status": "ok",
        "openai_vision_enabled": bool(settings.openai_api_key),
        "openai_vision_model": settings.openai_vision_model,
    }


@app.get("/api/picks/latest")
def api_latest_picks(
    q: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
):
    run = latest_run()
    if not run:
        return {"status": "empty", "data": [], "total": 0, "page": page, "page_size": page_size}

    offset = (page - 1) * page_size
    total, rows = fetch_picks(int(run["id"]), q=q, offset=offset, limit=page_size)
    return {
        "status": "ok",
        "run": dict(run),
        "data": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@app.get("/api/runs/latest")
def api_latest_runs(limit: int = Query(default=10, ge=1, le=100)):
    rows = latest_runs(limit=limit)
    return {"status": "ok", "data": [dict(r) for r in rows]}


@app.post("/api/convert/extract")
def api_extract_symbols(payload: ExtractRequest):
    symbols = extract_symbols(payload.text)
    return {"status": "ok", "symbols": symbols, "count": len(symbols)}


@app.post("/api/convert/validate")
def api_validate_symbols(payload: ValidateSymbolsRequest):
    symbols = validate_symbol_candidates(payload.candidates)
    return {"status": "ok", "symbols": symbols, "count": len(symbols)}


@app.post("/api/convert/extract-image")
def api_extract_symbols_from_image(payload: ImageExtractRequest):
    symbols = extract_symbols_from_image_data(payload.image_data_url)
    return {"status": "ok", "symbols": symbols, "count": len(symbols)}


@app.post("/api/convert/runs")
def api_create_convert_run(payload: ConvertRunRequest):
    symbols = payload.symbols or extract_symbols(payload.text)
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="Source text is required.")
    if not symbols:
        raise HTTPException(status_code=400, detail="No symbols were found.")

    run_id = create_convert_run(
        run_key=build_convert_run_key(),
        source_text=payload.text.strip(),
        symbols=symbols,
    )
    queued = _queue_task(capture_convert_run_task, run_id=run_id, inline_runner=run_convert_capture)
    return {
        "status": "queued" if queued["mode"] == "queued" else "ok",
        "mode": queued["mode"],
        "run_id": run_id,
        "task_id": queued["task_id"],
        "result": queued["result"],
        "symbols": symbols,
    }


@app.get("/api/convert/runs")
def api_list_convert_runs(limit: int = Query(default=10, ge=1, le=100)):
    rows = list_convert_runs(limit=limit)
    return {"status": "ok", "data": [dict(row) for row in rows]}


@app.get("/api/convert/runs/{run_id}")
def api_get_convert_run(run_id: int):
    run = get_convert_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found.")
    symbols = []
    for row in list_convert_symbols(run_id):
        item = dict(row)
        if item.get("image_path"):
            version = str(item.get("updated_at") or "").replace(":", "").replace("-", "")
            item["image_url"] = f"/artifacts/{item['image_path']}?v={version}"
        else:
            item["image_url"] = None
        symbols.append(item)
    return {"status": "ok", "run": dict(run), "symbols": symbols}


@app.get("/api/watchlist")
def api_list_watchlist():
    items = []
    for row in list_watchlist_symbols():
        item = dict(row)
        item["image_url"] = f"/artifacts/{item['image_path']}" if item.get("image_path") else None
        items.append(item)
    return {"status": "ok", "items": items}


@app.post("/api/watchlist")
def api_add_watchlist_symbol(payload: WatchlistRequest):
    symbol = payload.symbol.strip().upper()
    if not symbol:
        raise HTTPException(status_code=400, detail="Symbol is required.")
    watch_id = upsert_watchlist_symbol(
        symbol=symbol,
        source_url=payload.source_url.strip(),
        image_path=payload.image_path.strip(),
    )
    return {"status": "ok", "id": watch_id, "symbol": symbol}


@app.get("/api/saved-lists")
def api_list_saved_lists():
    items = []
    for row in list_saved_lists():
        item = dict(row)
        item["symbol_count"] = int(item.get("symbol_count") or 0)
        item["symbols"] = item.get("symbols") or ""
        items.append(item)
    return {"status": "ok", "items": items}


@app.post("/api/saved-lists")
def api_create_saved_list(payload: SavedListRequest):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Saved list name is required.")

    run = get_convert_run(payload.run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found.")

    symbols = [str(row["symbol"]).strip().upper() for row in list_convert_symbols(payload.run_id) if str(row["symbol"]).strip()]
    if not symbols:
        raise HTTPException(status_code=400, detail="No symbols available to save.")

    saved_list_id = create_saved_list(name=name, run_id=payload.run_id, symbols=symbols)
    saved_list = get_saved_list(saved_list_id)
    saved_symbols = [dict(row) for row in list_saved_list_symbols(saved_list_id)]
    return {
        "status": "ok",
        "id": saved_list_id,
        "name": saved_list["name"] if saved_list else name,
        "created_at": saved_list["created_at"] if saved_list else "",
        "symbols": [row["symbol"] for row in saved_symbols],
    }


@app.delete("/api/watchlist/{symbol}")
def api_delete_watchlist_symbol(symbol: str):
    deleted = delete_watchlist_symbol(symbol)
    if not deleted:
        raise HTTPException(status_code=404, detail="Symbol not found in watch list.")
    return {"status": "ok", "symbol": symbol.upper()}


@app.post("/api/jobs/run")
def api_run_job():
    queued = _queue_task(run_sctr_pipeline_task, source="manual", inline_runner=lambda source="manual": run_sctr_pipeline_task.run(source=source))
    return {
        "status": "queued" if queued["mode"] == "queued" else "ok",
        "mode": queued["mode"],
        "task_id": queued["task_id"],
        "result": queued["result"],
    }


@app.get("/api/export/latest.csv")
def api_export_latest_csv():
    run = latest_run()
    if not run:
        raise HTTPException(status_code=404, detail="No successful run found.")

    _, rows = fetch_picks(int(run["id"]), q="", offset=0, limit=5000)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["rank", "symbol", "sctr", "perf_1d", "perf_5d", "perf_20d", "perf_60d", "rsi_14"])
    for r in rows:
        writer.writerow([
            r["rank"],
            r["symbol"],
            r["sctr"],
            r["perf_1d"],
            r["perf_5d"],
            r["perf_20d"],
            r["perf_60d"],
            r["rsi_14"],
        ])

    data = output.getvalue()
    filename = f"sctr_top_{len(rows)}.csv"
    return StreamingResponse(
        iter([data]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.get("/api/jobs/status/{task_id}")
def api_job_status(task_id: str):
    result = AsyncResult(task_id, app=celery_app)
    payload = {
        "task_id": task_id,
        "state": result.state,
        "result": result.result if result.successful() else None,
    }
    if result.failed():
        payload["error"] = str(result.result)
    return payload
