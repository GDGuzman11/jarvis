"""LLM-driven memory fact extraction (Phase 16C).

Phase 12A distilled facts with a fast keyword-rule pass (see
:class:`~backend.memory.evaluator.MemoryEvaluator`). That pass is precise but
brittle: it misses paraphrases ("I moved to Boston" vs "Boston is where I live
now"), cannot tell a *new* fact from one that *updates* an old one, and never
retracts. Phase 16C augments — does not replace — that pass with an LLM
extractor that reads one conversation turn and returns a structured list of
memory operations, each classified ``ADD`` / ``UPDATE`` / ``DELETE`` / ``NOOP``.

Model strategy (decided by the user)
------------------------------------
* **Primary** — Claude Haiku 4.5 (``claude-haiku-4-5``): cheap and reliable at
  structured JSON. Reached through the existing
  :class:`~backend.ai.claude_client.ClaudeClient` (non-streaming ``complete``).
* **Fallback** — local Ollama ``phi3.5`` via
  :class:`~backend.ai.ollama_client.OllamaClient`, used when the Claude call
  raises (no key / no network / API error) *or* when its output cannot be parsed
  into a JSON array.
* **Graceful floor** — when both LLMs fail or yield nothing parseable, the
  extractor returns ``[]`` and the caller
  (:meth:`~backend.memory.manager.MemoryManager.consolidate`) falls back to the
  Phase 12A rule distillation. Extraction must *never* hard-fail a memory write.

The extractor is invoked off the voice hot path (from the fire-and-forget
``consolidate`` task), so the LLM round-trip never delays Helix's spoken reply.
The keyword rules act as a pre-filter upstream: ``consolidate`` only calls the
extractor for exchanges that already cleared the promotion threshold, so idle
chatter never reaches an LLM.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from backend.ai.claude_client import ClaudeClient
from backend.ai.ollama_client import OllamaClient
from backend.logging_config import get_logger

log = get_logger(__name__)

# Cheap, JSON-reliable extraction model (pinned by the user for Phase 16C).
EXTRACTION_MODEL: str = "claude-haiku-4-5"

# Extraction output is small (a short JSON array), so a tight cap is plenty and
# keeps the (already off-hot-path) call cheap.
EXTRACTION_MAX_TOKENS: int = 700

# Valid actions and provenance values the model may return; anything else is
# coerced/dropped during defensive parsing.
_VALID_ACTIONS: frozenset[str] = frozenset({"ADD", "UPDATE", "DELETE", "NOOP"})
_VALID_SOURCES: frozenset[str] = frozenset({"user", "inference"})

# Open-loop (reminder/follow-up) actions the open-loop extractor may return.
_VALID_OPEN_LOOP_ACTIONS: frozenset[str] = frozenset(
    {"CREATE", "RESOLVE", "NOOP"}
)

# The extraction contract. Kept stable (and cache-friendly) across calls so the
# Haiku prompt-cache prefix stays warm.
EXTRACTION_SYSTEM_PROMPT: str = (
    "You are the memory-extraction engine for Helix, a personal AI assistant.\n"
    "You read ONE conversation turn (the user's message and Helix's reply) and "
    "decide what, if anything, is worth remembering long-term about the user, "
    "their world, their decisions, preferences, standing instructions, the "
    "people they mention, or concrete work that was completed.\n\n"
    "For each durable fact, choose an action relative to what memory may already "
    "hold:\n"
    "  ADD    - a genuinely new fact.\n"
    "  UPDATE - a fact that changes or supersedes something likely already "
    "stored (e.g. the user moved cities, switched tools, changed a preference).\n"
    "  DELETE - a fact the user explicitly retracts or negates (\"I no longer "
    "use X\", \"forget that ...\").\n"
    "  NOOP   - nothing durable here (small talk, transient lookups, pure Q&A).\n\n"
    "Also classify each fact's source:\n"
    "  user      - stated directly by the user.\n"
    "  inference - you inferred it; it was not stated verbatim.\n\n"
    "Return ONLY a JSON array. No prose, no markdown, no code fences. Each "
    "element is an object with exactly these keys:\n"
    '  {"action": "ADD|UPDATE|DELETE|NOOP", "fact": "<concise third-person '
    'declarative statement>", "confidence": <number 0.0-1.0>, "subject": '
    '"<who or what the fact is about>", "source": "user|inference"}\n\n'
    "Rules:\n"
    "- Write each \"fact\" as a compact, self-contained statement, e.g. "
    '"User lives in Boston." Do not quote the raw transcript.\n'
    "- Prefer UPDATE over ADD when the new fact clearly revises an existing one.\n"
    "- If nothing is worth storing, return an empty array: []\n"
    "- Never put secrets, passwords, tokens, or API keys into a fact.\n"
    "- The entire output must be valid JSON parseable by a strict parser."
)

# The open-loop (reminder / follow-up / promise) extraction contract. Separate
# from fact extraction because the judgement is different: it is far stricter
# about what counts as a *genuine* reminder (the old keyword rule fired on bare
# phrases like "need to" and stored sentence fragments such as "anymore" or
# "s, no need to"), and it must also recognise when the user has *finished* or
# wants to *drop* a reminder already on file. Kept stable for prompt-cache reuse.
OPEN_LOOP_SYSTEM_PROMPT: str = (
    "You manage the reminder list for Helix, a personal AI assistant.\n"
    "You read ONE conversation turn (the user's message and Helix's reply) plus "
    "the list of reminders already on file, and decide what should change.\n\n"
    "Choose one action per item:\n"
    "  CREATE  - the user genuinely asks to be reminded, makes a promise, or "
    "commits to a concrete follow-up that should be tracked. Only create when "
    "there is a real, actionable task with a clear, well-formed description.\n"
    "  RESOLVE - the user indicates an existing reminder is done, handled, no "
    "longer needed, or asks to remove/forget/cancel/clear it. Reference the "
    "exact id of the reminder being closed out via \"target_id\".\n"
    "  NOOP    - nothing to track here (small talk, a passing mention, a vague "
    "musing, an incomplete fragment, or a pure question).\n\n"
    "Be conservative. Do NOT create a reminder from a bare phrase, a half-"
    "finished sentence, idle chatter, or a hypothetical. A reminder must read as "
    "a complete, self-contained instruction, e.g. \"Call the dentist on Friday\" "
    "or \"Send Maria the Q3 report\" - never a fragment like \"anymore\" or "
    "\"need to\".\n"
    "When the user is removing/forgetting/cancelling a reminder, ALWAYS choose "
    "RESOLVE for the matching reminder and NEVER also CREATE a new one.\n\n"
    "Return ONLY a JSON array. No prose, no markdown, no code fences. Each "
    "element is an object with exactly these keys:\n"
    '  {"action": "CREATE|RESOLVE|NOOP", "description": "<clean reminder text, '
    'empty for RESOLVE/NOOP>", "target_id": <id of the reminder for RESOLVE, '
    'else null>, "confidence": <number 0.0-1.0>}\n\n'
    "If nothing should change, return an empty array: []"
)


@dataclass(frozen=True)
class Extraction:
    """One memory operation produced by the LLM extractor.

    Attributes
    ----------
    action:
        One of ``ADD`` / ``UPDATE`` / ``DELETE`` / ``NOOP`` (upper-cased).
    fact:
        The compact declarative fact text (empty for ``NOOP``).
    confidence:
        Model confidence in ``[0.0, 1.0]``.
    subject:
        Who/what the fact is about (free text; may be empty).
    source:
        Provenance — ``'user'`` (stated directly) or ``'inference'`` (derived).
        Maps onto ``memory_facts.created_by``.
    """

    action: str
    fact: str
    confidence: float
    subject: str
    source: str


@dataclass(frozen=True)
class OpenLoopOp:
    """One reminder operation produced by the open-loop extractor.

    Attributes
    ----------
    action:
        One of ``CREATE`` / ``RESOLVE`` / ``NOOP`` (upper-cased).
    description:
        The clean reminder text for ``CREATE`` (empty for ``RESOLVE`` / ``NOOP``).
    target_id:
        For ``RESOLVE``, the ``open_loops.id`` the user just completed or asked to
        drop. ``None`` for ``CREATE`` / ``NOOP``.
    confidence:
        Model confidence in ``[0.0, 1.0]``.
    """

    action: str
    description: str
    target_id: int | None
    confidence: float


def _coerce_confidence(value: Any) -> float:
    """Best-effort parse of the model's confidence into a clamped ``[0,1]`` float."""
    try:
        conf = float(value)
    except (TypeError, ValueError):
        return 0.8
    if conf < 0.0:
        return 0.0
    if conf > 1.0:
        return 1.0
    return conf


