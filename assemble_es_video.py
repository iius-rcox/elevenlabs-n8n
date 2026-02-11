"""Assemble Spanish slide video with audio-driven slide durations + transitions.

For each slide:
1. Identify which TTS audio segments belong to it
2. Concatenate those segments (with small gaps) to get the slide's audio
3. Slide duration = audio duration + padding
4. Crossfade transition between slides

Result: a video where each slide shows exactly as long as the narrator
speaks about it, with smooth transitions between slides.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

BASE = Path(r"c:\Users\rcox\INSULATIONS, INC\Supervisory Training - Documents")
FFMPEG_TIMEOUT = 600

MODULES = {
    1: "Module 1 - Welcome and Culture",
    2: "Module 2 - Hiring Benefits and Supervisor Policy",
    3: "Module 3 - Supervisor Expectations and Job Rules",
    4: "Module 4 - Leadership",
    5: "Module 5 - Safety Leadership",
    6: "Module 6 - Accident Investigation",
    7: "Module 7 - Company-Owned Vehicles",
}

WIDTH = 1920
HEIGHT = 1080
FPS = 30
CRF = 18
PRESET = "medium"

# Padding: silence around audio within each slide
INTRO_PADDING = 2.0   # seconds of black before first slide
OUTRO_PADDING = 2.0   # seconds of black after last slide
SLIDE_PAD_BEFORE = 2.0  # silence before audio starts on each slide
SLIDE_PAD_AFTER = 2.0   # silence after audio ends on each slide

# Transition
TRANSITION_DURATION = 0.5  # seconds of crossfade between slides
SEGMENT_GAP = 0.15  # seconds of silence between audio segments within a slide


def get_duration(file_path: Path) -> float:
    """Get media file duration in seconds."""
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(file_path)],
        capture_output=True, text=True, timeout=30,
    )
    info = json.loads(result.stdout)
    return float(info["format"]["duration"])


def map_segments_to_slides(en_timing: dict, transcript_segments: list[dict]) -> list[int | None]:
    """Map each transcript segment to its English slide using midpoint matching."""
    en_segments = en_timing["segments"]
    mapping = []
    for seg in transcript_segments:
        midpoint = (seg["start"] + seg["end"]) / 2
        matched = None
        for en_seg in en_segments:
            if en_seg["start"] <= midpoint < en_seg["end"]:
                matched = en_seg.get("slide")
                break
        mapping.append(matched)
    return mapping


def concat_audio_segments(segment_files: list[Path], output_path: Path, gap: float = SEGMENT_GAP) -> float:
    """Concatenate audio segments with small gaps between them.

    Returns the total duration of the concatenated audio.
    """
    if not segment_files:
        return 0.0

    if len(segment_files) == 1:
        # Just copy
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(segment_files[0]), "-c", "copy", str(output_path)],
            capture_output=True, timeout=FFMPEG_TIMEOUT, check=True,
        )
        return get_duration(output_path)

    # Build concat file with gaps
    list_path = output_path.parent / f"{output_path.stem}_list.txt"
    silence_path = output_path.parent / "gap_silence.wav"

    # Create a small silence file for gaps
    if gap > 0 and not silence_path.exists():
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo",
             "-t", str(gap), str(silence_path)],
            capture_output=True, timeout=30, check=True,
        )

    with open(list_path, "w") as f:
        for i, seg_file in enumerate(segment_files):
            safe = str(seg_file).replace("\\", "/").replace("'", "'\\''")
            f.write(f"file '{safe}'\n")
            if gap > 0 and i < len(segment_files) - 1:
                safe_gap = str(silence_path).replace("\\", "/").replace("'", "'\\''")
                f.write(f"file '{safe_gap}'\n")

    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_path),
         "-c:a", "aac", "-b:a", "128k", str(output_path)],
        capture_output=True, timeout=FFMPEG_TIMEOUT, check=True,
    )

    list_path.unlink(missing_ok=True)
    return get_duration(output_path)


def create_slide_video_with_audio(
    image_path: Path | None,
    audio_path: Path,
    duration: float,
    output_path: Path,
) -> None:
    """Create a video segment: static slide image + audio for given duration."""
    if image_path and image_path.exists():
        subprocess.run(
            ["ffmpeg", "-y",
             "-loop", "1", "-i", str(image_path),
             "-i", str(audio_path),
             "-t", str(duration),
             "-vf", f"scale={WIDTH}:{HEIGHT},format=yuv420p",
             "-c:v", "libx264", "-crf", str(CRF), "-preset", PRESET,
             "-r", str(FPS),
             "-c:a", "aac", "-b:a", "128k",
             "-shortest",
             str(output_path)],
            capture_output=True, timeout=FFMPEG_TIMEOUT, check=True,
        )
    else:
        # Black frame with audio
        subprocess.run(
            ["ffmpeg", "-y",
             "-f", "lavfi", "-i", f"color=c=black:s={WIDTH}x{HEIGHT}:r={FPS}",
             "-i", str(audio_path),
             "-t", str(duration),
             "-vf", "format=yuv420p",
             "-c:v", "libx264", "-crf", str(CRF), "-preset", PRESET,
             "-c:a", "aac", "-b:a", "128k",
             "-shortest",
             str(output_path)],
            capture_output=True, timeout=FFMPEG_TIMEOUT, check=True,
        )


def create_silent_video(
    image_path: Path | None,
    duration: float,
    output_path: Path,
) -> None:
    """Create a video segment with silence (for intro/outro)."""
    if image_path and image_path.exists():
        src = ["-loop", "1", "-i", str(image_path)]
        vf = f"scale={WIDTH}:{HEIGHT},format=yuv420p"
    else:
        src = ["-f", "lavfi", "-i", f"color=c=black:s={WIDTH}x{HEIGHT}:r={FPS}"]
        vf = "format=yuv420p"

    subprocess.run(
        ["ffmpeg", "-y"] + src + [
         "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
         "-t", str(duration),
         "-vf", vf,
         "-c:v", "libx264", "-crf", str(CRF), "-preset", PRESET,
         "-r", str(FPS),
         "-c:a", "aac",
         "-shortest",
         str(output_path)],
        capture_output=True, timeout=FFMPEG_TIMEOUT, check=True,
    )


def concat_with_transitions(
    segment_files: list[Path],
    transition_duration: float,
    output_path: Path,
) -> None:
    """Concatenate video segments with crossfade transitions using xfade filter."""
    if len(segment_files) == 1:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(segment_files[0]),
             "-c:v", "libx264", "-crf", str(CRF), "-c:a", "aac",
             str(output_path)],
            capture_output=True, timeout=FFMPEG_TIMEOUT, check=True,
        )
        return

    # Get durations for offset calculation
    durations = [get_duration(f) for f in segment_files]

    # Build xfade filter chain
    # For N segments, we need N-1 xfade filters chained together
    inputs = []
    for f in segment_files:
        inputs.extend(["-i", str(f)])

    # Calculate offsets: each xfade starts at (cumulative_duration - transition_duration)
    # The xfade "eats" transition_duration from the end of clip A and start of clip B
    filter_parts = []
    audio_filter_parts = []

    # Running offset tracks where each transition occurs
    offset = durations[0] - transition_duration

    if len(segment_files) == 2:
        filter_parts.append(
            f"[0:v][1:v]xfade=transition=fade:duration={transition_duration}:offset={offset:.3f}[vout]"
        )
        audio_filter_parts.append(
            f"[0:a][1:a]acrossfade=d={transition_duration}:c1=tri:c2=tri[aout]"
        )
    else:
        # Chain xfades for 3+ segments
        # First transition
        filter_parts.append(
            f"[0:v][1:v]xfade=transition=fade:duration={transition_duration}:offset={offset:.3f}[v1]"
        )
        audio_filter_parts.append(
            f"[0:a][1:a]acrossfade=d={transition_duration}:c1=tri:c2=tri[a1]"
        )

        for i in range(2, len(segment_files)):
            prev_v = f"v{i-1}"
            prev_a = f"a{i-1}"
            # Offset accumulates: previous offset + next segment duration - transition overlap
            offset += durations[i - 1] - transition_duration

            if i == len(segment_files) - 1:
                # Last one outputs to [vout]/[aout]
                filter_parts.append(
                    f"[{prev_v}][{i}:v]xfade=transition=fade:duration={transition_duration}:offset={offset:.3f}[vout]"
                )
                audio_filter_parts.append(
                    f"[{prev_a}][{i}:a]acrossfade=d={transition_duration}:c1=tri:c2=tri[aout]"
                )
            else:
                filter_parts.append(
                    f"[{prev_v}][{i}:v]xfade=transition=fade:duration={transition_duration}:offset={offset:.3f}[v{i}]"
                )
                audio_filter_parts.append(
                    f"[{prev_a}][{i}:a]acrossfade=d={transition_duration}:c1=tri:c2=tri[a{i}]"
                )

    filter_graph = ";".join(filter_parts + audio_filter_parts)

    cmd = ["ffmpeg", "-y"] + inputs + [
        "-filter_complex", filter_graph,
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-crf", str(CRF), "-preset", PRESET,
        "-c:a", "aac", "-b:a", "128k",
        str(output_path),
    ]

    subprocess.run(cmd, capture_output=True, timeout=FFMPEG_TIMEOUT, check=True)


def assemble_video(module_num: int, part_num: int) -> bool:
    """Assemble a Spanish slide video with audio-driven durations + transitions."""
    module_name = MODULES[module_num]
    module_dir = BASE / module_name
    work_dir = module_dir / "Videos" / f"Module {module_num} Part {part_num}_work"
    slides_es_dir = work_dir / "slides_es"
    en_timing_path = work_dir / "timing.json"

    manifest_path = Path(f"C:/Users/rcox/elevenlabs-n8n/output/Module {module_num} Part {part_num}_work/manifest.json")
    output_path = module_dir / "Videos" / f"Module {module_num} Part {part_num}_es.mp4"

    # Check prerequisites
    if not en_timing_path.exists():
        print(f"  ERROR: English timing not found. Run detect_timing.py first.")
        return False
    if not manifest_path.exists():
        print(f"  ERROR: Manifest not found. Run audio pipeline first.")
        return False
    if not slides_es_dir.exists():
        print(f"  ERROR: Spanish slides not found. Run export_slides.ps1 first.")
        return False

    # Load data
    with open(en_timing_path) as f:
        en_timing = json.load(f)
    with open(manifest_path) as f:
        manifest = json.load(f)

    transcript_segs = manifest["transcript"]["segments"]
    synth_segs = manifest["synthesized_segments"]

    # Map transcript segments to slides
    slide_mapping = map_segments_to_slides(en_timing, transcript_segs)

    # Group synthesized audio segments by slide
    slide_audio: dict[int | None, list[Path]] = {}
    for i, (synth, slide_num) in enumerate(zip(synth_segs, slide_mapping)):
        seg_path = Path(synth["file_path"])
        if not seg_path.is_absolute():
            seg_path = Path("C:/Users/rcox/elevenlabs-n8n") / seg_path
        if slide_num not in slide_audio:
            slide_audio[slide_num] = []
        slide_audio[slide_num].append(seg_path)

    # Get ordered list of slides (preserve order from timing)
    slide_order = []
    for seg in en_timing["segments"]:
        s = seg.get("slide")
        if s not in slide_order:
            slide_order.append(s)

    print(f"  Slides: {len(slide_order)}, Audio segments: {len(synth_segs)}")

    # Assembly work directory
    assembly_dir = work_dir / "slide_assembly_es"
    assembly_dir.mkdir(exist_ok=True)

    # Build per-slide videos
    slide_videos = []

    # Intro black
    if INTRO_PADDING > 0:
        intro_path = assembly_dir / "intro_black.mp4"
        if not intro_path.exists():
            print(f"  Creating intro ({INTRO_PADDING}s black)...")
            create_silent_video(None, INTRO_PADDING, intro_path)
        slide_videos.append(intro_path)

    for slide_num in slide_order:
        audio_files = slide_audio.get(slide_num, [])
        slide_path = slides_es_dir / f"slide_{slide_num:02d}.png" if slide_num else None

        if not audio_files:
            print(f"  Slide {slide_num}: no audio segments, skipping")
            continue

        # Concatenate this slide's audio segments (raw, no padding)
        raw_audio_path = assembly_dir / f"slide_{slide_num}_audio_raw.aac"
        if not raw_audio_path.exists():
            audio_duration = concat_audio_segments(audio_files, raw_audio_path)
        else:
            audio_duration = get_duration(raw_audio_path)

        # Add silence padding before and after the audio
        slide_audio_path = assembly_dir / f"slide_{slide_num}_audio.aac"
        slide_duration = SLIDE_PAD_BEFORE + audio_duration + SLIDE_PAD_AFTER
        if not slide_audio_path.exists():
            subprocess.run(
                ["ffmpeg", "-y",
                 "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo",
                 "-i", str(raw_audio_path),
                 "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo",
                 "-filter_complex",
                 f"[0:a]atrim=0:{SLIDE_PAD_BEFORE}[pre];"
                 f"[2:a]atrim=0:{SLIDE_PAD_AFTER}[post];"
                 f"[pre][1:a][post]concat=n=3:v=0:a=1[out]",
                 "-map", "[out]",
                 "-c:a", "aac", "-b:a", "128k",
                 str(slide_audio_path)],
                capture_output=True, timeout=FFMPEG_TIMEOUT, check=True,
            )

        print(f"  Slide {slide_num}: {len(audio_files)} segments, "
              f"{audio_duration:.1f}s audio + {SLIDE_PAD_BEFORE}+{SLIDE_PAD_AFTER}s padding = {slide_duration:.1f}s")

        # Create slide video
        slide_video_path = assembly_dir / f"slide_{slide_num}_video.mp4"
        if not slide_video_path.exists():
            create_slide_video_with_audio(slide_path, slide_audio_path, slide_duration, slide_video_path)
        slide_videos.append(slide_video_path)

    # Outro black
    if OUTRO_PADDING > 0:
        outro_path = assembly_dir / "outro_black.mp4"
        if not outro_path.exists():
            print(f"  Creating outro ({OUTRO_PADDING}s black)...")
            create_silent_video(None, OUTRO_PADDING, outro_path)
        slide_videos.append(outro_path)

    if len(slide_videos) < 2:
        print(f"  ERROR: Not enough segments to assemble")
        return False

    # Concatenate with crossfade transitions
    print(f"\n  Concatenating {len(slide_videos)} segments with {TRANSITION_DURATION}s crossfade transitions...")
    try:
        concat_with_transitions(slide_videos, TRANSITION_DURATION, output_path)
    except subprocess.CalledProcessError as e:
        # If xfade fails, fall back to simple concat
        print(f"  Transition concat failed, falling back to simple concat...")
        stderr = e.stderr.decode("utf-8", errors="replace") if isinstance(e.stderr, bytes) else str(e.stderr)
        for line in stderr.strip().split("\n")[-3:]:
            print(f"    {line}")

        list_path = assembly_dir / "final_concat.txt"
        with open(list_path, "w") as f:
            for v in slide_videos:
                safe = str(v).replace("\\", "/").replace("'", "'\\''")
                f.write(f"file '{safe}'\n")
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_path),
             "-c:v", "libx264", "-crf", str(CRF), "-preset", PRESET,
             "-c:a", "aac", "-b:a", "128k", str(output_path)],
            capture_output=True, timeout=FFMPEG_TIMEOUT, check=True,
        )

    # Report
    out_duration = get_duration(output_path)
    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"\n  Output: {output_path.name} ({size_mb:.1f} MB, {out_duration:.1f}s)")

    return True


def main():
    module_filter = 0
    part_filter = 0
    for arg in sys.argv[1:]:
        if arg.startswith("--module="):
            module_filter = int(arg.split("=")[1])
        elif arg.startswith("--part="):
            part_filter = int(arg.split("=")[1])

    if module_filter and part_filter:
        assemble_video(module_filter, part_filter)
    elif module_filter:
        for part in range(1, 4):
            print(f"\n{'='*60}")
            print(f"Module {module_filter} Part {part}")
            print(f"{'='*60}")
            assemble_video(module_filter, part)
    else:
        for mod in range(1, 8):
            for part in range(1, 4):
                print(f"\n{'='*60}")
                print(f"Module {mod} Part {part}")
                print(f"{'='*60}")
                assemble_video(mod, part)


if __name__ == "__main__":
    main()
