import { clsx } from "clsx";
import type { HTMLAttributes, ReactNode } from "react";

export function Card({
  className,
  children,
  ...rest
}: HTMLAttributes<HTMLDivElement> & { children: ReactNode }) {
  return (
    <div
      className={clsx(
        "rounded-2xl border border-canopy-700/60 bg-canopy-900/70 p-5 shadow-canopy backdrop-blur-sm",
        className
      )}
      {...rest}
    >
      {children}
    </div>
  );
}

export function CardHeader({
  title,
  subtitle,
  action,
}: {
  title: string;
  subtitle?: string;
  action?: ReactNode;
}) {
  return (
    <div className="mb-4 flex items-start justify-between gap-3">
      <div>
        <h3 className="font-display text-base font-semibold text-canopy-50">{title}</h3>
        {subtitle ? <p className="mt-0.5 text-xs text-canopy-300">{subtitle}</p> : null}
      </div>
      {action}
    </div>
  );
}
