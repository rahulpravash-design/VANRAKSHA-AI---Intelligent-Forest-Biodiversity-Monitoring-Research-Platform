"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { ForestHeroClient as ForestHero } from "@/components/three/ForestHeroClient";
import { InlineAlert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Field, Input, Label, Select } from "@/components/ui/Field";
import { ApiError } from "@/lib/api";
import { useAuthStore } from "@/lib/auth-store";

export default function RegisterPage() {
  const router = useRouter();
  const register = useAuthStore((state) => state.register);
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [organization, setOrganization] = useState("");
  const [role, setRole] = useState<"RESEARCHER" | "VIEWER">("RESEARCHER");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    setFieldErrors({});
    if (password !== confirm) {
      setFieldErrors({ password_confirm: "Passwords do not match." });
      setSubmitting(false);
      return;
    }
    try {
      await register({
        full_name: fullName,
        email,
        password,
        organization: organization || undefined,
        role,
      });
      router.replace("/dashboard");
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
        setFieldErrors(err.fields ?? {});
      } else {
        setError("Could not create the account.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-canopy-950 px-4 py-10">
      <ForestHero className="absolute inset-0 h-full w-full opacity-60" density="compact" />
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-canopy-950/60 via-canopy-950/70 to-canopy-950" />

      <div className="relative z-10 w-full max-w-md rounded-2xl border border-canopy-700/60 bg-canopy-950/80 p-8 shadow-canopy backdrop-blur-md">
        <Link href="/" className="mb-6 flex items-center justify-center gap-2">
          <span className="text-2xl">🌳</span>
          <span className="font-display text-lg font-semibold text-canopy-50">VANRAKSHA</span>
        </Link>
        <h1 className="text-center font-display text-xl font-semibold text-canopy-50">
          Create your account
        </h1>
        <p className="mt-1 text-center text-xs text-canopy-300">
          Researcher and viewer accounts self-register. Expert and forest-officer
          accounts are created by an administrator.
        </p>

        <form className="mt-6 space-y-4" onSubmit={handleSubmit}>
          {error ? <InlineAlert tone="error">{error}</InlineAlert> : null}
          <Field>
            <Label htmlFor="full_name">Full name</Label>
            <Input
              id="full_name"
              required
              value={fullName}
              onChange={(event) => setFullName(event.target.value)}
            />
          </Field>
          <Field>
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
            {fieldErrors.email ? (
              <p className="mt-1 text-xs text-alert-critical">{fieldErrors.email}</p>
            ) : null}
          </Field>
          <Field>
            <Label htmlFor="organization">Organization (optional)</Label>
            <Input
              id="organization"
              value={organization}
              onChange={(event) => setOrganization(event.target.value)}
            />
          </Field>
          <Field>
            <Label htmlFor="role">Account type</Label>
            <Select id="role" value={role} onChange={(event) => setRole(event.target.value as typeof role)}>
              <option value="RESEARCHER">Researcher — records observations</option>
              <option value="VIEWER">Viewer — read-only access</option>
            </Select>
          </Field>
          <Field>
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              type="password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
            {fieldErrors.password ? (
              <p className="mt-1 text-xs text-alert-critical">{fieldErrors.password}</p>
            ) : null}
          </Field>
          <Field>
            <Label htmlFor="confirm">Confirm password</Label>
            <Input
              id="confirm"
              type="password"
              required
              value={confirm}
              onChange={(event) => setConfirm(event.target.value)}
            />
            {fieldErrors.password_confirm ? (
              <p className="mt-1 text-xs text-alert-critical">{fieldErrors.password_confirm}</p>
            ) : null}
          </Field>
          <Button type="submit" className="w-full" loading={submitting}>
            Create account
          </Button>
        </form>

        <p className="mt-6 text-center text-xs text-canopy-300">
          Already have an account?{" "}
          <Link href="/login" className="font-medium text-amber-glow-soft hover:underline">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
