/* ────────────────────────────────────────────────
 *  LoginPage  –  Combined login / register form
 * ──────────────────────────────────────────────── */
import { useState, type FormEvent } from "react";
import { useI18n } from "@/lib/i18n";
import { useAuthStore } from "@/stores/authStore";

export default function LoginPage() {
  const [isRegister, setIsRegister] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [email, setEmail] = useState("");
  const { t, locale, setLocale } = useI18n();
  const { login, register, loading, error } = useAuthStore();

  const translatedError = translateAuthError(error, t);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (isRegister) {
      await register(username, password, email || undefined);
    } else {
      await login(username, password);
    }
  };

  return (
    <div className="relative flex min-h-screen items-center justify-center bg-gradient-to-br from-indigo-50 via-slate-50 to-orange-50 px-4">
      <button
        type="button"
        onClick={() => setLocale(locale === "zh" ? "en" : "zh")}
        className="absolute right-4 top-4 rounded-lg bg-white/80 px-3 py-1.5 text-xs font-semibold text-slate-600 shadow-sm ring-1 ring-slate-200 backdrop-blur hover:bg-white"
      >
        {locale === "zh" ? "EN" : "中"}
      </button>

      <div className="w-full max-w-sm rounded-2xl border border-slate-100 bg-white p-8 shadow-xl">
        <h1 className="mb-6 text-center text-2xl font-bold text-slate-800">
          {isRegister ? t("auth.registerTitle") : t("auth.loginTitle")}
        </h1>

        <form onSubmit={handleSubmit} className="space-y-4">
          <input
            type="text"
            placeholder={t("auth.username")}
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
              placeholder={t("auth.emailOptional")}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-lg bg-slate-50 border border-slate-200 px-4 py-2.5 text-slate-800 placeholder-slate-400 outline-none focus:border-orange-400 focus:ring-1 focus:ring-orange-400 transition-colors"
            />
          )}

          <input
            type="password"
            placeholder={t("auth.password")}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={6}
            className="w-full rounded-lg bg-slate-50 border border-slate-200 px-4 py-2.5 text-slate-800 placeholder-slate-400 outline-none focus:border-orange-400 focus:ring-1 focus:ring-orange-400 transition-colors"
          />

          {translatedError && (
            <p className="text-center text-sm text-red-500">{translatedError}</p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-lg bg-orange-500 py-2.5 font-semibold text-white transition hover:bg-orange-600 disabled:opacity-50"
          >
            {loading ? t("auth.pleaseWait") : isRegister ? t("auth.register") : t("auth.login")}
          </button>
        </form>

        <p className="mt-4 text-center text-sm text-slate-500">
          {isRegister ? t("auth.hasAccount") : t("auth.noAccount")}
          <button
            type="button"
            onClick={() => {
              setIsRegister(!isRegister);
              useAuthStore.setState({ error: null });
            }}
            className="ml-1 text-orange-600 font-medium underline hover:text-orange-700"
          >
            {isRegister ? t("auth.goLogin") : t("auth.goRegister")}
          </button>
        </p>
      </div>
    </div>
  );
}

function translateAuthError(error: string | null, t: (key: string) => string) {
  if (!error) {
    return null;
  }

  if (error === "Network error") {
    return t("auth.error.network");
  }
  if (error === "Login failed") {
    return t("auth.error.loginFailed");
  }
  if (error === "Registration failed") {
    return t("auth.error.registerFailed");
  }

  return error;
}
