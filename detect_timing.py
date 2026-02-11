"""Detect slide timing from English videos using SSIM comparison.

For each Part video + corresponding English slide images:
1. Extract 1 frame per second from the video via FFmpeg
2. Compare each frame to each English slide image using SSIM
3. For each second, record which slide has the highest SSIM match
4. Group consecutive matches into segments
5. Save timing data as JSON
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
from skimage.metrics import structural_similarity as ssim
from PIL import Image

BASE = Path(r"c:\Users\rcox\INSULATIONS, INC\Supervisory Training - Documents")
FFMPEG_TIMEOUT = 600  # 10 minutes

# Module folder names
MODULES = {
    1: "Module 1 - Welcome and Culture",
    2: "Module 2 - Hiring Benefits and Supervisor Policy",
    3: "Module 3 - Supervisor Expectations and Job Rules",
    4: "Module 4 - Leadership",
    5: "Module 5 - Safety Leadership",
    6: "Module 6 - Accident Investigation",
    7: "Module 7 - Company-Owned Vehicles",
}

# Minimum SSIM threshold to consider a frame as matching a slide
# Below this, the frame is considered "black" or "transition"
SSIM_THRESHOLD = 0.40


def get_video_duration(video_path: Path) -> float:
    """Get video duration in seconds using FFprobe."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            str(video_path),
        ],
        capture_output=True, text=True, timeout=30,
    )
    info = json.loads(result.stdout)
    return float(info["format"]["duration"])


