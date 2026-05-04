function extractField(message, label) {
  const regex = new RegExp(`\\*\\*${label}:\\*\\*\\s*(.+)`, 'i');
  const match = message.match(regex);
  return match ? match[1].trim() : 'Unavailable';
}

function ThreatOverlay({ isActive, message, onDismiss }) {
  if (!isActive) return null;

  const source = message || '';
  const threatLevel = extractField(source, 'Threat Level');
  const triggers = extractField(source, 'Triggers Found');
  const analysis = extractField(source, 'Analysis');

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-red-900/80 px-4">
      <div className="w-full max-w-2xl rounded-xl border-2 border-red-500 bg-gray-900 p-8 text-slate-100 shadow-[0_20px_80px_rgba(127,29,29,0.55)]">
        <h2 className="text-center text-3xl font-extrabold tracking-wide text-red-300">THREAT ALERT</h2>
        <p className="mt-2 text-center text-sm text-red-200">Potential phishing or social engineering content was detected on screen.</p>

        <div className="mt-8 space-y-4 rounded-lg border border-red-700/50 bg-red-950/30 p-5">
          <div>
            <p className="text-xs uppercase tracking-[0.18em] text-red-300">Threat Level</p>
            <p className="mt-1 text-xl font-bold text-red-100">{threatLevel}</p>
          </div>

          <div>
            <p className="text-xs uppercase tracking-[0.18em] text-red-300">Triggers</p>
            <p className="mt-1 text-base text-red-100">{triggers}</p>
          </div>

          <div>
            <p className="text-xs uppercase tracking-[0.18em] text-red-300">Analysis</p>
            <p className="mt-1 text-base text-red-100">{analysis}</p>
          </div>
        </div>

        <div className="mt-8 flex justify-center">
          <button
            type="button"
            onClick={onDismiss}
            className="rounded bg-red-600 px-4 py-2 font-bold text-white transition hover:bg-red-500"
          >
            I Understand, Dismiss
          </button>
        </div>
      </div>
    </div>
  );
}

export default ThreatOverlay;
