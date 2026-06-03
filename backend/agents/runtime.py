"""Agent runtime — constructs, starts, and stops all 6 background agents.

This module is the single place the FastAPI lifespan wires the agent system in
and out. It builds the five specialists (Ben, Kado, Sentinel, Vega, Quill) plus
the Production Lead (Atlas), registers every specialist with the lead so it can
delegate to them, and exposes :meth:`start` / :meth:`stop` to bring the whole
roster up and down as asyncio background tasks.

Keeping construction here (rather than inline in ``main.py``) means tests can
spin up the same roster against a temp database and an injected hub without
touching the HTTP app.

Persistence across restarts
---------------------------
:meth:`start` calls each agent's ``start()``, which upserts the agent's row into
the ``agents`` table (status ``idle``) before serving — so every agent's
identity and status survive a backend restart. :meth:`stop` flips them all to
``offline`` on a clean shutdown.
"""

from __future__ import annotations

from typing import Any

from backend.agents.backend_agent import BackendAgent
from backend.agents.base_agent import BaseAgent
from backend.agents.content_creator import ContentCreatorAgent
from backend.agents.frontend_agent import FrontendAgent
from backend.agents.marketing_agent import MarketingAgent
from backend.agents.production_lead import ProductionLead
from backend.agents.security_agent import SecurityAgent
from backend.logging_config import get_logger
from backend.websocket_hub import ConnectionHub

log = get_logger(__name__)


class AgentRuntime:
    """Owns the full set of background agents and their lifecycle.

    Parameters
    ----------
    hub:
        WebSocket hub the agents broadcast :class:`AgentUpdate` events on. When
        ``None``, each agent uses the process-wide singleton hub.
    db_path:
        Optional SQLite path override, threaded through to every agent (tests
        point this at a temp database).

    Attributes
    ----------
    production_lead:
        The :class:`ProductionLead` orchestrator — submit goals here.
    specialists:
        Mapping of ``agent_id`` -> specialist agent.
    agents:
        Mapping of ``agent_id`` -> agent, including the Production Lead. The
        complete roster.
    """

    def __init__(
        self,
        *,
        hub: ConnectionHub | None = None,
        db_path: Any | None = None,
    ) -> None:
        common: dict[str, Any] = {}
        if hub is not None:
            common["hub"] = hub
        if db_path is not None:
            common["db_path"] = db_path

        # Build the five specialists.
        self.specialists: dict[str, BaseAgent] = {
            agent.agent_id: agent
            for agent in (
                FrontendAgent(**common),
                BackendAgent(**common),
                SecurityAgent(**common),
                MarketingAgent(**common),
                ContentCreatorAgent(**common),
            )
        }

        # The orchestrator delegates to every specialist.
        self.production_lead = ProductionLead(agents=self.specialists, **common)

        # Full roster, lead first for stable display ordering.
        self.agents: dict[str, BaseAgent] = {
            self.production_lead.agent_id: self.production_lead,
            **self.specialists,
        }

    async def start(self) -> None:
        """Start every agent's background run loop (idempotent per agent).

        Each ``start()`` upserts the agent's DB row to ``idle`` first, so the
        agents table is fully populated and persists across restarts.
        """
        for agent in self.agents.values():
            await agent.start()
        log.info("agent_runtime_started", count=len(self.agents))

    async def stop(self) -> None:
        """Stop every agent's run loop and mark them ``offline``."""
        for agent in self.agents.values():
            await agent.stop()
        log.info("agent_runtime_stopped", count=len(self.agents))

    async def submit_goal(
        self, goal: str, *, title: str | None = None
    ) -> dict[str, Any]:
        """Convenience pass-through to the Production Lead's goal router."""
        return await self.production_lead.submit_goal(goal, title=title)


__all__ = ["AgentRuntime"]