def extract_frames(video_path: Path, output_dir: Path, fps: int = 1) -> int:
    """Extract frames from video at given FPS. Returns frame count."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Extract at 1 fps, scaled to 1920x1080 to match slide images
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-vf", f"fps={fps},scale=1920:1080",
            "-q:v", "2",
            str(output_dir / "frame_%05d.png"),
        ],
        capture_output=True, timeout=FFMPEG_TIMEOUT, check=True,
    )

    frames = sorted(output_dir.glob("frame_*.png"))
    return len(frames)


def load_image_gray(path: Path, size: tuple[int, int] = (960, 540)) -> np.ndarray:
    """Load an image as grayscale numpy array, resized for fast SSIM."""
    img = Image.open(path).convert("L").resize(size, Image.LANCZOS)
    return np.array(img)


def detect_slide_timing(
    video_path: Path,
    slides_en_dir: Path,
    work_dir: Path,
) -> list[dict]:
    """Detect which slide is shown at each second of the video.

    Returns a list of segments: [{slide: int|null, start: float, end: float}, ...]
    slide=null means black/transition frame.
    """
    print(f"  Video: {video_path.name}")
    duration = get_video_duration(video_path)
    print(f"  Duration: {duration:.1f}s")

    # Extract frames
    frames_dir = work_dir / "frames_1fps"
    existing_frames = list(frames_dir.glob("frame_*.png")) if frames_dir.exists() else []
    if existing_frames:
        frame_count = len(existing_frames)
        print(f"  Frames already extracted: {frame_count}")
    else:
        print(f"  Extracting frames at 1 fps...")
        frame_count = extract_frames(video_path, frames_dir, fps=1)
        print(f"  Extracted {frame_count} frames")

    # Load slide reference images (grayscale, downscaled for speed)
    slide_files = sorted(slides_en_dir.glob("slide_*.png"))
    if not slide_files:
        print(f"  ERROR: No slide images found in {slides_en_dir}")
        return []

    print(f"  Loading {len(slide_files)} reference slide images...")
    slide_images = {}
    for sf in slide_files:
        # Extract slide number from filename (slide_01.png -> 1)
        match = re.search(r"slide_(\d+)", sf.stem)
        if match:
            slide_num = int(match.group(1))
            slide_images[slide_num] = load_image_gray(sf)

    print(f"  Loaded slides: {sorted(slide_images.keys())}")

    # Compare each frame to each slide
    frame_files = sorted(frames_dir.glob("frame_*.png"))
    print(f"  Comparing {len(frame_files)} frames against {len(slide_images)} slides...")

    frame_matches = []  # (second, best_slide_num_or_None, best_ssim)

    for fi, frame_path in enumerate(frame_files):
        frame_gray = load_image_gray(frame_path)
        second = fi  # frame_00001.png = second 0, frame_00002.png = second 1, etc.

        best_slide = None
        best_score = 0.0

        for slide_num, slide_gray in slide_images.items():
            score = ssim(frame_gray, slide_gray)
            if score > best_score:
                best_score = score
                best_slide = slide_num

        if best_score < SSIM_THRESHOLD:
            best_slide = None  # Black/transition frame

        frame_matches.append({
            "second": second,
            "slide": best_slide,
            "ssim": round(best_score, 4),
        })

        # Progress every 30 seconds
        if (fi + 1) % 30 == 0 or fi == len(frame_files) - 1:
            pct = (fi + 1) / len(frame_files) * 100
            slide_str = f"slide {best_slide}" if best_slide else "black"
            print(f"    {fi+1}/{len(frame_files)} ({pct:.0f}%) - sec {second}: {slide_str} (SSIM={best_score:.3f})")

    # Debounce: remove isolated single-frame slide changes (noise)
    frame_matches = _debounce_matches(frame_matches)

    # Group consecutive frames with same slide into segments
    segments = _group_segments(frame_matches, duration)

    print(f"  Found {len(segments)} segments")
    for seg in segments:
        slide_str = f"slide {seg['slide']}" if seg['slide'] is not None else "black"
        print(f"    {seg['start']:.1f}s - {seg['end']:.1f}s: {slide_str}")

    return segments


def _debounce_matches(frame_matches: list[dict], min_run: int = 2) -> list[dict]:
    """Remove isolated frame matches shorter than min_run consecutive frames.

    If a slide appears for fewer than min_run frames (seconds at 1fps),
    replace it with the surrounding slide value to suppress noise.
    """
    if len(frame_matches) < 3:
        return frame_matches

    result = [m.copy() for m in frame_matches]

    # Forward pass: if a single frame differs from both neighbors, snap it
    for i in range(1, len(result) - 1):
        prev_slide = result[i - 1]["slide"]
        curr_slide = result[i]["slide"]
        next_slide = result[i + 1]["slide"]

        if curr_slide != prev_slide and curr_slide != next_slide and prev_slide == next_slide:
            result[i]["slide"] = prev_slide

    return result


def _group_segments(frame_matches: list[dict], total_duration: float) -> list[dict]:
    """Group consecutive frame matches into segments."""
    if not frame_matches:
        return []

    segments = []
    current_slide = frame_matches[0]["slide"]
    current_start = 0.0

    for i in range(1, len(frame_matches)):
        if frame_matches[i]["slide"] != current_slide:
            # End current segment, start new one
            segments.append({
                "slide": current_slide,
                "start": current_start,
                "end": float(frame_matches[i]["second"]),
            })
            current_slide = frame_matches[i]["slide"]
            current_start = float(frame_matches[i]["second"])

    # Final segment extends to video end
    segments.append({
        "slide": current_slide,
        "start": current_start,
        "end": total_duration,
    })

    return segments


def process_video(module_num: int, part_num: int) -> bool:
    """Process a single video to detect slide timing."""
    module_name = MODULES[module_num]
    module_dir = BASE / module_name

    video_path = module_dir / "Videos" / f"Module {module_num} Part {part_num}.mp4"
    work_dir = module_dir / "Videos" / f"Module {module_num} Part {part_num}_work"
    slides_en_dir = work_dir / "slides_en"
    timing_path = work_dir / "timing.json"

    if not video_path.exists():
        print(f"  Video not found: {video_path}")
        return False

    if not slides_en_dir.exists() or not list(slides_en_dir.glob("slide_*.png")):
        print(f"  English slide images not found in {slides_en_dir}")
        print(f"  Run export_slides.ps1 first!")
        return False

    # Check if timing already detected
    if timing_path.exists():
        print(f"  Timing already detected: {timing_path}")
        with open(timing_path) as f:
            data = json.load(f)
        print(f"  {len(data['segments'])} segments")
        return True

    segments = detect_slide_timing(video_path, slides_en_dir, work_dir)

    if not segments:
        print(f"  ERROR: No segments detected!")
        return False

    # Save timing data
    timing_data = {
        "video": video_path.name,
        "module": module_num,
        "part": part_num,
        "segments": segments,
        "slide_count": len(set(s["slide"] for s in segments if s["slide"] is not None)),
        "duration": segments[-1]["end"] if segments else 0,
    }

    with open(timing_path, "w") as f:
        json.dump(timing_data, f, indent=2)

    print(f"  Saved timing: {timing_path}")
    return True


def main():
    # Parse optional --module argument
    module_filter = 0
    for arg in sys.argv[1:]:
        if arg.startswith("--module="):
            module_filter = int(arg.split("=")[1])
        elif arg.isdigit():
            module_filter = int(arg)

    if module_filter > 0:
        module_nums = [module_filter]
    else:
        module_nums = list(range(1, 8))  # Modules 1-7

    print(f"Detecting slide timing for {len(module_nums)} modules\n")

    results = []
    for module_num in module_nums:
        print(f"\n{'='*60}")
        print(f"Module {module_num} - {MODULES[module_num]}")
        print(f"{'='*60}")

        for part in range(1, 4):
            print(f"\n--- Part {part} ---")
            ok = process_video(module_num, part)
            results.append((f"Module {module_num} Part {part}", ok))

    print(f"\n{'='*60}")
    print("TIMING DETECTION COMPLETE")
    print(f"{'='*60}\n")

    for name, ok in results:
        status = "[OK]  " if ok else "[FAIL]"
        print(f"  {status} {name}")


if __name__ == "__main__":
    main()
