"""Assemble Spanish slide videos from timing data + Spanish slide images + Spanish audio.

For each Part video:
1. Load timing JSON (from detect_timing.py)
2. For each segment: create video segment from Spanish slide image or black frame
3. Concatenate all segments using FFmpeg concat demuxer
4. Get Spanish audio from existing _es.mp4 or assembled.wav
5. Mux slide video + Spanish audio -> final output
6. Match original: 1920x1080, 30fps, H.264
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

BASE = Path(r"c:\Users\rcox\INSULATIONS, INC\Supervisory Training - Documents")
FFMPEG_TIMEOUT = 600  # 10 minutes

MODULES = {
    1: "Module 1 - Welcome and Culture",
    2: "Module 2 - Hiring Benefits and Supervisor Policy",
    3: "Module 3 - Supervisor Expectations and Job Rules",
    4: "Module 4 - Leadership",
    5: "Module 5 - Safety Leadership",
    6: "Module 6 - Accident Investigation",
    7: "Module 7 - Company-Owned Vehicles",
}

# Video specs matching originals
WIDTH = 1920
HEIGHT = 1080
FPS = 30
VIDEO_CODEC = "libx264"
CRF = 18  # High quality
PRESET = "medium"


def create_segment_video(
    image_path: Path | None,
    duration: float,
    output_path: Path,
) -> None:
    """Create a video segment from a static image (or black frame) at given duration."""
    if image_path and image_path.exists():
        # Static image -> video segment
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-loop", "1",
                "-i", str(image_path),
                "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                "-t", str(duration),
                "-vf", f"scale={WIDTH}:{HEIGHT},format=yuv420p",
                "-c:v", VIDEO_CODEC,
                "-crf", str(CRF),
                "-preset", PRESET,
                "-r", str(FPS),
                "-c:a", "aac",
                "-shortest",
                str(output_path),
            ],
            capture_output=True, timeout=FFMPEG_TIMEOUT, check=True,
        )
    else:
        # Black frame segment
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", f"color=c=black:s={WIDTH}x{HEIGHT}:r={FPS}:d={duration}",
                "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                "-t", str(duration),
                "-vf", "format=yuv420p",
                "-c:v", VIDEO_CODEC,
                "-crf", str(CRF),
                "-preset", PRESET,
                "-c:a", "aac",
                "-shortest",
                str(output_path),
            ],
            capture_output=True, timeout=FFMPEG_TIMEOUT, check=True,
        )


def concat_segments(segment_files: list[Path], output_path: Path) -> None:
    """Concatenate video segments using FFmpeg concat demuxer."""
    # Create concat list file
    list_path = output_path.parent / "concat_list.txt"
    with open(list_path, "w") as f:
        for seg_file in segment_files:
            # Use forward slashes and escape single quotes for FFmpeg
            safe_path = str(seg_file).replace("\\", "/").replace("'", "'\\''")
            f.write(f"file '{safe_path}'\n")

    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(list_path),
            "-c:v", VIDEO_CODEC,
            "-crf", str(CRF),
            "-preset", PRESET,
            "-c:a", "aac",
            "-b:a", "128k",
            str(output_path),
        ],
        capture_output=True, timeout=FFMPEG_TIMEOUT, check=True,
    )

    # Cleanup list file
    list_path.unlink(missing_ok=True)


def extract_audio(source_path: Path, output_path: Path) -> None:
    """Extract audio from a video file."""
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(source_path),
            "-vn",
            "-acodec", "aac",
            "-b:a", "128k",
            str(output_path),
        ],
        capture_output=True, timeout=FFMPEG_TIMEOUT, check=True,
    )


def mux_video_audio(video_path: Path, audio_path: Path, output_path: Path) -> None:
    """Combine video and audio into final output."""
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-i", str(audio_path),
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "128k",
            "-shortest",
            str(output_path),
        ],
        capture_output=True, timeout=FFMPEG_TIMEOUT, check=True,
    )


def get_duration(file_path: Path) -> float:
    """Get media file duration in seconds."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            str(file_path),
        ],
        capture_output=True, text=True, timeout=30,
    )
    info = json.loads(result.stdout)
    return float(info["format"]["duration"])


