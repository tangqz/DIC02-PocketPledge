/* ────────────────────────────────────────────────
 *  LoginPage  –  Combined login / register form
 * ──────────────────────────────────────────────── */
import { useState, type FormEvent } from "react";
import { useAuthStore } from "@/stores/authStore";

export default function LoginPage() {
  const [isRegister, setIsRegister] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [email, setEmail] = useState("");
  const { login, register, loading, error } = useAuthStore();

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (isRegister) {
      await register(username, password, email || undefined);
    } else {
      await login(username, password);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-indigo-50 via-slate-50 to-orange-50">
      <div className="w-full max-w-sm rounded-2xl bg-white p-8 shadow-xl border border-slate-100">
        <h1 className="mb-6 text-center text-2xl font-bold text-slate-800">
          {isRegister ? "创建账号" : "登录 Study Buddy"}
        </h1>

        <form onSubmit={handleSubmit} className="space-y-4">
          <input
            type="text"
            placeholder="用户名"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
            minLength={2}
            maxLength={50}
            className="w-full rounded-lg bg-slate-50 border border-slate-200 px-4 py-2.5 text-slate-800 placeholder-slate-400 outline-none focus:border-orange-400 focus:ring-1 focus:ring-orange-400 transition-colors"
          />

          {isRegister && (
            <input
              type="email"
              placeholder="邮箱（可选）"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-lg bg-slate-50 border border-slate-200 px-4 py-2.5 text-slate-800 placeholder-slate-400 outline-none focus:border-orange-400 focus:ring-1 focus:ring-orange-400 transition-colors"
            />
          )}

          <input
            type="password"
            placeholder="密码"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={6}
            className="w-full rounded-lg bg-slate-50 border border-slate-200 px-4 py-2.5 text-slate-800 placeholder-slate-400 outline-none focus:border-orange-400 focus:ring-1 focus:ring-orange-400 transition-colors"
          />

          {error && (
            <p className="text-center text-sm text-red-500">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-lg bg-orange-500 py-2.5 font-semibold text-white transition hover:bg-orange-600 disabled:opacity-50"
          >
            {loading ? "请稍候…" : isRegister ? "注册" : "登录"}
          </button>
        </form>

        <p className="mt-4 text-center text-sm text-slate-500">
          {isRegister ? "已有账号？" : "还没有账号？"}
          <button
            type="button"
            onClick={() => {
              setIsRegister(!isRegister);
              useAuthStore.setState({ error: null });
            }}
            className="ml-1 text-orange-600 font-medium underline hover:text-orange-700"
          >
            {isRegister ? "去登录" : "去注册"}
          </button>
        </p>
      </div>
    </div>
  );
}
