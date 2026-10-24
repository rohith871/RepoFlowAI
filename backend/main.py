from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import Settings

settings = Settings()
settings.ensure_directories()
app = FastAPI(title="RepoFlow AI", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "repoflow-api", "version": app.version}
