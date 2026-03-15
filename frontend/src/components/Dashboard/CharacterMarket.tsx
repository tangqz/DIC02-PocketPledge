import { useMemo } from "react";
import { CHARACTER_MARKET } from "@/lib/modelConfig";
import { useCharacterStore } from "@/stores/characterStore";
import { useI18n } from "@/lib/i18n";

interface CharacterMarketProps {
  onSwitch: (characterId: string) => void;
}

export default function CharacterMarket({ onSwitch }: CharacterMarketProps) {
  const { locale } = useI18n();
  const selectedCharacterId = useCharacterStore((s) => s.selectedCharacterId);
  const setSelectedCharacterId = useCharacterStore((s) => s.setSelectedCharacterId);

  const selected = useMemo(
    () => CHARACTER_MARKET.find((item) => item.id === selectedCharacterId) ?? CHARACTER_MARKET[0],
    [selectedCharacterId],
  );

  return (
    <section className="rounded-2xl border border-slate-200 bg-surface-elevated/70 p-4 backdrop-blur-sm">
      <h3 className="mb-3 text-sm font-semibold text-slate-700">
        {locale === "zh" ? "角色市场" : "Character Market"}
      </h3>

      <div className="grid grid-cols-2 gap-2">
        {CHARACTER_MARKET.map((item) => {
          const isActive = item.id === selectedCharacterId;
          return (
            <button
              key={item.id}
              aria-pressed={isActive}
              aria-label={
                locale === "zh"
                  ? `选择角色: ${item.displayName}`
                  : `Select character: ${item.displayName}`
              }
              onClick={() => {
                if (item.id === selectedCharacterId) {
                  return;
                }
                setSelectedCharacterId(item.id);
                onSwitch(item.id);
              }}
              className={`rounded-xl border p-2 text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${
                isActive
                  ? "border-accent bg-accent/15"
                  : "border-slate-200 bg-slate-50 hover:border-slate-300"
              }`}
            >
              <p className="text-sm font-semibold text-slate-800">{item.displayName}</p>
              <p className="mt-1 text-xs text-slate-500">{item.shortDescription}</p>
            </button>
          );
        })}
      </div>

      {selected ? (
        <div className="mt-3 rounded-xl bg-slate-50 p-3">
          <p className="text-xs text-slate-600">{selected.personality}</p>
          <p className="mt-2 text-[11px] uppercase tracking-wider text-slate-400">
            {locale === "zh" ? "支持表情" : "Supported Expressions"}
          </p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {selected.supportedExpressions.map((exp) => (
              <span key={exp} className="rounded bg-slate-100 px-2 py-0.5 text-[11px] text-slate-600">
                {exp}
              </span>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}
