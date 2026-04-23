# Playwright Lighthouse Analysis

Python-first website crawler and Lighthouse runner modeled after the ALG project structure.

## What it does

The user provides only a base URL. The app then:

1. opens the site in Playwright
2. discovers visible links and buttons
3. sends those navigation candidates to an LLM to identify critical navigation paths
4. revisits the selected paths
5. runs Lighthouse in **navigation** mode with **desktop** preset and all four default categories:
   - performance
   - accessibility
   - best-practices
   - seo
6. exposes live run progress over HTTP while the automation is executing

## Current routes

- `GET /` dashboard and form
- `POST /runs` start a run
- `GET /runs/{run_id}` live status page
- `GET /api/runs/{run_id}` JSON polling endpoint
- `GET /reports/{run_id}` summary page
- `GET /health` health check

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r app\requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
```

Install Lighthouse CLI globally or make sure `npx lighthouse` works.

## Run

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8011
```

Open:

```text
http://127.0.0.1:8011
```

## Optional LLM configuration

Create a local `.env` and set:

```env
PLA_LLM_API_KEY=your_key_here
PLA_LLM_BASE_URL=https://api.openai.com/v1
PLA_LLM_MODEL=gpt-4.1-mini
```

If LLM settings are missing, the app falls back to the first five discovered navigation candidates.

## Notes

- Reports are written under `reports/{run_id}`.
- The live run page polls the backend every 2 seconds.
- Lighthouse output is linked from the run summary page.
