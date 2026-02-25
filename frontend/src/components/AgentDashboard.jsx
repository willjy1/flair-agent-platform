import React from "react";

export default function AgentDashboard({ stats = {} }) {
  const cards = [
    { label: "Active Conversations", value: stats.activeConversations ?? 12 },
    { label: "Escalations Waiting", value: stats.escalationQueue ?? 3 },
    { label: "Avg Handle Time", value: stats.avgHandleTime ?? "4m 38s" },
    { label: "Containment Rate", value: stats.containmentRate ?? "68%" },
  ];

  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      {cards.map((card) => (
        <div key={card.label} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="text-xs font-medium uppercase tracking-wide text-slate-500">{card.label}</div>
          <div className="mt-2 text-2xl font-semibold text-slate-900">{card.value}</div>
        </div>
      ))}
    </div>
  );
}

