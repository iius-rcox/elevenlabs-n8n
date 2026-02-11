"""ElevenLabs TTS: translated text segments -> audio files."""

from __future__ import annotations

from pathlib import Path

from elevenlabs.client import ElevenLabs
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from .audio_extract import get_duration
from .config import DEFAULT_VOICE_ID, TTS_MODEL
from .models import SynthesizedSegment, TranslatedSegment


def _preprocess_tts_text(text: str) -> str:
    """Clean up text for TTS pronunciation.

    Fixes known issues where symbols or abbreviations are mispronounced.
    """
    import re
    # "I&I" → "I and I" (TTS misreads ampersand as "uy" or similar)
    text = re.sub(r'\bI\s*&\s*I\b', 'I and I', text)
    # General ampersand cleanup for any remaining cases
    text = text.replace('&', ' and ')
    # Clean up double spaces
    text = re.sub(r'  +', ' ', text)
    return text.strip()


def synthesize_segment(
    index: int,
    segment: TranslatedSegment,
    voice_id: str,
    client: ElevenLabs,
    output_dir: Path,
) -> SynthesizedSegment:
    """Synthesize a single translated segment to an MP3 file.

    Returns a SynthesizedSegment with actual duration metadata.
    """
    output_path = output_dir / f"seg_{index:04d}.mp3"

    tts_text = _preprocess_tts_text(segment.translated_text)

    audio_iter = client.text_to_speech.convert(
        voice_id=voice_id,
        text=tts_text,
        model_id=TTS_MODEL,
        output_format="mp3_44100_128",
    )

    # Write audio bytes to file
    with open(output_path, "wb") as f:
        for chunk in audio_iter:
            f.write(chunk)

    # Measure actual duration
    actual_duration = get_duration(output_path)

    return SynthesizedSegment(
        index=index,
        file_path=output_path,
        actual_duration=actual_duration,
        start=segment.start,
        end=segment.end,
    )


def synthesize_all(
    segments: list[TranslatedSegment],
    voice_id: str,
    client: ElevenLabs,
    output_dir: Path,
) -> list[SynthesizedSegment]:
    """Synthesize all translated segments sequentially with a progress bar.

    Creates output_dir/segments/ and writes seg_NNNN.mp3 files.
    """
    seg_dir = output_dir / "segments"
    seg_dir.mkdir(parents=True, exist_ok=True)

    results: list[SynthesizedSegment] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
    ) as progress:
        task = progress.add_task("Synthesizing audio", total=len(segments))

        for i, seg in enumerate(segments):
            result = synthesize_segment(i, seg, voice_id, client, seg_dir)
            results.append(result)
            progress.update(task, advance=1)

    return results
