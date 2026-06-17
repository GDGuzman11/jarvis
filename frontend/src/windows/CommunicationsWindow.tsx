/**
 * Window 3 — CommunicationsWindow. Slack panel (left) + Gmail panel (right).
 * Each shows inbox items as sharp-edged glass cards that glow cyan on hover.
 * Action buttons emit a command over the WebSocket so the backend can trigger
 * the spoken voice confirmation.
 */

import type { ReactNode } from "react";
import { useStore } from "../lib/store";
import WindowFrame from "../components/WindowFrame";
import { sendCommand } from "../lib/websocket";
import type { GmailMessage, SlackMessage } from "../lib/types";

function Panel({ title, accent, action, children }: { title: string; accent: string; action: ReactNode; children: ReactNode }) {
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-center justify-between px-1 py-2">
        <h2 className="text-xs font-bold uppercase tracking-[0.3em]" style={{ color: accent }}>
          {title}
        </h2>
        {action}
      </div>
      <div className="hud-scroll min-h-0 flex-1 space-y-2 overflow-y-auto pr-1">{children}</div>
    </div>
  );
}

function ActionButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="glass glass-hover px-3 py-1 text-[10px] font-semibold uppercase tracking-widest text-helix-gold"
    >
      {label}
    </button>
  );
}

function MessageCard({ top, mid, snippet, unread }: { top: string; mid: string; snippet: string; unread: boolean }) {
  return (
    <div className="glass glass-hover p-3">
      <div className="flex items-center justify-between">
        <span className="truncate text-sm font-semibold text-helix-ink">{top}</span>
        {unread && <span className="h-2 w-2 shrink-0 bg-helix-accent" style={{ boxShadow: "0 0 8px #3fe3d0" }} />}
      </div>
      <p className="mt-0.5 truncate text-xs text-helix-gold/80">{mid}</p>
      <p className="mt-1 line-clamp-2 text-xs text-helix-muted">{snippet}</p>
    </div>
  );
}

function EmptyState({ label }: { label: string }) {
  return <p className="px-1 text-xs italic text-helix-muted">{label}</p>;
}

export function CommunicationsWindow() {
  const slack = useStore((s) => s.slackMessages);
  const gmail = useStore((s) => s.gmailMessages);

  return (
    <WindowFrame title="Communications" index={2}>
      <div className="flex h-full gap-4 p-4">
        <Panel
          title="Slack"
          accent="#ffc247"
          action={<ActionButton label="Reply" onClick={() => sendCommand({ type: "comms_action", channel: "slack", action: "reply" })} />}
        >
          {slack.length === 0 ? (
            <EmptyState label="No Slack messages." />
          ) : (
            slack.map((m: SlackMessage) => (
              <MessageCard key={m.id} top={m.sender} mid={`#${m.channel}`} snippet={m.text} unread={m.unread} />
            ))
          )}
        </Panel>

        <div className="w-px bg-helix-gold/15" />

        <Panel
          title="Gmail"
          accent="#ffe9a8"
          action={<ActionButton label="Compose" onClick={() => sendCommand({ type: "comms_action", channel: "gmail", action: "compose" })} />}
        >
          {gmail.length === 0 ? (
            <EmptyState label="Inbox empty." />
          ) : (
            gmail.map((m: GmailMessage) => (
              <MessageCard key={m.id} top={m.sender} mid={m.subject} snippet={m.snippet} unread={m.unread} />
            ))
          )}
        </Panel>
      </div>
    </WindowFrame>
  );
}

export default CommunicationsWindow;
