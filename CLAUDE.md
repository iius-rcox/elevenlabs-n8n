# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Python tool that processes a directory of videos: extracts audio, transcribes it, translates to conversational Spanish, and generates new audio using ElevenLabs TTS. Outputs one-to-one Spanish versions of each input video.

## Pipeline

1. **Extract audio** from input videos (FFmpeg)
2. **Transcribe** audio to English text (ElevenLabs Scribe)
3. **Translate** English text to conversational Spanish (GPT-4o)
4. **Generate Spanish audio** via ElevenLabs Text-to-Speech API
5. **Assemble** timed audio track with silence gaps, speed adjustment, truncation
6. **Recombine** generated audio with original video (FFmpeg)

## Stack

- **Python 3.11+** — primary language
- **ElevenLabs API** — speech-to-text (Scribe) and text-to-speech
- **OpenAI API** — GPT-4o for English-to-Spanish translation
- **FFmpeg** — audio extraction, speed adjustment, and video/audio muxing
- **Click** — CLI framework
- **Pydantic** — data models and validation
- **Rich** — terminal progress bars and formatting

## Setup

```bash
# 1. Install FFmpeg
winget install Gyan.FFmpeg

# 2. Create .env with your API keys (copy from .env.example)
cp .env.example .env
# Edit .env with real keys

# 3. Install the package
pip install -e .
```

## Usage

```bash
# Single video
video-translate video.mp4

# Directory of videos
video-translate ./videos/

# With options
video-translate video.mp4 --output-dir ./output --verbose --keep-intermediates --yes
```

## Modules

| Module | Description |
|---|---|
| `cli.py` | Click CLI entry point, pipeline orchestration, manifest tracking |
| `config.py` | API key loading, client creation, FFmpeg checks, path validation |
| `models.py` | Pydantic data models for transcript, translation, synthesis, pipeline |
| `audio_extract.py` | FFmpeg: extract audio, get duration, check streams, mux video |
| `transcribe.py` | ElevenLabs Scribe: audio -> word-level transcript -> sentence segments |
| `translate.py` | GPT-4o: English segments -> Spanish with syllable budget constraints |
| `synthesize.py` | ElevenLabs TTS: Spanish text -> MP3 audio files per segment |
| `assemble.py` | FFmpeg: timing alignment, speed adjustment, truncation, final mix |

## Key Constants

- Default voice ID: `sDh3eviBhiuHKi0MjTNq`
- TTS model: `eleven_multilingual_v2`
- STT model: `scribe_v1`
- Translation model: `gpt-4o`
- Spanish syllable rate: 4.3 syl/sec (used for syllable budgets)
