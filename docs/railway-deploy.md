# Railway Deployment

## Target URL

- `convert-to-sc-production.up.railway.app`

## Recommended Railway Architecture

Because this project stores screenshots and SQLite data on local persistent disk, the safest Railway setup is:

- `app` service: one Docker service that runs both the FastAPI web server and the Celery worker in the same container
- `redis` service: separate Railway Redis service
- `volume`: mounted to `/app/data`

This keeps the following files visible to both the web process and the screenshot worker:

- `/app/data/dreamlist.db`
- `/app/data/screenshots/...`

## Why One App Service

If the web app and worker run as separate Railway services, each service gets its own local filesystem. That would break a local-storage design because:

- the worker could save screenshots that the web app cannot read
- SQLite writes would live on only one service unless shared externally

Running both processes in one service avoids that problem while still keeping Redis separate.

## Services

### 1. Redis

Create a Railway Redis service.

### 2. App

Create a Docker-based Railway service from this repository.

Use the start command from the `Procfile` or set the Railway start command to:

```sh
./scripts/start_railway.sh
```

## Volume

Attach one Railway volume to the `app` service.

- mount path: `/app/data`

Railway documents that relative app writes like `./data` should be backed by a volume mounted at `/app/data`.

## Required Variables

Set these on the `app` service:

```env
APP_TIMEZONE=Asia/Taipei
SQLITE_PATH=/app/data/dreamlist.db
SCREENSHOT_OUTPUT_DIR=/app/data/screenshots
CHART_SITE_BASE_URL=https://stockcharts.com
CHART_CAPTURE_TIMEOUT_MS=45000
CHART_CAPTURE_VIEWPORT_WIDTH=1440
CHART_CAPTURE_VIEWPORT_HEIGHT=2200
REDIS_URL=${{Redis.REDIS_URL}}
CELERY_BROKER_URL=${{Redis.REDIS_URL}}
CELERY_RESULT_BACKEND=${{Redis.REDIS_URL}}
```

If your Redis service uses a different Railway service name, replace `Redis` with that service namespace in Railway's variable reference syntax.

## Public Domain

Generate a Railway public domain for the `app` service and set it to:

- `convert-to-sc-production.up.railway.app`

Railway provides one `*.up.railway.app` domain per service.

## Deploy Sequence

1. Create the Redis service.
2. Create the Docker app service from this repo.
3. Attach a volume to the app service at `/app/data`.
4. Add the environment variables above.
5. Deploy.
6. Generate the public Railway domain.
7. Open `/` and run a test conversion such as `NVDA`.

## First Smoke Test

Use sample input like:

```text
Watching NVDA for relative strength and chart breakout confirmation.
```

Expected result:

- symbols extracted: `NVDA`
- run queued
- worker captures the `SharpCharts Chart` image
- file written under `/app/data/screenshots`
- gallery loads the saved PNG from `/artifacts/...`

## Notes

- The screenshot worker depends on Playwright + Chromium, which are installed in the Docker image.
- This deployment favors local persistence simplicity over horizontal scaling.
- If you later split web and worker into separate services, move screenshots and database storage to shared managed services instead of local disk.
