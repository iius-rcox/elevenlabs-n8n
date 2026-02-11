"""Batch process all Module N Part videos through the translation pipeline."""

import os
import re
import sys
import traceback
from pathlib import Path

os.chdir(r"C:\Users\rcox\elevenlabs-n8n")

from click.testing import CliRunner
from video_translator.cli import main

BASE = Path(r"c:\Users\rcox\INSULATIONS, INC\Supervisory Training - Documents")

# Find all matching videos (exclude already-translated _es files)
videos = []
for mp4 in BASE.rglob("*.mp4"):
    if re.search(r"Module \d+ Part \d+\.mp4$", mp4.name):
        videos.append(mp4)

videos.sort(key=lambda p: p.name)

print(f"Found {len(videos)} source videos:\n")
for v in videos:
    out = v.parent / f"{v.stem}_es{v.suffix}"
    exists = out.exists()
    print(f"  {'[DONE]' if exists else '[ .. ]'} {v.name}")

pending = [v for v in videos if not (v.parent / f"{v.stem}_es{v.suffix}").exists()]
print(f"\n{len(pending)} remaining to process.\n")

runner = CliRunner()

for i, video in enumerate(pending, 1):
    output_dir = str(video.parent)
    print(f"\n{'='*60}")
    print(f"[{i}/{len(pending)}] {video.name}")
    print(f"Output: {output_dir}")
    print(f"{'='*60}\n", flush=True)

    result = runner.invoke(main, [
        str(video),
        "--output-dir", output_dir,
        "--yes",
        "--keep-intermediates",
    ])

    if result.exit_code != 0:
        print(f"ERROR (exit {result.exit_code}): {video.name}")
        if result.exception:
            traceback.print_exception(
                type(result.exception), result.exception,
                result.exception.__traceback__,
            )
    else:
        out = video.parent / f"{video.stem}_es{video.suffix}"
        if out.exists():
            size_mb = out.stat().st_size / (1024 * 1024)
            print(f"OK: {video.name} -> {out.name} ({size_mb:.1f} MB)")
        else:
            print(f"WARNING: {video.name} returned 0 but no output file!")
            # Print last few lines of output for debugging
            lines = result.output.strip().split("\n")
            for line in lines[-10:]:
                print(f"  > {line}")

print(f"\n{'='*60}")
print("BATCH COMPLETE")
print(f"{'='*60}")

# Final tally
done = 0
for v in videos:
    if (v.parent / f"{v.stem}_es{v.suffix}").exists():
        done += 1
print(f"\n{done}/{len(videos)} videos translated.")
