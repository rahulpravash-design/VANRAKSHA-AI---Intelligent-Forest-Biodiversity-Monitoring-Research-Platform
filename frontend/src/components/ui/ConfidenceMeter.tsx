import { clsx } from "clsx";

/** A confidence bar that visually distinguishes an AI-assisted guess from a
 * confirmed identification — never rendered without the label beside it, so
 * a bar alone can never be mistaken for a determination. */
export function ConfidenceMeter({
  confidence,
  isUncertain,
  label,
}: {
  confidence: number | null;
  isUncertain?: boolean;
  label?: string;
}) {
  if (isUncertain || confidence === null) {
    return (
      <div className="flex items-center gap-2 text-xs text-canopy-400">
        <span className="h-1.5 w-24 rounded-full bg-canopy-700" />
        Uncertain — not identified
      </div>
    );
  }
  const pct = Math.round(confidence * 100);
  const tone = pct >= 75 ? "bg-canopy-400" : pct >= 45 ? "bg-amber-glow" : "bg-alert-high";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-24 overflow-hidden rounded-full bg-canopy-700">
        <div className={clsx("h-full rounded-full", tone)} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs font-medium text-canopy-200">
        {label ?? "AI confidence"} {pct}%
      </span>
    </div>
  );
}
