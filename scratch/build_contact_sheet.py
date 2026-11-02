from __future__ import annotations

import subprocess
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
REPORT_DIR = ROOT / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)
PROPS = ROOT / "media" / "production_showcase" / "remotion_props.json"

# Key frame indices corresponding to:
# Frame 20: Scene 1 - Orientation & Gateway Boundary
# Frame 60: Scene 2 - Code Walkthrough with Failure Mode
# Frame 115: Scene 3 - Subsystem Architecture & Neon Edges
# Frame 160: Scene 4 - Data Flow Pipeline & Traveling Particle
frames = [20, 60, 115, 160]
frame_imgs = []

for idx, f_num in enumerate(frames):
    out_img = REPORT_DIR / f"frame_{f_num}.png"
    cmd = [
        "npx", "remotion", "still",
        "RepoFlowLesson",
        str(out_img),
        f"--frame={f_num}",
        f"--props={PROPS}"
    ]
    print(f"Rendering frame {f_num}...")
    res = subprocess.run(cmd, cwd=str(FRONTEND), capture_output=True, text=True, shell=True)
    if out_img.is_file():
        print(f"  Frame {f_num} successfully captured: {out_img.stat().st_size} bytes")
        frame_imgs.append(out_img)
    else:
        print(f"  Error rendering frame {f_num}: {res.stderr}")

if frame_imgs:
    # Stitch into 2x2 contact sheet
    canvas = Image.new("RGB", (1920, 1080), (10, 15, 29))
    w, h = 950, 530
    positions = [(10, 10), (960, 10), (10, 540), (960, 540)]
    for img_path, pos in zip(frame_imgs, positions):
        im = Image.open(img_path).resize((w, h), Image.Resampling.LANCZOS)
        canvas.paste(im, pos)
    
    contact_path = REPORT_DIR / "remotion_startup_quality_contact_sheet.png"
    canvas.save(contact_path)
    print(f"\nContact sheet generated successfully at: {contact_path}")
    print(f"Contact sheet file size: {contact_path.stat().st_size / 1024:.1f} KB")
