# RepoFlow AI

RepoFlow AI turns real source repositories into evidence-grounded, narrated, animated technical learning experiences.

## Current status

The Phase 1 implementation is being built in the nine documented milestones. The current baseline includes the local Python environment, FastAPI health service, React/Vite shell, configuration, test/lint/typecheck scaffolding, and the approved design contracts.

## Local setup

Windows PowerShell:

```powershell
py -3.13 -m venv .venv-win
.\.venv-win\Scripts\pip.exe install -e ".[test,dev,media]"
.\.venv-win\Scripts\uvicorn.exe backend.main:app --reload
```

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open the Vite URL shown by the frontend command. The frontend expects the API at `http://127.0.0.1:8000`.

## Verification

```powershell
.\.venv-win\Scripts\python.exe -m pytest -q
.\.venv-win\Scripts\ruff.exe check .
.\.venv-win\Scripts\mypy.exe .
cd frontend; npm run typecheck; npm run build
```

Do not put repositories, media, models, credentials, or `.env` files in Git.
