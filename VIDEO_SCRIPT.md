# Video demo script (target 8–9 minutes total)

## Part 1 — Client pitch (4:00–4:30)
1. **0:00–0:30 — Business context:** “Day-ahead buying decisions are made with uncertain wind output. This pilot makes the forecast vintage and its historical error visible in one place.”
2. **0:30–1:20 — Overview:** Show KPI cards; explain MAE, RMSE, bias and WAPE in MW/percent and why error direction matters.
3. **1:20–2:20 — Trend view:** Walk through forecast versus actual and signed error chart. Point out that under-forecast and over-forecast have different operational implications.
4. **2:20–3:10 — Decision transparency:** Change the forecast selection and date window; show publication time, lead time and settlement-period table. Export CSV.
5. **3:10–4:10 — Business value + boundaries:** Explain that a measured forecast miss can inform risk buffers and scenario analysis, but wind alone cannot calculate residual demand or a trade. State this is a January 2026 historical pilot and not live trading advice.

## Part 2 — Technical lead review (4:00–4:30)
1. **0:00–0:40 — Architecture:** React/Vite dashboard → FastAPI REST API → Elexon Insights API. Docker Compose runs both services locally.
2. **0:40–1:30 — Data flow:** API requests FUELHH and WINDFOR, filters WIND actuals, parses timestamps, selects a forecast vintage per `startTime`, and joins the two datasets.
3. **1:30–2:20 — Metrics:** Explain error = forecast − actual, MAE, RMSE, bias, WAPE and paired-period coverage. Explain null handling and why MAPE is avoided around zero actuals.
4. **2:20–3:10 — Implementation:** Show `backend/main.py`, frontend component, environment config and CSV export. Explain API error handling and CORS configuration.
5. **3:10–4:10 — Caveats / next steps:** The day-ahead selector uses a simplified UTC date cutoff; for production, use the actual decision cutoff in Europe/London and test BST/GMT boundaries. Add tests, caching, rate-limit handling, data-quality monitoring and CI. Verify API payload/query semantics against live data.

## Before recording
- Start with `docker compose up --build` and verify the dashboard has live data.
- Record the screen and voice; keep each part under five minutes and total video under ten.
- Upload to YouTube as **Unlisted** and test the link in a signed-out/incognito browser.
- Push the project to a public GitHub repository with a random/anonymous repository name.
- Deploy frontend and API, update README with the actual public URL, and test both URLs in incognito.
- Submit all required URLs through the Microsoft Form and verify access before submitting.
