"""Assemble narrated slide video from slide PNGs + TTS audio."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

FFMPEG_TIMEOUT = 600
WIDTH = 1920
HEIGHT = 1080
FPS = 30
CRF = 18
PRESET = "medium"

PRE_PAD = 1.0
POST_PAD = 1.0
SILENT_SLIDE_DUR = 2.0
TRANSITION_DURATION = 0.5


def get_duration(path):
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(path)],
        capture_output=True, text=True, timeout=30)
    return float(json.loads(r.stdout)["format"]["duration"])


def create_slide_video(image_path, audio_path, duration, output):
    subprocess.run(
        ["ffmpeg", "-y",
         "-loop", "1", "-i", str(image_path),
         "-i", str(audio_path),
         "-t", str(duration),
         "-vf", f"scale={WIDTH}:{HEIGHT},format=yuv420p",
         "-c:v", "libx264", "-crf", str(CRF), "-preset", PRESET,
         "-r", str(FPS),
         "-c:a", "aac", "-b:a", "128k", "-shortest",
         str(output)],
        capture_output=True, timeout=FFMPEG_TIMEOUT, check=True)


def create_silent_video(image_path, duration, output):
    subprocess.run(
        ["ffmpeg", "-y",
         "-loop", "1", "-i", str(image_path),
         "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
         "-t", str(duration),
         "-vf", f"scale={WIDTH}:{HEIGHT},format=yuv420p",
         "-c:v", "libx264", "-crf", str(CRF), "-preset", PRESET,
         "-r", str(FPS), "-c:a", "aac", "-shortest",
         str(output)],
        capture_output=True, timeout=FFMPEG_TIMEOUT, check=True)


def pad_audio(audio_path, padded_path, pre=PRE_PAD, post=POST_PAD):
    subprocess.run(
        ["ffmpeg", "-y",
         "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
         "-i", str(audio_path),
         "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
         "-filter_complex",
         f"[0:a]atrim=0:{pre}[pre];"
         f"[2:a]atrim=0:{post}[post];"
         f"[pre][1:a][post]concat=n=3:v=0:a=1[out]",
         "-map", "[out]", "-c:a", "aac", "-b:a", "128k",
         str(padded_path)],
        capture_output=True, timeout=FFMPEG_TIMEOUT, check=True)


def _xfade_pair(a_path, b_path, transition_dur, out_path):
    dur_a = get_duration(a_path)
    offset = dur_a - transition_dur
    fg = (
        f"[0:v][1:v]xfade=transition=fade:duration={transition_dur}:offset={offset:.3f}[vout];"
        f"[0:a][1:a]acrossfade=d={transition_dur}:c1=tri:c2=tri[aout]"
    )
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(a_path), "-i", str(b_path),
         "-filter_complex", fg,
         "-map", "[vout]", "-map", "[aout]",
         "-c:v", "libx264", "-crf", str(CRF), "-preset", PRESET,
         "-c:a", "aac", "-b:a", "128k", str(out_path)],
        capture_output=True, timeout=FFMPEG_TIMEOUT, check=True)


def concat_with_transitions(segments, transition_dur, output):
    if len(segments) == 1:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(segments[0]),
             "-c:v", "libx264", "-crf", str(CRF), "-c:a", "aac", str(output)],
            capture_output=True, timeout=FFMPEG_TIMEOUT, check=True)
        return

    try:
        work_dir = output.parent / f"{output.stem}_merge"
        work_dir.mkdir(parents=True, exist_ok=True)

        current = segments[0]
        for i in range(1, len(segments)):
            print(f"  Merging segment {i+1}/{len(segments)}...")
            if i == len(segments) - 1:
                _xfade_pair(current, segments[i], transition_dur, output)
            else:
                merged = work_dir / f"merged_{i:03d}.mp4"
                _xfade_pair(current, segments[i], transition_dur, merged)
                current = merged
    except subprocess.CalledProcessError as e:
        print(f"  xfade failed ({e}), falling back to simple concat...")
        list_path = output.parent / "fallback_concat.txt"
        with open(list_path, "w") as f:
            for v in segments:
                f.write(f"file '{str(v).replace(chr(92), '/')}'\n")
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_path),
             "-c:v", "libx264", "-crf", str(CRF), "-preset", PRESET,
             "-c:a", "aac", "-b:a", "128k", str(output)],
            capture_output=True, timeout=FFMPEG_TIMEOUT, check=True)


def assemble_section(name, work_dir, output_path):
    slides_dir = work_dir / "slides"
    audio_dir = work_dir / "audio"
    segments_dir = work_dir / "segments"
    segments_dir.mkdir(parents=True, exist_ok=True)

    with open(work_dir / "notes.json", encoding="utf-8") as f:
        notes = json.load(f)

    print(f"Assembling video: {len(notes)} slides")
    slide_videos = []

    for note in notes:
        sn = note["slide"]
        slide_img = slides_dir / f"slide_{sn:02d}.png"
        audio_file = audio_dir / f"slide_{sn:02d}.mp3"
        slide_vid = segments_dir / f"slide_{sn:02d}_video.mp4"

        if slide_vid.exists():
            print(f"  Slide {sn}: segment exists (checkpoint)")
            slide_videos.append(slide_vid)
            continue

        if audio_file.exists():
            padded = segments_dir / f"slide_{sn:02d}_padded.aac"
            if not padded.exists():
                pad_audio(audio_file, padded)
            audio_dur = get_duration(audio_file)
            total_dur = PRE_PAD + audio_dur + POST_PAD
            print(f"  Slide {sn}: creating video ({audio_dur:.1f}s audio, {total_dur:.1f}s total)")
            create_slide_video(slide_img, padded, total_dur, slide_vid)
        else:
            print(f"  Slide {sn}: silent ({SILENT_SLIDE_DUR}s)")
            create_silent_video(slide_img, SILENT_SLIDE_DUR, slide_vid)

        slide_videos.append(slide_vid)

    print(f"\nJoining {len(slide_videos)} segments with crossfade transitions...")
    concat_with_transitions(slide_videos, TRANSITION_DURATION, output_path)

    final_dur = get_duration(output_path)
    final_size = output_path.stat().st_size / (1024 * 1024)
    print(f"Done! {output_path.name}: {final_dur:.1f}s, {final_size:.1f} MB")


def main():
    base = Path(r"c:\Users\rcox\INSULATIONS, INC\Supervisory Training - Documents\Module 1 - Welcome and Culture\PowerPoints")

    sections = [
        ("Module 1 Section 2", base / "Module 1 Section 2_es_work"),
        ("Module 1 Section 3", base / "Module 1 Section 3_es_work"),
    ]

    for name, work_dir in sections:
        print(f"\n{'='*60}")
        print(f"=== {name} ===")
        print(f"{'='*60}")
        output_path = base / f"{name}_es.mp4"
        assemble_section(name, work_dir, output_path)


if __name__ == "__main__":
    main()
