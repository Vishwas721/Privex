import { useEffect, useRef, useState, useMemo } from 'react';
import {
  AlertTriangle,
  Bot,
  Circle,
  Link2,
  MemoryStick,
  SendHorizontal,
  Shield,
  User,
  Monitor,
  MessageSquare,
} from 'lucide-react';

import AlertCard from './components/AlertCard';
import LedgerTable from './components/LedgerTable';

function statusDot(colorClass) {
  return <Circle className={`h-2.5 w-2.5 fill-current ${colorClass}`} />;
}

function createAssistantResponse(userText) {
  return {
    id: `m-${Date.now()}`,
    role: 'assistant',
    text: `Stubbed response for: "${userText}". Wire sendMessage to your backend endpoint for live Privex intelligence.`,
    sources: [{ app: 'Local Memory Agent', time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) }],
  };
}

function App() {
  const [activeView, setActiveView] = useState('dashboard');
  const [alerts, setAlerts] = useState([]);
  const [socketState, setSocketState] = useState('connecting');
  const [messages, setMessages] = useState([
    {
      id: 'm-start',
      role: 'assistant',
      text: 'My memory banks and vision sensors are active. What would you like to know about your recent activity?',
    },
  ]);
  const [input, setInput] = useState('');
  const [isSending, setIsSending] = useState(false);
  const chatBottomRef = useRef(null);
  const coreApiUrl = import.meta.env.VITE_CORE_API_URL || 'http://localhost:8000';

  // WebSocket alerts management
  useEffect(() => {
    const wsUrl = import.meta.env.VITE_WS_URL || 'ws://localhost:3000';
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      setSocketState('online');
    };

    ws.onclose = () => {
      setSocketState('offline');
    };

    ws.onerror = () => {
      setSocketState('error');
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        if (!data.id) {
          console.error('CRITICAL: Received untracked alert without an ID. Dropping payload to maintain audit integrity.');
          return;
        }

        setAlerts((currentAlerts) => {
          const normalizedAlert = {
            id: data.id,
            risk: data.risk ?? 'High',
            detectedItem:
              data.detected_item ??
              (Array.isArray(data.detected) ? data.detected.join(', ') : undefined) ??
              'Unknown Threat',
            timestamp: data.timestamp ?? new Date().toISOString(),
            ocrText: data.ocr_text || 'No text detected',
            activeApp: data.active_app?.title || 'Unknown Application',
            raw: data,
          };

          return [normalizedAlert, ...currentAlerts];
        });
      } catch (err) {
        console.error('Failed to parse WebSocket alert payload:', err);
      }
    };

    return () => {
      ws.close();
    };
  }, []);

  // Chat auto-scroll
  useEffect(() => {
    chatBottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const statusPillClass = useMemo(() => {
    if (socketState === 'online') return 'border-emerald-400/40 text-emerald-300 bg-emerald-400/10';
    if (socketState === 'connecting') return 'border-amber-400/40 text-amber-200 bg-amber-400/10';
    return 'border-rose-500/50 text-rose-200 bg-rose-500/10';
  }, [socketState]);

  async function handleResolveAlert(alertId, decision) {
    const targetAlert = alerts.find(a => a.id === alertId);
    const payload = {
      alert_id: alertId,
      decision,
      timestamp: Date.now() / 1000,
      ocr_text: targetAlert?.ocrText || ""
    };

    try {
      const response = await fetch(`${coreApiUrl}/api/resolve-alert`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        throw new Error(`Resolve alert request failed with status ${response.status}`);
      }

      setAlerts((currentAlerts) => currentAlerts.filter((alert) => alert.id !== alertId));
    } catch (error) {
      console.error('Failed to resolve alert. Core API may be unavailable:', error);
    }
  }

  async function sendMessage(text) {
    try {
      const response = await fetch(`${coreApiUrl}/api/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ query: text }),
      });

      if (!response.ok) throw new Error('Network response was not ok');
      const data = await response.json();

      return {
        id: `m-${Date.now()}`,
        role: 'assistant',
        // The backend LangGraph returns the answer inside 'response'
        text: data.response || 'I am having trouble connecting to my memory bank.',
        sources: data.sources || [],
      };
    } catch (error) {
      console.error('Failed to send message:', error);
      return {
        id: `m-${Date.now()}`,
        role: 'assistant',
        text: 'Error: Could not reach the Privex Core API.',
      };
    }
  }

  async function handleSend(event) {
    event.preventDefault();
    const trimmed = input.trim();

    if (!trimmed || isSending) {
      return;
    }

    const userMessage = {
      id: `m-${Date.now()}-user`,
      role: 'user',
      text: trimmed,
    };

    setMessages((current) => [...current, userMessage]);
    setInput('');
    setIsSending(true);

    try {
      const aiMessage = await sendMessage(trimmed);
      setMessages((current) => [...current, aiMessage]);
    } finally {
      setIsSending(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <div className="flex h-screen w-full flex-col md:flex-row">
        <aside className="w-full border-b border-slate-800 bg-slate-950/80 p-6 backdrop-blur md:w-64 md:border-r md:border-b-0 md:flex md:flex-col">
          <div className="mb-8 flex items-center gap-2 text-lg font-semibold tracking-[0.15em] text-indigo-300">
            <Shield className="h-5 w-5 text-indigo-400 drop-shadow-[0_0_12px_rgba(129,140,248,0.7)]" />
            <span className="drop-shadow-[0_0_10px_rgba(52,211,153,0.35)]">PRIVEX</span>
          </div>

          <section className="mb-8 rounded-xl border border-slate-800 bg-slate-900/60 p-4 shadow-[0_0_30px_rgba(2,6,23,0.55)]">
            <h2 className="mb-4 text-xs uppercase tracking-[0.18em] text-slate-400">System Status</h2>

            <div className="space-y-3 text-sm">
              <div className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900/80 px-3 py-2">
                <span className="flex items-center gap-2 text-slate-200">
                  <Shield className="h-4 w-4 text-emerald-400" />
                  Visual Firewall
                </span>
                <span className="flex items-center gap-1.5 text-emerald-300">
                  {statusDot('text-emerald-400')}
                  Active
                </span>
              </div>

              <div className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900/80 px-3 py-2">
                <span className="flex items-center gap-2 text-slate-200">
                  <MemoryStick className="h-4 w-4 text-indigo-400" />
                  Memory Agent
                </span>
                <span className="flex items-center gap-1.5 text-indigo-300">
                  {statusDot('text-indigo-400')}
                  Active
                </span>
              </div>
            </div>
          </section>

          <section className="mb-8 rounded-xl border border-slate-800 bg-slate-900/60 p-4 shadow-[0_0_30px_rgba(2,6,23,0.55)]">
            <h2 className="mb-4 text-xs uppercase tracking-[0.18em] text-slate-400">Views</h2>

            <div className="space-y-2">
              <button
                onClick={() => setActiveView('dashboard')}
                className={`w-full rounded-lg border px-3 py-2 text-sm font-medium transition ${
                  activeView === 'dashboard'
                    ? 'border-emerald-400/50 bg-emerald-500/15 text-emerald-200'
                    : 'border-slate-700 bg-slate-900/60 text-slate-300 hover:bg-slate-800/80'
                }`}
              >
                <div className="flex items-center justify-center gap-2">
                  <Monitor className="h-4 w-4" />
                  Security Dashboard
                </div>
              </button>

              <button
                onClick={() => setActiveView('copilot')}
                className={`w-full rounded-lg border px-3 py-2 text-sm font-medium transition ${
                  activeView === 'copilot'
                    ? 'border-indigo-400/50 bg-indigo-500/15 text-indigo-200'
                    : 'border-slate-700 bg-slate-900/60 text-slate-300 hover:bg-slate-800/80'
                }`}
              >
                <div className="flex items-center justify-center gap-2">
                  <MessageSquare className="h-4 w-4" />
                  Privex Copilot
                </div>
              </button>
            </div>
          </section>

          <section>
            <h2 className="mb-3 text-xs uppercase tracking-[0.18em] text-slate-400">Recent Alerts</h2>
            <div className="space-y-2">
              {alerts.length === 0 && (
                 <p className="text-xs text-slate-500 italic">No recent alerts</p>
              )}
              {alerts.slice(0, 5).map((alert) => (
                <article
                  key={`sidebar-${alert.id}`}
                  className="rounded-xl border border-slate-800 bg-slate-900/70 p-3 backdrop-blur"
                >
                  <div className="flex items-start gap-2">
                    <AlertTriangle className="mt-0.5 h-4 w-4 text-orange-400" />
                    <p className="text-xs leading-relaxed text-slate-300">
                      {alert.detectedItem} - {alert.activeApp}
                    </p>
                  </div>
                </article>
              ))}
            </div>
          </section>
        </aside>

        <main className="flex min-h-0 flex-1 flex-col bg-linear-to-b from-slate-950 via-slate-950 to-slate-900/60">
          {/* DASHBOARD VIEW */}
          {activeView === 'dashboard' && (
            <>
              <header className="border-b border-slate-800/80 px-6 py-4">
                <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Realtime Monitoring</p>
                <div className="mt-1 flex items-center justify-between">
                  <h1 className="text-xl font-semibold text-slate-100">Security Dashboard</h1>
                  <span className={`inline-flex items-center rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-wider ${statusPillClass}`}>
                    Socket: {socketState}
                  </span>
                </div>
              </header>

              <section className="min-h-0 flex-1 overflow-y-auto px-4 py-6 sm:px-6">
                <div className="mx-auto flex w-full max-w-4xl flex-col gap-6">
                  {/* Pending Approvals */}
                  <div>
                    <div className="mb-4">
                      <p className="text-xs uppercase tracking-[0.24em] text-slate-400">Pending Queue</p>
                      <h2 className="mt-1 text-xl font-semibold text-slate-100">Approvals Required</h2>
                    </div>

                    {alerts.length === 0 && (
                      <div className="rounded-xl border border-dashed border-slate-700 bg-slate-900/50 p-8 text-center">
                        <p className="text-lg font-medium text-slate-200">No active threats detected</p>
                        <p className="mt-2 text-sm text-slate-400">
                          Incoming WebSocket alerts will appear here for your approval.
                        </p>
                      </div>
                    )}

                    {alerts.length > 0 && (
                      <div className="space-y-4">
                        {alerts.map((alert) => (
                          <AlertCard
                            key={alert.id}
                            alert={alert}
                            onApprove={() => handleResolveAlert(alert.id, 'approved')}
                            onBlock={() => handleResolveAlert(alert.id, 'blocked')}
                          />
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Ledger Table */}
                  <LedgerTable />
                </div>
              </section>
            </>
          )}

          {/* COPILOT VIEW */}
          {activeView === 'copilot' && (
            <>
              <header className="border-b border-slate-800/80 px-6 py-4">
                <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Privex Copilot</p>
                <h1 className="mt-1 text-xl font-semibold text-slate-100">Local Privacy Intelligence</h1>
              </header>

              <section className="min-h-0 flex-1 overflow-y-auto px-4 py-6 sm:px-6">
                <div className="mx-auto flex w-full max-w-4xl flex-col gap-5">
                  {messages.map((message) => {
                    const isUser = message.role === 'user';

                    return (
                      <div key={message.id} className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
                        <div className={`max-w-[85%] ${isUser ? 'items-end' : 'items-start'} flex flex-col gap-2`}>
                          <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-slate-400">
                            {isUser ? (
                              <>
                                <span>You</span>
                                <User className="h-3.5 w-3.5" />
                              </>
                            ) : (
                              <>
                                <Bot className="h-3.5 w-3.5 text-indigo-300" />
                                <span>Privex AI</span>
                              </>
                            )}
                          </div>

                          <div
                            className={
                              isUser
                                ? 'rounded-2xl rounded-br-sm border border-indigo-300/20 bg-linear-to-r from-indigo-600/35 to-indigo-500/20 px-4 py-3 text-sm leading-relaxed text-indigo-50 shadow-[0_6px_24px_rgba(79,70,229,0.28)]'
                                : 'px-1 py-1 text-sm leading-relaxed text-slate-100'
                            }
                          >
                            {message.text}
                          </div>

                          {!isUser && Array.isArray(message.sources) && message.sources.length > 0 && (
                            <div className="mt-1 flex flex-wrap gap-2">
                              {message.sources.map((source, index) => (
                                <button
                                  type="button"
                                  key={`${message.id}-source-${source.app}-${index}`}
                                  onClick={() => window.alert(`Source: ${source.app} at ${source.time}`)}
                                  className="inline-flex items-center gap-1.5 rounded-full border border-slate-700 bg-slate-800/50 px-3 py-1 text-xs text-slate-300 transition hover:border-indigo-400/50 hover:text-indigo-200"
                                >
                                  <Link2 className="h-3 w-3" />
                                  Source: {source.app}
                                </button>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                  <div ref={chatBottomRef} />
                </div>
              </section>

              <footer className="sticky bottom-0 border-t border-slate-800/90 bg-slate-950/80 px-4 py-4 backdrop-blur sm:px-6">
                <form onSubmit={handleSend} className="mx-auto flex w-full max-w-4xl items-center gap-3 rounded-2xl border border-slate-800 bg-slate-900/90 p-2 shadow-[0_12px_40px_rgba(2,6,23,0.65)]">
                  <input
                    type="text"
                    value={input}
                    onChange={(event) => setInput(event.target.value)}
                    placeholder="Ask Privex about recent redactions, app activity, or memory traces..."
                    className="flex-1 bg-transparent px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 outline-none"
                  />

                  <button
                    type="submit"
                    disabled={!input.trim() || isSending}
                    className={`inline-flex h-10 w-10 items-center justify-center rounded-xl border transition ${
                      input.trim() && !isSending
                        ? 'border-indigo-400/50 bg-indigo-500/20 text-indigo-200 shadow-[0_0_20px_rgba(99,102,241,0.45)] hover:bg-indigo-500/30'
                        : 'border-slate-700 bg-slate-800 text-slate-500'
                    }`}
                    aria-label="Send message"
                  >
                    <SendHorizontal className="h-4 w-4" />
                  </button>
                </form>
              </footer>
            </>
          )}
        </main>
      </div>
    </div>
  );
}

export default App;