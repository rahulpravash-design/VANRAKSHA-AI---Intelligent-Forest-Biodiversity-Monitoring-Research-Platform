import { clsx } from "clsx";
import type { ReactNode } from "react";

export function StatTile({
  label,
  value,
  hint,
  icon,
  className,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  icon?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={clsx(
        "rounded-xl border border-canopy-700/50 bg-canopy-900/60 p-4",
        className
      )}
    >
      <div className="flex items-center justify-between">
        <p className="text-xs font-medium uppercase tracking-wide text-canopy-300">{label}</p>
        {icon ? <span className="text-canopy-400">{icon}</span> : null}
      </div>
      <p className="mt-2 font-display text-2xl font-semibold text-canopy-50">{value}</p>
      {hint ? <p className="mt-1 text-[11px] text-canopy-400">{hint}</p> : null}
    </div>
  );
}
