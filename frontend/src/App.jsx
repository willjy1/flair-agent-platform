import React from "react";
import AgentDashboard from "./components/AgentDashboard";
import ChatWidget from "./components/ChatWidget";
import ConversationTimeline from "./components/ConversationTimeline";
import EscalationQueue from "./components/EscalationQueue";
import AnalyticsPanel from "./components/AnalyticsPanel";

export default function App() {
  return (
    <div className="min-h-screen bg-slate-100 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <div>
            <div className="text-xs uppercase tracking-[0.18em] text-slate-500">Flair Agent Platform</div>
            <h1 className="text-xl font-semibold">Customer Service Operations Dashboard</h1>
          </div>
          <div className="text-sm text-slate-600">Live monitor · Multi-channel agent orchestration</div>
        </div>
      </header>
      <main className="mx-auto grid max-w-7xl gap-6 px-6 py-6">
        <AgentDashboard />
        <div className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
          <ChatWidget />
          <EscalationQueue />
        </div>
        <div className="grid gap-6 xl:grid-cols-2">
          <ConversationTimeline />
          <AnalyticsPanel />
        </div>
      </main>
    </div>
  );
}

