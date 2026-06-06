"""Memory importance evaluator (Phase 12A).

The :class:`MemoryEvaluator` decides whether a single user<->Jarvis exchange is
worth promoting to long-term semantic memory, and — if so — distils it into a
compact declarative fact. It runs after every turn, so it is deliberately cheap:
a fast, rule-based keyword pass, *not* an ML model or an API call.

Design
------
The core test (from the Phase 12 plan): *did something change in the world
because of this exchange?* If yes, it scores high. Pure Q&A with no real-world
outcome scores low. :meth:`score` returns ``(score, category)`` where ``score``
is in ``[0.0, 1.0]`` and ``category`` names the matched signal. A score ``>=``
the promotion threshold (0.65) means the exchange should be stored to
``memory_facts`` and the FAISS vector store.

Scoring table (highest signal wins)
-----------------------------------
====================  =====  ====================================================
category              score  signal
====================  =====  ====================================================
agent_outcome         1.00   a completed/failed agent task result
app_work              0.90   "deployed/shipped/built/fixed/..." + an artifact
decision              0.85   "we decided/going with/chose/switched from X to Y"
failure               0.85   "tried X but/abandoned/reverted/didn't work because"
external_comm         0.85   email/Slack from a known or new contact
correction            0.85   "no that's wrong/actually/not quite"
instruction           0.80   "always/never/make sure/I want you to"
preference            0.75   "my name/I prefer/I work on/I use/I like/I hate"
open_loop             0.75   "remind me/follow up/don't forget/I need to"
repeated_topic        0.70   same topic mentioned 3+ times recently
general               0.20   status checks, lookups, greetings — diary only
====================  =====  ====================================================

This is Phase 12A infrastructure: the evaluator is complete enough to score and
extract, but it is not yet wired into the voice pipeline (that is Phase 12B) and
the richer people/open-loop intelligence lands in Phase 12D.
"""

from __future__ import annotations

import re
from datetime import date

# Promotion threshold: exchanges scoring at or above this go to semantic memory.
PROMOTION_THRESHOLD: float = 0.65

# Ordered most-significant first so the first matching category wins. Each entry
# is ``(category, score, keywords)``. Keywords are matched case-insensitively as
# word-boundary substrings against the combined user+reply text (except where a
# category has bespoke logic below, e.g. app_work which also needs an artifact).
_RULES: tuple[tuple[str, float, tuple[str, ...]], ...] = (
    (
        "decision",
        0.85,
        (
            "we decided", "i decided", "going with", "we chose", "i chose",
            "switched from", "switch from", "decided to use", "decided on",
            "let's go with", "we'll use", "we will use",
        ),
    ),
    (
        "failure",
        0.85,
        (
            "tried", "abandoned", "reverted", "didn't work", "did not work",
            "rolled back", "roll back", "gave up on", "ran into", "conflicted",
            "broke", "failed because", "doesn't work", "does not work",
        ),
    ),
    (
        "correction",
        0.85,
        (
            "no that's wrong", "no thats wrong", "that's wrong", "thats wrong",
            "that's not right", "thats not right", "not quite", "actually",
            "no, ", "that's incorrect", "you're wrong", "youre wrong",
            "that's not correct", "not what i meant",
        ),
    ),
    (
        "instruction",
        0.80,
        (
            "always", "never", "make sure", "i want you to", "from now on",
            "going forward", "be sure to", "remember to always",
            "i need you to", "please always", "don't ever", "do not ever",
        ),
    ),
    (
        "preference",
        0.75,
        (
            "my name is", "i'm called", "im called", "call me", "i prefer",
            "i work on", "i work at", "i use", "i like", "i hate", "i live in",
            "i love", "i enjoy", "my favorite", "my favourite", "i'm a ",
            "im a ", "i am a ",
        ),
    ),
    (
        "open_loop",
        0.75,
        (
            "remind me", "follow up", "follow-up", "don't forget", "dont forget",
            "i need to", "remember that", "remember to", "keep in mind",
            "make a note", "note that", "i have to", "later i", "tomorrow i",
        ),
    ),
)

# app_work needs BOTH an action verb AND a concrete artifact signal, so it is
# handled with bespoke logic rather than a flat keyword list.
_APP_WORK_VERBS: tuple[str, ...] = (
    "deployed", "shipped", "built", "fixed", "refactored", "completed",
    "implemented", "merged", "released", "added", "wired", "migrated",
    "created", "finished",
)
# Artifact signals: a file path, a version, a feature/endpoint name, code.
_ARTIFACT_PATTERNS: tuple[str, ...] = (
    r"\b[\w./-]+\.(?:py|ts|tsx|js|jsx|rs|json|md|sql|toml|css|html)\b",  # file
    r"\bv?\d+\.\d+(?:\.\d+)?\b",                                          # version
    r"/[\w./-]+",                                                         # path
    r"`[^`]+`",                                                           # code span
    r"\bhttps?://\S+\b",                                                  # URL
    r"\b(?:endpoint|api|table|schema|function|class|component|module)\b",  # artifact noun
)


