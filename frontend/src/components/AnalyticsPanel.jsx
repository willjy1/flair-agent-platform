import React from "react";

export default function AnalyticsPanel({ metrics = {} }) {
  const items = [
    ["Intent Distribution", metrics.intentDistribution ?? "Refund 22% · Delay 19% · Booking 18%"],
    ["Resolution by Channel", metrics.channelResolution ?? "Web 72% · SMS 58% · Voice 49%"],
    ["Sentiment Trend", metrics.sentimentTrend ?? "Improving (+0.08 vs prior week)"],
    ["APPR Compliance", metrics.apprCompliance ?? "100% calculations logged with citations"],
    ["Cost per Resolution", metrics.costPerResolution ?? "$3.82"],
  ];

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold text-slate-900">Analytics</h3>
      <div className="space-y-2">
        {items.map(([label, value]) => (
          <div key={label} className="rounded-lg border border-slate-100 p-3">
            <div className="text-xs uppercase tracking-wide text-slate-500">{label}</div>
            <div className="mt-1 text-sm text-slate-800">{value}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

