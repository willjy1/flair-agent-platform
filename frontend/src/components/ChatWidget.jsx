import React, { useEffect, useRef, useState } from "react";

export default function ChatWidget() {
  const [sessionId] = useState(`web-${Math.random().toString(36).slice(2, 8)}`);
  const [customerId] = useState("demo-customer");
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState([
    { role: "agent", text: "Hello. How can I help with your Flair trip today?" },
  ]);
  const [sending, setSending] = useState(false);
  const listRef = useRef(null);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  async function sendMessage() {
    const content = input.trim();
    if (!content || sending) return;
    setMessages((prev) => [...prev, { role: "user", text: content }]);
    setInput("");
    setSending(true);
    try {
      const resp = await fetch("/api/v1/chat/message", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, customer_id: customerId, channel: "web", content }),
      });
      const data = await resp.json();
      setMessages((prev) => [...prev, { role: "agent", text: data.response_text }]);
    } catch (err) {
      setMessages((prev) => [...prev, { role: "agent", text: `Network error: ${String(err)}` }]);
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-900">Web Chat Widget</h3>
        <span className="text-xs text-slate-500">Session {sessionId}</span>
      </div>
      <div ref={listRef} className="h-64 space-y-2 overflow-y-auto rounded-lg bg-slate-50 p-3">
        {messages.map((m, idx) => (
          <div
            key={idx}
            className={`max-w-[85%] rounded-2xl px-3 py-2 text-sm ${
              m.role === "user"
                ? "ml-auto bg-slate-900 text-white"
                : "bg-white text-slate-900 ring-1 ring-slate-200"
            }`}
          >
            {m.text}
          </div>
        ))}
      </div>
      <div className="mt-3 flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              sendMessage();
            }
          }}
          placeholder="Ask about a booking, refund, delay, or baggage issue"
          className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-500"
        />
        <button
          onClick={sendMessage}
          disabled={sending}
          className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
        >
          {sending ? "Sending..." : "Send"}
        </button>
      </div>
    </div>
  );
}

