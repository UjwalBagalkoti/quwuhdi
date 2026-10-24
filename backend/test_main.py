from datetime import date, datetime, timezone
import pytest
from fastapi.testclient import TestClient
import main

client = TestClient(main.app)

def test_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

@pytest.mark.anyio
async def test_analysis_uses_requested_dates_and_hourly_timeline(monkeypatch):
    async def fake_fetch_both(start, end, vintage="day-ahead"):
        assert start == date(2026, 1, 1)
        assert end == date(2026, 1, 1)
        actuals = [
            {"fuelType": "WIND", "startTime": "2026-01-01T00:00:00Z", "generation": 100},
            {"fuelType": "WIND", "startTime": "2026-01-01T00:30:00Z", "generation": 120},
            {"fuelType": "GAS", "startTime": "2026-01-01T00:00:00Z", "generation": 999},
            {"fuelType": "WIND", "startTime": "2026-02-01T00:00:00Z", "generation": 500},
        ]
        forecasts = [
            {"startTime": "2026-01-01T00:00:00Z", "publishTime": "2025-12-31T12:00:00Z", "generation": 130},
            {"startTime": "2026-01-01T00:00:00Z", "publishTime": "2026-01-01T01:00:00Z", "generation": 150},
            {"startTime": "2026-02-01T00:00:00Z", "publishTime": "2026-01-31T12:00:00Z", "generation": 600},
        ]
        return actuals, forecasts
    monkeypatch.setattr(main, "_fetch_both", fake_fetch_both)
    result = await main.analysis(start=date(2026,1,1), end=date(2026,1,1), vintage="day-ahead")
    assert result["summary"]["periods"] == 24
    assert result["rows"][0]["startTime"] == "2026-01-01T00:00:00Z"
    assert result["rows"][0]["actual"] == 110
    assert result["rows"][0]["forecast"] == 130
    assert result["rows"][0]["error"] == 20
    assert all(datetime.fromisoformat(row["startTime"].replace("Z", "+00:00")).astimezone(__import__("zoneinfo").ZoneInfo("Europe/London")).date().isoformat() == "2026-01-01" for row in result["rows"])
    assert result["summary"]["pairedPeriods"] == 1

@pytest.mark.anyio
async def test_analysis_returns_null_metrics_when_no_pairs(monkeypatch):
    async def fake_fetch_both(start, end, vintage="day-ahead"):
        return [], []
    monkeypatch.setattr(main, "_fetch_both", fake_fetch_both)
    result = await main.analysis(start=date(2026,1,1), end=date(2026,1,1), vintage="day-ahead")
    assert result["summary"]["pairedPeriods"] == 0
    assert result["summary"]["maeMW"] is None
    assert result["summary"]["rmseMW"] is None
    assert result["summary"]["coveragePct"] == 0

@pytest.mark.anyio
async def test_fetch_both_uses_documented_publication_time_filters(monkeypatch):
    calls = []

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload
        def raise_for_status(self):
            return None
        def json(self):
            return self._payload

    class FakeClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return False
        async def get(self, url, params=None, headers=None):
            calls.append((url, params))
            if url.endswith('/datasets/FUELHH/stream'):
                return FakeResponse([{'fuelType': 'WIND'}])
            return FakeResponse([{
                'startTime': '2026-01-01T00:00:00Z',
                'publishTime': '2025-12-31T12:00:00Z',
                'generation': 100,
            }])

    monkeypatch.setattr(main.httpx, 'AsyncClient', lambda **kwargs: FakeClient())
    actuals, forecasts = await main._fetch_both(date(2026, 1, 1), date(2026, 1, 2), 'day-ahead')
    assert len(actuals) == 1
    assert len(forecasts) == 1
    actual_call = next((url, params) for url, params in calls if url.endswith('/datasets/FUELHH/stream'))
    forecast_call = next((url, params) for url, params in calls if url.endswith('/datasets/WINDFOR/stream'))
    assert actual_call[1] == {'settlementDateFrom': '2026-01-01', 'settlementDateTo': '2026-01-02'}
    assert forecast_call[1] == {
        'publishDateTimeFrom': '2025-12-31T00:00:00Z',
        'publishDateTimeTo': '2026-01-03T00:00:00Z',
    }
    assert len(calls) == 2
