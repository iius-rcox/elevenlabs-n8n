"""Post-translation LLM review: catches terminology, grammar, and flow issues.

Runs between translation and TTS synthesis. Sends original English + Spanish
translation to o3 for review. Returns corrected translations for any flagged
segments. Unflagged segments pass through unchanged.
"""

from __future__ import annotations

import json
import logging

from openai import OpenAI

from .config import TRANSLATION_MODEL
from .models import TranslatedSegment, TranslationResult

logger = logging.getLogger("video_translator")

REVIEW_BATCH_SIZE = 25

REVIEW_PROMPT = """\
You are a Spanish-language quality reviewer for dubbed construction industry \
training videos. You will receive pairs of English original text and their \
Spanish translations. Your job is to catch errors before the text is sent \
to a TTS engine for audio synthesis.

Review each translation for these specific issues:

1. TERMINOLOGY — Flag if any of these terms are translated incorrectly:
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

2. GRAMMAR — Flag broken sentences, incomplete clauses, subject-verb \
disagreement, missing prepositions, or phrases that would sound unnatural \
when spoken aloud. Remember: this text will be read by a TTS voice, so it \
must flow naturally as spoken Spanish.

3. GARBLED MERGES — Flag when ideas from the English have been crammed \
together into a confusing run-on sentence. If multiple English ideas were \
merged, the Spanish should either: (a) merge them into one clean, \
restructured sentence, or (b) keep them separate. Never jam unfinished \
clauses together.

4. LOST MEANING — Flag if the Spanish drops important content from the \
English original. Brief condensation is acceptable; losing key points is not.

5. PRONUNCIATION TRAPS — Flag text that a TTS engine would likely \
mispronounce. Common issues:
   - "I&I" should be written as "I and I" (ampersand confuses TTS)
   - Abbreviations that should be spelled out for speech
   - Mixed-language words that need careful handling

For each segment, respond with:
- "ok": true if the translation is acceptable, false if it needs correction
- "corrected_text": the fixed Spanish text (only if ok=false)
- "issue": brief description of what was wrong (only if ok=false)

Return valid JSON matching the schema exactly. Do NOT change segments that \
are already correct — only fix actual problems.
"""


def review_translations(
    translation: TranslationResult,
    openai_client: OpenAI,
) -> tuple[TranslationResult, list[dict]]:
    """Review translated segments and return corrected version + issues log.

    Returns:
        (corrected_translation, issues) where issues is a list of
        {index, original, translated, corrected, issue} dicts for flagged segments.
    """
    all_issues: list[dict] = []
    corrected_segments = list(translation.segments)

    for batch_start in range(0, len(corrected_segments), REVIEW_BATCH_SIZE):
        batch = corrected_segments[batch_start:batch_start + REVIEW_BATCH_SIZE]
        batch_reviews = _review_batch(batch, batch_start, openai_client)

        for review in batch_reviews:
            if not review.get("ok", True):
                idx = review["index"]
                seg = corrected_segments[idx]
                old_text = seg.translated_text
                new_text = review.get("corrected_text", old_text)
                issue = review.get("issue", "unspecified")

                all_issues.append({
                    "index": idx,
                    "original": seg.original_text,
                    "translated": old_text,
                    "corrected": new_text,
                    "issue": issue,
                })

                # Apply correction
                corrected_segments[idx] = TranslatedSegment(
                    original_text=seg.original_text,
                    translated_text=new_text,
                    start=seg.start,
                    end=seg.end,
                    estimated_syllables=seg.estimated_syllables,
                )

    corrected = TranslationResult(segments=corrected_segments)
    return corrected, all_issues


def _review_batch(
    segments: list[TranslatedSegment],
    start_index: int,
    client: OpenAI,
) -> list[dict]:
    """Send a batch of segments for review."""
    items = []
    for i, seg in enumerate(segments):
        items.append({
            "index": start_index + i,
            "english": seg.original_text,
            "spanish": seg.translated_text,
        })

    user_message = json.dumps(items, ensure_ascii=False)

    schema = {
        "type": "object",
        "properties": {
            "reviews": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "index": {"type": "integer"},
                        "ok": {"type": "boolean"},
                        "corrected_text": {"type": "string"},
                        "issue": {"type": "string"},
                    },
                    "required": ["index", "ok", "corrected_text", "issue"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["reviews"],
        "additionalProperties": False,
    }

    response = client.responses.create(
        model=TRANSLATION_MODEL,
        input=[
            {"role": "system", "content": REVIEW_PROMPT},
            {"role": "user", "content": user_message},
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "translation_review",
                "strict": True,
                "schema": schema,
            }
        },
    )

    parsed = json.loads(response.output_text)
    return parsed["reviews"]
