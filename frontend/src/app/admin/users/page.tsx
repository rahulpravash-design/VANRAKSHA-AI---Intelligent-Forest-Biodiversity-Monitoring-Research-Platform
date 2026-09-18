"use client";

import { useState } from "react";

import { AppShell } from "@/components/layout/AppShell";
import { RequireAuth, RequireCapability } from "@/components/layout/RequireAuth";
import { InlineAlert } from "@/components/ui/Alert";
import { AsyncBoundary } from "@/components/ui/AsyncBoundary";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { Field, Input, Select } from "@/components/ui/Field";
import { useAsync } from "@/hooks/useAsync";
import { ApiError } from "@/lib/api";
import { usersApi } from "@/lib/endpoints";
import { formatDate } from "@/lib/format";
import type { UserRole } from "@/lib/types";

const ROLE_TONE: Record<UserRole, "amber" | "green" | "blue" | "neutral" | "gray"> = {
  ADMIN: "amber",
  RESEARCHER: "green",
  FOREST_OFFICER: "blue",
  EXPERT: "green",
  VIEWER: "gray",
};

function CreateUserForm({ onCreated }: { onCreated: () => void }) {
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<UserRole>("EXPERT");
  const [expertise, setExpertise] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setSubmitting(true);
    setError(null);
    try {
      await usersApi.create({
        full_name: fullName,
        email,
        password,
        role,
        expertise: expertise || undefined,
      });
      setFullName("");
      setEmail("");
      setPassword("");
      setExpertise("");
      onCreated();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create the account.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card>
      <CardHeader title="Create an account" subtitle="Any role, including expert and forest officer" />
      {error ? <InlineAlert tone="error">{error}</InlineAlert> : null}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field>
          <Input placeholder="Full name" value={fullName} onChange={(event) => setFullName(event.target.value)} />
        </Field>
        <Field>
          <Input placeholder="Email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} />
        </Field>
        <Field>
          <Select value={role} onChange={(event) => setRole(event.target.value as UserRole)}>
            <option value="EXPERT">Expert</option>
            <option value="FOREST_OFFICER">Forest Officer</option>
            <option value="RESEARCHER">Researcher</option>
            <option value="VIEWER">Viewer</option>
            <option value="ADMIN">Administrator</option>
          </Select>
        </Field>
        <Field>
          <Input placeholder="Expertise (optional)" value={expertise} onChange={(event) => setExpertise(event.target.value)} />
        </Field>
        <Field className="sm:col-span-2">
          <Input placeholder="Temporary password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
        </Field>
      </div>
      <Button className="mt-3" onClick={submit} loading={submitting} disabled={!fullName || !email || !password}>
        Create account
      </Button>
    </Card>
  );
}

function UsersContent() {
  const users = useAsync(() => usersApi.list({ limit: 100 }), []);

  async function toggleActive(id: number, isActive: boolean) {
    if (isActive) {
      await usersApi.deactivate(id);
    } else {
      await usersApi.update(id, { is_active: true });
    }
    users.reload();
  }

  return (
    <AppShell title="User administration">
      <div className="space-y-6">
        <CreateUserForm onCreated={() => users.reload()} />

        <Card>
          <CardHeader title="All accounts" />
          <AsyncBoundary loading={users.loading} error={users.error} data={users.data?.items ?? null}>
            {(items) => (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-canopy-800 text-left text-xs text-canopy-400">
                    <th className="pb-2">Name</th>
                    <th className="pb-2">Email</th>
                    <th className="pb-2">Role</th>
                    <th className="pb-2">Joined</th>
                    <th className="pb-2">Status</th>
                    <th className="pb-2" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-canopy-800">
                  {items.map((user) => (
                    <tr key={user.id}>
                      <td className="py-2 text-canopy-100">{user.full_name}</td>
                      <td className="py-2 text-canopy-300">{user.email}</td>
                      <td className="py-2">
                        <Badge tone={ROLE_TONE[user.role]}>{user.role}</Badge>
                      </td>
                      <td className="py-2 text-canopy-400">{formatDate(user.created_at)}</td>
                      <td className="py-2">
                        <Badge tone={user.is_active ? "green" : "gray"}>
                          {user.is_active ? "Active" : "Deactivated"}
                        </Badge>
                      </td>
                      <td className="py-2 text-right">
                        <button
                          type="button"
                          onClick={() => toggleActive(user.id, user.is_active)}
                          className="text-xs font-medium text-amber-glow-soft hover:underline"
                        >
                          {user.is_active ? "Deactivate" : "Reactivate"}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </AsyncBoundary>
        </Card>
      </div>
    </AppShell>
  );
}

export default function UsersPage() {
  return (
    <RequireAuth>
      <RequireCapability capability="can_manage_users">
        <UsersContent />
      </RequireCapability>
    </RequireAuth>
  );
}
