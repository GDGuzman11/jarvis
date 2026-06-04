/**
 * Window 2 — ReasoningWindow. A proper chat interface: model + cost/latency
 * header bar, a scrollable conversation history (user turns right-aligned,
 * Jarvis turns left-aligned with live token streaming), the tool-call cards,
 * and a text input. All data is store-driven; nothing is hardcoded except the
 * "Claude Opus 4.7" default until a `token`/`metrics` event overrides it.
 */

import { useState, useRef, useEffect, type KeyboardEvent } from "react";
import { useStore } from "../lib/store";
import type { ChatMessage } from "../lib/store";
import WindowFrame from "../components/WindowFrame";

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

function MessageBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === "user";
  return (
    <div className={`flex flex-col ${isUser ? "items-end" : "items-start"}`}>
      <span
        className={`mb-0.5 text-[9px] font-bold uppercase tracking-[0.25em] ${
          isUser ? "text-jarvis-muted" : "text-jarvis-cyan/70"
        }`}
      >
        {isUser ? "You" : "Jarvis"}
      </span>
      <div
        className={`max-w-[80%] whitespace-pre-wrap break-words px-3 py-2 text-xs leading-relaxed ${
          isUser
            ? "border border-jarvis-cyan/30 bg-jarvis-cyan/10 text-right text-jarvis-text"
            : "border border-white/10 bg-white/5 text-left text-jarvis-text"
        }`}
      >
        {msg.content}
        {msg.role === "jarvis" && !msg.complete && (
          <span className="ml-0.5 inline-block h-3 w-1.5 animate-pulse-glow bg-jarvis-cyan align-middle" />
        )}
      </div>
    </div>
  );
}

export function ReasoningWindow() {
  const model = useStore((s) => s.model);
  const chatHistory = useStore((s) => s.chatHistory);
  const toolCalls = useStore((s) => s.toolCalls);
  const metrics = useStore((s) => s.metrics);
  const sessionCostUsd = useStore((s) => s.sessionCostUsd);
  const addUserMessage = useStore((s) => s.addUserMessage);
  const voiceState = useStore((s) => s.voiceState);

  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const busy = voiceState !== "idle";

  // Auto-scroll to the bottom whenever the conversation grows or streams.
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [chatHistory]);

  async function handleSend() {
    const text = input.trim();
    if (!text || busy || sending) return;
    setSending(true);
    setError(null);
    setInput("");
    addUserMessage(text);
    try {
      const res = await fetch("http://127.0.0.1:8000/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        setError((data as { detail?: string }).detail ?? "Error — try again.");
      }
    } catch {
      setError("Backend offline.");
    } finally {
      setSending(false);
      inputRef.current?.focus();
    }
  }

  function handleKey(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") handleSend();
  }

  return (
    <WindowFrame title="Reasoning" index={1}>
      <div className="flex h-full flex-col gap-3 p-4">
        {/* Header row: model badge + live metrics */}
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="glass px-3 py-1.5 text-sm font-bold tracking-wide text-glow-cyan">
            {model}
          </span>
          <div className="flex flex-wrap items-center gap-2">
            <span className="glass px-3 py-1.5 text-xs">
              <span className="text-jarvis-muted">COST </span>
              <span className="font-mono text-jarvis-gold">${metrics.cost_usd.toFixed(4)}</span>
            </span>
            <span className="glass px-3 py-1.5 text-xs">
              <span className="text-jarvis-muted">SESSION </span>
              <span className="font-mono text-jarvis-gold">${sessionCostUsd.toFixed(2)}</span>
            </span>
            <span className="glass px-3 py-1.5 text-xs">
              <span className="text-jarvis-muted">LATENCY </span>
              <span className="font-mono text-jarvis-cyan">{metrics.latency_ms} ms</span>
            </span>
            <span className="px-1 text-[10px] text-jarvis-muted">
              {metrics.input_tokens} in / {metrics.output_tokens} out
              {metrics.cache_read_tokens > 0 && (
                <span className="text-jarvis-muted/70"> · {metrics.cache_read_tokens} cached</span>
              )}
            </span>
          </div>
        </div>

        {/* Chat history */}
        <div ref={scrollRef} className="hud-scroll glass min-h-0 flex-1 space-y-3 overflow-y-auto p-3">
          {chatHistory.length === 0 ? (
            <p className="text-xs italic text-jarvis-muted">
              No conversation yet. Say "Hey Jarvis" or type a message below.
            </p>
          ) : (
            chatHistory.map((m) => <MessageBubble key={m.id} msg={m} />)
          )}
        </div>

        {/* Tool calls */}
        <div className="hud-scroll max-h-[24%] min-h-0 shrink-0 space-y-2 overflow-y-auto">
          <p className="text-[10px] uppercase tracking-widest text-jarvis-muted">Tool Calls</p>
          {toolCalls.length === 0 ? (
            <p className="text-xs italic text-jarvis-muted">No tool calls yet.</p>
          ) : (
            toolCalls.map((c) => (
              <ToolCallCard key={c.id} toolName={c.tool_name} agentId={c.agent_id} args={c.args} result={c.result} />
            ))
          )}
        </div>

        {/* Text input — type a message when mic isn't available */}
        <div className="shrink-0 space-y-1">
          <p className="text-[10px] uppercase tracking-widest text-jarvis-muted">
            {busy ? voiceState.toUpperCase() : "Type a message"}
          </p>
          <div className="flex gap-2">
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKey}
              disabled={busy || sending}
              placeholder={busy ? "Jarvis is busy…" : "Ask Jarvis anything…"}
              className="flex-1 border border-jarvis-cyan/30 bg-jarvis-bg/60 px-3 py-2 text-xs text-jarvis-text placeholder:text-jarvis-muted/50 outline-none transition-colors focus:border-jarvis-cyan/70 disabled:opacity-40"
            />
            <button
              type="button"
              onClick={handleSend}
              disabled={busy || sending || !input.trim()}
              className="hud-btn shrink-0 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {sending ? "…" : "SEND"}
            </button>
          </div>
          {error && <p className="text-[10px] text-jarvis-red">{error}</p>}
        </div>
      </div>
    </WindowFrame>
  );
}

export default ReasoningWindow;
