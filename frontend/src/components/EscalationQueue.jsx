import React from "react";

export default function EscalationQueue({ items = [] }) {
  const rows =
    items.length > 0
      ? items
      : [
          { customer: "cust-183", issue: "Complaint / refund denial", urgency: 9, sentiment: "negative", waiting: "06:15" },
          { customer: "cust-744", issue: "Accessibility support", urgency: 8, sentiment: "neutral", waiting: "02:11" },
        ];

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold text-slate-900">Escalation Queue</h3>
      <div className="space-y-2">
        {rows.map((row, idx) => (
          <div key={`${row.customer}-${idx}`} className="grid grid-cols-[1fr_auto] gap-3 rounded-lg border border-slate-100 p-3">
            <div>
              <div className="text-sm font-medium text-slate-900">{row.customer}</div>
              <div className="text-sm text-slate-700">{row.issue}</div>
              <div className="mt-1 text-xs text-slate-500">
                Sentiment: {row.sentiment} · Waiting: {row.waiting}
              </div>
            </div>
            <div className="text-right">
              <div className="text-xs text-slate-500">Urgency</div>
              <div className="text-lg font-semibold text-rose-600">{row.urgency}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

