/* ────────────────────────────────────────────────
 *  i18n  –  Lightweight bilingual (zh / en) translation system
 *
 *  Usage:
 *    const { t } = useI18n();
 *    t("setup.title")  → "环境校准" | "Environment Calibration"
 * ──────────────────────────────────────────────── */

import React, { createContext, useContext, useState, useCallback, useMemo } from "react";

export type Locale = "zh" | "en";

type TranslationDict = Record<string, string>;

// ── Chinese translations ──
const zh: TranslationDict = {
  // App
  "app.title": "WarmBuddy",
  "app.loading": "加载中…",

  // Setup
  "setup.title": "环境校准",
  "setup.cameraLabel": "摄像头预览",
  "setup.cameraGranted": "摄像头已就绪",
  "setup.cameraDenied": "摄像头未授权",
  "setup.cameraPending": "请求权限中…",
  "setup.screenShare": "屏幕共享",
  "setup.screenReady": "屏幕共享已就绪",
  "setup.screenNotReady": "未开启屏幕共享",
  "setup.micLabel": "麦克风",
  "setup.start": "开始陪伴",
  "setup.duration": "陪伴时长",
  "setup.minutes": "分钟",
  "setup.chatHint": "和暖伴聊聊你现在的心情吧",
  "setup.agentStartHint": "暖伴会根据你的状态给你温柔回应",

  // Focus
  "focus.pause": "暂停",
  "focus.resume": "继续",
  "focus.subtitle": "字幕区域",
  "focus.sendPlaceholder": "输入消息…",
  "focus.send": "发送",
  "focus.openChat": "打开对话",

  // Status
  "status.balance": "余额(RMB)",
  "status.timer": "计时",
  "status.focusRemaining": "剩余时间",
  "status.state.active": "陪伴中",
  "status.state.paused": "已暂停",
  "status.state.setup": "准备中",
  "status.state.completed": "已完成",
  "status.connected": "已连接",
  "status.disconnected": "未连接",
  "status.charity": "慈善",
  "status.pool": "奖池",

  // Summary
  "summary.title": "陪伴小结",
  "summary.totalTime": "总时长",
  "summary.finalBalance": "最终余额",
  "summary.deductions": "总扣除",
  "summary.rewards": "总奖励",
  "summary.transactionLog": "明细记录",
  "summary.restart": "重新开始",
  "summary.noTransactions": "暂无明细",

  // Voice
  "voice.off": "语音已关闭",
  "voice.idle": "待命",
  "voice.listening": "正在聆听…",
  "voice.muted": "已静音",

  // Live2D
  "live2d.loading": "加载模型中…",
  "live2d.error": "模型加载失败",

  // Chat
  "chat.agent": "助手",
  "chat.user": "我",

  // Common
  "common.close": "关闭",
  "common.cancel": "取消",
  "common.refresh": "刷新",
  "common.loading": "加载中...",
  "common.submit": "提交",
  "common.submitFailed": "提交失败",
  "common.loadFailed": "加载失败",
  "common.networkRetry": "网络异常，请稍后再试",
  "common.processing": "系统正在处理你的请求",
  "common.switchToEnglish": "切换到英文",
  "common.switchToChinese": "切换到中文",

  // Companion
  "companion.enableMic": "开启麦克风",
  "companion.enableCamera": "开启摄像头",
  "companion.logMood": "记录心情",
  "companion.logMeal": "记录饮食",
  "companion.selfCheck": "心理自测",
  "companion.moodChart": "情绪记录",
  "companion.moodMeal": "情绪与饮食",

  // Assessment
  "assessment.title": "心理自测",
  "assessment.disclaimer": "仅供自我观察，不构成医学诊断。如持续不适，请及时寻求专业帮助。",
  "assessment.submitAndSave": "提交并记录",

  // Meal
  "meal.title": "饮食记录",
  "meal.what": "吃了什么",
  "meal.whatPlaceholder": "例如：午饭吃了鸡肉沙拉",
  "meal.afterMood": "饭后情绪",
  "meal.intensity": "强度",
  "meal.notesOptional": "备注（可选）",
  "meal.notesPlaceholder": "比如：吃饭时很赶、和朋友一起吃",
  "meal.submit": "提交记录",
  "meal.inputRequired": "请先输入饮食内容",
  "meal.noRecords": "还没有饮食记录",
  "meal.correlation": "饮食-情绪关联",

  // Auth
  "auth.loginTitle": "登录 WarmBuddy",
  "auth.registerTitle": "创建账号",
  "auth.username": "用户名",
  "auth.emailOptional": "邮箱（可选）",
  "auth.password": "密码",
  "auth.login": "登录",
  "auth.register": "注册",
  "auth.pleaseWait": "请稍候…",
  "auth.hasAccount": "已有账号？",
  "auth.noAccount": "还没有账号？",
  "auth.goLogin": "去登录",
  "auth.goRegister": "去注册",
  "auth.logout": "退出",
  "auth.error.network": "网络错误",
  "auth.error.loginFailed": "登录失败",
  "auth.error.registerFailed": "注册失败",

  // Media preview
  "media.previewTitle": "实时监督画面",
  "media.live": "实时",
  "media.inactive": "未连接",
  "media.camera": "摄像头",
  "media.screen": "屏幕",
  "media.ready": "已连接",
  "media.offline": "未开启",
  "media.cameraUnavailable": "摄像头未开启",
  "media.screenUnavailable": "屏幕共享未开启",
};

