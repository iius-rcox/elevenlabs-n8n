"""GPT-4o translation: English transcript segments -> conversational Spanish."""

from __future__ import annotations

import json

from openai import OpenAI

from .config import TRANSLATION_MODEL
from .models import (
    CostEstimate,
    TranscriptResult,
    TranscriptSegment,
    TranslatedSegment,
    TranslationEntry,
    TranslationResponse,
    TranslationResult,
)

# Approximate speaking rate for Spanish (syllables per second)
SPANISH_SYL_PER_SEC = 4.3

BATCH_SIZE = 25

SYSTEM_PROMPT = """\
You are a professional translator specializing in English-to-Spanish dubbing \
for construction industry supervisor training videos. The audience is field \
supervisors (foremen, superintendents, general foremen) at I&I Soft Craft Solutions, \
a company providing insulation, coatings, scaffolding, refractory, fireproofing, \
and heat tracing services.

Context & Tone:
- Use professional Latin American Spanish with the formal "usted" register, \
appropriate for corporate training materials.
- Tone should be warm, respectful, and encouraging — like an experienced mentor \
speaking to a valued team member. Avoid both cold corporate language and overly \
casual speech.
- Use first-person plural ("nosotros", "nuestro") to create a sense of shared \
ownership and belonging.

Translation Quality:
- Preserve full meaning. Condense phrasing where possible, but NEVER drop content \
or important context for the sake of brevity.
- For each segment you receive an index, the English text, and a max syllable budget. \
Stay within the syllable count, but prioritize clarity and completeness — if you \
must cut, cut filler words, not substantive content.
- When the English is abstract or corporate, ground it with brief concrete examples \
relevant to a field supervisor's daily work (managing a shift, guiding a crew, \
resolving a safety issue).
- This is persuasive training content. When the English states what to do, ensure \
the Spanish also conveys why it matters to the listener personally.
- Be aware of where each segment falls in the overall narrative. Opening segments \
should feel welcoming, middle segments informational, and closing segments \
inspirational and motivating.

Sentence Flow & Merging:
- These segments will be spoken aloud by a TTS voice. The result must sound like \
natural, fluent spoken Spanish — not a sequence of disconnected phrases.
- When consecutive segments form a single thought (e.g., a short statement followed \
by its reason or elaboration), merge them into one flowing sentence. \
Example: "We chose you as a supervisor." + "Because you have leadership qualities." \
→ "Te hemos elegido como supervisor porque tienes cualidades de liderazgo."
- When multiple segments restate the same idea from different angles, eliminate the \
redundant restatements and combine the unique points into one clear sentence. \
Do NOT cram all the original words together — instead, identify the core message \
and express it once, well.
- NEVER jam unfinished clauses together. If merging creates a grammatically awkward \
sentence, restructure it completely rather than concatenating fragments.
- Each translated segment must be a complete, grammatically correct sentence or \
phrase that can stand on its own when spoken aloud.

Language & Style:
- Use appropriate construction trade terminology in Spanish (capataz, superintendente, \
andamiaje, trazado térmico, ignifugación, etc.).
- Replace English idioms and colloquialisms with natural Spanish equivalents. \
Never translate idioms literally.
- When translating bulleted lists or enumerations, use parallel grammatical structure \
(all nouns, all infinitives, or all imperative — pick one and be consistent).
- Use short, punchy declarative sentences for emphasis on key messages and core values. \
Vary sentence length to create rhetorical impact.
- Always use correct Spanish punctuation: inverted question/exclamation marks (¿ ¡), \
all accent marks (á, é, í, ó, ú, ñ), and proper em-dashes.

Terminology Glossary (use these exact terms):
- insulation → aislamiento
- coatings → recubrimientos (NOT revestimientos)
- scaffolding → andamiaje
- refractory → refractario
- fireproofing → ignifugación
- heat tracing → trazado térmico
- foreman → capataz
- superintendent → superintendente
- general foreman → capataz general
- safety → seguridad
- quality → calidad

Preservation:
- Never translate the company name "I&I Soft Craft Solutions" or abbreviation "INI". \
Keep all branded service names in their original form.
- When writing "I&I", always write it as "I and I" so TTS can pronounce it correctly. \
For example: "I and I Soft Craft Solutions".
- Preserve the tone, intent, and emphasis of the original.
- Do NOT add filler words just to match length.
- Return valid JSON matching the schema exactly.
"""


