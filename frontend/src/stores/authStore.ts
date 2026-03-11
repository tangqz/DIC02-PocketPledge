/* ────────────────────────────────────────────────
 *  Auth Store  –  JWT token, user info, login/register
 *
 *  Persists token in localStorage so refreshes keep
 *  the user logged in. All HTTP calls to the backend
 *  go through the helpers here to attach Bearer token.
 * ──────────────────────────────────────────────── */
import { create } from "zustand";

const TOKEN_KEY = "sb_token";
const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:12393";

export interface AuthUser {
  user_id: number;
  username: string;
  email?: string | null;
  balance?: number;
}

interface AuthState {
  token: string | null;
  user: AuthUser | null;
  loading: boolean;
  error: string | null;

  /** Attempt login. Stores token on success. */
  login: (username: string, password: string) => Promise<boolean>;
  /** Attempt registration. Stores token on success. */
  register: (username: string, password: string, email?: string) => Promise<boolean>;
  /** Fetch /api/auth/me to verify token and load user info. */
  fetchMe: () => Promise<boolean>;
  /** Clear auth state and localStorage. */
  logout: () => void;
  /** Restore token from localStorage on app init. */
  hydrate: () => void;
}

async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const token = localStorage.getItem(TOKEN_KEY);
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string> ?? {}),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  return fetch(`${API_BASE}${path}`, { ...init, headers });
}

export const useAuthStore = create<AuthState>((set, get) => ({
  token: null,
  user: null,
  loading: false,
  error: null,

  login: async (username, password) => {
    set({ loading: true, error: null });
    try {
      const res = await apiFetch("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({ detail: "Login failed" }));
        set({ loading: false, error: data.detail ?? "Login failed" });
        return false;
      }
      const data = await res.json();
      localStorage.setItem(TOKEN_KEY, data.access_token);
      set({
        token: data.access_token,
        user: { user_id: data.user_id, username: data.username },
        loading: false,
      });
      return true;
    } catch (err) {
      set({ loading: false, error: "Network error" });
      return false;
    }
  },

  register: async (username, password, email) => {
    set({ loading: true, error: null });
    try {
      const body: Record<string, string> = { username, password };
      if (email) body.email = email;
      const res = await apiFetch("/api/auth/register", {
        method: "POST",
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({ detail: "Registration failed" }));
        set({ loading: false, error: data.detail ?? "Registration failed" });
        return false;
      }
      const data = await res.json();
      localStorage.setItem(TOKEN_KEY, data.access_token);
      set({
        token: data.access_token,
        user: { user_id: data.user_id, username: data.username },
        loading: false,
      });
      return true;
    } catch (err) {
      set({ loading: false, error: "Network error" });
      return false;
    }
  },

  fetchMe: async () => {
    const token = get().token ?? localStorage.getItem(TOKEN_KEY);
    if (!token) return false;
    try {
      const res = await apiFetch("/api/auth/me");
      if (!res.ok) {
        localStorage.removeItem(TOKEN_KEY);
        set({ token: null, user: null });
        return false;
      }
      const data = await res.json();
      set({
        token,
        user: {
          user_id: data.user_id,
          username: data.username,
          email: data.email,
          balance: data.balance,
        },
      });
      return true;
    } catch {
      return false;
    }
  },

  logout: () => {
    localStorage.removeItem(TOKEN_KEY);
    set({ token: null, user: null, error: null });
  },

  hydrate: () => {
    const token = localStorage.getItem(TOKEN_KEY);
    if (token) {
      set({ token });
    }
  },
}));
