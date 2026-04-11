// @ts-nocheck
/**
 * Copyright(c) Live2D Inc. All rights reserved.
 *
 * Use of this source code is governed by the Live2D Open Software license
 * that can be found at https://www.live2d.com/eula/live2d-open-software-license-agreement_en.html.
 */

import { CubismMatrix44 } from '@framework/math/cubismmatrix44';
import { ACubismMotion } from '@framework/motion/acubismmotion';
import { csmVector } from '@framework/type/csmvector';

import * as LAppDefine from './lappdefine';
import { canvas } from './lappglmanager';
import { LAppModel } from './lappmodel';
import { LAppPal } from './lapppal';

export let s_instance: LAppLive2DManager | null | undefined = null;

/**
 * サンプルアプリケーションにおいてCubismModelを管理するクラス
 * モデル生成と破棄、タップイベントの処理、モデル切り替えを行う。
 * 
 * 在示例应用程序中管理CubismModel的类
 * 执行模型生成和销毁、触摸事件处理、模型切换。
 */
export class LAppLive2DManager {
  /**
   * クラスのインスタンス（シングルトン）を返す。
   * インスタンスが生成されていない場合は内部でインスタンスを生成する。
   * 
   * 返回类的实例（单例）。
   * 如果尚未创建实例，则在内部创建实例。
   *
   * @return クラスのインスタンス
   */
  public static getInstance(): LAppLive2DManager {
    if (s_instance == null) {
      s_instance = new LAppLive2DManager();
    }

    return s_instance;
  }

  /**
   * クラスのインスタンス（シングルトン）を解放する。
   * 
   * 释放类的实例（单例）。
   */
  public static releaseInstance(): void {
    if (s_instance != null) {
      s_instance = void 0;
    }

    s_instance = null;
  }

  /**
   * 現在のシーンで保持しているモデルを返す。
   *
   * @param no モデルリストのインデックス値
   * @return モデルのインスタンスを返す。インデックス値が範囲外の場合はNULLを返す。
   */
  public getModel(no: number): LAppModel | null {
    if (no < this._models.getSize()) {
      return this._models.at(no);
    }

    return null;
  }

  /**
   * 現在のシーンで保持しているすべてのモデルを解放する
   */
  public releaseAllModel(): void {
    for (let i = 0; i < this._models.getSize(); i++) {
      this._models.at(i).release();
      this._models.set(i, null);
    }

    this._models.clear();
  }

  /**
   * 画面をドラッグした時の処理
   * 
   * 当拖动屏幕时的处理
   *
   * @param x 画面のX座標
   * @param y 画面のY座標
   */
  public onDrag(x: number, y: number): void {
    for (let i = 0; i < this._models.getSize(); i++) {
      const model: LAppModel = this.getModel(i)!;

      if (model) {
        model.setDragging(x, y);
      }
    }
  }

