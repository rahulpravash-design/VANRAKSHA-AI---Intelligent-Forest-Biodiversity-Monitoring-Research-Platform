"use client";

import { useState, type FormEvent } from "react";

import { AppShell } from "@/components/layout/AppShell";
import { RequireAuth } from "@/components/layout/RequireAuth";
import { InlineAlert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { Field, Input, Label } from "@/components/ui/Field";
import { ApiError } from "@/lib/api";
import { authApi } from "@/lib/endpoints";
import { useAuthStore } from "@/lib/auth-store";

function ProfileContent() {
  const user = useAuthStore((state) => state.user);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<{ tone: "info" | "error"; text: string } | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setMessage(null);
    try {
      await authApi.changePassword(currentPassword, newPassword);
      setCurrentPassword("");
      setNewPassword("");
      setMessage({ tone: "info", text: "Password updated." });
    } catch (err) {
      setMessage({ tone: "error", text: err instanceof ApiError ? err.message : "Could not update password." });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AppShell title="Profile">
      <div className="mx-auto max-w-lg space-y-6">
        <Card>
          <CardHeader title="Your account" />
          <dl className="space-y-2 text-sm">
            <div className="flex justify-between"><dt className="text-canopy-400">Name</dt><dd>{user?.full_name}</dd></div>
            <div className="flex justify-between"><dt className="text-canopy-400">Email</dt><dd>{user?.email}</dd></div>
            <div className="flex justify-between"><dt className="text-canopy-400">Role</dt><dd>{user?.role}</dd></div>
            <div className="flex justify-between"><dt className="text-canopy-400">Organization</dt><dd>{user?.organization ?? "—"}</dd></div>
          </dl>
        </Card>

        <Card>
          <CardHeader title="Change password" />
          <form className="space-y-3" onSubmit={handleSubmit}>
            {message ? <InlineAlert tone={message.tone}>{message.text}</InlineAlert> : null}
            <Field>
              <Label htmlFor="current">Current password</Label>
              <Input id="current" type="password" required value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} />
            </Field>
            <Field>
              <Label htmlFor="new">New password</Label>
              <Input id="new" type="password" required value={newPassword} onChange={(event) => setNewPassword(event.target.value)} />
            </Field>
            <Button type="submit" loading={submitting}>
              Update password
            </Button>
          </form>
        </Card>
      </div>
    </AppShell>
  );
}

export default function ProfilePage() {
  return (
    <RequireAuth>
      <ProfileContent />
    </RequireAuth>
  );
}
