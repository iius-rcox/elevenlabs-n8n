"""Generate Spanish slide timing from audio pipeline manifest + English slide timing.

Maps English transcript segments to slides (via English SSIM timing),
then uses the Spanish audio segment placement to compute when each
slide should appear in the Spanish video.

Output: timing_es.json in the work directory.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BASE = Path(r"c:\Users\rcox\INSULATIONS, INC\Supervisory Training - Documents")

MODULES = {
    1: "Module 1 - Welcome and Culture",
    2: "Module 2 - Hiring Benefits and Supervisor Policy",
    3: "Module 3 - Supervisor Expectations and Job Rules",
    4: "Module 4 - Leadership",
    5: "Module 5 - Safety Leadership",
    6: "Module 6 - Accident Investigation",
    7: "Module 7 - Company-Owned Vehicles",
}


def map_segments_to_slides(
    en_timing: dict, transcript_segments: list[dict]
) -> list[int | None]:
    """For each transcript segment, determine which English slide it falls on.

    Uses the midpoint of each transcript segment to look up which slide
    was showing at that time in the English video.
    """
    en_segments = en_timing["segments"]
    mapping = []

    for seg in transcript_segments:
        midpoint = (seg["start"] + seg["end"]) / 2
        matched_slide = None

        for en_seg in en_segments:
            if en_seg["start"] <= midpoint < en_seg["end"]:
                matched_slide = en_seg.get("slide")
                break

        mapping.append(matched_slide)

    return mapping


def generate_es_timing(
    en_timing: dict,
    manifest: dict,
) -> dict:
    """Generate Spanish slide timing from manifest data.

    The audio assembler places Spanish segments at the same start times
    as the English segments. So we use the English segment start/end
    times (which are also the Spanish audio placement times) to figure
    out when each slide should be shown.

    For each transcript segment, we know:
    - Which slide it maps to (from English SSIM timing)
    - When it starts/ends in the assembled audio timeline

    We group consecutive segments on the same slide into slide segments.
    """
    transcript_segs = manifest["transcript"]["segments"]

    # Map each transcript segment to a slide
    slide_mapping = map_segments_to_slides(en_timing, transcript_segs)

    print(f"  Segment-to-slide mapping:")
    for i, (seg, slide) in enumerate(zip(transcript_segs, slide_mapping)):
        print(f"    Seg {i}: {seg['start']:.1f}s-{seg['end']:.1f}s -> slide {slide}")

    # Build Spanish timing by grouping consecutive segments on same slide
    es_segments = []
    current_slide = None
    current_start = 0.0

    for seg, slide in zip(transcript_segs, slide_mapping):
        if slide != current_slide:
            if current_slide is not None:
                es_segments.append({
                    "slide": current_slide,
                    "start": current_start,
                    "end": seg["start"],
                })
            current_slide = slide
            current_start = seg["start"]

    # Close the last segment — use total duration from English timing
    total_duration = en_timing["duration"]
    if current_slide is not None:
        es_segments.append({
            "slide": current_slide,
            "start": current_start,
            "end": total_duration,
        })

    # Handle any leading silence (before first transcript segment)
    first_transcript_start = transcript_segs[0]["start"] if transcript_segs else 0
    if first_transcript_start > 0.5 and es_segments and es_segments[0]["start"] > 0:
        # Insert black/first-slide segment for the intro
        es_segments.insert(0, {
            "slide": es_segments[0]["slide"],
            "start": 0.0,
            "end": es_segments[0]["start"],
        })
        # Merge with the next segment if same slide
        if len(es_segments) > 1 and es_segments[0]["slide"] == es_segments[1]["slide"]:
            es_segments[1]["start"] = 0.0
            es_segments.pop(0)

    return {
        "segments": es_segments,
        "duration": total_duration,
        "source": "es_timing_from_manifest",
    }


def process_video(module_num: int, part_num: int) -> bool:
    """Generate Spanish timing for a single video."""
    module_name = MODULES[module_num]
    work_dir = BASE / module_name / "Videos" / f"Module {module_num} Part {part_num}_work"
    en_timing_path = work_dir / "timing.json"

    # Look for manifest in the output work dir
    manifest_path = Path(f"C:/Users/rcox/elevenlabs-n8n/output/Module {module_num} Part {part_num}_work/manifest.json")

    if not en_timing_path.exists():
        print(f"  English timing not found: {en_timing_path}")
        return False

    if not manifest_path.exists():
        print(f"  Manifest not found: {manifest_path}")
        return False

    with open(en_timing_path) as f:
        en_timing = json.load(f)

    with open(manifest_path) as f:
        manifest = json.load(f)

    print(f"  English timing: {len(en_timing['segments'])} segments")
    print(f"  Transcript: {len(manifest['transcript']['segments'])} segments")

    es_timing = generate_es_timing(en_timing, manifest)

    print(f"\n  Spanish timing: {len(es_timing['segments'])} segments")
    for seg in es_timing["segments"]:
        slide_str = f"slide {seg['slide']}" if seg['slide'] is not None else "black"
        duration = seg["end"] - seg["start"]
        print(f"    {seg['start']:.1f}s - {seg['end']:.1f}s ({duration:.1f}s) - {slide_str}")

    # Save
    output_path = work_dir / "timing_es.json"
    with open(output_path, "w") as f:
        json.dump(es_timing, f, indent=2)
    print(f"\n  Saved: {output_path}")

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
        process_video(module_filter, part_filter)
    elif module_filter:
        for part in range(1, 4):
            print(f"\n--- Module {module_filter} Part {part} ---")
            process_video(module_filter, part)
    else:
        for mod in range(1, 8):
            for part in range(1, 4):
                print(f"\n--- Module {mod} Part {part} ---")
                process_video(mod, part)


if __name__ == "__main__":
    main()