// ── English translations ──
const en: TranslationDict = {
  "app.title": "WarmBuddy",
  "app.loading": "Loading…",

  "setup.title": "Environment Calibration",
  "setup.cameraLabel": "Camera Preview",
  "setup.cameraGranted": "Camera Ready",
  "setup.cameraDenied": "Camera Not Authorized",
  "setup.cameraPending": "Requesting Permission…",
  "setup.screenShare": "Screen Share",
  "setup.screenReady": "Screen Share Ready",
  "setup.screenNotReady": "Screen Share Not Enabled",
  "setup.micLabel": "Microphone",
  "setup.start": "Start Companion",
  "setup.duration": "Companion Duration",
  "setup.minutes": "min",
  "setup.chatHint": "Talk to WarmBuddy about how you feel right now",
  "setup.agentStartHint": "WarmBuddy responds based on your emotional state",

  "focus.pause": "Pause",
  "focus.resume": "Resume",
  "focus.subtitle": "Subtitles",
  "focus.sendPlaceholder": "Type a message…",
  "focus.send": "Send",
  "focus.openChat": "Open Chat",

  "status.balance": "Balance (RMB)",
  "status.timer": "Timer",
  "status.focusRemaining": "Remaining",
  "status.state.active": "Companion Active",
  "status.state.paused": "Paused",
  "status.state.setup": "Setting Up",
  "status.state.completed": "Completed",
  "status.connected": "Connected",
  "status.disconnected": "Disconnected",
  "status.charity": "Charity",
  "status.pool": "Pool",

  "summary.title": "Companion Summary",
  "summary.totalTime": "Total Time",
  "summary.finalBalance": "Final Balance",
  "summary.deductions": "Total Deductions",
  "summary.rewards": "Total Rewards",
  "summary.transactionLog": "Transaction Log",
  "summary.restart": "Start Again",
  "summary.noTransactions": "No transactions yet",

  "voice.off": "Voice Off",
  "voice.idle": "Standby",
  "voice.listening": "Listening…",
  "voice.muted": "Muted",

  "live2d.loading": "Loading model…",
  "live2d.error": "Failed to load model",

  "chat.agent": "Agent",
  "chat.user": "Me",

  "common.close": "Close",
  "common.cancel": "Cancel",
  "common.refresh": "Refresh",
  "common.loading": "Loading...",
  "common.submit": "Submit",
  "common.submitFailed": "Submit failed",
  "common.loadFailed": "Failed to load",
  "common.networkRetry": "Network error, please retry",
  "common.processing": "System is processing your request",
  "common.switchToEnglish": "Switch to English",
  "common.switchToChinese": "Switch to Chinese",

  "companion.enableMic": "Enable Mic",
  "companion.enableCamera": "Enable Camera",
  "companion.logMood": "Log mood",
  "companion.logMeal": "Meal journal",
  "companion.selfCheck": "Self-check",
  "companion.moodChart": "Mood chart",
  "companion.moodMeal": "Mood & Meal",

  "assessment.title": "Quick Self-Check",
  "assessment.disclaimer": "For self-observation only. This is not a medical diagnosis. Seek professional help if needed.",
  "assessment.submitAndSave": "Submit",

  "meal.title": "Meal Journal",
  "meal.what": "What did you eat",
  "meal.whatPlaceholder": "e.g. chicken salad for lunch",
  "meal.afterMood": "After-meal mood",
  "meal.intensity": "Intensity",
  "meal.notesOptional": "Notes (optional)",
  "meal.notesPlaceholder": "e.g. rushed meal, ate with friends",
  "meal.submit": "Submit",
  "meal.inputRequired": "Please enter meal details",
  "meal.noRecords": "No meal records yet",
  "meal.correlation": "Meal-Mood Correlation",

  "auth.loginTitle": "Sign In to WarmBuddy",
  "auth.registerTitle": "Create Account",
  "auth.username": "Username",
  "auth.emailOptional": "Email (optional)",
  "auth.password": "Password",
  "auth.login": "Sign In",
  "auth.register": "Register",
  "auth.pleaseWait": "Please wait…",
  "auth.hasAccount": "Already have an account?",
  "auth.noAccount": "Need an account?",
  "auth.goLogin": "Sign in",
  "auth.goRegister": "Register",
  "auth.logout": "Log Out",
  "auth.error.network": "Network error",
  "auth.error.loginFailed": "Login failed",
  "auth.error.registerFailed": "Registration failed",

  "media.previewTitle": "Live Monitoring",
  "media.live": "Live",
  "media.inactive": "Offline",
  "media.camera": "Camera",
  "media.screen": "Screen",
  "media.ready": "Connected",
  "media.offline": "Off",
  "media.cameraUnavailable": "Camera is not enabled",
  "media.screenUnavailable": "Screen share is not enabled",
};

const dictionaries: Record<Locale, TranslationDict> = { zh, en };
const LOCALE_KEY = "sb_locale";

// ── Context ──
interface I18nContextValue {
  locale: Locale;
  setLocale: (l: Locale) => void;
  t: (key: string) => string;
}

const I18nContext = createContext<I18nContextValue | null>(null);

/** Detect browser language; fallback to 'zh' */
function detectLocale(): Locale {
  const stored = localStorage.getItem(LOCALE_KEY);
  if (stored === "zh" || stored === "en") {
    return stored;
  }
  const lang = navigator.language.toLowerCase();
  if (lang.startsWith("zh")) return "zh";
  return "en";
}

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocale] = useState<Locale>(detectLocale);

  const setLocaleWithPersist = useCallback((nextLocale: Locale) => {
    localStorage.setItem(LOCALE_KEY, nextLocale);
    setLocale(nextLocale);
  }, []);

  const t = useCallback(
    (key: string): string => {
      return dictionaries[locale][key] ?? key;
    },
    [locale],
  );

  const value = useMemo(() => ({ locale, setLocale: setLocaleWithPersist, t }), [locale, setLocaleWithPersist, t]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

/** Hook to access translations */
export function useI18n(): I18nContextValue {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used inside <I18nProvider>");
  return ctx;
}
