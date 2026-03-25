import { Activity, BellRing, LayoutDashboard, ShieldAlert, ShieldCheck } from 'lucide-react';

const navItems = [
  { label: 'Dashboard', icon: LayoutDashboard, active: true },
  { label: 'Threat Feed', icon: ShieldAlert },
  { label: 'Approvals', icon: BellRing },
  { label: 'Protection Logs', icon: Activity },
];

export default function SidebarNav() {
  return (
    <aside className="w-full border-b border-slate-800 bg-slate-900/70 p-4 backdrop-blur lg:min-h-screen lg:w-72 lg:border-b-0 lg:border-r lg:p-6">
      <div className="mb-6 flex items-center gap-3">
        <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 p-2 text-rose-300">
          <ShieldCheck size={18} />
        </div>
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-slate-400">Privex</p>
          <p className="text-sm font-semibold text-slate-100">Security Console</p>
        </div>
      </div>

      <nav className="grid gap-2 sm:grid-cols-2 lg:grid-cols-1">
        {navItems.map((item) => {
          const Icon = item.icon;
          return (
            <button
              key={item.label}
              type="button"
              className={`group flex items-center gap-3 rounded-lg border px-3 py-2 text-left transition ${
                item.active
                  ? 'border-rose-500/50 bg-rose-500/10 text-rose-200'
                  : 'border-slate-800 bg-slate-950/50 text-slate-300 hover:border-slate-600 hover:text-slate-100'
              }`}
            >
              <Icon size={16} className="shrink-0" />
              <span className="text-sm font-medium">{item.label}</span>
            </button>
          );
        })}
      </nav>
    </aside>
  );
}