def translate_segments(
    transcript: TranscriptResult,
    openai_client: OpenAI,
) -> TranslationResult:
    """Translate all transcript segments to Spanish using GPT-4o.

    Sends segments in batches of 25 with syllable budget constraints.
    """
    all_translated: list[TranslatedSegment] = []

    for batch_start in range(0, len(transcript.segments), BATCH_SIZE):
        batch = transcript.segments[batch_start : batch_start + BATCH_SIZE]
        entries = _translate_batch(batch, batch_start, openai_client)

        for entry, orig_seg in zip(entries, batch):
            all_translated.append(TranslatedSegment(
                original_text=orig_seg.text,
                translated_text=entry.translated_text,
                start=orig_seg.start,
                end=orig_seg.end,
                estimated_syllables=entry.estimated_syllables,
            ))

    return TranslationResult(segments=all_translated)


def _translate_batch(
    segments: list[TranscriptSegment],
    start_index: int,
    client: OpenAI,
) -> list[TranslationEntry]:
    """Send a batch of segments to GPT-4o for translation."""
    # Build the user message with syllable budgets
    items = []
    for i, seg in enumerate(segments):
        duration = seg.end - seg.start
        max_syllables = max(5, int(duration * SPANISH_SYL_PER_SEC))
        items.append({
            "index": start_index + i,
            "text": seg.text,
            "max_syllables": max_syllables,
        })

    user_message = json.dumps(items, ensure_ascii=False)

    schema = _strict_schema(TranslationResponse.model_json_schema())

    response = client.responses.create(
        model=TRANSLATION_MODEL,
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "translation_response",
                "strict": True,
                "schema": schema,
            }
        },
    )

    # Parse the structured output
    raw = response.output_text
    parsed = TranslationResponse.model_validate_json(raw)

    # Sort by index to ensure correct order
    entries = sorted(parsed.translations, key=lambda e: e.index)

    if len(entries) != len(segments):
        raise ValueError(
            f"Expected {len(segments)} translations, got {len(entries)}"
        )

    return entries


def _strict_schema(schema: dict) -> dict:
    """Add additionalProperties: false to all objects for OpenAI strict mode."""
    if isinstance(schema, dict):
        if schema.get("type") == "object":
            schema["additionalProperties"] = False
        for v in schema.values():
            if isinstance(v, dict):
                _strict_schema(v)
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, dict):
                        _strict_schema(item)
        # Handle $defs
        if "$defs" in schema:
            for defn in schema["$defs"].values():
                _strict_schema(defn)
    return schema


def estimate_cost(
    transcript: TranscriptResult,
    audio_duration: float,
) -> CostEstimate:
    """Estimate API costs for processing a video.

    Rough estimates:
    - Scribe: ~$0.40 per hour of audio
    - GPT-4o translation: ~$2.50 / 1M input tokens, ~$10 / 1M output tokens
    - ElevenLabs TTS: ~$0.30 per 1000 characters (Scale plan)
    """
    # Scribe cost
    scribe_cost = (audio_duration / 3600) * 0.40

    # Translation cost (rough token estimate: ~1.3 tokens per word)
    total_words = sum(len(s.text.split()) for s in transcript.segments)
    input_tokens = total_words * 1.3 + 500  # +500 for system prompt
    output_tokens = total_words * 1.5  # Spanish tends to be slightly longer
    translation_cost = (input_tokens / 1_000_000 * 2.50) + (output_tokens / 1_000_000 * 10.0)

    # TTS cost (characters of translated text)
    total_chars = sum(len(s.text) for s in transcript.segments) * 1.1  # estimate Spanish length
    tts_cost = (total_chars / 1000) * 0.30

    total = scribe_cost + translation_cost + tts_cost

    return CostEstimate(
        scribe_cost=round(scribe_cost, 4),
        translation_cost=round(translation_cost, 4),
        tts_cost=round(tts_cost, 4),
        total=round(total, 4),
    )
