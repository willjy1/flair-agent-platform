import React from "react";

export default function ConversationTimeline({ events = [] }) {
  const rows =
    events.length > 0
      ? events
      : [
          {
            ts: "10:12:05",
            agent: "triage_agent",
            action: "classify",
            reasoning: "Detected refund request with booking reference.",
          },
          {
            ts: "10:12:05",
            agent: "refund_agent",
            action: "refund_estimate",
            reasoning: "Fetched booking and estimated fare+ancillary refund.",
          },
        ];

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold text-slate-900">Conversation Timeline</h3>
      <ol className="space-y-3">
        {rows.map((row, idx) => (
          <li key={`${row.ts}-${idx}`} className="grid gap-1 rounded-lg border border-slate-100 p-3">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-slate-900">{row.agent}</span>
              <span className="text-xs text-slate-500">{row.ts}</span>
            </div>
            <div className="text-xs uppercase tracking-wide text-slate-500">{row.action}</div>
            <div className="text-sm text-slate-700">{row.reasoning}</div>
          </li>
        ))}
      </ol>
    </div>
  );
}

