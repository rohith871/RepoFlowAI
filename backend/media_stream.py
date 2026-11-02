from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import BinaryIO, Generator

from fastapi import HTTPException, Request
from fastapi.responses import Response, StreamingResponse


def parse_range_header(range_header: str, file_size: int) -> tuple[int, int] | None:
    """Parse HTTP Range header: bytes=start-end."""
    if not range_header or not range_header.startswith("bytes="):
        return None
    range_value = range_header[len("bytes="):].strip()
    match = re.match(r"^(\d*)-(\d*)$", range_value)
    if not match:
        return None
    start_str, end_str = match.groups()
    if not start_str and not end_str:
        return None
    if not start_str:  # bytes=-suffix (last N bytes)
        length = int(end_str)
        if length > file_size:
            length = file_size
        return file_size - length, file_size - 1
    start = int(start_str)
    if start >= file_size:
        return None
    if not end_str:
        end = file_size - 1
    else:
        end = min(int(end_str), file_size - 1)
    if start > end:
        return None
    return start, end


def file_chunk_generator(file_path: Path, start: int, end: int, chunk_size: int = 64 * 1024) -> Generator[bytes, None, None]:
    """Yield chunks of a file for HTTP byte-range streaming."""
    with open(file_path, "rb") as f:
        f.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            read_size = min(chunk_size, remaining)
            data = f.read(read_size)
            if not data:
                break
            remaining -= len(data)
            yield data


def stream_media_file(
    file_path: Path,
    request: Request,
    media_type: str = "video/mp4",
    allow_download_name: str | None = None,
) -> Response:
    """Stream a media file with full HTTP 206 Partial Content range-request support."""
    resolved = file_path.resolve()
    if not resolved.is_file():
        raise HTTPException(
            status_code=404,
            detail={"code": "MEDIA_NOT_FOUND", "message": f"Media file not found: {file_path.name}"},
        )
    file_size = os.path.getsize(resolved)
    if file_size == 0:
        raise HTTPException(
            status_code=404,
            detail={"code": "MEDIA_EMPTY", "message": "Media file exists but has 0 bytes."},
        )

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Type": media_type,
        "Cache-Control": "public, max-age=3600",
    }
    if allow_download_name:
        headers["Content-Disposition"] = f'inline; filename="{allow_download_name}"'

    range_header = request.headers.get("Range") or request.headers.get("range")
    if range_header:
        byte_range = parse_range_header(range_header, file_size)
        if byte_range is None:
            # Range Not Satisfiable
            return Response(
                status_code=416,
                headers={"Content-Range": f"bytes */{file_size}"},
            )
        start, end = byte_range
        content_length = end - start + 1
        headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
        headers["Content-Length"] = str(content_length)
        return StreamingResponse(
            file_chunk_generator(resolved, start, end),
            status_code=206,
            headers=headers,
            media_type=media_type,
        )

    headers["Content-Length"] = str(file_size)
    return StreamingResponse(
        file_chunk_generator(resolved, 0, file_size - 1),
        status_code=200,
        headers=headers,
        media_type=media_type,
    )


def validate_mp4_file(file_path: Path) -> dict[str, object]:
    """Validate MP4 container integrity, streams, and duration using imageio_ffmpeg."""
    resolved = file_path.resolve()
    if not resolved.is_file():
        return {"valid": False, "reason": "File does not exist"}
    size = os.path.getsize(resolved)
    if size < 5000:
        return {"valid": False, "reason": f"File is too small ({size} bytes)"}

    ffmpeg_exe = shutil.which("ffmpeg")
    if not ffmpeg_exe:
        try:
            import imageio_ffmpeg
            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        except ImportError:
            ffmpeg_exe = None

    if not ffmpeg_exe:
        return {"valid": True, "size_bytes": size, "note": "ffmpeg unavailable for deep inspection"}

    # Run ffmpeg to verify container without decoding all frames
    res = subprocess.run(
        [ffmpeg_exe, "-v", "error", "-i", str(resolved), "-f", "null", "-"],
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode != 0 and "moov atom not found" in res.stderr:
        return {"valid": False, "reason": "Corrupted MP4: missing moov atom", "error": res.stderr}

    # Extract duration / stream info
    probe_res = subprocess.run(
        [ffmpeg_exe, "-i", str(resolved)],
        capture_output=True,
        text=True,
        check=False,
    )
    stderr = probe_res.stderr or ""
    has_video = "Video:" in stderr
    has_audio = "Audio:" in stderr
    duration_match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", stderr)
    duration_seconds = 0.0
    if duration_match:
        h, m, s = duration_match.groups()
        duration_seconds = int(h) * 3600 + int(m) * 60 + float(s)

    return {
        "valid": has_video,
        "size_bytes": size,
        "has_video": has_video,
        "has_audio": has_audio,
        "duration_seconds": round(duration_seconds, 2),
        "error": res.stderr if res.returncode != 0 else None,
    }
