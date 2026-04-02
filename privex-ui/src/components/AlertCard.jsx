import { Ban, CheckCircle2, Siren } from 'lucide-react';

function formatTimestamp(value) {
  if (!value) return 'Unknown time';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
}

export default function AlertCard({ alert, onApprove, onBlock }) {
  return (
    <article className="rounded-xl border border-rose-500/50 bg-linear-to-br from-slate-900 via-slate-900 to-rose-950/40 p-5 shadow-[0_0_0_1px_rgba(244,63,94,0.15),0_12px_40px_-12px_rgba(244,63,94,0.45)]">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span className="inline-flex items-center gap-2 rounded-full border border-rose-400/50 bg-rose-500/10 px-3 py-1 text-xs font-semibold uppercase tracking-wider text-rose-200">
          <Siren size={14} />
          {alert.risk || 'High'} Risk
        </span>
        <span className="text-xs text-slate-400">{formatTimestamp(alert.timestamp)}</span>
      </div>

      <h2 className="mt-4 text-lg font-semibold leading-tight text-rose-100 sm:text-xl">
        🚨 ACTION REQUIRED: {alert.detectedItem}
      </h2>

      <div className="mt-3 rounded bg-slate-950/50 p-3 text-sm text-slate-300">
        <p><span className="font-semibold text-slate-400">App:</span> {alert.activeApp}</p>
        <p className="mt-1 truncate" title={alert.ocrText}>
          <span className="font-semibold text-slate-400">OCR:</span> {alert.ocrText}
        </p>
      </div>

      <div className="mt-5 flex flex-col gap-3 sm:flex-row">
        <button
          type="button"
          onClick={onApprove}
          className="inline-flex items-center justify-center gap-2 rounded-lg border border-emerald-400/40 bg-emerald-500/10 px-4 py-2 text-sm font-semibold text-emerald-100 transition hover:bg-emerald-500/20"
        >
          <CheckCircle2 size={16} />
          Approve (Ignore)
        </button>
        <button
          type="button"
          onClick={onBlock}
          className="inline-flex items-center justify-center gap-2 rounded-lg border border-rose-400/50 bg-rose-500/20 px-4 py-2 text-sm font-semibold text-rose-100 transition hover:bg-rose-500/30"
        >
          <Ban size={16} />
          Block (Redact)
        </button>
      </div>
    </article>
  );
}
