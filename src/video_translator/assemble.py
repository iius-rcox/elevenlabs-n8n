"""Audio assembly: combine synthesized segments into a timed audio track."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from .audio_extract import get_duration
from .config import check_ffmpeg
from .models import SynthesizedSegment

logger = logging.getLogger(__name__)

TIMEOUT = 600
# Max speed-up factor before truncating
MAX_TEMPO = 1.15
# Fade-out duration for truncated segments (ms)
FADE_MS = 100
# Max segments per FFmpeg filter graph batch
FILTER_BATCH_SIZE = 25


def assemble_audio(
    synth_segments: list[SynthesizedSegment],
    total_duration: float,
    output_path: Path,
) -> Path:
    """Assemble synthesized segments into a single audio track.

    Strategy:
    1. Generate a silent base track of total_duration
    2. For each segment, speed-adjust if needed, then overlay at its start time
    3. Batch filter graphs for large segment counts

    Returns the output path.
    """
    ffmpeg = str(check_ffmpeg())

    if not synth_segments:
        # Just create a silent track
        _create_silence(ffmpeg, total_duration, output_path)
        return output_path

    # Process segments: speed-adjust or truncate as needed
    work_dir = output_path.parent / "assembly_work"
    work_dir.mkdir(parents=True, exist_ok=True)

    prepared = _prepare_segments(ffmpeg, synth_segments, work_dir)

    # Assemble in batches if many segments
    if len(prepared) <= FILTER_BATCH_SIZE:
        _assemble_batch(ffmpeg, prepared, total_duration, output_path)
    else:
        _assemble_multi_batch(ffmpeg, prepared, total_duration, output_path, work_dir)

    return output_path


def _create_silence(ffmpeg: str, duration: float, output_path: Path) -> None:
    """Create a silent audio file of the given duration."""
    subprocess.run(
        [
            ffmpeg,
            "-f", "lavfi",
            "-i", f"anullsrc=r=44100:cl=stereo:d={duration}",
            "-t", str(duration),
            "-y",
            str(output_path),
        ],
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
        check=True,
    )


def _prepare_segments(
    ffmpeg: str,
    segments: list[SynthesizedSegment],
    work_dir: Path,
) -> list[tuple[SynthesizedSegment, Path]]:
    """Prepare each segment: speed-adjust or truncate if needed.

    Returns list of (segment, prepared_file_path) tuples.
    """
    prepared = []

    for seg in segments:
        slot_duration = seg.end - seg.start
        if slot_duration <= 0:
            logger.warning("Segment %d has zero/negative slot duration, skipping", seg.index)
            continue

        ratio = seg.actual_duration / slot_duration

        if ratio <= 1.0:
            # Fits fine, use as-is
            prepared.append((seg, seg.file_path))
        elif ratio <= MAX_TEMPO:
            # Speed up slightly
            tempo = ratio
            out = work_dir / f"adj_{seg.index:04d}.mp3"
            _speed_adjust(ffmpeg, seg.file_path, tempo, out)
            prepared.append((seg, out))
        else:
            # Too long: truncate with fade-out
            logger.warning(
                "Segment %d is %.0f%% too long (%.2fs vs %.2fs slot), truncating",
                seg.index,
                (ratio - 1) * 100,
                seg.actual_duration,
                slot_duration,
            )
            out = work_dir / f"trunc_{seg.index:04d}.mp3"
            _truncate_with_fade(ffmpeg, seg.file_path, slot_duration, out)
            prepared.append((seg, out))

    return prepared


def _speed_adjust(ffmpeg: str, input_path: Path, tempo: float, output_path: Path) -> None:
    """Speed up audio by the given tempo factor."""
    subprocess.run(
        [
            ffmpeg,
            "-i", str(input_path),
            "-af", f"atempo={tempo:.4f}",
            "-y",
            str(output_path),
        ],
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
        check=True,
    )


def _truncate_with_fade(
    ffmpeg: str, input_path: Path, duration: float, output_path: Path
) -> None:
    """Truncate audio to duration with a short fade-out at the end."""
    fade_start = max(0, duration - FADE_MS / 1000)
    subprocess.run(
        [
            ffmpeg,
            "-i", str(input_path),
            "-t", str(duration),
            "-af", f"afade=t=out:st={fade_start:.3f}:d={FADE_MS / 1000:.3f}",
            "-y",
            str(output_path),
        ],
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
        check=True,
    )


def _assemble_batch(
    ffmpeg: str,
    segments: list[tuple[SynthesizedSegment, Path]],
    total_duration: float,
    output_path: Path,
) -> None:
    """Assemble a batch of segments using a single FFmpeg filter graph.

    Creates a silent base track, delays each segment to its start time,
    then mixes all together.
    """
    inputs = ["-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo:d={total_duration}"]
    filter_parts = []

    for i, (seg, path) in enumerate(segments):
        input_idx = i + 1  # 0 is the silence base
        inputs.extend(["-i", str(path)])

        delay_ms = int(seg.start * 1000)
        filter_parts.append(
            f"[{input_idx}:a]adelay={delay_ms}|{delay_ms}[d{i}]"
        )

    # Mix all delayed segments with the silent base
    mix_inputs = "[0:a]" + "".join(f"[d{i}]" for i in range(len(segments)))
    n_inputs = len(segments) + 1
    filter_parts.append(
        f"{mix_inputs}amix=inputs={n_inputs}:duration=first:dropout_transition=0:normalize=0[out]"
    )

    filter_graph = ";".join(filter_parts)

    cmd = [ffmpeg] + inputs + [
        "-filter_complex", filter_graph,
        "-map", "[out]",
        "-t", str(total_duration),
        "-y",
        str(output_path),
    ]

    subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
        check=True,
    )


def _assemble_multi_batch(
    ffmpeg: str,
    segments: list[tuple[SynthesizedSegment, Path]],
    total_duration: float,
    output_path: Path,
    work_dir: Path,
) -> None:
    """Assemble segments in batches, then merge batch outputs."""
    batch_outputs: list[Path] = []

    for batch_idx in range(0, len(segments), FILTER_BATCH_SIZE):
        batch = segments[batch_idx : batch_idx + FILTER_BATCH_SIZE]
        batch_out = work_dir / f"batch_{batch_idx:04d}.wav"
        _assemble_batch(ffmpeg, batch, total_duration, batch_out)
        batch_outputs.append(batch_out)

    if len(batch_outputs) == 1:
        # Just rename/copy
        subprocess.run(
            [ffmpeg, "-i", str(batch_outputs[0]), "-y", str(output_path)],
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
            check=True,
        )
        return

    # Mix all batch outputs together
    inputs = []
    for p in batch_outputs:
        inputs.extend(["-i", str(p)])

    n = len(batch_outputs)
    mix_refs = "".join(f"[{i}:a]" for i in range(n))
    filter_graph = f"{mix_refs}amix=inputs={n}:duration=longest:dropout_transition=0:normalize=0[out]"

    cmd = [ffmpeg] + inputs + [
        "-filter_complex", filter_graph,
        "-map", "[out]",
        "-t", str(total_duration),
        "-y",
        str(output_path),
    ]

    subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
        check=True,
    )
