# RepoFlow AI

RepoFlow AI turns real source repositories into evidence-grounded, narrated, animated technical learning experiences.

## Current status

The working product now supports static repository analysis, persistent evidence-linked knowledge models, local and GitHub import jobs, source-grounded Ollama questions, persisted lessons and learner progress, a separately trained PyTorch teaching policy, Pocket TTS `alba` narration, and FFmpeg MP4 rendering with captions and chapters. Repository code is analyzed statically and is never executed. The configured primary model is `qwen2.5-coder:7b`; when Ollama is unavailable, the UI and job metadata identify the deterministic evidence fallback.

## Local setup

Windows PowerShell:

```powershell
py -3.13 -m venv .venv-win
.\.venv-win\Scripts\pip.exe install -e ".[test,dev,media]"
.\.venv-win\Scripts\uvicorn.exe backend.main:app --reload
```

Train or refresh the adaptive policy explicitly when needed:

```powershell
$env:REPOFLOW_STORAGE_DIR = "storage"
.\.venv-win\Scripts\python.exe scripts\train_policy.py
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

The generated policy checkpoint and evaluation report are written under `storage/models/`. Rendered lessons are written under `storage/media/<lesson_id>/`; a successful narrated render produces `lesson.mp4`, `captions.vtt`, and `manifest.json`.

Do not put repositories, media, models, credentials, or `.env` files in Git.
