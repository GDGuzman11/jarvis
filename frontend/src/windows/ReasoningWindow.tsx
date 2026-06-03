/**
 * Window 2 — ReasoningWindow. Model badge, live streaming token output, tool
 * call cards, and cost/latency metrics. All data is store-driven; nothing is
 * hardcoded except the static "Claude Opus 4.7" default until a `token`/`metrics`
 * event overrides the model name.
 */

import { useStore } from "../lib/store";
import WindowFrame from "../components/WindowFrame";
import StreamViewer from "../components/StreamViewer";

function ToolCallCard({
  toolName,
  agentId,
  args,
  result,
}: {
  toolName: string;
  agentId: string;
  args: Record<string, unknown>;
  result: unknown | null;
}) {
  return (
    <div className="glass p-3">
      <div className="flex items-center justify-between">
        <span className="font-mono text-sm font-bold text-jarvis-cyan">{toolName}()</span>
        <span className="text-[10px] uppercase tracking-widest text-jarvis-muted">{agentId}</span>
      </div>
      <pre className="hud-scroll mt-2 max-h-20 overflow-auto whitespace-pre-wrap break-words text-[11px] text-jarvis-text/70">
        {JSON.stringify(args, null, 2)}
      </pre>
      <div className="mt-1 border-t border-jarvis-cyan/10 pt-1">
        <span className="text-[10px] uppercase tracking-widest text-jarvis-muted">Result</span>
        <pre className="hud-scroll mt-0.5 max-h-20 overflow-auto whitespace-pre-wrap break-words text-[11px] text-jarvis-gold/80">
          {result === null ? "… in flight" : JSON.stringify(result, null, 2)}
        </pre>
      </div>
    </div>
  );
}

export function ReasoningWindow() {
  const model = useStore((s) => s.model);
  const streamingText = useStore((s) => s.streamingText);
  const toolCalls = useStore((s) => s.toolCalls);
  const metrics = useStore((s) => s.metrics);
  const voiceState = useStore((s) => s.voiceState);

  return (
    <WindowFrame title="Reasoning" index={1}>
      <div className="flex h-full flex-col gap-3 p-4">
        {/* Header row: model badge + metrics */}
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="glass px-3 py-1.5 text-sm font-bold tracking-wide text-glow-cyan">
            {model}
          </span>
          <div className="flex gap-2">
            <span className="glass px-3 py-1.5 text-xs">
              <span className="text-jarvis-muted">COST </span>
              <span className="font-mono text-jarvis-gold">${metrics.cost_usd.toFixed(4)}</span>
            </span>
            <span className="glass px-3 py-1.5 text-xs">
              <span className="text-jarvis-muted">LATENCY </span>
              <span className="font-mono text-jarvis-cyan">{metrics.latency_ms} ms</span>
            </span>
          </div>
        </div>

        {/* Token stream */}
        <div className="glass min-h-0 flex-1">
          <StreamViewer text={streamingText} active={voiceState === "thinking" || voiceState === "speaking"} />
        </div>

        {/* Tool calls */}
        <div className="hud-scroll max-h-[38%] min-h-0 shrink-0 space-y-2 overflow-y-auto">
          <p className="text-[10px] uppercase tracking-widest text-jarvis-muted">Tool Calls</p>
          {toolCalls.length === 0 ? (
            <p className="text-xs italic text-jarvis-muted">No tool calls yet.</p>
          ) : (
            toolCalls.map((c) => (
              <ToolCallCard key={c.id} toolName={c.tool_name} agentId={c.agent_id} args={c.args} result={c.result} />
            ))
          )}
        </div>
      </div>
    </WindowFrame>
  );
}

export default ReasoningWindow;
