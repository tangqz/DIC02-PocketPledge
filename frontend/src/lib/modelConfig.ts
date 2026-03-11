/* ────────────────────────────────────────────────
 *  Live2D Model Configuration
 *  Maps semantic emotion names → expression file indices
 * ──────────────────────────────────────────────── */

export interface ModelConfig {
  name: string;
  url: string;
  kScale: number;
  /** Maps emotion keyword → expression index (0-based, referencing exp_XX.exp3.json) */
  emotionMap: Record<string, number>;
  /** Idle motion group name */
  idleMotionGroup: string;
  /** Talk motion group name (empty string = default group) */
  talkMotionGroup: string;
  /** LipSync parameter ID in the model */
  lipSyncParamId: string;
  /** Lip sync RMS amplification factor */
  lipSyncGain: number;
  /** Hit area interactions */
  tapMotions: Record<string, { motion: string; expression: string }>;
}

export interface CharacterProfile {
  id: string;
  displayName: string;
  shortDescription: string;
  personality: string;
  supportedExpressions: string[];
  model: ModelConfig;
}

/**
 * mao_pro model config.
 * LipSync param is "ParamA" (not the standard "ParamMouthOpenY").
 * Expression files: exp_01..exp_08 → indices 0..7.
 */
export const MAO_PRO_CONFIG: ModelConfig = {
  name: "mao_pro",
  url: "/live2d-models/mao_pro/mao_pro.model3.json",
  kScale: 0.5,
  emotionMap: {
    neutral: 0, // exp_01
    fear: 1, // exp_02
    sadness: 1, // exp_02
    anger: 2, // exp_03
    disgust: 2, // exp_03
    joy: 3, // exp_04
    happy: 3, // exp_04
    smirk: 3, // exp_04
    surprise: 3, // exp_04
    encouraging: 4, // exp_05
    concerned: 5, // exp_06
    disappointed: 6, // exp_07
    proud: 7, // exp_08
    serious: 2, // exp_03 (reuse anger set)
    playful: 3, // exp_04 (reuse joy set)
  },
  idleMotionGroup: "Idle",
  talkMotionGroup: "", // default group for mao_pro
  lipSyncParamId: "ParamA",
  lipSyncGain: 2.0,
  tapMotions: {
    HitAreaHead: { motion: "", expression: "happy" },
    HitAreaBody: { motion: "", expression: "surprise" },
  },
};

export const REN_PRO_CONFIG: ModelConfig = {
  name: "natori_pro_zh",
  url: "/live2d-models/natori_pro_zh/runtime/natori_pro_t06.model3.json",
  kScale: 0.52,
  emotionMap: {
    neutral: 2,
    fear: 3,
    sadness: 3,
    anger: 0,
    disgust: 0,
    joy: 4,
    happy: 4,
    smirk: 1,
    surprise: 5,
    encouraging: 4,
    concerned: 3,
    disappointed: 3,
    proud: 4,
    serious: 0,
    playful: 1,
  },
  idleMotionGroup: "Idle",
  talkMotionGroup: "Tap",
  lipSyncParamId: "ParamMouthOpenY",
  lipSyncGain: 2.0,
  tapMotions: {
    HitAreaHead: { motion: "Tap@Head", expression: "happy" },
    HitAreaBody: { motion: "Flick@Body", expression: "encouraging" },
  },
};

export const CHARACTER_MARKET: CharacterProfile[] = [
  {
    id: "milly",
    displayName: "Milly",
    shortDescription: "Warm but strict study buddy",
    personality: "Emotional, playful, and sharp when you slack. She pushes you with pressure and care.",
    supportedExpressions: ["neutral", "happy", "encouraging", "angry", "proud"],
    model: MAO_PRO_CONFIG,
  },
  {
    id: "ren",
    displayName: "Natori",
    shortDescription: "Calm mentor companion",
    personality: "Steady and concise. Keeps boundaries and gives clear, rational guidance.",
    supportedExpressions: ["neutral", "encouraging", "proud", "angry", "happy"],
    model: REN_PRO_CONFIG,
  },
];

/** Default model for the application */
export const DEFAULT_MODEL_CONFIG = MAO_PRO_CONFIG;
