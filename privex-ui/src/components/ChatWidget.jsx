import { useMemo, useState } from 'react';

function formatAssistantMessage(payload) {
  if (!payload || typeof payload !== 'object') {
    return 'No response payload returned.';
  }

  const risk = payload.risk_level || 'Unknown';
  const action = payload.proposed_action || 'N/A';
  const approval = payload.human_approval_required ? 'Required' : 'Not required';

  return `Risk: ${risk}\nAction: ${action}\nHuman Approval: ${approval}`;
}

export default function ChatWidget() {
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      text: 'Privex assistant online. Ask me to analyze a privacy/security task.',
    },
  ]);
  const [inputValue, setInputValue] = useState('');
  const [isSending, setIsSending] = useState(false);

  // Point to the Express MCP server instead of FastAPI directly
  const mcpApiUrl = useMemo(() => import.meta.env.VITE_MCP_API_URL || 'http://localhost:3000', []);

  async function handleSubmit(event) {
    event.preventDefault();
    const query = inputValue.trim();
    if (!query || isSending) return;

    setMessages((current) => [...current, { role: 'user', text: query }]);
    setInputValue('');
    setIsSending(true);

    try {
      const response = await fetch(`${mcpApiUrl}/api/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ query }),
      });

      if (!response.ok) {
        throw new Error(`Chat request failed with status ${response.status}`);
      }

      const data = await response.json();
      setMessages((current) => [...current, { role: 'assistant', text: formatAssistantMessage(data) }]);
    } catch (error) {
      console.error('Failed to send chat message:', error);
      setMessages((current) => [
        ...current,
        {
          role: 'assistant',
          text: 'Unable to reach LangGraph backend. Please verify the core API is running.',
        },
      ]);
    } finally {
      setIsSending(false);
    }
  }

  return (
    <aside className="fixed bottom-4 right-4 z-50 flex h-128 w-88 max-w-[calc(100vw-2rem)] flex-col rounded-2xl border border-slate-700 bg-slate-900/95 shadow-[0_24px_80px_-24px_rgba(0,0,0,0.8)] backdrop-blur">
      <header className="border-b border-slate-800 px-4 py-3">
        <p className="text-xs uppercase tracking-[0.2em] text-slate-400">LangGraph Chat</p>
        <h2 className="mt-1 text-sm font-semibold text-slate-100">Interactive Assistant</h2>
      </header>

      <div className="flex-1 space-y-3 overflow-y-auto px-4 py-3">
        {messages.map((message, idx) => (
          <div
            key={`${message.role}-${idx}`}
            className={`max-w-[90%] whitespace-pre-wrap rounded-xl px-3 py-2 text-sm ${
              message.role === 'user'
                ? 'ml-auto bg-cyan-500/20 text-cyan-100'
                : 'mr-auto bg-slate-800 text-slate-100'
            }`}
          >
            {message.text}
          </div>
        ))}
      </div>

      <form onSubmit={handleSubmit} className="border-t border-slate-800 p-3">
        <label htmlFor="chat-widget-input" className="sr-only">
          Ask Privex assistant
        </label>
        <div className="flex gap-2">
          <input
            id="chat-widget-input"
            type="text"
            value={inputValue}
            onChange={(event) => setInputValue(event.target.value)}
            placeholder="Ask about this threat context..."
            className="flex-1 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none transition focus:border-cyan-400/60"
            disabled={isSending}
          />
          <button
            type="submit"
            disabled={isSending || inputValue.trim().length === 0}
            className="rounded-lg border border-cyan-400/40 bg-cyan-500/20 px-3 py-2 text-sm font-semibold text-cyan-100 transition hover:bg-cyan-500/30 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isSending ? 'Sending...' : 'Send'}
          </button>
        </div>
      </form>
    </aside>
  );
}
