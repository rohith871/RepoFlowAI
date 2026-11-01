from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a contact sheet from extracted video frames.")
    parser.add_argument("frames_dir", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--columns", type=int, default=3)
    args = parser.parse_args()
    frames = sorted(args.frames_dir.glob("*.png"))
    if not frames:
        raise SystemExit(f"No PNG frames found in {args.frames_dir}")
    thumb_w, thumb_h = 480, 270
    label_h = 34
    rows = (len(frames) + args.columns - 1) // args.columns
    sheet = Image.new("RGB", (args.columns * thumb_w, rows * (thumb_h + label_h)), (7, 15, 27))
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for index, frame_path in enumerate(frames):
        image = Image.open(frame_path).convert("RGB")
        image.thumbnail((thumb_w, thumb_h))
        x = (index % args.columns) * thumb_w
        y = (index // args.columns) * (thumb_h + label_h)
        sheet.paste(image, (x, y))
        draw.text((x + 8, y + thumb_h + 8), frame_path.name, fill=(210, 230, 245), font=font)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(args.output)
    print(args.output)


if __name__ == "__main__":
    main()