def _extract_json_array(raw: str) -> list[Any] | None:
    """Pull a JSON array out of a raw model response, defensively.

    Models wrap JSON in prose or ```` ```json ```` fences despite instructions, so
    this never relies on the response being clean. Strategy, in order:

    1. Try to parse the whole (fence-stripped) string as JSON.
    2. Failing that, slice from the first ``[`` to the last ``]`` and parse that.

    Returns the decoded list, or ``None`` when no JSON array can be recovered
    (the caller then falls back to the next extractor / the rule pass). Never
    raises.
    """
    if not raw or not raw.strip():
        return None

    text = raw.strip()
    # Strip a leading/trailing markdown code fence if present.
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text).strip()

    # Attempt 1: the whole thing is the JSON value.
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
    except (json.JSONDecodeError, ValueError):
        pass

    # Attempt 2: carve out the outermost [...] span and parse that.
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        snippet = text[start : end + 1]
        try:
            parsed = json.loads(snippet)
            if isinstance(parsed, list):
                return parsed
        except (json.JSONDecodeError, ValueError):
            return None
    return None


def _normalise(raw_items: list[Any]) -> list[Extraction]:
    """Validate + normalise raw JSON objects into :class:`Extraction` records.

    Drops malformed entries rather than raising: a single bad object never
    discards the whole extraction. ``NOOP`` entries are kept (so the caller can
    see the model deliberately decided nothing), and entries with an empty
    non-NOOP ``fact`` are dropped (an ADD/UPDATE/DELETE with no fact is useless).
    """
    out: list[Extraction] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        action = str(item.get("action", "")).strip().upper()
        if action not in _VALID_ACTIONS:
            continue
        fact = str(item.get("fact", "") or "").strip()
        if action != "NOOP" and not fact:
            continue
        source = str(item.get("source", "inference")).strip().lower()
        if source not in _VALID_SOURCES:
            source = "inference"
        out.append(
            Extraction(
                action=action,
                fact=fact,
                confidence=_coerce_confidence(item.get("confidence", 0.8)),
                subject=str(item.get("subject", "") or "").strip(),
                source=source,
            )
        )
    return out


