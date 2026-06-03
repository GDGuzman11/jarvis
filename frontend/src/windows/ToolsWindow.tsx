/**
 * Window 5 — ToolsWindow. The tool/agent permission matrix: rows are tools,
 * columns are agents, each cell is a ToolCard checkbox. The tool list and
 * permission matrix come from the store (seeded from backend defaults, then
 * overwritten by `tool_permissions` events).
 */

import { useStore } from "../lib/store";
import WindowFrame from "../components/WindowFrame";
import ToolCard from "../components/ToolCard";

export function ToolsWindow() {
  const tools = useStore((s) => s.tools);
  const agents = useStore((s) => s.agents);

  return (
    <WindowFrame title="Tools" index={4}>
      <div className="hud-scroll h-full overflow-auto p-4">
        <table className="w-full border-separate" style={{ borderSpacing: "0.5rem" }}>
          <thead>
            <tr>
              <th className="sticky left-0 bg-jarvis-bg/80 px-2 py-1 text-left text-[10px] uppercase tracking-widest text-jarvis-muted">
                Tool / Agent
              </th>
              {agents.map((a) => (
                <th key={a.agent_id} className="px-1 py-1 text-center">
                  <div className="text-xs font-bold text-glow-cyan">{a.agent_name}</div>
                  <div className="text-[9px] uppercase tracking-widest text-jarvis-muted">{a.role}</div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {tools.map((tool) => (
              <tr key={tool}>
                <td className="sticky left-0 bg-jarvis-bg/80 px-2 py-1 font-mono text-xs text-jarvis-text">
                  {tool}
                </td>
                {agents.map((a) => (
                  <td key={a.agent_id} className="px-1 py-1 text-center">
                    <div className="flex justify-center">
                      <ToolCard agentId={a.agent_id} tool={tool} />
                    </div>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </WindowFrame>
  );
}

export default ToolsWindow;