  /**
   * 画面をタップした時の処理
   *
   * @param x 画面のX座標
   * @param y 画面のY座標
   */
  public onTap(x: number, y: number): void {
    if (LAppDefine.DebugLogEnable) {
      LAppPal.printMessage(
        `[APP]tap point: {x: ${x.toFixed(2)} y: ${y.toFixed(2)}}`
      );
    }

    const classifyHorizontal = (viewX: number): 'Left' | 'Right' | 'Center' => {
      if (viewX <= -0.25) {
        return 'Left';
      }
      if (viewX >= 0.25) {
        return 'Right';
      }
      return 'Center';
    };

    const classifyHeadTapRegion = (viewX: number, viewY: number): string => {
      const horizontal = classifyHorizontal(viewX);

      if (viewY > 0.9) {
        return horizontal === 'Center' ? 'Head.Forehead' : `Head.Forehead${horizontal}`;
      }

      if (viewY < 0.3) {
        return horizontal === 'Center' ? 'Head.Cheek' : `Head.Cheek${horizontal}`;
      }

      return horizontal === 'Center' ? 'Head' : `Head.${horizontal}`;
    };

    const classifyBodyTapRegion = (viewX: number, viewY: number): string => {
      const horizontal = classifyHorizontal(viewX);

      if (viewY > 0.45) {
        return horizontal === 'Center' ? 'Body.Chest' : `Body.Shoulder${horizontal}`;
      }

      if (viewY > -0.05) {
        return horizontal === 'Center' ? 'Body.UpperTorso' : `Body.Arm${horizontal}`;
      }

      if (viewY > -0.5) {
        return horizontal === 'Center' ? 'Body.Waist' : `Body.Waist${horizontal}`;
      }

      if (viewY > -0.95) {
        return horizontal === 'Center' ? 'Body.Thigh' : `Body.Leg${horizontal}`;
      }

      return horizontal === 'Center' ? 'Body.Foot' : `Body.Foot${horizontal}`;
    };

    const fireCoarseRegionTap = (viewX: number, viewY: number): void => {
      // Fallback route for models whose built-in hit areas only cover upper body.
      if (viewY > 0.38) {
        LAppDefine.fireModelTapped(classifyHeadTapRegion(viewX, viewY));
        return;
      }
      LAppDefine.fireModelTapped(classifyBodyTapRegion(viewX, viewY));
    };

    for (let i = 0; i < this._models.getSize(); i++) {
      const model = this._models.at(i);
      if (!model || !model.getModel()) {
        continue;
      }
      const hitAreaId = model.anyhitTest(x, y);

      const applySemanticExpression = (emotionKeyword: string): void => {
        if (!emotionKeyword) {
          return;
        }
        const normalized = emotionKeyword.toLowerCase();
        const expressionIndex = LAppDefine.RuntimeEmotionMap[normalized];
        if (expressionIndex == null || !model._modelSetting) {
          return;
        }
        const expressionName = model._modelSetting.getExpressionName(expressionIndex);
        if (expressionName) {
          model.setExpression(expressionName);
        }
      };

      const playConfiguredTapMotion = (hitAreaId: string): boolean => {
        const action = LAppDefine.TapMotions[hitAreaId];
        if (!action) {
          return false;
        }

        if (action.expression) {
          applySemanticExpression(action.expression);
        }

        if (action.motion) {
          const motionCount = model._modelSetting?.getMotionCount(action.motion) ?? 0;
          if (motionCount > 0) {
            const randomIndex = Math.floor(Math.random() * motionCount);
            model.startMotion(action.motion, randomIndex, LAppDefine.PriorityNormal, this._finishedMotion);
            return true;
          }
        }

        return false;
      };

      const playDefaultBodyTapMotion = (): void => {
        model.startRandomMotion(
          LAppDefine.MotionGroupTapBody,
          LAppDefine.PriorityNormal,
          this._finishedMotion
        );
      };

      if (hitAreaId === 'HitAreaHead' || model.hitTest(LAppDefine.HitAreaNameHead, x, y)) {
        if (LAppDefine.DebugLogEnable) {
          LAppPal.printMessage(
            `[APP]hit area: [${LAppDefine.HitAreaNameHead}]`
          );
        }
        const usedConfig = playConfiguredTapMotion('HitAreaHead');
        if (!usedConfig) {
          model.setRandomExpression();
        }
        LAppDefine.fireModelTapped(classifyHeadTapRegion(x, y));
      } else if (hitAreaId === 'HitAreaBody' || model.hitTest(LAppDefine.HitAreaNameBody, x, y)) {
        if (LAppDefine.DebugLogEnable) {
          LAppPal.printMessage(
            `[APP]hit area: [${LAppDefine.HitAreaNameBody}]`
          );
        }
        const usedConfig = playConfiguredTapMotion('HitAreaBody');
        if (!usedConfig) {
          playDefaultBodyTapMotion();
        }
        LAppDefine.fireModelTapped(classifyBodyTapRegion(x, y));
      } else if (model.isHitOnModel(x, y)) {
        // Generic mesh hit fallback: still allow full-body interaction even when
        // model3 HitArea only defines head/body around upper torso.
        const usedBodyConfig = playConfiguredTapMotion('HitAreaBody');
        if (!usedBodyConfig) {
          playDefaultBodyTapMotion();
        }
        fireCoarseRegionTap(x, y);
      }
    }
  }

  /**
   * 画面を更新するときの処理
   * モデルの更新処理及び描画処理を行う
   */
  public onUpdate(): void {
    if (!canvas) {
      return;
    }
    const { width, height } = canvas;

    const modelCount: number = this._models.getSize();

    for (let i = 0; i < modelCount; ++i) {
      const projection: CubismMatrix44 = new CubismMatrix44();
      const model: LAppModel = this.getModel(i);

      if (!model) {
        continue;
      }

      if (model.getModel()) {
        if (model.getModel().getCanvasWidth() > 1.0 && width < height) {
          // 横に長いモデルを縦長ウィンドウに表示する際モデルの横サイズでscaleを算出する
          model.getModelMatrix().setWidth(2.0);
          projection.scale(1.0, width / height);
        } else {
          projection.scale(height / width, 1.0);
        }

        // 必要があればここで乗算
        if (this._viewMatrix != null) {
          projection.multiplyByMatrix(this._viewMatrix);
        }
      }

      model.update();
      model.draw(projection); // 参照渡しなのでprojectionは変質する。
    }
  }

  /**
   * 次のシーンに切りかえる
   * サンプルアプリケーションではモデルセットの切り替えを行う。
   */
  public nextScene(): void {
    const no: number = (this._sceneIndex + 1) % LAppDefine.ModelDirSize;
    this.changeScene(no);
  }

  /**
   * シーンを切り替える
   * サンプルアプリケーションではモデルセットの切り替えを行う。
   */
  public changeScene(index: number): void {
    if (!LAppDefine.ModelDir.length || !LAppDefine.ModelDir[index]) {
      return;
    }
    this._sceneIndex = index;
    if (LAppDefine.DebugLogEnable) {
      LAppPal.printMessage(`[APP]model index: ${this._sceneIndex}`);
    }

    // Use the directory name and file name from our configuration
    const model: string = LAppDefine.ModelDir[index];
    const resourcePath = LAppDefine.ResourcesPath.endsWith('/')
      ? LAppDefine.ResourcesPath
      : `${LAppDefine.ResourcesPath}/`;
    const modelPath: string = `${resourcePath}${model}/`;
    
    // Use ModelFileNames if available, otherwise fall back to ModelDir
    let modelJsonName: string = LAppDefine.ModelFileNames && 
                                LAppDefine.ModelFileNames[index] ? 
                                LAppDefine.ModelFileNames[index] : 
                                LAppDefine.ModelDir[index];

    if (!modelJsonName.endsWith('.model3.json')) {
      modelJsonName += '.model3.json';
    }

    if (LAppDefine.DebugLogEnable) {
      LAppPal.printMessage(`[APP]model path: ${modelPath}${modelJsonName}`);
    }

    this.releaseAllModel();
    this._models.pushBack(new LAppModel());
    this._models.at(0).loadAssets(modelPath, modelJsonName);
  }

  public setViewMatrix(m: CubismMatrix44) {
    if (!this._viewMatrix || !m) {
      return;
    }
    for (let i = 0; i < 16; i++) {
      this._viewMatrix.getArray()[i] = m.getArray()[i];
    }
  }

  /**
   * コンストラクタ
   */
  constructor() {
    this._viewMatrix = new CubismMatrix44();
    this._models = new csmVector<LAppModel>();
    this._sceneIndex = 0;
    this.changeScene(this._sceneIndex);
  }

  _viewMatrix: CubismMatrix44; // モデル描画に用いるview行列
  _models: csmVector<LAppModel>; // モデルインスタンスのコンテナ
  _sceneIndex: number; // 表示するシーンのインデックス値
  // モーション再生終了のコールバック関数
  _finishedMotion = (self: ACubismMotion): void => {
    LAppPal.printMessage('Motion Finished:');
    console.log(self);
  };
}
