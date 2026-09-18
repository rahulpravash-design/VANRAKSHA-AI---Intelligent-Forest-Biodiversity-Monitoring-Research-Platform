"use client";

import { clsx } from "clsx";
import type { HTMLAttributes, InputHTMLAttributes, LabelHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";

export function Field({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return <div className={clsx("space-y-1", className)} {...rest} />;
}

export function Label({ className, ...rest }: LabelHTMLAttributes<HTMLLabelElement>) {
  return (
    <label className={clsx("mb-1 block text-xs font-medium text-canopy-200", className)} {...rest} />
  );
}

const inputClasses =
  "w-full rounded-lg border border-canopy-600 bg-canopy-950/60 px-3 py-2 text-sm text-canopy-50 placeholder:text-canopy-500 focus:border-amber-glow focus:outline-none focus:ring-1 focus:ring-amber-glow disabled:opacity-50";

export function Input({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={clsx(inputClasses, className)} {...rest} />;
}

export function Textarea({ className, ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={clsx(inputClasses, className)} {...rest} />;
}

export function Select({
  className,
  children,
  ...rest
}: SelectHTMLAttributes<HTMLSelectElement> & { children: ReactNode }) {
  return (
    <select className={clsx(inputClasses, className)} {...rest}>
      {children}
    </select>
  );
}

export function FieldError({ children }: { children?: string }) {
  if (!children) return null;
  return <p className="mt-1 text-xs text-alert-critical">{children}</p>;
}