class MemoryEvaluator:
    """Score exchanges for semantic importance and extract compact facts.

    Stateless and synchronous by design — :meth:`score` and
    :meth:`extract_fact` are pure functions of their inputs, so the evaluator is
    trivially testable and safe to call on the hot path after every turn.
    """

    def __init__(self, threshold: float = PROMOTION_THRESHOLD) -> None:
        self.threshold = threshold

    # --- Scoring ------------------------------------------------------------

    def score(self, user_text: str, reply: str) -> tuple[float, str]:
        """Return ``(score, category)`` for a user/Jarvis exchange.

        Runs the fast rule-based pass over the combined text. The first matching
        category (in significance order) wins. When nothing matches, the
        exchange is ``general`` with a low diary-only score.
        """
        user_l = (user_text or "").lower()
        combined = f"{user_text or ''}\n{reply or ''}"
        combined_l = combined.lower()

        # app_work first: highest score among score-based rules, but requires
        # both a verb and a concrete artifact so we don't promote idle chatter.
        if self._is_app_work(combined_l, combined):
            return 0.90, "app_work"

        for category, value, keywords in _RULES:
            # Preference/open-loop/instruction signals are first-person user
            # statements; the others may appear in either side of the exchange.
            haystack = user_l if category in {"preference", "open_loop"} else combined_l
            for kw in keywords:
                if kw in haystack:
                    return value, category

        return 0.20, "general"

    def _is_app_work(self, combined_lower: str, combined_raw: str) -> bool:
        """True when the exchange reports concrete dev work (verb + artifact)."""
        if not any(verb in combined_lower for verb in _APP_WORK_VERBS):
            return False
        return any(
            re.search(pattern, combined_raw, flags=re.IGNORECASE)
            for pattern in _ARTIFACT_PATTERNS
        )

    def should_store(self, user_text: str, reply: str) -> bool:
        """Convenience: ``True`` when the exchange scores at/above threshold."""
        value, _ = self.score(user_text, reply)
        return value >= self.threshold

    # --- Fact extraction ----------------------------------------------------

    def extract_fact(self, user_text: str, reply: str, category: str) -> str:
        """Distil an exchange into a compact declarative fact string.

        Returns a short, self-contained statement suitable for the vector store
        and ``memory_facts.content`` — never a raw transcript dump. The phrasing
        is tailored per category so recalled memories read naturally in the
        system prompt (e.g. "User prefers ... (noted 2026-06-05)."). Always
        timestamped so recall can reason about recency.
        """
        stamp = date.today().isoformat()
        user = self._compress(user_text)
        reply_c = self._compress(reply)

        if category == "preference":
            return f"{self._as_user_statement(user)} (noted {stamp})."
        if category == "instruction":
            return f"Standing instruction: {self._as_user_statement(user)} (noted {stamp})."
        if category == "correction":
            return (
                f"User corrected Jarvis: {user} "
                f"(corrected {stamp})."
            )
        if category == "decision":
            detail = user or reply_c
            return f"Decision: {detail} (decided {stamp})."
        if category == "failure":
            detail = user or reply_c
            return f"Failure/dead-end: {detail} (recorded {stamp})."
        if category == "open_loop":
            return f"Open loop: {user} (created {stamp})."
        if category == "external_comm":
            return f"Communication: {user or reply_c} (on {stamp})."
        if category in {"app_work", "agent_outcome"}:
            detail = reply_c or user
            return f"Work done: {detail} (on {stamp})."
        if category == "repeated_topic":
            return f"Recurring topic: {user} (noted {stamp})."

        # general / fallback — keep it short and timestamped.
        detail = user or reply_c
        return f"{detail} (noted {stamp})."

    # --- Helpers ------------------------------------------------------------

    @staticmethod
    def _compress(text: str, max_len: int = 240) -> str:
        """Collapse whitespace and trim to a single compact clause."""
        if not text:
            return ""
        collapsed = re.sub(r"\s+", " ", text).strip()
        if len(collapsed) <= max_len:
            return collapsed
        # Cut on a word boundary near the cap so we don't slice mid-word.
        cut = collapsed[:max_len].rsplit(" ", 1)[0]
        return f"{cut}…"

    @staticmethod
    def _as_user_statement(text: str) -> str:
        """Render a first-person user clause as a third-person fact.

        Light touch — maps leading "I"/"my" so the stored fact reads as a
        statement *about* the user rather than a quote *from* them.
        """
        if not text:
            return "User stated a preference"
        t = text.strip()
        lowered = t.lower()
        replacements = (
            ("my name is ", "User's name is "),
            ("i prefer ", "User prefers "),
            ("i work on ", "User works on "),
            ("i work at ", "User works at "),
            ("i live in ", "User lives in "),
            ("i use ", "User uses "),
            ("i like ", "User likes "),
            ("i love ", "User likes "),
            ("i hate ", "User dislikes "),
            ("i want you to ", "User wants Jarvis to "),
            ("i need you to ", "User wants Jarvis to "),
            ("call me ", "User is called "),
        )
        for prefix, repl in replacements:
            if lowered.startswith(prefix):
                return repl + t[len(prefix):]
        # No recognised first-person opener: return as-is (already compressed).
        return t


__all__ = ["MemoryEvaluator", "PROMOTION_THRESHOLD"]
