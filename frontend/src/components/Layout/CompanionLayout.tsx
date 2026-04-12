import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSend } from "@/lib/sendContext";
import { useSessionStore } from "@/stores/sessionStore";
import { useMediaStore } from "@/stores/mediaStore";
import { useChatStore } from "@/stores/chatStore";
import { useAvatarStore } from "@/stores/avatarStore";
import { useAuthStore } from "@/stores/authStore";
import { useCharacterStore } from "@/stores/characterStore";
import { useI18n } from "@/lib/i18n";
import { CHARACTER_MARKET } from "@/lib/modelConfig";
import ChatPanel from "@/components/ChatPanel/ChatPanel";
import VoiceInput from "@/components/VoiceInput/VoiceInput";
import Live2DCanvas, { type Live2DCanvasHandle } from "@/components/Live2DCanvas/Live2DCanvas";
import CameraPreviewDock from "@/components/Media/CameraPreviewDock";
import CharacterMarket from "@/components/Dashboard/CharacterMarket";
import AssessmentModal from "@/components/Health/AssessmentModal";
import AssessmentInsightsPanel from "@/components/Health/AssessmentInsightsPanel";
import MealCorrelationPanel from "@/components/Health/MealCorrelationPanel";
import MealJournalModal, { type MealJournalSavedPayload } from "@/components/Health/MealJournalModal";
import MealSupportPanel, {
  type MealSupportMealContext,
  type MealSupportPhase,
} from "@/components/Health/MealSupportPanel";
import MoodPicker from "@/components/Mood/MoodPicker";
import MoodChart from "@/components/Mood/MoodChart";

const EMOTION_LABELS: Record<string, { zh: string; en: string }> = {
  happy: { zh: "开心", en: "Happy" },
  sad: { zh: "难过", en: "Sad" },
  anxious: { zh: "焦虑", en: "Anxious" },
  stressed: { zh: "压力大", en: "Stressed" },
  angry: { zh: "生气", en: "Angry" },
  tired: { zh: "疲惫", en: "Tired" },
  calm: { zh: "平静", en: "Calm" },
  neutral: { zh: "平稳", en: "Neutral" },
  loved: { zh: "被爱", en: "Loved" },
};

function emotionLabel(emotion: string, locale: "zh" | "en"): string {
  const normalized = emotion.trim().toLowerCase();
  const labels = EMOTION_LABELS[normalized];
  if (!labels) {
    return normalized;
  }
  return locale === "zh" ? labels.zh : labels.en;
}

function buildCareHint(emotion: string, intensity: number, locale: "zh" | "en"): string {
  const normalized = emotion.trim().toLowerCase();
  if (locale === "en") {
    if (normalized === "sad" || normalized === "anxious" || normalized === "stressed" || normalized === "angry") {
      return intensity >= 4
        ? "This looks like a heavy moment. Start with the one thing that feels hardest right now."
        : "You seem a bit tense. A short check-in with yourself is enough for now.";
    }
    if (normalized === "tired") {
      return "Your energy looks low. Loosen your shoulders and slow down for a minute.";
    }
    if (normalized === "happy" || normalized === "calm" || normalized === "loved") {
      return "This is a good moment to notice what is helping and keep a little of it with you.";
    }
    return "You can keep talking from this state, one small feeling at a time.";
  }

  if (normalized === "sad" || normalized === "anxious" || normalized === "stressed" || normalized === "angry") {
    return intensity >= 4
      ? "这会儿可能有点重，先从最卡住你的那一件事说起就够了。"
      : "你现在有点绷着，先轻轻照看一下自己的感受就好。";
  }
  if (normalized === "tired") {
    return "你像是在硬撑，先松一松肩颈，慢一点也没关系。";
  }
  if (normalized === "happy" || normalized === "calm" || normalized === "loved") {
    return "现在的状态挺珍贵，可以顺手记住是什么让你稍微好一点。";
  }
  return "你现在的状态适合继续慢慢聊，不用一下子说很多。";
}

type MealSupportSuggestionSource = "user" | "meal" | "camera";

interface MealSupportSuggestion {
  key: string;
  phase: MealSupportPhase;
  title: string;
  body: string;
  source: MealSupportSuggestionSource;
}

const NEGATIVE_EMOTIONS = new Set(["sad", "anxious", "stressed", "angry", "tired"]);

