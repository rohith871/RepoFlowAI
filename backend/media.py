from __future__ import annotations

import json
import shutil
import subprocess
import textwrap
from pathlib import Path
from typing import Any


def _escape(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _make_png_frames(lesson: dict[str, Any], output_dir: Path) -> list[Path]:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return []
    png_dir = output_dir / "png"
    png_dir.mkdir(exist_ok=True)
    try:
        title_font: Any = ImageFont.truetype("arial.ttf", 44)
        body_font: Any = ImageFont.truetype("arial.ttf", 26)
        small_font: Any = ImageFont.truetype("arial.ttf", 16)
    except OSError:
        title_font = ImageFont.load_default()
        body_font = ImageFont.load_default()
        small_font = ImageFont.load_default()
    frames: list[Path] = []
    for index, scene in enumerate(lesson["scenes"]):
        image = Image.new("RGB", (1280, 720), (8, 17, 31))
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, 1280, 720), fill=(8 + index * 4, 17 + index * 3, 31 + index * 7))
        draw.ellipse((920, -80, 1320, 320), fill=(28, 76, 113))
        draw.text((84, 72), f"REPOFLOW AI • {str(scene['kind']).replace('_', ' ').upper()}", fill=(100, 215, 255), font=small_font)
        draw.text((84, 145), str(scene["title"])[:48], fill=(242, 246, 255), font=title_font)
        narration = str(scene["narration"])
        for line_index, line in enumerate(textwrap.wrap(narration, width=65)):
            draw.text((84, 235 + line_index * 42), line, fill=(201, 215, 234), font=body_font)
        if scene["kind"] == "code_walkthrough":
            draw.rounded_rectangle((760, 220, 1196, 470), radius=14, fill=(5, 12, 23), outline=(57, 102, 145), width=2)
            for line_index, line in enumerate(textwrap.wrap(str(scene.get("code_excerpt", "")), width=38)[:7]):
                draw.text((790, 245 + line_index * 27), line, fill=(151, 218, 181) if line_index == 0 else (191, 205, 223), font=small_font)
        if scene["kind"] == "data_flow":
            nodes = [str(node)[:18] for node in scene.get("flow_nodes", [])]
            for node_index, node in enumerate(nodes[:2]):
                x = 790 + node_index * 230
                draw.rounded_rectangle((x, 280, x + 170, 370), radius=12, fill=(20, 58, 91), outline=(100, 215, 255), width=2)
                draw.text((x + 15, 315), node, fill=(234, 241, 255), font=small_font)
            if len(nodes) == 2:
                draw.line((960, 325, 1015, 325), fill=(100, 215, 255), width=5)
                draw.polygon([(1015, 325), (1000, 315), (1000, 335)], fill=(100, 215, 255))
        draw.line((84, 520, 1196, 520), fill=(76, 113, 156), width=2)
        draw.text((84, 558), "Source evidence", fill=(145, 177, 210), font=small_font)
        draw.text((84, 600), (", ".join(dict.fromkeys(scene.get("source_refs", []))) or "No source reference")[:92], fill=(234, 241, 255), font=small_font)
        path = png_dir / f"scene-{index:03d}.png"
        image.save(path)
        frames.append(path)
    return frames


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
    if not ffmpeg:
        try:
            import imageio_ffmpeg  # type: ignore[import-untyped]
            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        except ImportError:
            ffmpeg = None
    if ffmpeg:
        manifest["video_status"] = "attempted"
        video_path = output_dir / "lesson.mp4"
        png_frames = _make_png_frames(lesson, output_dir)
        if png_frames:
            result = subprocess.run([ffmpeg, "-y", "-framerate", "1", "-i", str(output_dir / "png" / "scene-%03d.png"), "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video_path)], check=False, capture_output=True)
            if result.returncode == 0 and video_path.exists():
                manifest["video_status"] = "playable"
                manifest["video_path"] = str(video_path)
        elif shutil.which("convert") or shutil.which("magick"):
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
            manifest["video_status"] = "blocked_missing_image_renderer"
    else:
        manifest["video_status"] = "blocked_missing_ffmpeg"
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest
