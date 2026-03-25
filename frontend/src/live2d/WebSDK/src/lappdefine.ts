/**
 * Copyright(c) Live2D Inc. All rights reserved.
 *
 * Use of this source code is governed by the Live2D Open Software license
 * that can be found at https://www.live2d.com/eula/live2d-open-software-license-agreement_en.html.
 */

import { LogLevel } from '@framework/live2dcubismframework';

/**
 * Sample Appで使用する定数
 */

// Canvas width and height pixel values, or dynamic screen size ('auto').
export const CanvasSize: { width: number; height: number } | 'auto' = 'auto';

// 画面
export const ViewScale = 1.0;
export let CurrentKScale = ViewScale;
export const ViewMaxScale = 2.0;
export const ViewMinScale = 0.8;

export const ViewLogicalLeft = -1.0;
export const ViewLogicalRight = 1.0;
export const ViewLogicalBottom = -1.0;
export const ViewLogicalTop = 1.0;

export const ViewLogicalMaxLeft = -2.0;
export const ViewLogicalMaxRight = 2.0;
export const ViewLogicalMaxBottom = -2.0;
export const ViewLogicalMaxTop = 2.0;

// Dynamic resource path that will be set by the model loader
export let ResourcesPath = "";

// Model directory and filename storage
export let ModelDir: string[] = [];
export let ModelFileNames: string[] = []; // New array to store model file names

// Function to update model configuration with both directory and file name
export function updateModelConfig(resourcePath: string, modelDirectory: string, modelFileName: string, kScale?: number) {
  const normalizedResourcePath = resourcePath.endsWith('/') ? resourcePath : `${resourcePath}/`;
  const normalizedModelDirectory = modelDirectory.replace(/^\/+|\/+$/g, '');
  const normalizedModelFileName = modelFileName.replace(/\.model3\.json$/i, '');

  console.log('Updating model config:', {
    resourcePath: normalizedResourcePath,
    modelDirectory: normalizedModelDirectory,
    modelFileName: normalizedModelFileName,
    kScale,
  });
  ResourcesPath = normalizedResourcePath;
  ModelDir = [normalizedModelDirectory];
  ModelFileNames = [normalizedModelFileName];
  if (kScale !== undefined) {
    CurrentKScale = kScale;
  }
  // Update ModelDirSize when ModelDir changes
  ModelDirSize = ModelDir.length;
}

// Export ModelDirSize as a variable instead of a constant
export let ModelDirSize = ModelDir.length;

// モデルの後ろにある背景の画像ファイル
export const BackImageName = 'back_class_normal.png';

// 歯車
export const GearImageName = 'icon_gear.png';

// 終了ボタン
export const PowerImageName = 'CloseNormal.png';

// モデル定義---------------------------------------------
// モデルを配置したディレクトリ名の配列
// ディレクトリ名とmodel3.jsonの名前を一致させておくこと

// 外部定義ファイル（json）と合わせる
// 外部定义文件（json）与之匹配
export const MotionGroupIdle = 'Idle'; // アイドリング  // 空闲
export const MotionGroupTapBody = 'TapBody'; // 体をタップしたとき  // 点击身体时

// 外部定義ファイル（json）と合わせる
// 外部定义文件（json）与之匹配
export const HitAreaNameHead = 'Head';
export const HitAreaNameBody = 'Body';

// モーションの優先度定数
// 动作优先级常数
export const PriorityNone = 0;
export const PriorityIdle = 1;
export const PriorityNormal = 2;
export const PriorityForce = 3;

// MOC3の一貫性検証オプション
// MOC3一致性验证选项
export const MOCConsistencyValidationEnable = true;

// デバッグ用ログの表示オプション
// 调试用日志显示选项
export const DebugLogEnable = false;
export const DebugTouchLogEnable = false;

// Frameworkから出力するログのレベル設定
// 设置Framework输出的日志级别
export const CubismLoggingLevel = LogLevel.LogLevel_Verbose;

// デフォルトのレンダーターゲットサイズ
// 默认的渲染目标大小
export const RenderTargetWidth = 1900;
export const RenderTargetHeight = 1000;

export const ENABLE_LIMITED_FRAME_RATE = true;
export const LIMITED_FRAME_RATE = 60;
export const ModelInteractionDragThreshold = 14;
export const ModelInteractionDragSensitivity = 0.3;
export const ModelInteractionWheelScaleStep = 0.05;
export const ModelInteractionMinScale = 0.15;
export const ModelInteractionMaxScale = 8.0;

export interface HitAreaTapAction {
  motion: string;
  expression: string;
}

export let TapMotions: Record<string, HitAreaTapAction> = {};
export let RuntimeEmotionMap: Record<string, number> = {};

export function updateInteractionConfig(
  tapMotions: Record<string, HitAreaTapAction> | undefined,
  emotionMap: Record<string, number> | undefined,
): void {
  TapMotions = { ...(tapMotions ?? {}) };
  RuntimeEmotionMap = { ...(emotionMap ?? {}) };
}

/**
 * Callback invoked when the user taps on the Live2D model's hit area.
 * Set by the React layer to bridge into the chat system.
 */
let _onModelTapped: ((hitArea: string) => void) | null = null;

export function setOnModelTapped(cb: ((hitArea: string) => void) | null): void {
  _onModelTapped = cb;
}

export function fireModelTapped(hitArea: string): void {
  _onModelTapped?.(hitArea);
}