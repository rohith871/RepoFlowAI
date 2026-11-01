from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any


class RemotionRenderer:
    """Coordinates rendering through Remotion CLI when installed, or delegates to native renderer."""

    def __init__(self, frontend_dir: Path | None = None):
        self.frontend_dir = frontend_dir or (Path(__file__).parents[1] / "frontend")

    def available(self) -> bool:
        """Check if Remotion CLI and node modules are available."""
        npm_bin = shutil.which("npx") or shutil.which("pnpm")
        if not npm_bin:
            return False
        # Check if @remotion/core or remotion exists in node_modules
        node_modules = self.frontend_dir / "node_modules" / "remotion"
        return node_modules.is_dir()

    def render(self, props_path: Path, output_mp4: Path, timeout_seconds: int = 240, frames: str | None = None) -> dict[str, Any]:
        """Render using Remotion CLI if available, otherwise return status."""
        if not self.available():
            return {
                "status": "unavailable",
                "reason": "remotion_not_installed",
                "renderer": "remotion",
            }

        npx_bin = shutil.which("npx") or shutil.which("npx.cmd") or "npx"
        output_mp4 = output_mp4.resolve()
        output_mp4.parent.mkdir(parents=True, exist_ok=True)
        props_path = props_path.resolve()

        # Compute relative path from frontend_dir if possible for Windows shell safety
        try:
            rel_props = os.path.relpath(props_path, self.frontend_dir).replace("\\", "/")
        except ValueError:
            rel_props = props_path.as_posix()

        try:
            rel_out = os.path.relpath(output_mp4, self.frontend_dir).replace("\\", "/")
        except ValueError:
            rel_out = str(output_mp4)

        cmd = [
            npx_bin,
            "remotion",
            "render",
            "src/remotion/index.tsx",
            "RepoFlowLesson",
            rel_out,
            f"--props={rel_props}",
        ]
        if frames:
            cmd.append(f"--frames={frames}")

        try:
            res = subprocess.run(
                cmd,
                cwd=str(self.frontend_dir),
                check=False,
                capture_output=True,
                text=True,
                shell=(True if shutil.which("cmd.exe") else False),
                timeout=timeout_seconds,
            )
            if res.returncode == 0 and output_mp4.is_file() and output_mp4.stat().st_size > 0:
                return {
                    "status": "playable",
                    "video_path": str(output_mp4),
                    "renderer": "remotion",
                    "file_size": output_mp4.stat().st_size,
                }
            return {
                "status": "failed",
                "reason": (res.stderr or res.stdout)[-600:],
                "renderer": "remotion",
            }
        except subprocess.TimeoutExpired:
            return {
                "status": "failed",
                "reason": f"Remotion render timed out after {timeout_seconds} seconds",
                "renderer": "remotion",
            }
        except Exception as exc:
            return {
                "status": "failed",
                "reason": str(exc),
                "renderer": "remotion",
            }
