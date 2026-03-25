/* ────────────────────────────────────────────────
 *  StreamingAudioPlayer  –  Gapless AudioContext-based playback
 *
 *  Instead of creating a new HTMLAudioElement per chunk (which introduces
 *  audible gaps / artifacts at boundaries), this class decodes incoming
 *  WAV chunks into AudioBuffers and schedules them back-to-back using
 *  AudioBufferSourceNode.start(time).  The Web Audio API guarantees
 *  sample-accurate timing, producing seamless audio.
 *
 *  Usage:
 *    const player = new StreamingAudioPlayer();
 *    player.feed(base64Wav);   // call for each chunk
 *    player.end();             // signal no more chunks
 *    await player.waitComplete();
 *    player.dispose();
 * ──────────────────────────────────────────────── */

const TTS_SAMPLE_RATE = 24_000;
/** Minimum schedule-ahead time to prevent late-start glitches */
const SCHEDULE_AHEAD_S = 0.02;

export class StreamingAudioPlayer {
  private ctx: AudioContext;
  private analyser: AnalyserNode;
  private nextTime = 0;
  private pendingCount = 0;
  private ended = false;
  private disposed = false;
  private completionCallbacks: Array<() => void> = [];
  /** Sequential feed queue – ensures decoding order even with async ops */
  private feedChain: Promise<void> = Promise.resolve();

  constructor() {
    const AudioCtx =
      window.AudioContext ||
      (window as Window & { webkitAudioContext?: typeof AudioContext })
        .webkitAudioContext;
    this.ctx = new AudioCtx({ sampleRate: TTS_SAMPLE_RATE });
    this.analyser = this.ctx.createAnalyser();
    this.analyser.fftSize = 1024;
    this.analyser.smoothingTimeConstant = 0.55;
    this.analyser.connect(this.ctx.destination);
  }

  // ── public API ────────────────────────────────────────────

  /** Decode and schedule a base64-encoded WAV chunk for gapless playback. */
  feed(base64Wav: string): void {
    if (this.disposed) return;
    this.pendingCount++;
    this.feedChain = this.feedChain
      .then(() => this.decodeFeed(base64Wav))
      .catch((err) => {
        console.error("[StreamingAudioPlayer] feed error", err);
        this.pendingCount--;
        this.checkCompletion();
      });
  }

  /** Signal that no more chunks will arrive. */
  end(): void {
    this.ended = true;
    this.checkCompletion();
  }

  /** Returns a promise that resolves when all scheduled audio has finished. */
  waitComplete(): Promise<void> {
    if (this.ended && this.pendingCount <= 0) return Promise.resolve();
    return new Promise((resolve) => this.completionCallbacks.push(resolve));
  }

  /** Read current RMS lip-sync value from the analyser (0–1). */
  getLipSyncValue(gain: number): number {
    if (this.disposed) return 0;
    const samples = new Uint8Array(this.analyser.fftSize);
    this.analyser.getByteTimeDomainData(samples);
    let sum = 0;
    for (let i = 0; i < samples.length; i++) {
      const centered = (samples[i] - 128) / 128;
      sum += centered * centered;
    }
    const rms = Math.sqrt(sum / samples.length);
    return Math.min(1.0, rms * gain * 8.0);
  }

  /** Stop all scheduled audio immediately. */
  interrupt(): void {
    this.ended = true;
    this.pendingCount = 0;
    this.fireCompletion();
    this.dispose();
  }

  /** Release AudioContext resources. */
  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    try {
      void this.ctx.close();
    } catch {
      /* ignore */
    }
  }

  get isActive(): boolean {
    return !this.disposed && (!this.ended || this.pendingCount > 0);
  }

  // ── internal ──────────────────────────────────────────────

  private async decodeFeed(base64Wav: string): Promise<void> {
    if (this.disposed) {
      this.pendingCount--;
      return;
    }

    // Resume suspended context (browser autoplay policy)
    if (this.ctx.state === "suspended") {
      await this.ctx.resume();
    }

    // Decode base64 → ArrayBuffer
    const binary = atob(base64Wav);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {
      bytes[i] = binary.charCodeAt(i);
    }

    const audioBuffer = await this.ctx.decodeAudioData(bytes.buffer);
    if (this.disposed) {
      this.pendingCount--;
      return;
    }

    const source = this.ctx.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(this.analyser);

    // Schedule gaplessly: start right after previous chunk ends.
    // If we've fallen behind (nextTime < currentTime), start ASAP with
    // a tiny lookahead to avoid late-scheduling glitches.
    const now = this.ctx.currentTime;
    const startAt = Math.max(now + SCHEDULE_AHEAD_S, this.nextTime);
    this.nextTime = startAt + audioBuffer.duration;
    source.start(startAt);

    source.onended = () => {
      this.pendingCount--;
      this.checkCompletion();
    };
  }

  private checkCompletion(): void {
    if (this.ended && this.pendingCount <= 0) {
      this.fireCompletion();
    }
  }

  private fireCompletion(): void {
    const cbs = this.completionCallbacks;
    this.completionCallbacks = [];
    for (const cb of cbs) cb();
  }
}
