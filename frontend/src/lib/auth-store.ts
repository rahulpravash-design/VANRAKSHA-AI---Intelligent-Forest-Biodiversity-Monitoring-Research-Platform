"use client";

/**
 * Global auth state (Zustand — no provider tree needed, and it survives
 * client-side navigation without a re-fetch on every route change).
 *
 * The store starts in a `status: "loading"` state and resolves to either
 * `"authenticated"` or `"anonymous"` once `bootstrap()` has checked
 * localStorage and, if a token is present, confirmed it against
 * `GET /auth/me`. Route guards (`RequireAuth`, `RequireRole`) key off this
 * status rather than off "is `user` null" so a page never briefly renders
 * its signed-out state before the token check has even run.
 */

import { create } from "zustand";

import { ApiError } from "./api";
import { readStoredTokens, writeStoredTokens } from "./api";
import { authApi } from "./endpoints";
import type { LoginRequestBody, RegisterRequestBody, UserCapabilities, UserPublic } from "./types";

type AuthStatus = "loading" | "authenticated" | "anonymous";

interface AuthState {
  status: AuthStatus;
  user: UserPublic | null;
  capabilities: UserCapabilities | null;
  error: string | null;
  bootstrap: () => Promise<void>;
  login: (body: LoginRequestBody) => Promise<void>;
  register: (body: RegisterRequestBody) => Promise<void>;
  logout: () => Promise<void>;
  refreshProfile: () => Promise<void>;
  clearError: () => void;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  status: "loading",
  user: null,
  capabilities: null,
  error: null,

  bootstrap: async () => {
    const tokens = readStoredTokens();
    if (!tokens) {
      set({ status: "anonymous" });
      return;
    }
    try {
      const me = await authApi.me();
      set({ status: "authenticated", user: me.user, capabilities: me.capabilities });
    } catch {
      writeStoredTokens(null);
      set({ status: "anonymous", user: null, capabilities: null });
    }
  },

  login: async (body) => {
    set({ error: null });
    try {
      const tokens = await authApi.login(body);
      writeStoredTokens({
        access_token: tokens.access_token,
        refresh_token: tokens.refresh_token,
        expires_at: tokens.expires_at,
      });
      const me = await authApi.me();
      set({ status: "authenticated", user: me.user, capabilities: me.capabilities });
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Could not sign in.";
      set({ error: message });
      throw err;
    }
  },

  register: async (body) => {
    set({ error: null });
    try {
      await authApi.register(body);
      await get().login({ email: body.email, password: body.password });
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Could not register.";
      set({ error: message });
      throw err;
    }
  },

  logout: async () => {
    const tokens = readStoredTokens();
    writeStoredTokens(null);
    set({ status: "anonymous", user: null, capabilities: null });
    try {
      await authApi.logout(tokens?.refresh_token);
    } catch {
      /* best effort — client-side state is already cleared */
    }
  },

  refreshProfile: async () => {
    try {
      const me = await authApi.me();
      set({ user: me.user, capabilities: me.capabilities });
    } catch {
      /* leave current state */
    }
  },

  clearError: () => set({ error: null }),
}));
