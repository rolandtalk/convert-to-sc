# Convert to SC

Convert to SC is the starter repository for a workflow that turns chart-related text into a browsable chart web app.

## Goal

The product we are building will:

1. Accept chart descriptions or chart-rich text as input.
2. Extract and normalize ticker symbols from the subject.
3. Open the relevant chart pages on StandardChart/StockCharts-style sources.
4. Capture screenshots for the matched symbols.
5. Publish those screenshots to a simple web interface.

This repository already includes a working FastAPI + Celery foundation and an SCTR scraping pipeline we can build on.

## Current Status

The current codebase provides:

- `FastAPI` web app and static frontend
- `Celery` background task infrastructure
- `Redis` task queue support
- `SQLite` persistence
- Existing `SCTR` scraping utilities from StockCharts-style pages

The screenshot workflow and text-to-symbol extraction workflow are the next features to implement.

## Production Shape

The current deployment target is:

- `convert-to-sc-production.up.railway.app`

The recommended production setup is Railway with:

- one Docker app service running both FastAPI and the Celery worker
- one Redis service
- one Railway volume mounted at `/app/data` for SQLite and screenshot files

See [docs/railway-deploy.md](docs/railway-deploy.md) for the full setup.

## Planned Workflow

### Phase 1

- Define the input format for raw chart descriptions
- Extract symbols from text
- Review and confirm extracted symbols in the UI

### Phase 2

- Navigate to chart pages for each symbol
- Capture screenshots automatically
- Store screenshot metadata and file paths

### Phase 3

- Publish screenshots in a searchable web gallery
- Add run history, status tracking, and export support

See [docs/product-spec.md](docs/product-spec.md) and [docs/roadmap.md](docs/roadmap.md) for the starting scope.

## Repo Structure

- `app/` application code
- `app/services/` symbol extraction, scraping, and future screenshot services
- `static/` frontend assets
- `.github/` issue and PR templates
- `docs/` product and implementation planning

## Local Run

1. Create a virtual environment and install dependencies from `requirements.txt`.
2. Copy `.env.example` to `.env`.
3. Start Redis.
4. Run the web app with `python run_web.py`.
5. Run the worker with `celery -A app.celery_app:celery_app worker --loglevel=INFO`.

### Codex Browser Preview

If you want to preview the UI quickly in Codex without Redis/Celery, set:

```env
RUN_TASKS_INLINE=true
```

In that mode, chart capture runs execute inline in the web process so the app can still be tested locally in one service.

## Railway Run

For Railway, use:

- start command: `./scripts/start_railway.sh`
- volume mount path: `/app/data`
- public domain: `convert-to-sc-production.up.railway.app`

## Existing API Endpoints

- `GET /api/picks/latest?q=&page=1&page_size=50`
- `GET /api/runs/latest?limit=10`
- `POST /api/jobs/run`
- `GET /api/jobs/status/{task_id}`
- `GET /api/export/latest.csv`

These are inherited from the current SCTR pipeline and can be adapted as we move toward the Convert to SC workflow.

## Notes

- The current implementation depends on StockCharts-style HTML, which can change over time.
- The project name uses `Convert to SC` and keeps the existing SCTR pipeline only as an initial building block.
- If you want, the next step can be either the symbol-extraction feature or the chart-screenshot automation.
