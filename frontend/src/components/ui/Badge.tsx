import { clsx } from "clsx";
import type { ReactNode } from "react";

type Tone = "neutral" | "amber" | "green" | "red" | "blue" | "gray";

const TONE_CLASSES: Record<Tone, string> = {
  neutral: "bg-canopy-700 text-canopy-100",
  amber: "bg-amber-glow/20 text-amber-glow-soft border border-amber-glow/40",
  green: "bg-canopy-500/25 text-canopy-100 border border-canopy-400/40",
  red: "bg-alert-critical/20 text-red-200 border border-alert-critical/40",
  blue: "bg-alert-info/20 text-cyan-100 border border-alert-info/40",
  gray: "bg-white/5 text-canopy-300 border border-white/10",
};

export function Badge({
  tone = "neutral",
  children,
  className,
}: {
  tone?: Tone;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[11px] font-medium",
        TONE_CLASSES[tone],
        className
      )}
    >
      {children}
    </span>
  );
}

const CONSERVATION_TONE: Record<string, Tone> = {
  CR: "red",
  EN: "red",
  VU: "amber",
  NT: "amber",
  LC: "green",
  DD: "gray",
  NE: "gray",
  EX: "gray",
  EW: "gray",
};

const CONSERVATION_LABEL: Record<string, string> = {
  CR: "Critically Endangered",
  EN: "Endangered",
  VU: "Vulnerable",
  NT: "Near Threatened",
  LC: "Least Concern",
  DD: "Data Deficient",
  NE: "Not Evaluated",
  EX: "Extinct",
  EW: "Extinct in the Wild",
};

export function ConservationBadge({ status }: { status: string }) {
  return (
    <Badge tone={CONSERVATION_TONE[status] ?? "gray"} className="uppercase">
      {status} · {CONSERVATION_LABEL[status] ?? status}
    </Badge>
  );
}

const VERIFICATION_TONE: Record<string, Tone> = {
  PENDING: "amber",
  CONFIRMED: "green",
  CORRECTED: "blue",
  REJECTED: "red",
  UNCERTAIN: "gray",
};

export function VerificationBadge({ status }: { status: string }) {
  return (
    <Badge tone={VERIFICATION_TONE[status] ?? "gray"}>
      {status.charAt(0) + status.slice(1).toLowerCase()}
    </Badge>
  );
}

const SEVERITY_TONE: Record<string, Tone> = {
  INFO: "blue",
  LOW: "gray",
  MEDIUM: "amber",
  HIGH: "red",
};

export function SeverityBadge({ severity }: { severity: string }) {
  return <Badge tone={SEVERITY_TONE[severity] ?? "gray"}>{severity}</Badge>;
}
