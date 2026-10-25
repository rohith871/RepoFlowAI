from __future__ import annotations

import json
import shutil
import subprocess
import textwrap
from pathlib import Path
from typing import Any

from backend.narration import PocketNarrator


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
        image = Image.new("RGB", (1920, 1080), (8, 17, 31))
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, 1920, 1080), fill=(8 + index * 4, 17 + index * 3, 31 + index * 7))
        draw.ellipse((1380, -120, 1980, 420), fill=(28, 76, 113))
        draw.text((126, 108), f"REPOFLOW AI • {str(scene['kind']).replace('_', ' ').upper()}", fill=(100, 215, 255), font=small_font)
        draw.text((126, 220), str(scene["title"])[:58], fill=(242, 246, 255), font=title_font)
        narration = str(scene["narration"])
        for line_index, line in enumerate(textwrap.wrap(narration, width=65)):
            draw.text((126, 350 + line_index * 52), line, fill=(201, 215, 234), font=body_font)
        if scene["kind"] == "code_walkthrough":
            draw.rounded_rectangle((1140, 320, 1780, 710), radius=14, fill=(5, 12, 23), outline=(57, 102, 145), width=2)
            for line_index, line in enumerate(textwrap.wrap(str(scene.get("code_excerpt", "")), width=38)[:7]):
                draw.text((1182, 360 + line_index * 38), line, fill=(151, 218, 181) if line_index == 0 else (191, 205, 223), font=small_font)
        if scene["kind"] == "architecture_overview":
            visual_nodes = scene.get("visual_nodes", [])
            node_positions: dict[str, tuple[int, int]] = {}
            for node_index, node in enumerate(visual_nodes[:10]):
                x = 1080 + (node_index % 3) * 230
                y = 300 + (node_index // 3) * 145
                node_positions[str(node.get("id", node_index))] = (x, y)
                draw.rounded_rectangle((x, y, x + 190, y + 78), radius=12, fill=(15, 54, 82), outline=(100, 215, 255), width=2)
                draw.text((x + 14, y + 15), str(node.get("kind", "symbol")).upper()[:16], fill=(100, 215, 255), font=small_font)
                draw.text((x + 14, y + 43), str(node.get("label", "node"))[:22], fill=(240, 246, 255), font=small_font)
            for edge in scene.get("visual_edges", [])[:12]:
                start = node_positions.get(str(edge.get("source")))
                end = node_positions.get(str(edge.get("target")))
                if start and end:
                    draw.line((start[0] + 190, start[1] + 39, end[0], end[1] + 39), fill=(102, 215, 255), width=4)
                    draw.polygon([(end[0], end[1] + 39), (end[0] + 14, end[1] + 31), (end[0] + 14, end[1] + 47)], fill=(102, 215, 255))
        if scene["kind"] == "data_flow":
            nodes = [str(node)[:18] for node in scene.get("flow_nodes", [])]
            for node_index, node in enumerate(nodes[:2]):
                x = 1180 + node_index * 310
                draw.rounded_rectangle((x, 390, x + 230, 520), radius=12, fill=(20, 58, 91), outline=(100, 215, 255), width=2)
                draw.text((x + 18, 440), node, fill=(234, 241, 255), font=small_font)
            if len(nodes) == 2:
                draw.line((1410, 455, 1460, 455), fill=(100, 215, 255), width=7)
                draw.polygon([(1460, 455), (1440, 442), (1440, 468)], fill=(100, 215, 255))
        draw.line((126, 780, 1790, 780), fill=(76, 113, 156), width=3)
        draw.text((126, 835), "Source evidence", fill=(145, 177, 210), font=small_font)
        draw.text((126, 900), (", ".join(dict.fromkeys(scene.get("source_refs", []))) or "No source reference")[:120], fill=(234, 241, 255), font=small_font)
        draw.text((126, 1000), f"Scene {index + 1} • Evidence-linked • 1920×1080 • 30 FPS", fill=(100, 215, 255), font=small_font)
        path = png_dir / f"scene-{index:03d}.png"
        image.save(path)
        frames.append(path)
    return frames


def _timestamp(milliseconds: int) -> str:
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"


def render_lesson(lesson: dict[str, Any], output_dir: Path, voice: str = "alba") -> dict[str, Any]:
    output_dir = output_dir.resolve()
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

    narrator = PocketNarrator(voice)
    audio_dir = output_dir / "audio"
    narration_segments: list[dict[str, Any]] = []
    for index, scene in enumerate(lesson["scenes"]):
        audio_path = audio_dir / f"scene-{index:03d}.wav"
        result = narrator.generate(str(scene["narration"]), audio_path)
        narration_segments.append({"scene_id": scene["scene_id"], "text": scene["narration"], "path": result.get("path"), "duration_ms": result.get("duration_ms", int(scene.get("duration_ms", 6000))), "status": result.get("status")})
    manifest: dict[str, Any] = {
        "lesson_id": lesson["lesson_id"],
        "status": "preview_ready",
        "frames": [str(item) for item in frames],
        "narration": {"status": "generated" if all(item["status"] == "generated" for item in narration_segments) else "fallback_text_only", "voice": voice, "segments": narration_segments},
        "captions": [],
        "chapters": [],
        "render": {"width": 1920, "height": 1080, "fps": 30, "codec": "h264", "audio_codec": "aac"},
        "scope": lesson.get("scope", "learning_lesson"),
        "generation_provider": lesson.get("generation_provider", "unknown"),
        "estimated_duration_ms": lesson.get("estimated_duration_ms"),
        "storyboard": lesson.get("storyboard"),
    }
    narration_ready = manifest["narration"]["status"] == "generated"
    cursor = 0
    for index, segment in enumerate(narration_segments):
        end = cursor + int(segment["duration_ms"])
        manifest["captions"].append({"scene_id": segment["scene_id"], "text": segment["text"], "start_ms": cursor, "end_ms": end})
        scene = lesson["scenes"][index]
        manifest["chapters"].append({"title": scene["title"], "start_ms": cursor, "end_ms": end, "scene_id": scene["scene_id"]})
        cursor = end
    manifest["actual_duration_ms"] = cursor
    srt_lines: list[str] = []
    vtt_lines = ["WEBVTT", ""]
    for index, caption in enumerate(manifest["captions"], start=1):
        start_time = _timestamp(int(caption["start_ms"]))
        end_time = _timestamp(int(caption["end_ms"]))
        srt_lines.extend([str(index), f"{start_time.replace('.', ',')} --> {end_time.replace('.', ',')}", caption["text"], ""])
        vtt_lines.extend([f"{start_time} --> {end_time}", caption["text"], ""])
    (output_dir / "captions.srt").write_text("\n".join(srt_lines), encoding="utf-8")
    (output_dir / "captions.vtt").write_text("\n".join(vtt_lines), encoding="utf-8")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        try:
            import imageio_ffmpeg
            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        except ImportError:
            ffmpeg = None
    if ffmpeg:
        manifest["video_status"] = "attempted"
        video_path = output_dir / "lesson.mp4"
        process_result: subprocess.CompletedProcess[bytes] | None = None
        png_frames = _make_png_frames(lesson, output_dir)
        if png_frames:
            clip_dir = output_dir / "clips"
            clip_dir.mkdir(exist_ok=True)
            clip_paths: list[Path] = []
            for index, segment in enumerate(narration_segments):
                clip = clip_dir / f"scene-{index:03d}.mp4"
                subprocess.run([ffmpeg, "-y", "-loop", "1", "-i", str(png_frames[index]), "-t", f"{max(.5, segment['duration_ms'] / 1000):.3f}", "-vf", "scale=1920:1080,zoompan=z='min(zoom+0.0007,1.08)':d=1:s=1920x1080:fps=30,format=yuv420p", "-r", "30", "-c:v", "libx264", "-preset", "veryfast", str(clip)], check=False, capture_output=True)
                if clip.exists():
                    clip_paths.append(clip)
            concat_file = output_dir / "video-concat.txt"
            concat_file.write_text("\n".join(f"file '{path.resolve().as_posix()}'" for path in clip_paths), encoding="utf-8")
            narration_paths = [Path(item["path"]) for item in narration_segments if item.get("path")]
            audio_path = output_dir / "narration.wav"
            audio_concat = output_dir / "audio-concat.txt"
            if narration_paths:
                audio_concat.write_text("\n".join(f"file '{path.resolve().as_posix()}'" for path in narration_paths), encoding="utf-8")
                subprocess.run([ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(audio_concat), "-c", "copy", str(audio_path)], check=False, capture_output=True)
            if clip_paths:
                silent_video = output_dir / "silent.mp4"
                subprocess.run([ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", str(silent_video)], check=False, capture_output=True)
                command = [ffmpeg, "-y", "-i", str(silent_video)]
                if audio_path.exists():
                    command.extend(["-i", str(audio_path), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k"])
                else:
                    command.extend(["-c:v", "copy"])
                command.extend(["-movflags", "+faststart", "-shortest", str(video_path)])
                process_result = subprocess.run(command, check=False, capture_output=True)
            else:
                process_result = subprocess.CompletedProcess([], 1)
            if process_result.returncode == 0 and video_path.exists():
                manifest["video_status"] = "playable" if narration_ready else "preview_ready_no_narration"
                manifest["video_path"] = str(video_path)
        elif shutil.which("convert") or shutil.which("magick"):
            rasteriser = shutil.which("magick") or shutil.which("convert")
            assert rasteriser is not None
            png_dir = output_dir / "png"
            png_dir.mkdir(exist_ok=True)
            for frame in frames:
                subprocess.run([rasteriser, str(frame), str(png_dir / f"{frame.stem}.png")], check=False, capture_output=True)
            process_result = subprocess.run([ffmpeg, "-y", "-framerate", "1", "-i", str(png_dir / "scene-%03d.png"), "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video_path)], check=False, capture_output=True)
            if process_result.returncode == 0 and video_path.exists():
                manifest["video_status"] = "playable" if narration_ready else "preview_ready_no_narration"
                manifest["video_path"] = str(video_path)
        else:
            manifest["video_status"] = "blocked_missing_image_renderer"
    else:
        manifest["video_status"] = "blocked_missing_ffmpeg"
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest
