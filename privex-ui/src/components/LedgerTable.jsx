import { useEffect, useMemo, useState } from 'react';

function formatTimestamp(value) {
  if (!value) return 'Unknown time';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
}

function formatDetected(log) {
  if (Array.isArray(log.detected) && log.detected.length > 0) {
    return log.detected.join(', ');
  }
  if (log.detected_item) {
    return String(log.detected_item);
  }
  return 'N/A';
}

export default function LedgerTable() {
  const [logs, setLogs] = useState([]);
  const [status, setStatus] = useState('loading');

  const logsApiUrl = useMemo(() => import.meta.env.VITE_LOGS_API_URL || 'http://localhost:3000/api/logs', []);

  useEffect(() => {
    let isMounted = true;

    async function fetchLogs() {
      try {
        const response = await fetch(logsApiUrl);
        if (!response.ok) {
          throw new Error(`Failed logs fetch with status ${response.status}`);
        }

        const data = await response.json();
        if (!isMounted) return;

        const normalizedLogs = Array.isArray(data?.logs) ? data.logs : [];
        setLogs(normalizedLogs);
        setStatus('ready');
      } catch (error) {
        console.error('Failed to fetch ledger logs:', error);
        if (isMounted) {
          setStatus('error');
        }
      }
    }

    fetchLogs();

    return () => {
      isMounted = false;
    };
  }, [logsApiUrl]);

  return (
    <section className="mt-12 rounded-2xl border border-slate-800 bg-slate-900/50 p-5 sm:p-6">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-slate-400">Audit History</p>
          <h2 className="mt-1 text-xl font-semibold text-slate-100">Ledger</h2>
        </div>
      </div>

      {status === 'loading' && (
        <p className="text-sm text-slate-400">Loading historical alerts...</p>
      )}

      {status === 'error' && (
        <p className="text-sm text-rose-300">Unable to load ledger data right now.</p>
      )}

      {status === 'ready' && logs.length === 0 && (
        <p className="text-sm text-slate-400">No historical alerts recorded yet.</p>
      )}

      {status === 'ready' && logs.length > 0 && (
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-800 text-left text-sm">
            <thead>
              <tr className="text-xs uppercase tracking-wider text-slate-400">
                <th className="px-3 py-2">Time</th>
                <th className="px-3 py-2">Risk</th>
                <th className="px-3 py-2">App</th>
                <th className="px-3 py-2">Detected</th>
                <th className="px-3 py-2">OCR Context</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/80 text-slate-200">
              {logs.map((log) => (
                <tr key={log.id || `${log.timestamp}-${formatDetected(log)}`}>
                  <td className="px-3 py-2 align-top text-slate-300">{formatTimestamp(log.timestamp)}</td>
                  <td className="px-3 py-2 align-top">{log.risk || 'High'}</td>
                  <td className="max-w-40 truncate px-3 py-2 align-top text-slate-300" title={log.active_app?.title || 'Unknown'}>
                    {log.active_app?.title || 'Unknown'}
                  </td>
                  <td className="px-3 py-2 align-top">{formatDetected(log)}</td>
                  <td className="max-w-xs truncate px-3 py-2 align-top text-slate-300" title={log.ocr_text || ''}>
                    {log.ocr_text || '-'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
