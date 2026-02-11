"""ElevenLabs Scribe transcription: audio -> transcript with timestamps."""

from __future__ import annotations

import re
from pathlib import Path

from elevenlabs.client import ElevenLabs

from .config import SCRIBE_MODEL
from .models import TranscriptResult, TranscriptSegment, TranscriptWord

# Sentence-ending punctuation
SENTENCE_END = re.compile(r"[.!?]$")
# Max gap between words before forcing a new segment (seconds)
MAX_PAUSE = 0.7
# Max segment duration (seconds)
MAX_SEGMENT_DURATION = 15.0


def transcribe(audio_path: Path, client: ElevenLabs) -> TranscriptResult:
    """Transcribe an audio file using ElevenLabs Scribe.

    Returns a TranscriptResult with sentence-level segments built from
    word-level timestamps.
    """
    with open(audio_path, "rb") as f:
        response = client.speech_to_text.convert(
            model_id=SCRIBE_MODEL,
            file=f,
            language_code="en",
            timestamps_granularity="word",
        )

    # Extract words from response
    words = _extract_words(response)

    if not words:
        return TranscriptResult(
            segments=[],
            full_text="",
            duration=0.0,
        )

    # Group words into sentence segments
    segments = _group_into_segments(words)

    full_text = " ".join(w.text for w in words)
    duration = words[-1].end if words else 0.0

    return TranscriptResult(
        segments=segments,
        full_text=full_text,
        duration=duration,
    )


def _extract_words(response: object) -> list[TranscriptWord]:
    """Extract TranscriptWord list from the Scribe API response."""
    words = []

    # The response has a `words` attribute with word-level timestamps
    if hasattr(response, "words") and response.words:
        for w in response.words:
            words.append(TranscriptWord(
                start=w.start,
                end=w.end,
                text=w.text.strip(),
            ))

    return words


def _group_into_segments(words: list[TranscriptWord]) -> list[TranscriptSegment]:
    """Group words into sentence-level segments using punctuation, pauses, and max duration."""
    segments: list[TranscriptSegment] = []
    current_words: list[TranscriptWord] = []

    for i, word in enumerate(words):
        current_words.append(word)

        should_break = False

        # Check sentence-ending punctuation
        if SENTENCE_END.search(word.text):
            should_break = True

        # Check for long pause before next word
        if not should_break and i + 1 < len(words):
            gap = words[i + 1].start - word.end
            if gap > MAX_PAUSE:
                should_break = True

        # Check max segment duration
        if not should_break and current_words:
            seg_duration = word.end - current_words[0].start
            if seg_duration >= MAX_SEGMENT_DURATION:
                should_break = True

        if should_break:
            segments.append(_words_to_segment(current_words))
            current_words = []

    # Flush remaining words
    if current_words:
        segments.append(_words_to_segment(current_words))

    return segments


def _words_to_segment(words: list[TranscriptWord]) -> TranscriptSegment:
    """Create a TranscriptSegment from a list of words."""
    text = " ".join(w.text for w in words)
    return TranscriptSegment(
        start=words[0].start,
        end=words[-1].end,
        text=text,
    )
