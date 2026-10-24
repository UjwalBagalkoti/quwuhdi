# Debugging and verification notes

Changes in this review package:
- Uses the documented raw `FUELHH` and `WINDFOR` dataset streams. Actuals use settlement-date bounds; forecast records use publication-time bounds (`publishDateTimeFrom` / `publishDateTimeTo`) and are filtered by delivery timestamp in the backend. This avoids a guessed `startTime` parameter and avoids hundreds of per-hour HTTP requests.
- Uses a complete hourly timeline and averages available half-hourly FUELHH wind values into hourly means to align with hourly WINDFOR values.
- Filters returned timestamps to the requested delivery window and chooses the latest eligible forecast vintage.
- Aligns the frontend's chart/table interval labels with hourly data and makes the default selection day-ahead.
- Adds Docker API healthcheck, pins frontend package versions, and adds mocked backend tests.

Important limits:
- Network/DNS access was unavailable in the review container, so the live Elexon integration could not be completed and `npm install` timed out. No Docker executable/engine is installed in this review container, so a Docker build could not be run.
- The day-ahead cutoff is currently 00:00 UTC on the delivery day; confirm the assignment's required decision time and UK market convention before claiming operational validity.
- FUELHH aggregation is an hourly mean of two half-hourly average-MW values, not an energy sum.
- Four backend tests pass and mock upstream responses; they verify API health, hourly alignment, filtering, metrics when no records match, and that forecast requests use publication-time bounds. They do not prove live upstream endpoint availability.

Run backend tests:
```bash
cd backend
pip install -r requirements-dev.txt
pytest -q
```

Rebuild locally:
```bash
docker compose down
docker compose up --build
```

Then check `/api/health` and `/api/analysis?start=2026-01-01&end=2026-01-31&vintage=day-ahead`; every row must fall in January 2026. The query performs two upstream requests for the full month, so it should be much faster than the earlier per-hour implementation. Verify no chosen forecast has a publication timestamp at or after its delivery-day cutoff.
