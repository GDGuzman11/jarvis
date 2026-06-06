/**
 * Window 4 — AgentsWindow. Grid of 6 agent cards driven entirely by
 * `agent_update` events. Each card shows name, role, status badge, current task,
 * and an expandable task history.
 */

import { useStore } from "../lib/store";
import WindowFrame from "../components/WindowFrame";
import AgentCard from "../components/AgentCard";
import MissionControl from "../components/MissionControl";

export function AgentsWindow() {
  const agents = useStore((s) => s.agents);

  return (
    <WindowFrame title="Agents" index={3}>
      <div className="hud-scroll h-full overflow-y-auto p-4">
        {/* Phase 13A — high-level goal entry; Atlas delegates to the team. */}
        <MissionControl />
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {agents.map((agent) => (
            <AgentCard key={agent.agent_id} agent={agent} />
          ))}
        </div>
      </div>
    </WindowFrame>
  );
}

export default AgentsWindow;
