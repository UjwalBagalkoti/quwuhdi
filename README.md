# Wind Procurement Intelligence

A pilot dashboard for UK day-ahead wind forecast visibility and forecast-error analysis. Built with React + Vite, Python FastAPI, and Docker Compose. AI tools were used to assist with scaffolding and implementation; all generated code should be reviewed and tested before production use.

## Features
- National wind forecast comparison at hourly resolution; half-hourly FUELHH actuals are averaged into hourly means for alignment.
- Forecast publication timestamps and estimated lead time for the selected forecast vintage.
- MAE, RMSE, signed bias, WAPE, matched-period coverage and downloadable CSV.
- Date window and forecast-selection filters.
- Responsive dashboard with time-series charts and settlement-period table.

## Repository layout
- `frontend/`: React UI, charts, styling and Vite setup.
- `frontend/src/main.jsx`: dashboard, filters, chart/table rendering and CSV export.
- `frontend/src/style.css`: responsive visual system.
- `backend/main.py`: FastAPI endpoints, Elexon data retrieval, joining and metrics.
- `backend/requirements.txt`: Python dependencies.
- `backend/Dockerfile`: API container image.
- `docker-compose.yml`: local full-stack development environment.

## Run locally with Docker
Prerequisite: Docker Desktop / Docker Engine with Compose.

```bash
docker compose up --build
```

Open `http://localhost:5173` for the UI and `http://localhost:8000/docs` for API docs. Health endpoint: `http://localhost:8000/api/health`.

## Run without Docker
Backend:
```bash
cd backend
python -m venv .venv
# Windows: .venv\\Scripts\\activate  | macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```
Frontend in a second terminal:
```bash
cd frontend
npm install
npm run dev
```
Set `VITE_API_URL` if the API is not at `http://localhost:8000`. Backend configuration supports `ELEXON_API_BASE` and comma-separated `CORS_ORIGINS` environment variables.

## Data sources and assumptions
- Elexon Insights API base: `https://data.elexon.co.uk/bmrs/api/v1`
- Actuals: `/datasets/FUELHH/stream`, filtered with `settlementDateFrom` and `settlementDateTo`, then filtered to `fuelType == WIND`. Forecast revisions: `/datasets/WINDFOR/stream`, filtered by the documented `publishDateTimeFrom` and `publishDateTimeTo` publication-time bounds. The app then filters delivery timestamps locally and chooses the latest revision, or the latest revision published before 00:00 UTC on the delivery day for the day-ahead proxy.
- Target interval: `startTime`; forecast issue time: `publishTime`; MW values: `generation`.
- Analysis defaults to January 2026. Times are shown in UTC. The `latest` selection chooses the latest returned publication vintage per target interval. The `day-ahead` selection chooses the latest returned revision published before 00:00 UTC on the delivery date; this is a simplified proxy, not a verified market gate-closure rule. `day-ahead` excludes forecasts published on or after the target's UTC calendar date; this is an explicit, simplified proxy for the day-ahead decision cutoff and should be aligned to the client's actual decision timestamp and market gate closure before operational use.
- Forecast error is defined as forecast minus actual. Positive bias means over-forecasting wind; negative bias means under-forecasting wind. MAE and RMSE are in MW. WAPE = sum(abs(error))/sum(abs(actual))*100; unlike MAPE it remains defined when individual actuals are zero, provided total absolute actual generation is non-zero.
- Actual and forecast records are joined by `startTime`. Metrics use only intervals with both values available; coverage is reported to make missingness visible.
- Residual demand / additional procurement is not calculated because demand and other supply are explicitly out of scope. Wind forecast alone is not sufficient to determine a purchase volume.

## Deployment notes
This repository is deployment-ready as a starting point, but a public deployment URL has not been created by this local scaffold. Deploy the frontend to Vercel with `VITE_API_URL` pointing to a publicly deployed API; deploy the FastAPI backend to a container host that supports Docker and set `CORS_ORIGINS` to the deployed frontend origin. Do not expose secrets in frontend environment variables. Vercel's serverless runtime may require adapting the API entrypoint; a dedicated container host is the simplest path for this Compose-based backend.

## Tests

Backend unit tests are in `backend/test_main.py`. Install development dependencies with `pip install -r requirements-dev.txt` from `backend/`, then run `pytest -q`. These tests mock Elexon responses and do not replace a live API integration test.

## Known limitations / next steps
- The Elexon API could not be reached from the review environment because DNS/network access was unavailable. The live integration test is therefore still pending. The app now makes two bounded API requests per analysis (one for actuals and one for forecast revisions) instead of hundreds of per-hour calls. If Elexon returns 429/5xx or no records, inspect the API logs and verify archived forecast availability.
- For rigorous historical day-ahead backtesting, select the latest forecast published before the specific decision cutoff (including UK local time / GMT-BST handling), not simply the latest forecast in the target-day set.
- Add automated unit/integration tests, caching/retry/backoff, data freshness alerts, API pagination/large-range handling, and CI before production.
- This is an analytical pilot, not a trading system or a substitute for balancing, portfolio, price, or risk controls.

## Video and submission checklist
The assignment requires an unlisted YouTube demo (maximum 10 minutes), a public GitHub repository with an anonymous name, and submission through the supplied Microsoft Form. These external deliverables must be created and verified by the submitter; this local project does not claim to have uploaded a video, created a public repo, deployed the app, or submitted the form.
"# quwuhdi" 
