from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


def _escape(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def render_lesson(lesson: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    frames: list[Path] = []
    for index, scene in enumerate(lesson["scenes"]):
        frame = output_dir / f"scene-{index:03d}.svg"
        title = _escape(str(scene["title"]))
        narration = _escape(str(scene["narration"]))
        refs = _escape(", ".join(scene.get("source_refs", [])) or "No source reference")
        kind = _escape(str(scene["kind"]).replace("_", " ").title())
        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720">
<defs><linearGradient id="bg" x1="0" x2="1"><stop stop-color="#08111f"/><stop offset="1" stop-color="#17365e"/></linearGradient></defs>
<rect width="1280" height="720" fill="url(#bg)"/><circle cx="1120" cy="100" r="180" fill="#64d7ff" opacity=".08"/>
<text x="84" y="88" fill="#64d7ff" font-family="Arial" font-size="20" font-weight="bold">REPOFLOW AI • {kind.upper()}</text>
<text x="84" y="168" fill="#f2f6ff" font-family="Arial" font-size="46" font-weight="bold">{title}</text>
<foreignObject x="84" y="225" width="1100" height="220"><div xmlns="http://www.w3.org/1999/xhtml" style="font-family:Arial;color:#c9d7ea;font-size:28px;line-height:1.4">{narration}</div></foreignObject>
<rect x="84" y="520" width="1112" height="1" fill="#4c719c"/><text x="84" y="575" fill="#91b1d2" font-family="Arial" font-size="20">Source evidence</text>
<text x="84" y="615" fill="#eaf1ff" font-family="monospace" font-size="20">{refs}</text>
<text x="84" y="680" fill="#64d7ff" font-family="Arial" font-size="16">Scene {index + 1} • Evidence-linked • Static-analysis status shown in narration</text>
</svg>'''
        frame.write_text(svg, encoding="utf-8")
        frames.append(frame)

    manifest: dict[str, Any] = {
        "lesson_id": lesson["lesson_id"],
        "status": "preview_ready",
        "frames": [str(item) for item in frames],
        "narration": {"status": "fallback_text_only", "reason": "No local TTS engine detected"},
        "captions": [{"scene_id": scene["scene_id"], "text": scene["narration"], "start_ms": sum(int(s["duration_ms"]) for s in lesson["scenes"][:i]), "end_ms": sum(int(s["duration_ms"]) for s in lesson["scenes"][:i + 1])} for i, scene in enumerate(lesson["scenes"])],
    }
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        manifest["video_status"] = "attempted"
        video_path = output_dir / "lesson.mp4"
        # SVG-to-video is intentionally attempted only when an external rasteriser is available.
        # The manifest remains truthful if the host lacks one.
        if shutil.which("convert") or shutil.which("magick"):
            rasteriser = shutil.which("magick") or shutil.which("convert")
            assert rasteriser is not None
            png_dir = output_dir / "png"
            png_dir.mkdir(exist_ok=True)
            for frame in frames:
                subprocess.run([rasteriser, str(frame), str(png_dir / f"{frame.stem}.png")], check=False, capture_output=True)
            result = subprocess.run([ffmpeg, "-y", "-framerate", "1", "-i", str(png_dir / "scene-%03d.png"), "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video_path)], check=False, capture_output=True)
            if result.returncode == 0 and video_path.exists():
                manifest["video_status"] = "playable"
                manifest["video_path"] = str(video_path)
        else:
            manifest["video_status"] = "blocked_missing_svg_rasteriser"
    else:
        manifest["video_status"] = "blocked_missing_ffmpeg"
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest
