from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo
import os
import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Wind Procurement Intelligence API", version="1.1.0")
origins = [x.strip() for x in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",") if x.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
BASE = os.getenv("ELEXON_API_BASE", "https://data.elexon.co.uk/bmrs/api/v1")
UK_TZ = ZoneInfo("Europe/London")


def unpack_rows(payload: Any) -> list[dict[str, Any]]:
    """Normalize Elexon JSON responses that are either a list or {data:[...]} object."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("data", "results", "items"):
            if isinstance(payload.get(key), list):
                return payload[key]
    return []


async def fetch(path: str, params: dict[str, str]) -> list[dict[str, Any]]:
    """Fetch a list response from Elexon."""
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.get(
            f"{BASE}{path}", params=params, headers={"Accept": "application/json"}
        )
        response.raise_for_status()
        return unpack_rows(response.json())


def number(value: Any) -> float | None:
    try:
        if value is None or str(value).strip().lower() in {"", "null"}:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def as_utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "wind-procurement-api"}


@app.get("/api/analysis")
async def analysis(
    start: date = Query(date(2026, 1, 1)),
    end: date = Query(date(2026, 1, 31)),
    vintage: str = Query("day-ahead", pattern="^(latest|day-ahead)$"),
):
    if end < start or (end - start).days > 31:
        raise HTTPException(400, "Choose a valid date range of no more than 32 days.")

    # Date inputs are UK settlement/calendar dates, not UTC calendar dates. Convert
    # UK local midnight to UTC so winter dates include the first delivery hour at 23:00Z
    # on the preceding date, and DST transitions remain correctly bounded.
    start_dt = datetime.combine(start, time.min, tzinfo=UK_TZ).astimezone(timezone.utc)
    end_exclusive = datetime.combine(end + timedelta(days=1), time.min, tzinfo=UK_TZ).astimezone(timezone.utc)

    # FUELHH is filtered by settlement date, not the generic from/to parameters.
    # WINDFOR is filtered by publication time; we then explicitly filter delivery startTime.
    try:
        actual_rows, forecast_rows = await _fetch_both(start, end, vintage)
    except httpx.HTTPError as exc:
        raise HTTPException(
            502,
            f"Elexon API request failed: {exc.__class__.__name__}. Please retry shortly.",
        ) from exc

    # FUELHH is half-hourly; WINDFOR forecasts are hourly. Aggregate the two half-hour
    # actual values into an hourly mean so forecast and actual intervals align correctly.
    half_hour_actuals: dict[datetime, float] = {}
    for row in actual_rows:
        if str(row.get("fuelType", "")).upper() != "WIND":
            continue
        stamp = parse_time(row.get("startTime"))
        value = number(row.get("generation"))
        if stamp is None or value is None or not (start_dt <= stamp < end_exclusive):
            continue
        half_hour_actuals[stamp] = value

    hourly_values: dict[datetime, list[float]] = {}
    for stamp, value in half_hour_actuals.items():
        hour = stamp.replace(minute=0, second=0, microsecond=0)
        hourly_values.setdefault(hour, []).append(value)
    actual_by_time = {
        stamp: sum(values) / len(values)
        for stamp, values in hourly_values.items()
        if values
    }

    forecast_by_time: dict[datetime, list[dict[str, Any]]] = {}
    for row in forecast_rows:
        stamp = parse_time(row.get("startTime"))
        published = parse_time(row.get("publishTime"))
        value = number(row.get("generation"))
        if stamp is None or published is None or value is None:
            continue
        if not (start_dt <= stamp < end_exclusive):
            continue
        delivery_date = stamp.astimezone(UK_TZ).date()
        delivery_day_start = datetime.combine(delivery_date, time.min, tzinfo=UK_TZ).astimezone(timezone.utc)
        if vintage == "day-ahead" and published >= delivery_day_start:
            continue
        if vintage == "latest" and published > datetime.now(timezone.utc):
            continue
        forecast_by_time.setdefault(stamp.replace(minute=0, second=0, microsecond=0), []).append(
            {"publishTime": published, "generation": value}
        )

    # Build the complete hourly timeline, not only the timestamps returned by the APIs.
    # The requested interval is hourly because WINDFOR is an hourly national forecast.
    rows = []
    current = start_dt
    while current < end_exclusive:
        options = forecast_by_time.get(current, [])
        chosen = max(options, key=lambda item: item["publishTime"]) if options else None
        actual = actual_by_time.get(current)
        forecast = chosen["generation"] if chosen else None
        error = forecast - actual if forecast is not None and actual is not None else None
        rows.append({
            "startTime": as_utc_iso(current),
            "actual": round(actual, 3) if actual is not None else None,
            "forecast": round(forecast, 3) if forecast is not None else None,
            "publishTime": as_utc_iso(chosen["publishTime"]) if chosen else None,
            "forecastCount": len(options),
            "error": round(error, 3) if error is not None else None,
            "absoluteError": round(abs(error), 3) if error is not None else None,
            "leadHours": round((current - chosen["publishTime"]).total_seconds() / 3600, 2) if chosen else None,
        })
        current += timedelta(hours=1)

    paired = [row for row in rows if row["actual"] is not None and row["forecast"] is not None]
    n = len(paired)
    mae = sum(row["absoluteError"] for row in paired) / n if n else None
    rmse = (sum(row["error"] ** 2 for row in paired) / n) ** 0.5 if n else None
    bias = sum(row["error"] for row in paired) / n if n else None
    actual_mean = sum(row["actual"] for row in paired) / n if n else None
    actual_abs_sum = sum(abs(row["actual"]) for row in paired)
    wape = sum(row["absoluteError"] for row in paired) / actual_abs_sum * 100 if n and actual_abs_sum else None
    latest_pub = max((parse_time(row["publishTime"]) for row in rows if row["publishTime"]), default=None)
    expected_hours = len(rows)
    actual_count = sum(row["actual"] is not None for row in rows)
    forecast_count = sum(row["forecast"] is not None for row in rows)

    return {
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "vintage": vintage,
        "source": "Elexon Insights API (FUELHH actuals and WINDFOR forecast revisions)",
        "retrievedAt": datetime.now(timezone.utc).isoformat(),
        "latestPublishTime": latest_pub.isoformat() if latest_pub else None,
        "summary": {
            "periods": expected_hours,
            "pairedPeriods": n,
            "coveragePct": round(n / expected_hours * 100, 1) if expected_hours else 0,
            "actualCoveragePct": round(actual_count / expected_hours * 100, 1) if expected_hours else 0,
            "forecastCoveragePct": round(forecast_count / expected_hours * 100, 1) if expected_hours else 0,
            "maeMW": round(mae, 1) if mae is not None else None,
            "rmseMW": round(rmse, 1) if rmse is not None else None,
            "biasMW": round(bias, 1) if bias is not None else None,
            "wapePct": round(wape, 1) if wape is not None else None,
            "meanActualMW": round(actual_mean, 1) if actual_mean is not None else None,
        },
        "warnings": _warnings(start, end, expected_hours, actual_count, forecast_count, n),
        "rows": rows,
    }


async def _fetch_both(start: date, end: date, vintage: str = "day-ahead") -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Fetch actuals and archived forecast revisions using documented dataset filters.

    WINDFOR's dataset stream is filtered by publication time (publishDateTimeFrom /
    publishDateTimeTo). Querying the evolution endpoint with a guessed startTime
    parameter was unreliable, and making one request per delivery hour was wasteful.
    A single bounded publication window includes the day-before issue needed for
    day-ahead comparisons and the in-window issues needed for the latest view.
    """
    publication_from = datetime.combine(start - timedelta(days=1), time.min, tzinfo=UK_TZ).astimezone(timezone.utc)
    publication_to = datetime.combine(end + timedelta(days=1), time.min, tzinfo=UK_TZ).astimezone(timezone.utc)
    actual_params = {
        "settlementDateFrom": start.isoformat(),
        "settlementDateTo": end.isoformat(),
    }
    forecast_params = {
        "publishDateTimeFrom": as_utc_iso(publication_from),
        "publishDateTimeTo": as_utc_iso(publication_to),
    }

    async with httpx.AsyncClient(timeout=60) as client:
        actual_response = await client.get(
            f"{BASE}/datasets/FUELHH/stream", params=actual_params,
            headers={"Accept": "application/json"}
        )
        actual_response.raise_for_status()
        actual_rows = unpack_rows(actual_response.json())

        forecast_response = await client.get(
            f"{BASE}/datasets/WINDFOR/stream", params=forecast_params,
            headers={"Accept": "application/json"}
        )
        forecast_response.raise_for_status()
        forecast_rows = unpack_rows(forecast_response.json())

    return actual_rows, forecast_rows


def _warnings(start: date, end: date, expected: int, actual_count: int, forecast_count: int, paired: int) -> list[str]:
    warnings = []
    if actual_count < expected:
        warnings.append(f"Actual data covers {actual_count} of {expected} hourly intervals; check Elexon availability and the requested dates.")
    if forecast_count < expected:
        warnings.append(f"Forecast data covers {forecast_count} of {expected} hourly intervals; some forecast values may be unavailable.")
    if paired < expected:
        warnings.append(f"Accuracy metrics use {paired} paired intervals out of {expected}; interpret MAE/RMSE/WAPE with this coverage limitation.")
    if end < date.today() - timedelta(days=90):
        warnings.append("Historical backtest: verify archived forecast revisions and the exact market decision cutoff before interpreting day-ahead accuracy as operationally representative.")
    return warnings
