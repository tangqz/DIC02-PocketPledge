/**
 * Global type declarations for Cubism Core.
 * `live2dcubismcore.min.js` is loaded via <script> tag (IIFE)
 * and attaches `Live2DCubismCore` to `window`.
 */

// eslint-disable-next-line @typescript-eslint/no-namespace
declare namespace Live2DCubismCore {
  class Version {
    static csmGetVersion(): number;
    static csmGetLatestMocVersion(): number;
  }

  class Logging {
    static csmSetLogFunction(handler: (message: string) => void): void;
    static csmGetLogFunction(): (message: string) => void;
  }

  class Memory {
    static initialize(size: number): void;
    static dispose(): void;
  }

  class Moc {
    static fromArrayBuffer(buffer: ArrayBuffer): Moc;
    release(): void;
  }

  class Model {
    static fromMoc(moc: Moc): Model;
    update(): void;
    release(): void;

    readonly parameters: Parameters;
    readonly parts: Parts;
    readonly drawables: Drawables;
    readonly canvasinfo: CanvasInfo;
  }

  interface Parameters {
    count: number;
    ids: string[];
    maximumValues: Float32Array;
    minimumValues: Float32Array;
    defaultValues: Float32Array;
    values: Float32Array;
    types: Int32Array;
    keyCounts: Int32Array;
    keyValues: Float32Array[];
  }

  interface Parts {
    count: number;
    ids: string[];
    opacities: Float32Array;
    parentIndices: Int32Array;
  }

  interface Drawables {
    count: number;
    ids: string[];
    constantFlags: Uint8Array;
    dynamicFlags: Uint8Array;
    textureIndices: Int32Array;
    drawOrders: Int32Array;
    renderOrders: Int32Array;
    opacities: Float32Array;
    maskCounts: Int32Array;
    masks: Int32Array[];
    vertexCounts: Int32Array;
    vertexPositions: Float32Array[];
    vertexUvs: Float32Array[];
    indexCounts: Int32Array;
    indices: Uint16Array[];
    multiplyColors: Float32Array;
    screenColors: Float32Array;
    parentPartIndices: Int32Array;
    resetDynamicFlags(): void;
  }

  interface CanvasInfo {
    CanvasWidth: number;
    CanvasHeight: number;
    CanvasOriginX: number;
    CanvasOriginY: number;
    PixelsPerUnit: number;
  }
}

interface Window {
  Live2DCubismCore: typeof Live2DCubismCore;
}
