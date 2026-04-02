import { useEffect, useMemo, useState } from 'react';

import AlertCard from './components/AlertCard';
import ChatWidget from './components/ChatWidget';
import LedgerTable from './components/LedgerTable';
import SidebarNav from './components/SidebarNav';

function App() {
  const [alerts, setAlerts] = useState([]);
  const [socketState, setSocketState] = useState('connecting');
  const coreApiUrl = import.meta.env.VITE_CORE_API_URL || 'http://localhost:8000';

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

  const statusPillClass = useMemo(() => {
    if (socketState === 'online') return 'border-emerald-400/40 text-emerald-300 bg-emerald-400/10';
    if (socketState === 'connecting') return 'border-amber-400/40 text-amber-200 bg-amber-400/10';
    return 'border-rose-500/50 text-rose-200 bg-rose-500/10';
  }, [socketState]);

  async function handleResolveAlert(alertId, decision) {
    const targetAlert = alerts.find(a => a.id === alertId); // Find the specific alert
    const payload = {
      alert_id: alertId,
      decision,
      timestamp: Date.now() / 1000,
      ocr_text: targetAlert?.ocrText || "" // Send the text back to Python!
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

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <div className="mx-auto flex max-w-360 flex-col lg:flex-row">
        <SidebarNav />

        <main className="flex-1 p-6 sm:p-8 lg:p-10">
          <header className="mb-8 flex flex-col gap-4 border-b border-slate-800 pb-6 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-xs uppercase tracking-[0.28em] text-slate-400">Realtime Monitoring</p>
              <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-100 sm:text-4xl">
                Active Threats Dashboard
              </h1>
            </div>

            <span className={`inline-flex items-center rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-wider ${statusPillClass}`}>
              Socket: {socketState}
            </span>
          </header>

          <section className="space-y-4">
            {alerts.length === 0 && (
              <div className="rounded-xl border border-dashed border-slate-700 bg-slate-900/50 p-8 text-center">
                <p className="text-lg font-medium text-slate-200">No active threats detected yet</p>
                <p className="mt-2 text-sm text-slate-400">
                  Incoming WebSocket alerts from {import.meta.env.VITE_WS_URL || 'ws://localhost:3000'} will appear here in real time.
                </p>
              </div>
            )}

            {alerts.map((alert) => (
              <AlertCard
                key={alert.id}
                alert={alert}
                onApprove={() => handleResolveAlert(alert.id, 'approved')}
                onBlock={() => handleResolveAlert(alert.id, 'blocked')}
              />
            ))}
          </section>

          <LedgerTable />
        </main>
      </div>

      <ChatWidget />
    </div>
  );
}

export default App;