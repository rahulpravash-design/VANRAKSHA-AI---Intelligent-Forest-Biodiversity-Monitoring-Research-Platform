"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { DemoAccounts } from "@/components/DemoNotice";
import { ForestHeroClient as ForestHero } from "@/components/three/ForestHeroClient";
import { Button } from "@/components/ui/Button";
import { Field, Input, Label } from "@/components/ui/Field";
import { InlineAlert } from "@/components/ui/Alert";
import { ApiError } from "@/lib/api";
import { useAuthStore } from "@/lib/auth-store";

export default function LoginPage() {
  const router = useRouter();
  const login = useAuthStore((state) => state.login);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await login({ email, password });
      router.replace("/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not sign in.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-canopy-950 px-4">
      <ForestHero className="absolute inset-0 h-full w-full opacity-60" density="compact" />
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-canopy-950/60 via-canopy-950/70 to-canopy-950" />

      <div className="relative z-10 w-full max-w-sm rounded-2xl border border-canopy-700/60 bg-canopy-950/80 p-8 shadow-canopy backdrop-blur-md">
        <Link href="/" className="mb-6 flex items-center justify-center gap-2">
          <span className="text-2xl">🌳</span>
          <span className="font-display text-lg font-semibold text-canopy-50">VANRAKSHA</span>
        </Link>
        <h1 className="text-center font-display text-xl font-semibold text-canopy-50">
          Sign in
        </h1>
        <p className="mt-1 text-center text-xs text-canopy-300">
          Biodiversity Intelligence Platform
        </p>

        <form className="mt-6 space-y-4" onSubmit={handleSubmit}>
          {error ? <InlineAlert tone="error">{error}</InlineAlert> : null}
          <Field>
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="researcher@vanraksha.ai"
            />
          </Field>
          <Field>
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="••••••••••"
            />
          </Field>
          <Button type="submit" className="w-full" loading={submitting}>
            Sign in
          </Button>
        </form>

        <DemoAccounts
          onPick={(demoEmail, demoPassword) => {
            setEmail(demoEmail);
            setPassword(demoPassword);
            setError(null);
          }}
        />

        <p className="mt-6 text-center text-xs text-canopy-300">
          Don&apos;t have an account?{" "}
          <Link href="/register" className="font-medium text-amber-glow-soft hover:underline">
            Create account
          </Link>
        </p>
        <p className="mt-4 text-center text-[11px] text-canopy-500">
          Expert and forest-officer accounts are created by an administrator.
        </p>
      </div>
    </div>
  );
}
