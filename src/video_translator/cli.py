"""CLI entry point and pipeline orchestration."""

from __future__ import annotations

import json
import logging
import shutil
import sys
from datetime import datetime
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from .assemble import assemble_audio
from .audio_extract import extract_audio, get_duration, has_audio_stream, mux_audio
from .config import (
    DEFAULT_VOICE_ID,
    SUPPORTED_EXTENSIONS,
    ConfigError,
    check_ffmpeg,
    check_ffprobe,
    create_clients,
    validate_path,
)
from .models import (
    CostEstimate,
    PipelineManifest,
    StageStatus,
    StageStatusEnum,
    SynthesizedSegment,
    TranscriptResult,
    TranslationResult,
)
from .review import review_translations
from .synthesize import synthesize_all
from .transcribe import transcribe
from .translate import estimate_cost, translate_segments

console = Console()
logger = logging.getLogger("video_translator")

MANIFEST_FILE = "manifest.json"


@click.command()
@click.argument("input_path", type=click.Path(exists=True))
@click.option(
    "--output-dir", "-o",
    type=click.Path(),
    default=None,
    help="Output directory (default: ./output)",
)
@click.option(
    "--voice", "-v",
    default=DEFAULT_VOICE_ID,
    help=f"ElevenLabs voice ID (default: {DEFAULT_VOICE_ID})",
)
@click.option("--keep-intermediates", "-k", is_flag=True, help="Keep intermediate files")
@click.option("--verbose", is_flag=True, help="Enable verbose logging")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompts")
def main(
    input_path: str,
    output_dir: str | None,
    voice: str,
    keep_intermediates: bool,
    verbose: bool,
    yes: bool,
) -> None:
    """Translate English video(s) to Spanish with ElevenLabs TTS dubbing.

    INPUT_PATH can be a single video file or a directory of videos.
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    # --- Validate prerequisites ---
    try:
        check_ffmpeg()
        check_ffprobe()
        el_client, oa_client = create_clients()
    except ConfigError as e:
        console.print(f"[red]Configuration error:[/red] {e}")
        sys.exit(1)

    # --- Discover videos ---
    input_p = validate_path(Path(input_path))
    if input_p.is_file():
        videos = [input_p]
    elif input_p.is_dir():
        videos = sorted(
            f for f in input_p.iterdir()
            if f.suffix.lower() in SUPPORTED_EXTENSIONS
        )
        if not videos:
            console.print(f"[red]No supported video files found in {input_p}[/red]")
            console.print(f"Supported: {', '.join(SUPPORTED_EXTENSIONS)}")
            sys.exit(1)
    else:
        console.print(f"[red]{input_p} is not a file or directory[/red]")
        sys.exit(1)

    # --- Set up output directory ---
    out_dir = Path(output_dir) if output_dir else Path("output")
    out_dir.mkdir(parents=True, exist_ok=True)

    console.print(f"\nFound [bold]{len(videos)}[/bold] video(s) to process.\n")

    total_cost = CostEstimate()
    processed = 0

    for video in videos:
        console.rule(f"[bold blue]{video.name}")
        try:
            cost = _process_video(
                video, out_dir, voice, keep_intermediates, yes,
                el_client, oa_client, verbose,
            )
            total_cost.scribe_cost += cost.scribe_cost
            total_cost.translation_cost += cost.translation_cost
            total_cost.tts_cost += cost.tts_cost
            total_cost.total += cost.total
            processed += 1
        except Exception as e:
            console.print(f"[red]Error processing {video.name}:[/red] {e}")
            if verbose:
                logger.exception("Full traceback:")
            continue

    # --- Summary ---
    console.print()
    console.rule("[bold green]Summary")
    table = Table()
    table.add_column("Metric", style="bold")
    table.add_column("Value")
    table.add_row("Videos processed", f"{processed}/{len(videos)}")
    table.add_row("Output directory", str(out_dir.resolve()))
    table.add_row("Est. Scribe cost", f"${total_cost.scribe_cost:.4f}")
    table.add_row("Est. Translation cost", f"${total_cost.translation_cost:.4f}")
    table.add_row("Est. TTS cost", f"${total_cost.tts_cost:.4f}")
    table.add_row("Est. Total cost", f"${total_cost.total:.4f}")
    console.print(table)


def _process_video(
    video_path: Path,
    out_dir: Path,
    voice_id: str,
    keep_intermediates: bool,
    auto_yes: bool,
    el_client: object,
    oa_client: object,
    verbose: bool,
) -> CostEstimate:
    """Run the full pipeline for a single video. Returns cost estimate."""
    stem = video_path.stem
    work_dir = out_dir / f"{stem}_work"
    work_dir.mkdir(parents=True, exist_ok=True)

    output_video = out_dir / f"{stem}_es{video_path.suffix}"

    # Load or create manifest
    manifest = _load_manifest(work_dir, video_path, out_dir)

    cost = CostEstimate()

    # --- Stage 1: Extract audio ---
    audio_path = work_dir / "audio.wav"
    if _should_run(manifest, "extract"):
        console.print("  [cyan]Extracting audio...[/cyan]")
        _mark_running(manifest, "extract")
        if not has_audio_stream(video_path):
            raise ValueError(f"{video_path.name} has no audio stream")
        extract_audio(video_path, audio_path)
        _mark_completed(manifest, "extract")
        _save_manifest(manifest, work_dir)
    else:
        console.print("  [dim]Extract: already done, skipping[/dim]")

    audio_duration = get_duration(audio_path)

    # --- Stage 2: Transcribe ---
    if _should_run(manifest, "transcribe"):
        console.print("  [cyan]Transcribing audio...[/cyan]")
        _mark_running(manifest, "transcribe")
        transcript = transcribe(audio_path, el_client)
        manifest.transcript = transcript
        _mark_completed(manifest, "transcribe")
        _save_manifest(manifest, work_dir)
    else:
        console.print("  [dim]Transcribe: already done, skipping[/dim]")
        transcript = manifest.transcript

    if not transcript or not transcript.segments:
        console.print("  [yellow]No speech detected, skipping video[/yellow]")
        return cost

    console.print(f"  Found {len(transcript.segments)} segments, {len(transcript.full_text)} chars")

    # --- Cost estimate + confirm ---
    cost = estimate_cost(transcript, audio_duration)
    if not auto_yes:
        console.print(f"  Estimated cost: [bold]${cost.total:.4f}[/bold]")
        if not click.confirm("  Proceed?", default=True):
            console.print("  [yellow]Skipped[/yellow]")
            return cost

    # --- Stage 3: Translate ---
    if _should_run(manifest, "translate"):
        console.print("  [cyan]Translating to Spanish...[/cyan]")
        _mark_running(manifest, "translate")
        translation = translate_segments(transcript, oa_client)
        manifest.translation = translation
        _mark_completed(manifest, "translate")
        _save_manifest(manifest, work_dir)
    else:
        console.print("  [dim]Translate: already done, skipping[/dim]")
        translation = manifest.translation

    if not translation:
        raise ValueError("Translation result is missing")

    # --- Stage 3.5: Review translations ---
    if _should_run(manifest, "review"):
        console.print("  [cyan]Reviewing translations for quality...[/cyan]")
        _mark_running(manifest, "review")
        translation, issues = review_translations(translation, oa_client)
        if issues:
            console.print(f"  [yellow]Review found {len(issues)} issue(s):[/yellow]")
            for issue in issues:
                console.print(f"    [dim]Seg {issue['index']}:[/dim] {issue['issue']}")
                if verbose:
                    console.print(f"      [red]Before:[/red] {issue['translated']}")
                    console.print(f"      [green]After:[/green]  {issue['corrected']}")
            manifest.translation = translation
        else:
            console.print("  [green]Review passed — no issues found[/green]")
        _mark_completed(manifest, "review")
        _save_manifest(manifest, work_dir)
    else:
        console.print("  [dim]Review: already done, skipping[/dim]")

    # --- Stage 4: Synthesize ---
    if _should_run(manifest, "synthesize"):
        console.print("  [cyan]Synthesizing Spanish audio...[/cyan]")
        _mark_running(manifest, "synthesize")
        synth_segments = synthesize_all(
            translation.segments, voice_id, el_client, work_dir,
        )
        manifest.synthesized_segments = synth_segments
        _mark_completed(manifest, "synthesize")
        _save_manifest(manifest, work_dir)
    else:
        console.print("  [dim]Synthesize: already done, skipping[/dim]")
        synth_segments = manifest.synthesized_segments or []

    # --- Stage 5: Assemble ---
    if _should_run(manifest, "assemble"):
        console.print("  [cyan]Assembling final audio track...[/cyan]")
        _mark_running(manifest, "assemble")
        assembled_audio = work_dir / "assembled.wav"
        assemble_audio(synth_segments, audio_duration, assembled_audio)

        console.print("  [cyan]Muxing audio with video...[/cyan]")
        mux_audio(video_path, assembled_audio, output_video)
        manifest.output_video = output_video
        _mark_completed(manifest, "assemble")
        _save_manifest(manifest, work_dir)
    else:
        console.print("  [dim]Assemble: already done, skipping[/dim]")

    console.print(f"  [green]Done![/green] Output: {output_video}")

    # Clean up intermediates
    if not keep_intermediates:
        shutil.rmtree(work_dir, ignore_errors=True)

    return cost


# --- Manifest helpers ---


def _load_manifest(work_dir: Path, video_path: Path, out_dir: Path) -> PipelineManifest:
    """Load an existing manifest or create a new one."""
    manifest_path = work_dir / MANIFEST_FILE
    if manifest_path.exists():
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        return PipelineManifest.model_validate(data)
    return PipelineManifest(input_video=video_path, output_dir=out_dir)


def _save_manifest(manifest: PipelineManifest, work_dir: Path) -> None:
    """Save manifest to disk."""
    manifest_path = work_dir / MANIFEST_FILE
    data = manifest.model_dump(mode="json")
    manifest_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _should_run(manifest: PipelineManifest, stage: str) -> bool:
    """Check if a stage needs to run (not already completed)."""
    return manifest.stages[stage].status != StageStatusEnum.COMPLETED


def _mark_running(manifest: PipelineManifest, stage: str) -> None:
    manifest.stages[stage].status = StageStatusEnum.RUNNING
    manifest.stages[stage].started_at = datetime.now()


def _mark_completed(manifest: PipelineManifest, stage: str) -> None:
    manifest.stages[stage].status = StageStatusEnum.COMPLETED
    manifest.stages[stage].completed_at = datetime.now()
    manifest.stages[stage].error = None


def _mark_failed(manifest: PipelineManifest, stage: str, error: str) -> None:
    manifest.stages[stage].status = StageStatusEnum.FAILED
    manifest.stages[stage].error = error