def assemble_video(module_num: int, part_num: int) -> bool:
    """Assemble a single Spanish slide video."""
    module_name = MODULES[module_num]
    module_dir = BASE / module_name

    work_dir = module_dir / "Videos" / f"Module {module_num} Part {part_num}_work"
    timing_es_path = work_dir / "timing_es.json"
    timing_en_path = work_dir / "timing.json"
    slides_es_dir = work_dir / "slides_es"
    assembled_wav = work_dir / "assembled.wav"

    # The existing _es.mp4 (audio-only Spanish dub) is also our final output target.
    # We MUST extract audio from it before overwriting.
    es_video_path = module_dir / "Videos" / f"Module {module_num} Part {part_num}_es.mp4"
    output_path = es_video_path  # Will overwrite with slide version

    # Prefer Spanish timing if available, fall back to English
    if timing_es_path.exists():
        timing_path = timing_es_path
        print(f"  Using Spanish-aware timing (timing_es.json)")
    elif timing_en_path.exists():
        timing_path = timing_en_path
        print(f"  Using English timing (timing.json) — run generate_es_timing.py for better sync")
    else:
        print(f"  Timing data not found in {work_dir}")
        print(f"  Run detect_timing.py first!")
        return False

    # Check prerequisites
    if not timing_path.exists():
        print(f"  Timing data not found: {timing_path}")
        print(f"  Run detect_timing.py first!")
        return False

    if not slides_es_dir.exists() or not any(slides_es_dir.glob("slide_*.png")):
        print(f"  Spanish slide images not found in {slides_es_dir}")
        print(f"  Run export_slides.ps1 first!")
        return False

    # Load timing data
    with open(timing_path) as f:
        timing = json.load(f)

    segments = timing["segments"]
    print(f"  Timing: {len(segments)} segments, {timing['duration']:.1f}s total")

    # Determine audio source — MUST extract audio BEFORE we overwrite the _es.mp4
    audio_source = work_dir / "spanish_audio.aac"
    if assembled_wav.exists():
        audio_source = assembled_wav
        print(f"  Audio source: assembled.wav")
    elif audio_source.exists():
        print(f"  Audio source: spanish_audio.aac (previously extracted)")
    elif es_video_path.exists():
        # Extract audio from existing _es.mp4 BEFORE we overwrite it
        print(f"  Extracting audio from existing _es.mp4 (before overwrite)...")
        extract_audio(es_video_path, audio_source)
        print(f"  Audio source: spanish_audio.aac (from _es.mp4)")
    else:
        print(f"  ERROR: No Spanish audio found!")
        print(f"  Need either assembled.wav or existing _es.mp4")
        return False

    # Create assembly work directory (clear if timing data is newer than cached segments)
    assembly_dir = work_dir / "slide_assembly"
    if assembly_dir.exists():
        timing_mtime = timing_path.stat().st_mtime
        slides_video = assembly_dir / "slides_only.mp4"
        if slides_video.exists() and slides_video.stat().st_mtime < timing_mtime:
            print(f"  Timing data is newer than cached assembly, clearing cache...")
            shutil.rmtree(assembly_dir)
    assembly_dir.mkdir(exist_ok=True)

    # Create video segments
    print(f"  Creating {len(segments)} video segments...")
    segment_files = []

    for i, seg in enumerate(segments):
        seg_file = assembly_dir / f"seg_{i:04d}.mp4"
        duration = seg["end"] - seg["start"]

        if duration <= 0:
            continue

        slide_num = seg.get("slide")
        if slide_num is not None:
            # Use Spanish slide image
            slide_path = slides_es_dir / f"slide_{slide_num:02d}.png"
            if not slide_path.exists():
                print(f"    WARNING: Slide {slide_num} not found, using black frame")
                slide_path = None
        else:
            slide_path = None  # Black frame

        if not seg_file.exists():
            slide_str = f"slide {slide_num}" if slide_num else "black"
            print(f"    Segment {i}: {seg['start']:.1f}s-{seg['end']:.1f}s ({duration:.1f}s) - {slide_str}")
            create_segment_video(slide_path, duration, seg_file)

        segment_files.append(seg_file)

    if not segment_files:
        print(f"  ERROR: No segments created!")
        return False

    # Concatenate all segments
    slides_video = assembly_dir / "slides_only.mp4"
    if not slides_video.exists():
        print(f"  Concatenating {len(segment_files)} segments...")
        concat_segments(segment_files, slides_video)
    else:
        print(f"  Slides video already concatenated")

    # Mux with Spanish audio
    print(f"  Muxing video + audio -> {output_path.name}")
    mux_video_audio(slides_video, audio_source, output_path)

    # Verify output
    out_duration = get_duration(output_path)
    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"  Output: {output_path.name} ({size_mb:.1f} MB, {out_duration:.1f}s)")

    # Compare with original duration
    original_video = module_dir / "Videos" / f"Module {module_num} Part {part_num}.mp4"
    if original_video.exists():
        orig_duration = get_duration(original_video)
        diff = abs(out_duration - orig_duration)
        if diff > 2.0:
            print(f"  WARNING: Duration mismatch! Original: {orig_duration:.1f}s, Output: {out_duration:.1f}s (diff: {diff:.1f}s)")
        else:
            print(f"  Duration match OK (original: {orig_duration:.1f}s, diff: {diff:.1f}s)")

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
        module_nums = list(range(1, 8))

    print(f"Assembling Spanish slide videos for {len(module_nums)} modules\n")

    results = []
    for module_num in module_nums:
        print(f"\n{'='*60}")
        print(f"Module {module_num} - {MODULES[module_num]}")
        print(f"{'='*60}")

        for part in range(1, 4):
            # Check if video exists
            video_path = BASE / MODULES[module_num] / "Videos" / f"Module {module_num} Part {part}.mp4"
            if not video_path.exists():
                print(f"\n--- Part {part} --- [SKIP: no source video]")
                results.append((f"Module {module_num} Part {part}", None))
                continue

            print(f"\n--- Part {part} ---")
            try:
                ok = assemble_video(module_num, part)
                results.append((f"Module {module_num} Part {part}", ok))
            except subprocess.CalledProcessError as e:
                print(f"  FFmpeg ERROR: {e}")
                if e.stderr:
                    stderr = e.stderr.decode("utf-8", errors="replace")
                    for line in stderr.strip().split("\n")[-5:]:
                        print(f"    {line}")
                results.append((f"Module {module_num} Part {part}", False))
            except Exception as e:
                print(f"  ERROR: {e}")
                import traceback
                traceback.print_exc()
                results.append((f"Module {module_num} Part {part}", False))

    print(f"\n{'='*60}")
    print("ASSEMBLY COMPLETE")
    print(f"{'='*60}\n")

    for name, ok in results:
        if ok is None:
            status = "[SKIP]"
        elif ok:
            status = "[OK]  "
        else:
            status = "[FAIL]"
        print(f"  {status} {name}")


if __name__ == "__main__":
    main()
