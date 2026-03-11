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
    <section className="rounded-2xl border border-white/10 bg-surface-elevated/70 p-4 backdrop-blur-sm">
      <h3 className="mb-3 text-sm font-semibold text-white/85">
        {locale === "zh" ? "角色市场" : "Character Market"}
      </h3>

      <div className="grid grid-cols-2 gap-2">
        {CHARACTER_MARKET.map((item) => {
          const isActive = item.id === selectedCharacterId;
          return (
            <button
              key={item.id}
              onClick={() => {
                setSelectedCharacterId(item.id);
                onSwitch(item.id);
              }}
              className={`rounded-xl border p-2 text-left transition ${
                isActive
                  ? "border-accent bg-accent/15"
                  : "border-white/10 bg-white/5 hover:border-white/25"
              }`}
            >
              <p className="text-sm font-semibold text-white/90">{item.displayName}</p>
              <p className="mt-1 text-xs text-white/55">{item.shortDescription}</p>
            </button>
          );
        })}
      </div>

      {selected ? (
        <div className="mt-3 rounded-xl bg-black/20 p-3">
          <p className="text-xs text-white/70">{selected.personality}</p>
          <p className="mt-2 text-[11px] uppercase tracking-wider text-white/40">
            {locale === "zh" ? "支持表情" : "Supported Expressions"}
          </p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {selected.supportedExpressions.map((exp) => (
              <span key={exp} className="rounded bg-white/10 px-2 py-0.5 text-[11px] text-white/75">
                {exp}
              </span>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}