def _coerce_target_id(value: Any) -> int | None:
    """Best-effort parse of a RESOLVE ``target_id`` into an int, else ``None``."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalise_open_loops(raw_items: list[Any]) -> list[OpenLoopOp]:
    """Validate + normalise raw JSON objects into :class:`OpenLoopOp` records.

    Drops malformed/under-specified entries rather than raising so one bad object
    never discards the whole batch: a ``CREATE`` with no description and a
    ``RESOLVE`` with no resolvable ``target_id`` are both useless and skipped.
    ``NOOP`` entries are dropped too — they carry no action for the caller.
    """
    out: list[OpenLoopOp] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        action = str(item.get("action", "")).strip().upper()
        if action not in _VALID_OPEN_LOOP_ACTIONS:
            continue
        description = str(item.get("description", "") or "").strip()
        target_id = _coerce_target_id(item.get("target_id"))
        if action == "CREATE" and not description:
            continue
        if action == "RESOLVE" and target_id is None:
            continue
        if action == "NOOP":
            continue
        out.append(
            OpenLoopOp(
                action=action,
                description=description,
                target_id=target_id,
                confidence=_coerce_confidence(item.get("confidence", 0.8)),
            )
        )
    return out


class LLMExtractor:
    """Extract structured memory operations from a turn via Haiku → phi3.5.

    Parameters
    ----------
    claude_client / ollama_client:
        Optional injected clients (tests pass fakes). Defaults construct real
        clients lazily — building them is cheap and touches no network/keyring
        until the first call.
    model:
        Extraction model id for the Claude call. Defaults to
        :data:`EXTRACTION_MODEL` (``claude-haiku-4-5``).
    """

    def __init__(
        self,
        claude_client: ClaudeClient | None = None,
        ollama_client: OllamaClient | None = None,
        *,
        model: str = EXTRACTION_MODEL,
    ) -> None:
        self._claude = claude_client or ClaudeClient()
        self._ollama = ollama_client or OllamaClient()
        self._model = model

    @staticmethod
    def _build_messages(user_text: str, reply: str) -> list[dict[str, Any]]:
        """Render the turn into the single user message the extractor sends."""
        return [
            {
                "role": "user",
                "content": (
                    f"User: {user_text or ''}\n"
                    f"Helix: {reply or ''}\n\n"
                    "Extract memory operations as a JSON array."
                ),
            }
        ]

    async def extract(self, user_text: str, reply: str) -> list[Extraction]:
        """Return the memory operations for one turn (Haiku → phi3.5 → ``[]``).

        Tries Claude Haiku first; on an API/credential error *or* an unparseable
        response, falls back to local phi3.5; if that too fails or yields no
        parseable JSON, returns ``[]`` so the caller degrades to the rule pass.
        Never raises — a memory write must not be broken by extraction.
        """
        messages = self._build_messages(user_text, reply)

        # --- Primary: Claude Haiku ---------------------------------------
        raw: str | None = None
        try:
            raw = await self._claude.complete(
                messages,
                EXTRACTION_SYSTEM_PROMPT,
                model=self._model,
                max_tokens=EXTRACTION_MAX_TOKENS,
            )
        except Exception as exc:  # noqa: BLE001 — any failure → fall back
            log.warning("memory_extract_claude_failed", error=str(exc))
            raw = None

        items = _extract_json_array(raw) if raw is not None else None

        # --- Fallback: local phi3.5 --------------------------------------
        # Triggered when Claude raised (raw is None) or its output did not parse
        # into a JSON array (items is None).
        if items is None:
            try:
                raw = await self._ollama.complete(
                    messages, EXTRACTION_SYSTEM_PROMPT, fmt="json"
                )
            except Exception as exc:  # noqa: BLE001 — fallback must not raise
                log.warning("memory_extract_ollama_failed", error=str(exc))
                raw = None
            items = _extract_json_array(raw) if raw else None

        if items is None:
            log.info("memory_extract_unparseable")
            return []

        extractions = _normalise(items)
        log.info("memory_extract_done", count=len(extractions))
        return extractions

    # --- Open-loop (reminder/follow-up) judgement ---------------------------

    @staticmethod
    def _build_open_loop_messages(
        user_text: str, reply: str, open_loops: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Render the turn + the current reminder list into one user message."""
        if open_loops:
            loop_lines = "\n".join(
                f"{loop.get('id')}: {loop.get('description', '')}"
                for loop in open_loops
            )
            loop_block = (
                "Reminders already on file (id: description):\n" + loop_lines
            )
        else:
            loop_block = "There are no reminders on file."
        return [
            {
                "role": "user",
                "content": (
                    f"User: {user_text or ''}\n"
                    f"Helix: {reply or ''}\n\n"
                    f"{loop_block}\n\n"
                    "Return reminder operations as a JSON array."
                ),
            }
        ]

    async def extract_open_loops(
        self,
        user_text: str,
        reply: str,
        open_loops: list[dict[str, Any]],
    ) -> list[OpenLoopOp]:
        """Judge reminder CREATE/RESOLVE for one turn (Haiku → phi3.5 → ``[]``).

        Mirrors :meth:`extract`'s resilience: Claude Haiku first; on an API error
        *or* unparseable output, fall back to local phi3.5; if both fail, return
        ``[]`` so the caller simply makes no reminder change. The LLM is far better
        than the old keyword rule at telling a genuine reminder from a fragment,
        and — given the current ``open_loops`` with their ids — can resolve the
        right reminder when the user says it is done or asks to forget it. Never
        raises; off the voice hot path (called from the fire-and-forget
        consolidate task).
        """
        messages = self._build_open_loop_messages(user_text, reply, open_loops)

        raw: str | None = None
        try:
            raw = await self._claude.complete(
                messages,
                OPEN_LOOP_SYSTEM_PROMPT,
                model=self._model,
                max_tokens=EXTRACTION_MAX_TOKENS,
            )
        except Exception as exc:  # noqa: BLE001 — any failure → fall back
            log.warning("open_loop_extract_claude_failed", error=str(exc))
            raw = None

        items = _extract_json_array(raw) if raw is not None else None

        if items is None:
            try:
                raw = await self._ollama.complete(
                    messages, OPEN_LOOP_SYSTEM_PROMPT, fmt="json"
                )
            except Exception as exc:  # noqa: BLE001 — fallback must not raise
                log.warning("open_loop_extract_ollama_failed", error=str(exc))
                raw = None
            items = _extract_json_array(raw) if raw else None

        if items is None:
            log.info("open_loop_extract_unparseable")
            return []

        ops = _normalise_open_loops(items)
        log.info("open_loop_extract_done", count=len(ops))
        return ops


__all__ = [
    "LLMExtractor",
    "Extraction",
    "OpenLoopOp",
    "EXTRACTION_MODEL",
    "EXTRACTION_SYSTEM_PROMPT",
    "OPEN_LOOP_SYSTEM_PROMPT",
    "EXTRACTION_MAX_TOKENS",
]
