"""Production Lead — the orchestrator agent.

The Production Lead is Jarvis's project manager. It takes incoming *goals*
(high-level requests, typically from the user via the voice pipeline) and routes
each to the specialist best suited to handle it: UI work to Ben, backend/API work
to Kado, security to Sentinel, marketing strategy to Vega, and writing/copy to
Quill.

How routing works
-----------------
Routing is itself an agent task. When a goal arrives, the Production Lead runs as
any other agent (status ``working``), classifies the goal to a target agent, then
performs the *delegation*:

    1. create a row in the ``tasks`` table (``create_task``) recording who
       delegated to whom — this is the agent-to-agent messaging channel and the
       durable record of the hand-off, and
    2. enqueue the task (carrying that ``task_id``) onto the chosen specialist's
       in-memory queue so it starts work immediately.

Classification first tries fast, deterministic keyword/intent matching (cheap, no
API call, easy to test). Only if that is inconclusive does it fall back to asking
Claude to pick the best agent — so the common cases are instant and the
ambiguous ones still route sensibly.

The Production Lead's own :meth:`handle_task` *is* the routing step, so a goal can
be enqueued onto the Production Lead exactly like any other task and it will fan
out to the right specialist.
"""

from __future__ import annotations

import re
from typing import Any

from backend.agents.base_agent import BaseAgent
from backend.ai.persona import build_system_prompt
from backend.logging_config import get_logger
from backend.memory import database

log = get_logger(__name__)

AGENT_ID = "production_lead"
AGENT_NAME = "Atlas"
AGENT_ROLE = "Production lead — breaks goals into tasks, delegates, and monitors"

# The Production Lead orchestrates; it does not need tool access of its own.
DEFAULT_TOOLS: list[str] = []

# --- Keyword routing table --------------------------------------------------
# Ordered most-specific to least so the first matching agent wins. Each entry
# maps a target agent_id to the regex keywords that route a goal to it. Kept as
# word-boundary patterns so "ui" doesn't match "build" and "api" matches "API".
_ROUTING_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "security",
        (
            "security", "secure", "vulnerab", "audit", "exploit", "cve",
            "credential", "secret", "encrypt", "auth", "oauth", "penetrat",
            "key rotation", "sanitiz", "sandbox",
        ),
    ),
    (
        "frontend",
        (
            "ui", "ux", "frontend", "front-end", "react", "tauri", "component",
            "css", "tailwind", "styling", "design", "window", "orb", "animation",
            "three.js", "layout", "button", "zustand", "vite",
        ),
    ),
    (
        "backend",
        (
            "backend", "back-end", "api", "endpoint", "database", "sqlite",
            "websocket", "fastapi", "server", "voice pipeline", "performance",
            "latency", "faiss", "schema", "migration", "async", "ollama",
            "whisper", "query",
        ),
    ),
    (
        "marketing",
        (
            "marketing", "campaign", "growth", "launch", "audience", "brand",
            "positioning", "social media strategy", "go-to-market", "seo",
            "funnel", "advertis",
        ),
    ),
    (
        "content",
        (
            "write", "draft", "copy", "content", "blog", "post", "email copy",
            "newsletter", "documentation", "docs", "article", "caption",
            "headline", "tagline", "script",
        ),
    ),
)

# Fallback target when nothing matches and the LLM classifier is unavailable.
# Backend is the safest default for a local-first engineering project.
_DEFAULT_TARGET = "backend"

# The valid set of routable targets (everything the Production Lead can delegate
# to). Used to validate the LLM classifier's answer.
_VALID_TARGETS = frozenset(agent_id for agent_id, _ in _ROUTING_RULES)

_CLASSIFIER_SYSTEM = """\
You are the routing brain of Jarvis's production lead. Given a goal, reply with EXACTLY ONE \
word naming the single best agent to handle it, chosen from this set and nothing else:
- frontend  (UI, React/Tauri, design, visual work)
- backend   (APIs, database, server, voice pipeline, performance)
- security  (audits, vulnerabilities, credentials, OAuth, sandboxing)
- marketing (campaign planning, positioning, social strategy)
- content   (writing posts, emails, copy, documentation)
Reply with only the agent id, lowercase, no punctuation, no explanation."""


