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


def _make_png_frames(lesson: dict[str, Any], output_dir: Path) -> list[list[Path]]:
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
    frame_sequences: list[list[Path]] = []
    for index, scene in enumerate(lesson["scenes"]):
        sequence: list[Path] = []
        frame_count = 24
        for frame_index in range(frame_count):
            progress = frame_index / max(1, frame_count - 1)
            image = Image.new("RGB", (1920, 1080), (8, 17, 31))
            draw = ImageDraw.Draw(image)
            draw.rectangle((0, 0, 1920, 1080), fill=(8 + index * 4, 17 + index * 3, 31 + index * 7))
            draw.ellipse((1380, -120, 1980, 420), fill=(28, 76, 113))
            v_type = str(scene.get("visual_type", scene.get("kind", "scene"))).replace("_", " ").upper()
            draw.text((126, 80), f"REPOFLOW AI • {v_type}", fill=(100, 215, 255), font=small_font)
            draw.text((126, 160), str(scene["title"])[:58], fill=(242, 246, 255), font=title_font)
            
            # Core question or objective badge
            q_text = str(scene.get("question_answered") or scene.get("objective", ""))
            if q_text:
                draw.rounded_rectangle((126, 230, 1000, 280), radius=6, fill=(15, 45, 75), outline=(50, 130, 190), width=1)
                draw.text((140, 246), f"QUESTION: {q_text[:75]}", fill=(170, 220, 255), font=small_font)

            narration = str(scene["narration"])
            for line_index, line in enumerate(textwrap.wrap(narration, width=62)[:8]):
                draw.text((126, 310 + line_index * 42), line, fill=(201, 215, 234), font=body_font)

            # Takeaway or developer guidance
            takeaway = scene.get("takeaway") or scene.get("developer_guidance")
            if takeaway:
                draw.rounded_rectangle((126, 660, 1000, 730), radius=8, fill=(11, 38, 59), outline=(100, 215, 255), width=2)
                draw.text((140, 672), "KEY TAKEAWAY", fill=(100, 215, 255), font=small_font)
                draw.text((140, 696), str(takeaway)[:80], fill=(255, 255, 255), font=small_font)

            # Interactive Checkpoint badge if present
            chk = scene.get("checkpoint")
            if chk:
                draw.rounded_rectangle((126, 740, 1000, 770), radius=6, fill=(40, 30, 15), outline=(245, 159, 0), width=1)
                chk_title = f"CHECKPOINT: {chk.get('question_text', '')[:70]}"
                draw.text((140, 748), chk_title, fill=(255, 214, 102), font=small_font)

            if scene.get("visual_type") == "code" or scene["kind"] == "code_walkthrough":
                draw.rounded_rectangle((1080, 220, 1810, 740), radius=14, fill=(5, 12, 23), outline=(57, 102, 145), width=2)
                code_path = scene.get("code_path") or (scene.get("source_refs", [""])[0])
                draw.text((1110, 240), f"File: {code_path}", fill=(100, 215, 255), font=small_font)
                code_lines = str(scene.get("code_excerpt", "")).splitlines()[:12]
                highlight_lines = scene.get("highlight_lines", []) or [1]
                active_line = highlight_lines[min(len(highlight_lines) - 1, int(progress * len(highlight_lines)))]
                start_line = int(highlight_lines[0]) if highlight_lines else 1
                for line_index, line in enumerate(code_lines):
                    line_no = start_line + line_index
                    y = 280 + line_index * 36
                    if line_no == active_line:
                        draw.rounded_rectangle((1100, y - 3, 1790, y + 28), radius=5, fill=(24, 83, 82))
                    draw.text((1110, y), f"{line_no:>4}", fill=(105, 147, 166), font=small_font)
                    draw.text((1170, y), line[:62], fill=(151, 218, 181) if line_no == active_line else (191, 205, 223), font=small_font)

            elif scene.get("visual_type") in {"data_transformation"} or scene["kind"] == "cause_and_effect":
                draw.rounded_rectangle((1080, 220, 1810, 740), radius=14, fill=(8, 20, 36), outline=(100, 215, 255), width=2)
                draw.text((1110, 250), "TRANSFORMATION & BOUNDARIES", fill=(100, 215, 255), font=small_font)
                
                # Input Box
                draw.rounded_rectangle((1120, 320, 1310, 430), radius=10, fill=(15, 54, 82), outline=(100, 215, 255), width=2)
                draw.text((1135, 340), "INPUT", fill=(100, 215, 255), font=small_font)
                draw.text((1135, 375), "Client Request", fill=(240, 246, 255), font=small_font)

                # Arrow 1
                draw.line((1310, 375, 1360, 375), fill=(100, 215, 255), width=4)
                draw.polygon([(1360, 375), (1350, 368), (1350, 382)], fill=(100, 215, 255))

                # Service/Model Box
                draw.rounded_rectangle((1360, 320, 1560, 430), radius=10, fill=(20, 70, 105), outline=(100, 215, 255), width=2)
                draw.text((1375, 340), "DOMAIN LOGIC", fill=(100, 215, 255), font=small_font)
                draw.text((1375, 375), "Typed Entity", fill=(240, 246, 255), font=small_font)

                # Arrow 2
                draw.line((1560, 375, 1610, 375), fill=(100, 215, 255), width=4)
                draw.polygon([(1610, 375), (1600, 368), (1600, 382)], fill=(100, 215, 255))

                # Output Box
                draw.rounded_rectangle((1610, 320, 1780, 430), radius=10, fill=(15, 54, 82), outline=(100, 215, 255), width=2)
                draw.text((1625, 340), "OUTPUT", fill=(100, 215, 255), font=small_font)
                draw.text((1625, 375), "API Payload", fill=(240, 246, 255), font=small_font)

                # Hypothetical Callout
                if scene.get("counterfactual"):
                    draw.rounded_rectangle((1120, 480, 1780, 680), radius=10, fill=(35, 22, 10), outline=(245, 159, 0), width=2)
                    draw.text((1140, 500), "[HYPOTHETICAL] FAILURE MODE REASONING", fill=(255, 192, 120), font=small_font)
                    cf_text = str(scene["counterfactual"]).replace("[HYPOTHETICAL]", "").strip()
                    for cfi, cfl in enumerate(textwrap.wrap(cf_text, width=48)[:4]):
                        draw.text((1140, 535 + cfi * 32), cfl, fill=(255, 224, 102), font=small_font)

            elif scene.get("visual_type") in {"architecture", "summary"} or scene["kind"] in {"architecture_overview", "summary", "recap"}:
                visual_nodes = scene.get("visual_nodes", [])
                node_positions: dict[str, tuple[int, int]] = {}
                visible_count = max(1, min(len(visual_nodes), int(progress * len(visual_nodes)) + 1))
                for node_index, node in enumerate(visual_nodes[:visible_count]):
                    x = 1040 + (node_index % 3) * 245
                    y = 240 + (node_index // 3) * 145
                    node_positions[str(node.get("id", node_index))] = (x, y)
                    draw.rounded_rectangle((x, y, x + 215, y + 95), radius=12, fill=(15, 54, 82), outline=(100, 215, 255), width=2)
                    role_badge = str(node.get("role", node.get("kind", "symbol"))).replace("_", " ").upper()
                    draw.text((x + 14, y + 14), role_badge[:18], fill=(100, 215, 255), font=small_font)
                    draw.text((x + 14, y + 45), str(node.get("label", "node"))[:20], fill=(240, 246, 255), font=small_font)
                visible_edges = scene.get("visual_edges", [])[: max(0, min(len(scene.get("visual_edges", [])), int(progress * len(scene.get("visual_edges", [])) + 1)))]
                for edge in visible_edges:
                    start = node_positions.get(str(edge.get("source")))
                    end = node_positions.get(str(edge.get("target")))
                    if start and end:
                        draw.line((start[0] + 215, start[1] + 47, end[0], end[1] + 47), fill=(102, 215, 255), width=4)
                        draw.polygon([(end[0], end[1] + 47), (end[0] + 14, end[1] + 39), (end[0] + 14, end[1] + 55)], fill=(102, 215, 255))
                if visible_edges:
                    edge = visible_edges[min(len(visible_edges) - 1, int(progress * len(visible_edges)))]
                    start = node_positions.get(str(edge.get("source")))
                    end = node_positions.get(str(edge.get("target")))
                    if start and end:
                        packet_x = start[0] + 215 + (end[0] - start[0] - 215) * progress
                        packet_y = start[1] + 47 + (end[1] - start[1]) * progress
                        draw.ellipse((packet_x - 9, packet_y - 9, packet_x + 9, packet_y + 9), fill=(255, 214, 102), outline=(255, 247, 188), width=2)

            elif scene.get("visual_type") == "flow" or scene["kind"] in {"data_flow", "execution_flow"}:
                flow_steps = scene.get("flow_steps", [])
                if flow_steps:
                    draw.rounded_rectangle((1080, 220, 1810, 740), radius=14, fill=(6, 18, 32), outline=(100, 215, 255), width=2)
                    draw.text((1110, 240), "EXECUTION PATH TRACE", fill=(100, 215, 255), font=small_font)
                    active_step_idx = min(len(flow_steps) - 1, int(progress * len(flow_steps)))
                    for s_idx, st in enumerate(flow_steps[:6]):
                        sy = 280 + s_idx * 70
                        is_active = (s_idx == active_step_idx)
                        bg_col = (20, 70, 105) if is_active else (12, 35, 55)
                        border_col = (100, 215, 255) if is_active else (40, 80, 120)
                        draw.rounded_rectangle((1110, sy, 1780, sy + 60), radius=8, fill=bg_col, outline=border_col, width=2 if is_active else 1)
                        draw.text((1130, sy + 18), f"Step {st.get('step_number', s_idx + 1)}", fill=(100, 215, 255) if is_active else (130, 170, 200), font=small_font)
                        draw.text((1220, sy + 18), str(st.get("description", ""))[:55], fill=(255, 255, 255) if is_active else (190, 205, 220), font=small_font)
                else:
                    flow_nodes = [str(node)[:18] for node in scene.get("flow_nodes", [])]
                    positions = [(1130, 395), (1510, 395)]
                    for node_index, node in enumerate(flow_nodes[:2]):
                        x, y = positions[node_index]
                        draw.rounded_rectangle((x, y, x + 240, y + 130), radius=12, fill=(20, 58, 91), outline=(100, 215, 255), width=2)
                        draw.text((x + 18, y + 48), node, fill=(234, 241, 255), font=small_font)
                    if len(flow_nodes) == 2:
                        draw.line((1370, 460, 1510, 460), fill=(100, 215, 255), width=7)
                        packet_x = 1370 + 140 * progress
                        draw.ellipse((packet_x - 10, 450, packet_x + 10, 470), fill=(255, 214, 102))
                        draw.polygon([(1510, 460), (1488, 447), (1488, 473)], fill=(100, 215, 255))
            draw.line((126, 780, 1790, 780), fill=(76, 113, 156), width=3)
            draw.text((126, 835), "Source evidence", fill=(145, 177, 210), font=small_font)
            draw.text((126, 900), (", ".join(dict.fromkeys(scene.get("source_refs", []))) or "No source reference")[:120], fill=(234, 241, 255), font=small_font)
            draw.text((126, 1000), f"Scene {index + 1} • Evidence-linked • 1920×1080 • 30 FPS", fill=(100, 215, 255), font=small_font)
            # Animated scene progress bar at bottom
            draw.line((0, 1074, 1920, 1074), fill=(16, 36, 58), width=6)
            draw.line((0, 1074, int(1920 * progress), 1074), fill=(100, 215, 255), width=6)
            path = png_dir / f"scene-{index:03d}-{frame_index:03d}.png"
            image.save(path)
            sequence.append(path)
        frame_sequences.append(sequence)
    return frame_sequences


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

    from backend.transcript import build_transcript_from_lesson, TranscriptValidator
    transcript_segments = build_transcript_from_lesson(lesson)
    validator = TranscriptValidator()
    transcript_report = validator.validate(transcript_segments)

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
        "transcript_validation": transcript_report.model_dump(mode="json"),
        "transcript_segments": [s.model_dump(mode="json") for s in transcript_segments],
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
    remotion_props = {
        "lesson_id": lesson.get("lesson_id", "lesson"),
        "title": lesson.get("title", "RepoFlow Lesson"),
        "repository_id": lesson.get("repository_id", ""),
        "scenes": [
            {
                **scene,
                "visual_type": scene.get("visual_type") or scene.get("kind") or "summary",
                "audio_url": f"audio/scene-{idx:03d}.wav" if (idx < len(narration_segments) and narration_segments[idx].get("path")) else None,
                "duration_ms": narration_segments[idx]["duration_ms"] if idx < len(narration_segments) else int(scene.get("duration_ms", 6000)),
            }
            for idx, scene in enumerate(lesson.get("scenes", []))
        ],
        "captions": manifest["captions"],
        "chapters": manifest["chapters"],
        "render": manifest["render"],
    }
    (output_dir / "remotion_props.json").write_text(json.dumps(remotion_props, indent=2), encoding="utf-8")
    
    from backend.remotion_renderer import RemotionRenderer
    remotion_renderer = RemotionRenderer()
    if remotion_renderer.available():
        target_mp4 = output_dir / "lesson.mp4"
        if target_mp4.is_file():
            try:
                target_mp4.unlink()
            except OSError:
                pass
        remotion_res = remotion_renderer.render(output_dir / "remotion_props.json", target_mp4)
        if remotion_res.get("status") == "playable":
            manifest["video_status"] = "playable"
            manifest["video_path"] = remotion_res["video_path"]
            manifest["renderer"] = "remotion"
            (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            return manifest
    manifest["renderer"] = "pillow_ffmpeg"

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
        png_sequences = _make_png_frames(lesson, output_dir)
        if png_sequences:
            clip_dir = output_dir / "clips"
            clip_dir.mkdir(exist_ok=True)
            clip_paths: list[Path] = []
            for index, segment in enumerate(narration_segments):
                clip = clip_dir / f"scene-{index:03d}.mp4"
                sequence = png_sequences[index]
                pattern = sequence[0].with_name(f"scene-{index:03d}-%03d.png")
                subprocess.run([ffmpeg, "-y", "-framerate", "30", "-stream_loop", "-1", "-i", str(pattern), "-t", f"{max(.5, segment['duration_ms'] / 1000):.3f}", "-vf", "scale=1920:1080,format=yuv420p", "-r", "30", "-c:v", "libx264", "-preset", "veryfast", str(clip)], check=False, capture_output=True)
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
