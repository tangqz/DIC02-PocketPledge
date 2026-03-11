import { create } from "zustand";
import { CHARACTER_MARKET } from "@/lib/modelConfig";

const CHARACTER_KEY = "sb_character_id";

interface CharacterState {
  selectedCharacterId: string;
  setSelectedCharacterId: (characterId: string) => void;
}

function getInitialCharacterId(): string {
  const stored = localStorage.getItem(CHARACTER_KEY);
  if (stored && CHARACTER_MARKET.some((item) => item.id === stored)) {
    return stored;
  }
  return CHARACTER_MARKET[0]?.id ?? "milly";
}

export const useCharacterStore = create<CharacterState>((set) => ({
  selectedCharacterId: getInitialCharacterId(),
  setSelectedCharacterId: (characterId) => {
    localStorage.setItem(CHARACTER_KEY, characterId);
    set({ selectedCharacterId: characterId });
  },
}));