class ProductionLead(BaseAgent):
    """Atlas: classifies incoming goals and delegates them to specialists.

    Parameters
    ----------
    agents:
        Mapping of ``agent_id`` -> the specialist :class:`BaseAgent` instance the
        Production Lead may delegate to. Wired up at startup in the FastAPI
        lifespan. Tests can pass fakes here.
    """

    def __init__(self, agents: dict[str, BaseAgent] | None = None, **kwargs: Any) -> None:
        super().__init__(
            agent_id=AGENT_ID,
            name=AGENT_NAME,
            role=AGENT_ROLE,
            tools=list(DEFAULT_TOOLS),
            **kwargs,
        )
        # The roster of specialists this lead can delegate to. May be populated
        # after construction via :meth:`register_agent` (e.g. once all agents
        # exist in the lifespan).
        self._agents: dict[str, BaseAgent] = dict(agents or {})

    def register_agent(self, agent: BaseAgent) -> None:
        """Add (or replace) a specialist in the delegation roster."""
        self._agents[agent.agent_id] = agent

    # --- Public entry point -------------------------------------------------

    async def submit_goal(
        self, goal: str, *, title: str | None = None
    ) -> dict[str, Any]:
        """Route an incoming goal: classify, record the hand-off, and delegate.

        This is the orchestrator's primary public method — the voice pipeline or
        a route handler calls it with a user goal. It returns a small dict
        describing the routing decision: ``{"target": <agent_id>, "task_id":
        <int|None>, "delegated": <bool>}``.
        """
        target = await self.classify(goal)
        task_id, delegated = await self._delegate(goal, target, title=title)
        return {"target": target, "task_id": task_id, "delegated": delegated}

    # --- Routing as a task --------------------------------------------------

    async def handle_task(self, task: dict[str, Any]) -> str:
        """Treat an inbound task as a goal to route, and delegate it.

        Lets a goal be enqueued onto the Production Lead exactly like any other
        agent task; processing it performs the classification + delegation and
        returns a human-readable summary of where it went.
        """
        goal = task.get("description", "").strip()
        title = task.get("title")
        result = await self.submit_goal(goal, title=title)
        target = result["target"]
        target_name = self._agent_name(target)
        return f"Routed to {target_name} ({target}); task #{result['task_id']}."

    # --- Classification -----------------------------------------------------

    async def classify(self, goal: str) -> str:
        """Return the ``agent_id`` best suited to handle ``goal``.

        Tries deterministic keyword matching first (no API call). If that is
        inconclusive, asks Claude to pick from the valid set; if even that is
        unavailable, falls back to :data:`_DEFAULT_TARGET`. The result is always
        a member of :data:`_VALID_TARGETS`.
        """
        keyword_match = self._match_keywords(goal)
        if keyword_match is not None:
            log.info("route_keyword", goal_len=len(goal), target=keyword_match)
            return keyword_match

        llm_match = await self._classify_with_llm(goal)
        if llm_match is not None:
            log.info("route_llm", goal_len=len(goal), target=llm_match)
            return llm_match

        log.info("route_default", goal_len=len(goal), target=_DEFAULT_TARGET)
        return _DEFAULT_TARGET

    @staticmethod
    def _match_keywords(goal: str) -> str | None:
        """Deterministic first-pass routing via word-boundary keyword match."""
        text = goal.lower()
        for agent_id, keywords in _ROUTING_RULES:
            for kw in keywords:
                # Word-boundary match so short tokens ("ui", "api") don't match
                # inside unrelated words. ``re.escape`` keeps "." / "-" literal.
                if re.search(rf"\b{re.escape(kw)}", text):
                    return agent_id
        return None

    async def _classify_with_llm(self, goal: str) -> str | None:
        """Ask Claude (Ollama fallback) to pick a target; validate the answer.

        Returns a valid ``agent_id`` or ``None`` if the model is unavailable or
        returns something not in the allowed set (so the caller can default).
        """
        if not goal:
            return None
        try:
            answer = await self.reason(goal, _CLASSIFIER_SYSTEM)
        except Exception:  # noqa: BLE001 — never let routing crash on the model
            log.warning("route_llm_failed", exc_info=True)
            return None
        # The model should return a bare agent id; normalise and validate.
        token = answer.strip().lower().split()[0] if answer.strip() else ""
        token = re.sub(r"[^a-z_]", "", token)
        return token if token in _VALID_TARGETS else None

    # --- Delegation (the agent-to-agent hand-off) ---------------------------

    async def _delegate(
        self, goal: str, target: str, *, title: str | None
    ) -> tuple[int | None, bool]:
        """Record the hand-off in ``tasks`` and enqueue it on the specialist.

        Always writes the durable ``tasks`` row (the agent-to-agent message),
        even if the target specialist isn't currently registered, so the
        delegation is auditable. Returns ``(task_id, delegated)`` where
        ``delegated`` is ``True`` only if the task was also enqueued live.
        """
        task_title = title or self._summarise(goal)
        task_id = await database.create_task(
            self.agent_id,
            target,
            task_title,
            description=goal if goal and goal != task_title else None,
            **self._db_kwargs(),
        )
        await self._log_audit("task.delegate", target=f"{target}:task:{task_id}")

        specialist = self._agents.get(target)
        if specialist is None:
            log.warning("route_target_unavailable", target=target, task_id=task_id)
            return task_id, False

        specialist.enqueue_task(
            {
                "task_id": task_id,
                "title": task_title,
                "description": goal,
                "created_by": self.agent_id,
            }
        )
        return task_id, True

    # --- Helpers ------------------------------------------------------------

    def _agent_name(self, agent_id: str) -> str:
        """Display name for ``agent_id`` if known, else the id itself."""
        agent = self._agents.get(agent_id)
        return agent.name if agent is not None else agent_id

    @staticmethod
    def _summarise(goal: str) -> str:
        """Derive a short task title from the goal's first line."""
        first_line = (goal or "").strip().splitlines()[0] if goal.strip() else ""
        return first_line[:120] or "Untitled goal"


__all__ = [
    "ProductionLead",
    "AGENT_ID",
    "AGENT_NAME",
    "AGENT_ROLE",
    "DEFAULT_TOOLS",
]
