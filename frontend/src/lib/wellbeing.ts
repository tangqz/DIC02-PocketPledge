import type { SendFn } from "@/lib/sendContext";
import { useAuthStore } from "@/stores/authStore";
import { useAvatarStore } from "@/stores/avatarStore";
import { useChatStore } from "@/stores/chatStore";
import { useSessionStore } from "@/stores/sessionStore";

interface EmotionSnapshot {
  emotion: string;
  intensity: number;
  cues?: string;
  suggestion?: string;
}

interface MoodReflectionPayload {
  emotion: string;
  intensity: number;
  context?: string;
  totalReward?: number;
  streakDays?: number;
}

interface MealReflectionPayload {
  mealInfo: string;
  mealEmotion: string;
  intensity: number;
  notes?: string;
  totalReward?: number;
}

interface AssessmentReflectionPayload {
  phq2Score: number;
  phq2Severity: string;
  gad2Score: number;
  gad2Severity: string;
  totalReward?: number;
  riskLevel: "low" | "moderate" | "high";
  shouldSeekSupport: boolean;
}

function sanitizeSystemValue(value: string | undefined, maxLength = 120): string {
  const normalized = String(value || "")
    .replace(/[[\]]/g, " ")
    .replace(/[\r\n]+/g, " ")
    .replace(/[,]+/g, "，")
    .replace(/[:]+/g, "：")
    .replace(/\s+/g, " ")
    .trim();
  if (normalized.length <= maxLength) {
    return normalized;
  }
  return `${normalized.slice(0, maxLength - 1)}…`;
}

function buildSystemResult(tag: string, fields: Record<string, string | number | boolean | undefined>): string {
  const serialized = Object.entries(fields)
    .filter(([, value]) => value !== undefined && value !== "")
    .map(([key, value]) => {
      if (typeof value === "boolean") {
        return `${key}: ${value ? "yes" : "no"}`;
      }
      return `${key}: ${value}`;
    })
    .join(", ");
  return serialized ? `[SYSTEM_RESULT: ${tag}, ${serialized}]` : `[SYSTEM_RESULT: ${tag}]`;
}

function interruptAgentOutput(send: SendFn): void {
  const chat = useChatStore.getState();
  const avatar = useAvatarStore.getState();
  const lastMessage = chat.messages.length > 0 ? chat.messages[chat.messages.length - 1] : null;
  const shouldInterrupt =
    chat.isAgentSpeaking || avatar.pendingAudioMessages.length > 0 || Boolean(chat.streamingText);

  if (!shouldInterrupt) {
    return;
  }

  avatar.requestPlaybackInterrupt();
  avatar.clearAudioMessages();
  chat.clearStreaming();
  chat.setAgentSpeaking(false);
  send({ type: "interrupt-signal", text: chat.streamingText || lastMessage?.text || "" });
}

export async function syncWellbeingAfterSave(options?: {
  emotion?: EmotionSnapshot;
}): Promise<void> {
  const session = useSessionStore.getState();
  if (options?.emotion) {
    session.applyEmotionUpdate(
      options.emotion.emotion,
      options.emotion.intensity,
      options.emotion.cues ?? "",
      options.emotion.suggestion ?? "",
    );
  }
  session.markWellbeingUpdated();
  try {
    await useAuthStore.getState().fetchMe();
  } catch {
    // Best-effort sync only.
  }
}

export function sendCompanionWellbeingReflection(send: SendFn, eventText: string): void {
  const normalized = eventText.trim();
  if (!normalized) {
    return;
  }
  interruptAgentOutput(send);
  send({ type: "text-input", text: normalized, tool_result: true });
}

export function buildMoodRecordedReflection(payload: MoodReflectionPayload): string {
  const reward = Number(payload.totalReward ?? 0);
  const lines = [
    buildSystemResult("MOOD_RECORDED", {
      SOURCE: "manual",
      EMOTION: sanitizeSystemValue(payload.emotion, 40),
      INTENSITY: Math.max(1, Math.min(payload.intensity, 5)),
      CONTEXT: sanitizeSystemValue(payload.context, 90) || undefined,
      POINTS: reward > 0 ? `+${reward}` : undefined,
      STREAK_DAYS: payload.streakDays && payload.streakDays > 0 ? payload.streakDays : undefined,
    }),
  ];

  if (reward > 0) {
    lines.push(buildSystemResult("REWARD_GRANTED", { POINTS: `+${reward}` }));
  }

  return lines.join("\n");
}

export function buildMealRecordedReflection(payload: MealReflectionPayload): string {
  const reward = Number(payload.totalReward ?? 0);
  const lines = [
    buildSystemResult("MEAL_RECORDED", {
      MEAL: sanitizeSystemValue(payload.mealInfo, 70),
      EMOTION: sanitizeSystemValue(payload.mealEmotion, 40),
      INTENSITY: Math.max(1, Math.min(payload.intensity, 5)),
      NOTES: sanitizeSystemValue(payload.notes, 90) || undefined,
      POINTS: reward > 0 ? `+${reward}` : undefined,
    }),
  ];

  if (reward > 0) {
    lines.push(buildSystemResult("REWARD_GRANTED", { POINTS: `+${reward}` }));
  }

  return lines.join("\n");
}

export function buildAssessmentRecordedReflection(payload: AssessmentReflectionPayload): string {
  const reward = Number(payload.totalReward ?? 0);
  const lines = [
    buildSystemResult("ASSESSMENT_RECORDED", {
      PHQ2: `${payload.phq2Score}(${sanitizeSystemValue(payload.phq2Severity, 30)})`,
      GAD2: `${payload.gad2Score}(${sanitizeSystemValue(payload.gad2Severity, 30)})`,
      RISK: payload.riskLevel,
      SEEK_SUPPORT: payload.shouldSeekSupport,
      POINTS: reward > 0 ? `+${reward}` : undefined,
    }),
  ];

  if (reward > 0) {
    lines.push(buildSystemResult("REWARD_GRANTED", { POINTS: `+${reward}` }));
  }

  return lines.join("\n");
}