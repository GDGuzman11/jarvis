"""Memory importance evaluator (Phase 12A).

The :class:`MemoryEvaluator` decides whether a single user<->Helix exchange is
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

Phase 12D adds the intelligence layer on top of the 12A scoring core:
:meth:`detect_open_loops` scans an utterance for promise/reminder/follow-up
patterns and returns concise loop descriptions; :meth:`extract_person` pulls a
named contact + email/"from X" hint out of Gmail/Slack-flavoured text; and the
``failure`` category now extracts a structured "approach / reason" fact so a
dead-end is never silently re-attempted.
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
            "tried", "attempted", "abandoned", "reverted", "didn't work",
            "did not work", "rolled back", "roll back", "gave up on", "ran into",
            "conflicted", "conflicted with", "broke", "failed because",
            "doesn't work", "does not work", "caused issues", "was too slow",
            "too slow",
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

# --- Open-loop / people patterns (Phase 12D) --------------------------------

# Trigger phrases that introduce a promise/reminder/follow-up. Ordered longest-
# first within overlapping families so the more specific phrase is consumed (and
# stripped) before a shorter prefix of it. Matched case-insensitively against
# each sentence; the text after the trigger becomes the loop description.
_OPEN_LOOP_TRIGGERS: tuple[str, ...] = (
    "remind me to",
    "remind me",
    "don't forget to",
    "dont forget to",
    "don't forget",
    "dont forget",
    "follow up on",
    "follow-up on",
    "follow up with",
    "follow up",
    "remember to",
    "make sure to",
    "make sure",
    "check on",
    "schedule",
    "we need to",
    "i need to",
)

# Resolution hints — phrases that suggest an *existing* reminder is finished or
# should be dropped. These are only a cheap pre-filter to decide whether the
# (off-hot-path) open-loop LLM is worth calling when reminders exist; the LLM
# makes the actual create/resolve judgement. Kept broad so genuine resolutions
# are not missed — false positives merely cost one LLM call that returns NOOP.
_OPEN_LOOP_RESOLVE_HINTS: tuple[str, ...] = (
    "done", "did it", "did that", "i did", "already did", "finished",
    "completed", "complete", "handled", "took care of", "taken care of",
    "sorted", "resolved", "forget", "remove", "cancel", "clear", "delete",
    "no longer", "scratch that", "never mind", "nevermind", "no need",
)


# --- Capture gate (Memory Capture Overhaul) ---------------------------------
# The light chatter-skip that replaces the old hard ``score < 0.65`` gate. A turn
# is "chatter" only when it is very short AND every word is a pure greeting /
# pleasantry / acknowledgement / filler — i.e. there is no substance an LLM could
# possibly distil. Anything else (a question, a one-word noun, a statement) is
# NOT chatter and flows on to the LLM extractor, which NOOPs genuine fluff. This
# is deliberately conservative: the cost of a false negative (chatter slipping
# through) is one Haiku call that returns ``[]``; a false positive (real content
# wrongly skipped) silently loses a memory, so the bar to call something chatter
# is high.
_CHATTER_TOKENS: frozenset[str] = frozenset(
    {
        # greetings
        "hi", "hii", "hey", "hello", "helloo", "yo", "hiya", "sup", "heya",
        "morning", "afternoon", "evening", "night", "greetings",
        # sign-offs
        "bye", "goodbye", "cya", "later", "ttyl",
        # acknowledgements / pleasantries
        "thanks", "thank", "thx", "ty", "cheers", "ok", "okay", "k", "kk",
        "cool", "nice", "great", "awesome", "perfect", "good", "fine", "sweet",
        "yes", "yep", "yeah", "yup", "no", "nope", "nah", "sure", "alright",
        "right", "gotcha", "ok!", "welcome", "please", "done", "mhm", "hmm",
        "lol", "haha", "hah", "np", "indeed", "splendid", "lovely",
        # light fillers that commonly pad an acknowledgement
        "you", "u", "it", "that", "this", "the", "a", "an", "and", "is", "im",
        "i", "to", "so", "very", "much", "for", "all", "mate", "sir", "helix",
        "there", "now", "then", "well",
    }
)
# Above this word count a turn is never treated as chatter (it is long enough to
# plausibly carry substance worth an LLM look).
_CHATTER_MAX_WORDS: int = 5

# Tokeniser for the chatter test: words = letters/digits/apostrophes only, so
# trailing punctuation never blocks a match ("thanks!" -> "thanks").
_WORD_RE = re.compile(r"[a-z0-9']+")

# Phrases that make a turn an explicit "remember this" request. When present the
# turn always passes the gate AND its facts auto-store (skipping the confirm
# band) — the user asked for it by name, so we never second-guess with a prompt.
_EXPLICIT_MEMORY_PATTERNS: tuple[str, ...] = (
    "remember this", "remember that", "remember my", "remember i ",
    "remember to remember", "please remember", "remember,", "remember:",
    "note that", "make a note", "take a note", "jot this down", "jot that down",
    "save this", "keep in mind", "bear in mind", "don't forget", "dont forget",
    "do not forget", "for the record", "remember",
)


# A pragmatic email matcher — good enough for Gmail/Slack context strings.
_EMAIL_RE: str = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"

# "from <Name>" — captures one to three capitalised name tokens after "from".
# Stops before a lowercase word, an email, or punctuation, so "from Sarah at
# sarah@..." captures just "Sarah".
_FROM_NAME_RE: str = (
    r"\bfrom\s+([A-Z][a-zA-Z'’-]+(?:\s+[A-Z][a-zA-Z'’-]+){0,2})"
)

# Sentence splitter: break on ., !, ?, ; or newlines so each trigger scan and
# each "from <Name>" capture stays within one clause.
_SENTENCE_SPLIT_RE = re.compile(r"[.!?;\n]+")


def _split_sentences(text: str) -> list[str]:
    """Split text into trimmed sentence-ish fragments (non-empty only)."""
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]


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
        """Return ``(score, category)`` for a user/Helix exchange.

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

    # --- Capture gate (Memory Capture Overhaul) -----------------------------

    def is_chatter(self, user_text: str, reply: str = "") -> bool:
        """``True`` when a turn is pure greeting/pleasantry/ack with no substance.

        This is the *light* capture gate that replaces the old hard
        ``score < threshold`` skip. It returns ``True`` only for clearly-trivial
        turns — empty/punctuation-only, or a short message whose every word is a
        known greeting / acknowledgement / filler token. Everything else (a
        question, a one-word noun, any statement carrying a content word) is NOT
        chatter and reaches the LLM extractor, which is far better at judging
        whether a real fact is present. The ``reply`` is accepted for signature
        symmetry/future use but the decision rests on the user's words, where
        substance lives.
        """
        text = (user_text or "").strip()
        if not text:
            return True
        words = _WORD_RE.findall(text.lower())
        if not words:
            # Pure punctuation / emoji — nothing to remember.
            return True
        if len(words) > _CHATTER_MAX_WORDS:
            return False
        # Chatter only when EVERY word is a known greeting/pleasantry/filler; a
        # single content word (a name, a place, "birthday", "broken") tips it
        # into "send to the LLM".
        return all(word in _CHATTER_TOKENS for word in words)

    def is_explicit_memory_request(self, user_text: str) -> bool:
        """``True`` when the user explicitly asked Helix to remember something.

        Detects "remember (this/that)", "note that", "don't forget", "make a
        note", "save this", "keep in mind" and similar. An explicit request
        always passes the capture gate and forces its facts to auto-store
        (bypassing the confirm-when-unsure band) — the user named the intent, so
        Helix should not answer it with a confirmation prompt.
        """
        if not user_text or not user_text.strip():
            return False
        lowered = user_text.lower()
        return any(pat in lowered for pat in _EXPLICIT_MEMORY_PATTERNS)

    # --- Open-loop detection (Phase 12D) ------------------------------------

    def open_loop_prefilter(
        self, user_text: str, *, has_open_loops: bool = False
    ) -> bool:
        """Cheap gate: should the open-loop LLM be consulted for this utterance?

        Returns ``True`` when the turn carries a plausible reminder signal, so the
        (off-hot-path) LLM judgement is worth the call — and ``False`` for idle
        chatter, so the LLM is never invoked needlessly. Two signals:

        * a *creation* trigger (``"remind me"``, ``"follow up"``, ``"need to"`` …)
          is always worth a look (the LLM then decides if it is a genuine reminder
          or just a fragment — the keyword pass alone used to store garbage here);
        * a *resolution* hint (``"done"``, ``"forget"``, ``"cancel"`` …) only when
          ``has_open_loops`` — there is no point asking the LLM to close a reminder
          out when none exist.

        This is intentionally permissive: a false positive costs one LLM call that
        returns an empty/NOOP result; the strict judgement lives in the LLM.
        """
        if not user_text or not user_text.strip():
            return False
        lowered = user_text.lower()
        if any(trigger in lowered for trigger in _OPEN_LOOP_TRIGGERS):
            return True
        if has_open_loops and any(
            hint in lowered for hint in _OPEN_LOOP_RESOLVE_HINTS
        ):
            return True
        return False

    def detect_open_loops(self, user_text: str) -> list[str]:
        """Scan ``user_text`` for promises/reminders/follow-ups.

        Returns a list of concise open-loop description strings — one per matched
        trigger — or an empty list when nothing looks like a commitment. Each
        description is the *content* of the commitment (the trigger phrase
        stripped off) so it reads naturally when surfaced later, e.g.
        ``"remind me to follow up with Maria"`` -> ``"follow up with Maria"``.

        Multiple distinct triggers in the same utterance each yield a loop, but
        duplicates (same normalised description) are collapsed so "remind me to X
        and don't forget to X" records X once.
        """
        if not user_text or not user_text.strip():
            return []

        loops: list[str] = []
        seen: set[str] = set()
        for sentence in _split_sentences(user_text):
            lowered = sentence.lower()
            # Collect every trigger occurrence as a (start, end) span. A sentence
            # may carry more than one commitment ("I need to X and don't forget
            # to Y"), so we must not stop at the first match.
            spans: list[tuple[int, int]] = []
            for trigger in _OPEN_LOOP_TRIGGERS:
                start = 0
                while True:
                    idx = lowered.find(trigger, start)
                    if idx == -1:
                        break
                    end = idx + len(trigger)
                    # Skip occurrences nested inside an already-recorded span
                    # (e.g. "remind me" inside "remind me to") so overlapping
                    # triggers don't double-count the same commitment.
                    if not any(s <= idx < e for s, e in spans):
                        spans.append((idx, end))
                    start = idx + 1
            # Order matches by position so each commitment body can be bounded
            # by the start of the next trigger in the same sentence.
            spans.sort()
            # A later trigger only starts a *new* commitment when a clause
            # separator (",", "and", "then", ";") sits between it and the
            # previous trigger — otherwise it is part of the current body
            # ("remind me to [follow up with Maria]" is one loop, not two).
            boundaries = [
                spans[i + 1][0]
                for i in range(len(spans) - 1)
                if re.search(
                    r"(?:,|\band\b|\bthen\b|;)",
                    sentence[spans[i][1]:spans[i + 1][0]],
                    flags=re.IGNORECASE,
                )
            ]
            for i, (_, end) in enumerate(spans):
                # Skip a trigger whose start is inside a prior commitment body
                # (no separator preceded it): it was absorbed, not a new loop.
                if i > 0 and spans[i][0] not in boundaries:
                    continue
                next_start = next(
                    (b for b in boundaries if b > end), len(sentence)
                )
                body = sentence[end:next_start].strip()
                desc = self._clean_loop_description(body)
                if not desc:
                    continue
                key = desc.lower()
                if key in seen:
                    # Skip near-identical triggers ("remind me to X and don't
                    # forget to X") so the same commitment records once.
                    continue
                seen.add(key)
                loops.append(desc)
        return loops

    @staticmethod
    def _clean_loop_description(body: str) -> str:
        """Tidy a raw commitment fragment into a concise description."""
        text = re.sub(r"\s+", " ", body).strip()
        # Drop a leading "to "/"that "/"on " left over after the trigger word.
        text = re.sub(r"^(?:to|that|on|about)\s+", "", text, flags=re.IGNORECASE)
        # Trim trailing punctuation/conjunctions so the snippet ends cleanly.
        text = text.rstrip(" .,!?;:")
        if len(text) > 120:
            text = text[:120].rsplit(" ", 1)[0] + "…"
        return text

    # --- People extraction (Phase 12D) --------------------------------------

    def extract_person(self, text: str) -> dict | None:
        """Extract a named person + contact hint from ``text``.

        Built for Gmail/Slack-flavoured context such as "I got an email from
        Sarah at sarah@example.com" or "message from Maria Lopez". Returns
        ``{"name": str, "email": str | None, "notes": str}`` when a person is
        found, else ``None``.

        Strategy (cheap, rule-based):

        * An email address is captured if present.
        * A name is taken from a "from <Name>" pattern (Gmail/Slack style) or,
          failing that, from the local-part of the email when it looks like a
          name. The first capitalised token(s) after "from" win.
        """
        if not text or not text.strip():
            return None

        email_match = re.search(_EMAIL_RE, text)
        email = email_match.group(0) if email_match else None

        name: str | None = None
        from_match = re.search(_FROM_NAME_RE, text)
        if from_match:
            name = from_match.group(1).strip()
            # Don't let a "from" immediately followed by the email steal the
            # email as a name (e.g. "from sarah@example.com").
            if email and name.lower() in email.lower():
                name = None

        if name is None and email:
            # Derive a display name from the local-part: "sarah.lopez" -> "Sarah Lopez".
            local = email.split("@", 1)[0]
            parts = re.split(r"[._-]+", local)
            if parts and all(p.isalpha() for p in parts):
                name = " ".join(p.capitalize() for p in parts)

        if not name:
            return None

        notes = self._compress(text, max_len=160)
        return {"name": name, "email": email, "notes": notes}

    # --- Failure splitting (Phase 12D) --------------------------------------

    @staticmethod
    def _split_failure(detail: str) -> tuple[str, str]:
        """Split a failure clause into ``(approach, reason)`` halves.

        Splits on the first "but/because/since/as" conjunction so
        "we tried Redis but it conflicted with the audio pipeline" yields
        ``("we tried Redis", "it conflicted with the audio pipeline")``. When no
        conjunction is present the whole clause is the approach and the reason is
        left unspecified.
        """
        text = re.sub(r"\s+", " ", detail or "").strip()
        if not text:
            return "unspecified", "unspecified"
        match = re.search(r"\b(but|because|since|as)\b", text, flags=re.IGNORECASE)
        if match:
            approach = text[: match.start()].strip(" .,;:")
            reason = text[match.end():].strip(" .,;:")
            return (approach or "unspecified", reason or "unspecified")
        return text.strip(" .,;:"), "unspecified"

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
                f"User corrected Helix: {user} "
                f"(corrected {stamp})."
            )
        if category == "decision":
            detail = user or reply_c
            return f"Decision: {detail} (decided {stamp})."
        if category == "failure":
            approach, reason = self._split_failure(user or reply_c)
            return (
                f"Failed approach: {approach}. Reason: {reason}. "
                f"Date: {stamp}."
            )
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
            ("i want you to ", "User wants Helix to "),
            ("i need you to ", "User wants Helix to "),
            ("call me ", "User is called "),
        )
        for prefix, repl in replacements:
            if lowered.startswith(prefix):
                return repl + t[len(prefix):]
        # No recognised first-person opener: return as-is (already compressed).
        return t


__all__ = ["MemoryEvaluator", "PROMOTION_THRESHOLD"]
