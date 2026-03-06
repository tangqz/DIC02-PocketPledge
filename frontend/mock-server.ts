/* ────────────────────────────────────────────────
 *  Mock WebSocket Server  –  Simulates backend for frontend development
 *
 *  Run:  npx tsx mock-server.ts
 *  Provides fake responses for all RxMessage types.
 * ──────────────────────────────────────────────── */

// @ts-check
import { WebSocketServer, WebSocket } from "ws";

const PORT = 12393;
const wss = new WebSocketServer({ port: PORT, path: "/ws" });

console.log(`[Mock Server] Listening on ws://localhost:${PORT}/ws`);

// Minimal base64 WAV: 100ms of silence at 16kHz 16-bit mono
function generateSilentWav(durationMs = 500): string {
  const sampleRate = 16000;
  const bitsPerSample = 16;
  const numChannels = 1;
  const numSamples = Math.floor(sampleRate * (durationMs / 1000));
  const byteRate = (sampleRate * numChannels * bitsPerSample) / 8;
  const blockAlign = (numChannels * bitsPerSample) / 8;
  const dataLength = numSamples * blockAlign;
  const buffer = Buffer.alloc(44 + dataLength);

  // RIFF header
  buffer.write("RIFF", 0);
  buffer.writeUInt32LE(36 + dataLength, 4);
  buffer.write("WAVE", 8);
  buffer.write("fmt ", 12);
  buffer.writeUInt32LE(16, 16);
  buffer.writeUInt16LE(1, 20);
  buffer.writeUInt16LE(numChannels, 22);
  buffer.writeUInt32LE(sampleRate, 24);
  buffer.writeUInt32LE(byteRate, 28);
  buffer.writeUInt16LE(blockAlign, 32);
  buffer.writeUInt16LE(bitsPerSample, 34);
  buffer.write("data", 36);
  buffer.writeUInt32LE(dataLength, 40);
  // samples are all zeros (silence)

  return buffer.toString("base64");
}

const MOCK_RESPONSES = [
  {
    text: "你好！我是你的学习伙伴。让我们开始今天的学习吧！",
    expression: "happy",
  },
  {
    text: "看起来你在认真学习，做得很好！继续保持。",
    expression: "encouraging",
  },
  {
    text: "让我想想这个问题……我觉得你可以从另一个角度来思考。",
    expression: "neutral",
  },
  {
    text: "嗯，我注意到你可能有点分心了。要不要休息一下？",
    expression: "concerned",
  },
  {
    text: "太棒了！你回答得非常正确，我为你感到骄傲！",
    expression: "proud",
  },
];

let responseIndex = 0;

wss.on("connection", (ws) => {
  console.log("[Mock Server] Client connected");

  // Send initial model info
  ws.send(
    JSON.stringify({
      type: "model-info",
      model_info: {
        name: "mao_pro",
        url: "/live2d-models/mao_pro/mao_pro.model3.json",
        kScale: 0.5,
        emotionMap: {
          neutral: 0,
          happy: 3,
          encouraging: 4,
          concerned: 5,
          proud: 7,
        },
        idleMotionGroup: "Idle",
        talkMotionGroup: "",
      },
    }),
  );

  ws.on("message", (rawData) => {
    try {
      const msg = JSON.parse(rawData.toString());
      console.log("[Mock Server] Received:", msg.type);

      switch (msg.type) {
        case "text-input":
        case "mic-audio-end": {
          // Simulate processing delay
          setTimeout(() => {
            const resp = MOCK_RESPONSES[responseIndex % MOCK_RESPONSES.length];
            responseIndex++;

            // Send text chunk first
            ws.send(
              JSON.stringify({
                type: "agent-text-chunk",
                text: resp.text,
              }),
            );

            // Then send audio message
            setTimeout(() => {
              if (ws.readyState === WebSocket.OPEN) {
                ws.send(
                  JSON.stringify({
                    type: "audio",
                    audio: generateSilentWav(800),
                    actions: { expressions: [resp.expression] },
                    display_text: { text: resp.text, name: "Study Buddy" },
                  }),
                );
              }
            }, 300);
          }, 500);
          break;
        }

        case "periodic-screenshot": {
          // Randomly send balance updates
          if (Math.random() > 0.5) {
            const change = Math.random() > 0.3 ? -5 : 10;
            ws.send(
              JSON.stringify({
                type: "balance-update",
                balance: 100 + change,
                change,
                reason:
                  change < 0 ? "检测到注意力分散" : "保持专注奖励",
              }),
            );
          }
          break;
        }

        case "pause-request": {
          ws.send(
            JSON.stringify({
              type: "supervision-state-change",
              state: "paused",
            }),
          );
          break;
        }

        case "resume-request": {
          ws.send(
            JSON.stringify({
              type: "supervision-state-change",
              state: "active",
            }),
          );
          break;
        }

        case "frontend-playback-complete": {
          console.log("[Mock Server] Playback complete acknowledged");
          break;
        }

        default:
          break;
      }
    } catch (err) {
      console.warn("[Mock Server] Invalid message:", err);
    }
  });

  ws.on("close", () => {
    console.log("[Mock Server] Client disconnected");
  });
});
