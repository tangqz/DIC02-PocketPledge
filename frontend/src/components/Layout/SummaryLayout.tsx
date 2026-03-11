/* ────────────────────────────────────────────────
 *  SummaryLayout  –  Session end summary
 * ──────────────────────────────────────────────── */
import { useSessionStore } from "@/stores/sessionStore";
import { useI18n } from "@/lib/i18n";
import { formatRmbFromCents, formatSignedRmbFromCents } from "@/lib/currency";

export default function SummaryLayout() {
  const { totalDuration, balance, balanceHistory, reset } = useSessionStore();
  const { t, locale } = useI18n();

  const totalDeductions = balanceHistory
    .filter((e) => e.change < 0)
    .reduce((sum, e) => sum + e.change, 0);
  const totalRewards = balanceHistory
    .filter((e) => e.change > 0)
    .reduce((sum, e) => sum + e.change, 0);

  const minutes = Math.floor(totalDuration / 60);

  const coinSuffix = locale === "zh" ? "元" : "RMB";

  return (
    <div className="flex h-full items-center justify-center p-8 animate-fade-in">
      <div className="w-full max-w-md space-y-6">
        {/* Header */}
        <div className="text-center">
          <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-accent/20">
            <span className="text-3xl">🎯</span>
          </div>
          <h1 className="text-2xl font-bold">{t("summary.title")}</h1>
          <p className="mt-1 text-white/50">
            {t("summary.totalTime")}: {minutes} {t("setup.minutes")}
          </p>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-3 gap-4">
          <StatCard label={t("summary.finalBalance")} value={formatRmbFromCents(balance)} suffix={coinSuffix} color="text-success" />
          <StatCard
            label={t("summary.deductions")}
            value={formatRmbFromCents(Math.abs(totalDeductions))}
            suffix={coinSuffix}
            color="text-danger"
          />
          <StatCard
            label={t("summary.rewards")}
            value={formatRmbFromCents(totalRewards)}
            suffix={coinSuffix}
            color="text-accent"
          />
        </div>

        {/* Transaction log */}
        {balanceHistory.length > 0 && (
          <div className="space-y-2 rounded-2xl bg-surface-elevated/50 p-4">
            <h3 className="mb-3 text-sm font-medium text-white/50">
              {t("summary.transactionLog")}
            </h3>
            <div className="max-h-48 space-y-1.5 overflow-y-auto">
              {balanceHistory.map((event, i) => (
                <div
                  key={i}
                  className="flex items-center justify-between text-sm"
                >
                  <span className="text-white/60">{event.reason}</span>
                  <span
                    className={`font-mono font-medium ${
                      event.change < 0 ? "text-danger" : "text-success"
                    }`}
                  >
                    {formatSignedRmbFromCents(event.change)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Action */}
        <button
          onClick={reset}
          className="w-full rounded-2xl bg-surface-elevated py-3 text-sm font-medium text-white/70 transition-all hover:bg-surface-elevated/80 hover:text-white"
        >
          {t("summary.restart")}
        </button>
      </div>
    </div>
  );
}

function StatCard({
  label,
  value,
  suffix,
  color,
}: {
  label: string;
  value: string;
  suffix: string;
  color: string;
}) {
  return (
    <div className="rounded-xl bg-surface-elevated/50 p-4 text-center">
      <p className="text-xs text-white/40">{label}</p>
      <p className={`mt-1 font-mono text-xl font-bold ${color}`}>
        {value}
        <span className="ml-0.5 text-xs font-normal text-white/30">
          {suffix}
        </span>
      </p>
    </div>
  );
}
