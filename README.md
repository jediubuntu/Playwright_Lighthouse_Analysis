# Playwright Lighthouse Analysis

Python-first website crawler and Lighthouse runner modeled after the ALG project structure.

## What it does

The user provides only a base URL. The app then:

1. opens the site in Playwright
2. discovers visible links and buttons
3. filters out obvious auth/login/basic-auth style routes
4. sends remaining navigation candidates to an OpenAI-compatible LLM to identify critical navigation paths
5. revisits the selected paths
6. runs Lighthouse in **navigation** mode with **desktop** preset and all four default categories:
   - performance
   - accessibility
   - best-practices
   - seo
7. exposes live run progress over HTTP while the automation is executing
8. repeats the same flow for 3 built-in **virtual region profiles**:
   - India - Mumbai
   - US West - San Francisco
   - Europe - London

## Important limitation: virtual region simulation, not real geo-origin execution

This project does **not** make requests originate from Mumbai, San Francisco, or London at the network level.

It runs entirely from your laptop and simulates these browser/user-context signals per region:

- locale
- timezone
- geolocation
- `Accept-Language` header

This is useful for:
- localized UI/content differences
- timezone-sensitive rendering
- browser geolocation-based behavior
- comparing Lighthouse output under different browser-region contexts

It does **not** change:
- your real IP
- CDN edge selection by true origin
- server-side geo decisions based only on IP

## Current routes

- `GET /` dashboard and form
- `POST /runs` start a run
- `GET /runs/{run_id}` live status page
- `GET /api/runs/{run_id}` JSON polling endpoint
- `GET /reports/{run_id}` summary page
- `GET /health` health check

## Report structure

For each run, reports are written under:

```text
reports/{run_id}/
```

Each virtual region gets its own folder:

```text
reports/{run_id}/india-mumbai/
reports/{run_id}/us-west-san-francisco/
reports/{run_id}/europe-london/
```

Each audited page generates:

- `*.report.html`
- `*.report.json`

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r app\requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
npm install -g lighthouse
```

You can also rely on `npx lighthouse`, but Node.js and Lighthouse must be installed and available on PATH.

## Run

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8011
```

Open:

```text
http://127.0.0.1:8011
```

## Optional LLM configuration

Set these as environment variables in your shell before starting the app:

```powershell
$env:PLA_LLM_API_KEY="your_key_here"
$env:PLA_LLM_BASE_URL="https://api.openai.com/v1"
$env:PLA_LLM_MODEL="gpt-4.1-mini"
```

If LLM settings are missing, the app falls back to the first five discovered navigation candidates after filtering blocked auth/login-style links.

## How the virtual locations help

The built-in location profiles help by changing browser context for the same URL:

### India - Mumbai
- locale: `en-IN`
- timezone: `Asia/Kolkata`
- browser geolocation: Mumbai
- `Accept-Language: en-IN,en;q=0.9`

### US West - San Francisco
- locale: `en-US`
- timezone: `America/Los_Angeles`
- browser geolocation: San Francisco
- `Accept-Language: en-US,en;q=0.9`

### Europe - London
- locale: `en-GB`
- timezone: `Europe/London`
- browser geolocation: London
- `Accept-Language: en-GB,en;q=0.9`

This can expose:
- different page variants
- localized text/date/time/currency behavior
- different user flows or banners
- different Lighthouse outcomes caused by client-side regional behavior

## Security and git hygiene

This repository is intended to be safe to upload to git if you follow these rules:

- do **not** commit `.env`
- do **not** hardcode API keys in source files
- do **not** commit generated reports
- do **not** paste secrets into README examples, screenshots, or shell history

Current git-safe behavior:
- `.env` is ignored by `.gitignore`
- `reports/*` is ignored by `.gitignore`
- the codebase contains no embedded credentials
- LLM credentials are expected from environment variables only

Before pushing to git, verify:
- `.env` is not tracked
- no reports are tracked
- no API keys are present in committed files

Useful commands:

```powershell
git status
git ls-files
```

## Notes

- the live run page polls the backend every 2 seconds
- Lighthouse on Windows may sometimes return a non-zero exit code after writing output files due to temp cleanup issues; this project treats written report files as usable
- auth/login/basic-auth style navigation targets are filtered before crawling
- this project is path-portable and can be moved to another folder as long as dependencies are installed there