function isNegativeEmotion(emotion: string | undefined): boolean {
  return NEGATIVE_EMOTIONS.has(String(emotion || "").trim().toLowerCase());
}

function detectMealSupportPhase(text: string): MealSupportPhase | null {
  const normalized = text.trim().toLowerCase();
  if (!normalized) {
    return null;
  }

  if (/(刚吃完|吃完了|饭后|吃完很难受|补偿|内疚|羞耻|想吐|不想消化|after.*meal|just ate|post.?meal|compensat)/.test(normalized)) {
    return "post";
  }
  if (/(正在吃|吃到一半|边吃边|饭中|陪我吃|eating now|during.*meal|mid.?meal)/.test(normalized)) {
    return "during";
  }
  if (/(要吃饭了|准备吃饭|饭前|开饭|去吃饭|before.*meal|about to eat|meal time)/.test(normalized)) {
    return "pre";
  }
  return null;
}

function resolveDefaultMealSupportPhase(
  latestMeal: MealSupportMealContext | null,
  currentEmotion: ReturnType<typeof useSessionStore.getState>["currentEmotion"],
): MealSupportPhase {
  if (!latestMeal) {
    return "pre";
  }
  if (Date.now() - latestMeal.timestamp > 90 * 60 * 1000) {
    return "pre";
  }
  if (currentEmotion && currentEmotion.intensity >= 3 && isNegativeEmotion(currentEmotion.emotion)) {
    return "post";
  }
  return "during";
}

function buildMealSupportSuggestion(
  phase: MealSupportPhase,
  locale: "zh" | "en",
  source: MealSupportSuggestionSource,
  latestMeal: MealSupportMealContext | null,
  currentEmotion: ReturnType<typeof useSessionStore.getState>["currentEmotion"],
): Omit<MealSupportSuggestion, "key" | "phase" | "source"> {
  const mealLabel = latestMeal?.mealInfo ? ` ${latestMeal.mealInfo}` : "";
  if (locale === "en") {
    if (phase === "pre") {
      return {
        title: "Meal-time Escort is ready",
        body:
          source === "user"
            ? "This sounds like a before-meal moment. WarmBuddy can stay with you through the first hard minutes."
            : `If this meal${mealLabel} feels loaded, start with a 30-second check-in before it gets heavier.`,
      };
    }
    if (phase === "during") {
      return {
        title: "Keep company through this meal",
        body: "WarmBuddy can switch into a low-pressure meal-time support mode and stay beside you without judgment.",
      };
    }
    return {
      title: "This looks like a post-meal window",
      body:
        source === "camera"
          ? `Recent emotion signals${currentEmotion ? ` (${emotionLabel(currentEmotion.emotion, locale)} ${currentEmotion.intensity}/5)` : ""} suggest this could be a good moment to enter the ten-minute rescue.`
          : "WarmBuddy can help you through the ten hardest minutes after the meal, before you rush into self-blame or compensation.",
    };
  }

  if (phase === "pre") {
    return {
      title: "餐时护航已经准备好",
      body:
        source === "user"
          ? "这听起来像是饭前时刻。暖伴可以先陪你做个 30 秒 check-in，再一起进这顿饭。"
          : `如果这顿饭${mealLabel}已经让你开始绷起来，可以先开一下护航。`,
    };
  }
  if (phase === "during") {
    return {
      title: "这顿饭可以有人陪着你",
      body: "暖伴可以切到低压力的餐时陪伴模式，只陪你把这几分钟过完，不评价食物。",
    };
  }
  return {
    title: "现在像是饭后十分钟窗口",
    body:
      source === "camera"
        ? `最近的情绪信号${currentEmotion ? `（${emotionLabel(currentEmotion.emotion, locale)} ${currentEmotion.intensity}/5）` : ""}提示你可能需要一点饭后救援。`
        : "暖伴可以先陪你把最难的十分钟扛过去，不急着责备自己，也不急着做补偿决定。",
  };
}

