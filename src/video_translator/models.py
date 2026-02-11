"""Pydantic data models for the video translation pipeline."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field


# --- Transcription ---


class TranscriptWord(BaseModel):
    """A single word with timing information."""

    start: float
    end: float
    text: str


class TranscriptSegment(BaseModel):
    """A sentence-level segment of the transcript."""

    start: float
    end: float
    text: str
    speaker: str | None = None


class TranscriptResult(BaseModel):
    """Full transcription output."""

    segments: list[TranscriptSegment]
    full_text: str
    duration: float
    language: str = "en"


# --- Translation ---


class TranslatedSegment(BaseModel):
    """A translated segment with timing and syllable estimate."""

    original_text: str
    translated_text: str
    start: float
    end: float
    estimated_syllables: int = 0


class TranslationResult(BaseModel):
    """Full translation output."""

    segments: list[TranslatedSegment]


class TranslationEntry(BaseModel):
    """Single entry in a GPT-4o translation batch response."""

    index: int
    translated_text: str
    estimated_syllables: int


class TranslationResponse(BaseModel):
    """Structured output schema for GPT-4o translation calls."""

    translations: list[TranslationEntry]


# --- Synthesis ---


class SynthesizedSegment(BaseModel):
    """A synthesized audio segment with duration metadata."""

    index: int
    file_path: Path
    actual_duration: float
    start: float
    end: float


# --- Pipeline ---


class StageStatusEnum(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class StageStatus(BaseModel):
    """Status of a single pipeline stage."""

    status: StageStatusEnum = StageStatusEnum.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None


class PipelineManifest(BaseModel):
    """Tracks pipeline progress for a single video, enabling resume."""

    input_video: Path
    output_dir: Path
    stages: dict[str, StageStatus] = Field(default_factory=lambda: {
        "extract": StageStatus(),
        "transcribe": StageStatus(),
        "translate": StageStatus(),
        "review": StageStatus(),
        "synthesize": StageStatus(),
        "assemble": StageStatus(),
    })
    created_at: datetime = Field(default_factory=datetime.now)
    transcript: TranscriptResult | None = None
    translation: TranslationResult | None = None
    synthesized_segments: list[SynthesizedSegment] | None = None
    output_video: Path | None = None


class CostEstimate(BaseModel):
    """Estimated API costs for processing a video."""

    scribe_cost: float = 0.0
    translation_cost: float = 0.0
    tts_cost: float = 0.0
    total: float = 0.0