export default function CompanionLayout() {
  const live2dRef = useRef<Live2DCanvasHandle>(null);
  const lastTapRef = useRef(0);
  const lastHandledUserMessageIdRef = useRef<string | null>(null);
  const dismissedMealSupportKeyRef = useRef<string | null>(null);
  const lastCameraMealNudgeRef = useRef<number | null>(null);
  const send = useSend();
  const { t, locale, setLocale } = useI18n();
  const [showAssessment, setShowAssessment] = useState(false);
  const [showMealJournal, setShowMealJournal] = useState(false);
  const [showMealSupport, setShowMealSupport] = useState<MealSupportPhase | null>(null);
  const [mealSupportSuggestion, setMealSupportSuggestion] = useState<MealSupportSuggestion | null>(null);
  const [latestMealSupportContext, setLatestMealSupportContext] = useState<MealSupportMealContext | null>(null);
  const [showMoodPicker, setShowMoodPicker] = useState(false);
  const [showMoodChart, setShowMoodChart] = useState(false);
  const [showCharacterPanel, setShowCharacterPanel] = useState(false);

  const activeToolCall = useSessionStore((s) => s.activeToolCall);
  const currentEmotion = useSessionStore((s) => s.currentEmotion);
  const messages = useChatStore((s) => s.messages);
  const cameraGranted = useMediaStore((s) => s.cameraGranted);
  const requestCamera = useMediaStore((s) => s.requestCamera);
  const requestMicrophone = useMediaStore((s) => s.requestMicrophone);
  const micGranted = useMediaStore((s) => s.micGranted);
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const selectedCharacterId = useCharacterStore((s) => s.selectedCharacterId);

  const selectedCharacter = useMemo(
    () => CHARACTER_MARKET.find((item) => item.id === selectedCharacterId) ?? null,
    [selectedCharacterId],
  );
  const defaultMealSupportPhase = useMemo(
    () => resolveDefaultMealSupportPhase(latestMealSupportContext, currentEmotion),
    [currentEmotion, latestMealSupportContext],
  );

  const requestMealSupportSuggestion = useCallback(
    (nextSuggestion: MealSupportSuggestion) => {
      if (showMealSupport) {
        return;
      }
      if (dismissedMealSupportKeyRef.current === nextSuggestion.key) {
        return;
      }
      setMealSupportSuggestion(nextSuggestion);
    },
    [showMealSupport],
  );

  const openMealSupport = useCallback((phase: MealSupportPhase) => {
    setShowMealJournal(false);
    setShowMoodPicker(false);
    setShowAssessment(false);
    setShowMoodChart(false);
    setMealSupportSuggestion(null);
    setShowMealSupport(phase);
  }, []);

  const dismissMealSupportSuggestion = useCallback(() => {
    if (mealSupportSuggestion) {
      dismissedMealSupportKeyRef.current = mealSupportSuggestion.key;
    }
    setMealSupportSuggestion(null);
  }, [mealSupportSuggestion]);

  const handleMealJournalSaved = useCallback(
    (payload: MealJournalSavedPayload) => {
      const latestMeal: MealSupportMealContext = {
        mealInfo: payload.mealInfo,
        mealEmotion: payload.mealEmotion,
        intensity: payload.intensity,
        context: payload.context,
        timestamp: payload.timestamp,
      };
      setLatestMealSupportContext(latestMeal);

      if (payload.intensity >= 3 || isNegativeEmotion(payload.mealEmotion)) {
        const suggestionCopy = buildMealSupportSuggestion("post", locale, "meal", latestMeal, currentEmotion);
        requestMealSupportSuggestion({
          key: `meal:${payload.timestamp}`,
          phase: "post",
          source: "meal",
          ...suggestionCopy,
        });
      }
    },
    [currentEmotion, locale, requestMealSupportSuggestion],
  );

  const interruptAgentOutput = useCallback(() => {
    const chat = useChatStore.getState();
    const avatar = useAvatarStore.getState();
    const lastMessage = chat.messages.length > 0 ? chat.messages[chat.messages.length - 1] : null;
    const shouldInterrupt =
      chat.isAgentSpeaking || avatar.pendingAudioMessages.length > 0 || Boolean(chat.streamingText);
    if (!shouldInterrupt) return;
    avatar.requestPlaybackInterrupt();
    avatar.clearAudioMessages();
    chat.clearStreaming();
    chat.setAgentSpeaking(false);
    send({ type: "interrupt-signal", text: chat.streamingText || lastMessage?.text || "" });
  }, [send]);

  const handleSendText = useCallback(
    (text: string) => {
      interruptAgentOutput();
      useChatStore.getState().addMessage("user", text);
      send({ type: "text-input", text });
    },
    [interruptAgentOutput, send],
  );

  const handleModelTapped = useCallback(
    (hitArea: string) => {
      const now = Date.now();
      if (now - lastTapRef.current < 1200) return;
      lastTapRef.current = now;
      const chat = useChatStore.getState();
      if (chat.isAgentSpeaking) return;
      const msg = (() => {
        if (hitArea.startsWith("Head")) {
          if (hitArea.includes("ForeheadLeft")) return "[用户轻轻碰了碰你的左额头]";
          if (hitArea.includes("ForeheadRight")) return "[用户轻轻碰了碰你的右额头]";
          if (hitArea.includes("Forehead")) return "[用户轻轻碰了碰你的额头]";
          if (hitArea.includes("CheekLeft")) return "[用户轻轻戳了戳你的左脸颊]";
          if (hitArea.includes("CheekRight")) return "[用户轻轻戳了戳你的右脸颊]";
          if (hitArea.includes("Cheek")) return "[用户轻轻戳了戳你的脸颊]";
          if (hitArea.includes("Left")) return "[用户轻轻摸了摸你的左侧头发]";
          if (hitArea.includes("Right")) return "[用户轻轻摸了摸你的右侧头发]";
          return "[用户摸了摸你的头]";
        }

        if (hitArea.startsWith("Body")) {
          if (hitArea.includes("ShoulderLeft")) return "[用户轻轻碰了碰你的左肩]";
          if (hitArea.includes("ShoulderRight")) return "[用户轻轻碰了碰你的右肩]";
          if (hitArea.includes("Chest")) return "[用户轻轻点了点你的胸口]";
          if (hitArea.includes("UpperTorso")) return "[用户轻轻碰了碰你的上身]";
          if (hitArea.includes("ArmLeft")) return "[用户轻轻碰了碰你的左手臂]";
          if (hitArea.includes("ArmRight")) return "[用户轻轻碰了碰你的右手臂]";
          if (hitArea.includes("WaistLeft")) return "[用户轻轻碰了碰你的左腰侧]";
          if (hitArea.includes("WaistRight")) return "[用户轻轻碰了碰你的右腰侧]";
          if (hitArea.includes("Waist")) return "[用户轻轻碰了碰你的腰间]";
          if (hitArea.includes("LegLeft")) return "[用户轻轻碰了碰你的左腿]";
          if (hitArea.includes("LegRight")) return "[用户轻轻碰了碰你的右腿]";
          if (hitArea.includes("Thigh")) return "[用户轻轻碰了碰你的腿部]";
          if (hitArea.includes("FootLeft")) return "[用户轻轻碰了碰你的左脚踝]";
          if (hitArea.includes("FootRight")) return "[用户轻轻碰了碰你的右脚踝]";
          if (hitArea.includes("Foot")) return "[用户轻轻碰了碰你的脚边]";
          return "[用户轻轻碰了碰你]";
        }

        return "[用户轻轻碰了碰你]";
      })();
      send({ type: "text-input", text: msg });
    },
    [send],
  );

  const emotionStatusLabel = currentEmotion
    ? `${emotionLabel(currentEmotion.emotion, locale)} ${currentEmotion.intensity}/5`
    : null;
  const careHint = currentEmotion
    ? buildCareHint(currentEmotion.emotion, currentEmotion.intensity, locale)
    : null;
  const balanceLabel = user?.balance !== undefined
    ? `${t("status.balance")}: ${user.balance}`
    : null;

  useEffect(() => {
    const lastMessage = messages.length > 0 ? messages[messages.length - 1] : null;
    if (!lastMessage || lastMessage.role !== "user") {
      return;
    }
    if (lastHandledUserMessageIdRef.current === lastMessage.id) {
      return;
    }
    lastHandledUserMessageIdRef.current = lastMessage.id;

    const detectedPhase = detectMealSupportPhase(lastMessage.text);
    if (!detectedPhase) {
      return;
    }

    const suggestionCopy = buildMealSupportSuggestion(
      detectedPhase,
      locale,
      "user",
      latestMealSupportContext,
      currentEmotion,
    );
    requestMealSupportSuggestion({
      key: `message:${lastMessage.id}`,
      phase: detectedPhase,
      source: "user",
      ...suggestionCopy,
    });
  }, [currentEmotion, latestMealSupportContext, locale, messages, requestMealSupportSuggestion]);

  useEffect(() => {
    if (!currentEmotion || !latestMealSupportContext || showMealSupport) {
      return;
    }
    if (!isNegativeEmotion(currentEmotion.emotion) || currentEmotion.intensity < 3) {
      return;
    }
    if (Date.now() - latestMealSupportContext.timestamp > 90 * 60 * 1000) {
      return;
    }
    if (currentEmotion.timestamp - latestMealSupportContext.timestamp < 45 * 1000) {
      return;
    }
    if (lastCameraMealNudgeRef.current === latestMealSupportContext.timestamp) {
      return;
    }
    lastCameraMealNudgeRef.current = latestMealSupportContext.timestamp;

    const suggestionCopy = buildMealSupportSuggestion(
      "post",
      locale,
      "camera",
      latestMealSupportContext,
      currentEmotion,
    );
    requestMealSupportSuggestion({
      key: `camera:${latestMealSupportContext.timestamp}`,
      phase: "post",
      source: "camera",
      ...suggestionCopy,
    });
  }, [currentEmotion, latestMealSupportContext, locale, requestMealSupportSuggestion, showMealSupport]);

  return (
    <div className="relative flex h-full min-h-0 flex-col bg-slate-50 animate-fade-in">
      {/* Top bar */}
      <div className="z-20 flex shrink-0 items-center justify-between px-4 py-2">
        <span className="text-sm font-semibold text-slate-700">
          {t("app.title")}
        </span>
        <div className="flex items-center gap-2">
          {balanceLabel && (
            <span className="rounded-full bg-amber-100 px-2.5 py-0.5 text-xs text-amber-700">
              {balanceLabel}
            </span>
          )}
          {emotionStatusLabel && (
            <span className="rounded-full bg-violet-100 px-2.5 py-0.5 text-xs text-violet-700">
              {emotionStatusLabel}
            </span>
          )}
          <button
            type="button"
            onClick={() => setLocale(locale === "zh" ? "en" : "zh")}
            aria-label={locale === "zh" ? t("common.switchToEnglish") : t("common.switchToChinese")}
            title={locale === "zh" ? t("common.switchToEnglish") : t("common.switchToChinese")}
            className="rounded-lg bg-white/85 px-2.5 py-1 text-xs font-semibold text-slate-600 ring-1 ring-slate-200 backdrop-blur hover:bg-white"
          >
            {locale === "zh" ? "EN" : "中"}
          </button>
          <button
            type="button"
            onClick={() => setShowCharacterPanel((value) => !value)}
            className="rounded-lg bg-white/85 px-2.5 py-1 text-xs font-semibold text-slate-600 ring-1 ring-slate-200 backdrop-blur hover:bg-white"
          >
            {selectedCharacter ? selectedCharacter.displayName : (locale === "zh" ? "角色" : "Character")}
          </button>
          {/* Permission buttons */}
          {!micGranted && (
            <button
              onClick={() => void requestMicrophone()}
              className="rounded-lg bg-blue-100 px-2.5 py-1 text-xs text-blue-700 hover:bg-blue-200"
            >
              🎤 {t("companion.enableMic")}
            </button>
          )}
          {!cameraGranted && (
            <button
              onClick={() => void requestCamera()}
              className="rounded-lg bg-green-100 px-2.5 py-1 text-xs text-green-700 hover:bg-green-200"
            >
              📷 {t("companion.enableCamera")}
            </button>
          )}
          <button
            onClick={logout}
            className="rounded-lg bg-slate-100 px-2.5 py-1 text-xs text-slate-500 hover:bg-slate-200"
          >
            {t("auth.logout")}
          </button>
        </div>
      </div>

      {careHint && (
        <div className="z-20 px-4 pb-2">
          <div className="mx-auto w-full max-w-xl rounded-2xl border border-amber-100 bg-white/85 px-4 py-2 text-center text-xs text-slate-600 shadow-sm backdrop-blur">
            {careHint}
          </div>
        </div>
      )}

      {mealSupportSuggestion && !showMealSupport && (
        <div className="z-20 px-4 pb-3">
          <div className="mx-auto flex w-full max-w-3xl flex-col gap-3 rounded-[24px] border border-orange-100 bg-[linear-gradient(135deg,#fff6ef_0%,#fff9f3_55%,#ffffff_100%)] px-4 py-4 shadow-sm md:flex-row md:items-center md:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-orange-500">
                {locale === "zh" ? "餐时护航" : "Meal Support"}
              </p>
              <p className="mt-1 text-sm font-semibold text-slate-700">{mealSupportSuggestion.title}</p>
              <p className="mt-1 text-sm text-slate-600">{mealSupportSuggestion.body}</p>
            </div>
            <div className="flex shrink-0 gap-2">
              <button
                type="button"
                onClick={() => openMealSupport(mealSupportSuggestion.phase)}
                className="rounded-full bg-orange-500 px-4 py-2 text-sm font-semibold text-white transition hover:bg-orange-600"
              >
                {locale === "zh" ? "进入护航" : "Enter support"}
              </button>
              <button
                type="button"
                onClick={dismissMealSupportSuggestion}
                className="rounded-full bg-white px-4 py-2 text-sm font-medium text-slate-500 ring-1 ring-slate-200 transition hover:bg-slate-50"
              >
                {locale === "zh" ? "稍后" : "Later"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Live2D avatar */}
      <div className="relative min-h-0 flex-1">
        <div id="live2d-container" className="absolute inset-0">
          <Live2DCanvas ref={live2dRef} onModelTapped={handleModelTapped} />
        </div>

        <div className="absolute bottom-4 left-1/2 z-20 -translate-x-1/2">
          <VoiceInput />
        </div>

        <CameraPreviewDock className="absolute right-4 top-4 z-20" />

        {activeToolCall && (
          <div className="absolute left-1/2 top-4 z-20 -translate-x-1/2 rounded-full bg-accent/20 px-4 py-1.5 text-xs font-medium text-accent">
            {activeToolCall.tool}
          </div>
        )}
      </div>

      {/* Chat panel */}
      <div className="h-[34%] min-h-[210px] border-t border-slate-200 bg-surface-elevated/60 backdrop-blur-lg">
        <ChatPanel expanded onSendText={handleSendText} />
      </div>

      {/* Emotion buttons - vertical on mobile, horizontal on desktop */}
      <div className="fixed bottom-[38%] left-4 z-30 flex flex-col gap-2 md:hidden">
        <button
          onClick={() => openMealSupport(defaultMealSupportPhase)}
          className="flex h-12 w-12 items-center justify-center rounded-full bg-orange-400 text-lg text-white shadow-lg hover:bg-orange-500 active:scale-95"
          title={locale === "zh" ? "餐时护航" : "Meal support"}
        >
          🫶
        </button>
        <button
          onClick={() => setShowMoodPicker((v) => !v)}
          className="flex h-12 w-12 items-center justify-center rounded-full bg-violet-500 text-xl text-white shadow-lg hover:bg-violet-600 active:scale-95"
          title={t("companion.logMood")}
        >
          😊
        </button>
        <button
          onClick={() => setShowMealJournal((v) => !v)}
          className="flex h-10 w-10 items-center justify-center rounded-full bg-emerald-200 text-sm text-emerald-700 shadow hover:bg-emerald-300 active:scale-95"
          title={t("companion.logMeal")}
        >
          🍽
        </button>
        <button
          onClick={() => setShowAssessment((v) => !v)}
          className="flex h-10 w-10 items-center justify-center rounded-full bg-sky-200 text-sm text-sky-700 shadow hover:bg-sky-300 active:scale-95"
          title={t("companion.selfCheck")}
        >
          📝
        </button>
        <button
          onClick={() => setShowMoodChart((v) => !v)}
          className="flex h-10 w-10 items-center justify-center rounded-full bg-slate-200 text-sm text-slate-600 shadow hover:bg-slate-300 active:scale-95"
          title={t("companion.moodChart")}
        >
          📊
        </button>
      </div>

      {/* Mood floating button - desktop only */}
      <button
        onClick={() => setShowMoodPicker((v) => !v)}
        className="fixed bottom-[38%] right-4 z-30 hidden h-12 w-12 items-center justify-center rounded-full bg-violet-500 text-xl text-white shadow-lg hover:bg-violet-600 active:scale-95 md:flex"
        title={t("companion.logMood")}
      >
        😊
      </button>

      {/* Meal journal button - desktop only */}
      <button
        onClick={() => setShowMealJournal((v) => !v)}
        className="fixed bottom-[38%] right-[7.6rem] z-30 hidden h-10 w-10 items-center justify-center rounded-full bg-emerald-200 text-sm text-emerald-700 shadow hover:bg-emerald-300 active:scale-95 md:flex"
        title={t("companion.logMeal")}
      >
        🍽
      </button>

      {/* Assessment button - desktop only */}
      <button
        onClick={() => setShowAssessment((v) => !v)}
        className="fixed bottom-[38%] right-[10.7rem] z-30 hidden h-10 w-10 items-center justify-center rounded-full bg-sky-200 text-sm text-sky-700 shadow hover:bg-sky-300 active:scale-95 md:flex"
        title={t("companion.selfCheck")}
      >
        📝
      </button>

      {/* Mood chart toggle - desktop only */}
      <button
        onClick={() => setShowMoodChart((v) => !v)}
        className="fixed bottom-[38%] right-[4.5rem] z-30 hidden h-10 w-10 items-center justify-center rounded-full bg-slate-200 text-sm text-slate-600 shadow hover:bg-slate-300 active:scale-95 md:flex"
        title={t("companion.moodChart")}
      >
        📊
      </button>

      <button
        onClick={() => openMealSupport(defaultMealSupportPhase)}
        className="fixed bottom-[38%] right-[13.8rem] z-30 hidden items-center gap-2 rounded-full bg-orange-400 px-4 py-2 text-sm font-semibold text-white shadow-lg transition hover:bg-orange-500 active:scale-95 md:flex"
        title={locale === "zh" ? "餐时护航" : "Meal support"}
      >
        <span>🫶</span>
        <span>{locale === "zh" ? "餐时护航" : "Meal Support"}</span>
      </button>

      {/* Mood picker modal */}
      {showMoodPicker && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/20 backdrop-blur-sm">
          <MoodPicker onClose={() => setShowMoodPicker(false)} />
        </div>
      )}

      {showCharacterPanel && (
        <div
          className="fixed inset-0 z-40 flex items-center justify-center bg-black/20 backdrop-blur-sm"
          onClick={() => setShowCharacterPanel(false)}
        >
          <div
            className="w-[min(92vw,720px)]"
            onClick={(event) => event.stopPropagation()}
          >
            <CharacterMarket onSwitch={() => setShowCharacterPanel(false)} />
          </div>
        </div>
      )}

      {/* Meal journal modal */}
      {showMealJournal && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/20 backdrop-blur-sm">
          <MealJournalModal onClose={() => setShowMealJournal(false)} onSaved={handleMealJournalSaved} />
        </div>
      )}

      {showMealSupport && (
        <div className="fixed inset-0 z-40 flex items-center justify-center overflow-y-auto bg-black/20 p-4 backdrop-blur-sm">
          <MealSupportPanel
            initialPhase={showMealSupport}
            latestMeal={latestMealSupportContext}
            currentEmotion={currentEmotion}
            onClose={() => setShowMealSupport(null)}
          />
        </div>
      )}

      {/* Assessment modal */}
      {showAssessment && (
        <div className="fixed inset-0 z-40 flex items-center justify-center overflow-y-auto bg-black/20 p-4 backdrop-blur-sm">
          <AssessmentModal onClose={() => setShowAssessment(false)} />
        </div>
      )}

      {/* Mood chart drawer */}
      {showMoodChart && (
        <div className="fixed bottom-[38%] right-4 z-30 w-80 rounded-2xl border border-slate-200 bg-white/95 shadow-xl backdrop-blur-sm">
          <div className="flex items-center justify-between px-4 pt-3">
            <span className="text-xs font-semibold text-slate-600">
              {t("companion.moodMeal")}
            </span>
            <button
              onClick={() => setShowMoodChart(false)}
              className="text-xs text-slate-400 hover:text-slate-600"
            >
              ✕
            </button>
          </div>
          <MoodChart />
          <MealCorrelationPanel />
          <AssessmentInsightsPanel />
        </div>
      )}
    </div>
  );
}
