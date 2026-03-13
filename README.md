# PocketPledge

<div align="center">
  <img src="imgs/logo.jpg" alt="PocketPledge Logo" width="400" />
</div>

<div align="center">
  <strong>PocketPledge</strong> is a hardcore AI companion and supervision system designed for study monitoring scenarios.<br>
  Combining <b>Live2D virtual avatars</b>, <b>real-time voice conversation</b>, <b>visual state analysis</b>, and a <b>financial penalty mechanism</b>, it creates a comprehensive and immersive study experience for you.<br>
  <i>End your moments of distraction with the cost of real money!</i>
</div>

<div align="center">
  <a href="README-zh.md">简体中文</a>
</div>

---

## 🌟 Core Charms & Features

PocketPledge breaks the dullness and rigidity of traditional time management software, perfectly blending "companionship" and "supervision":

- 🎭 **Live2D Virtual Companion**: Say goodbye to cold countdown timers! The system provides an interactive virtual companion frontend interface that supports synchronized expressions and movements, accompanying you throughout your long study sessions.
- 🗣️ **Ultra-fast Real-time Voice Conversation**: Through a combination of powerful local ASR (Sherpa-ONNX) and cloud TTS, coupled with the proxy model's reasoning, it achieves low-latency voice streaming. Thinking about slacking off? Your companion won't just remind you verbally, but will also hit you with some soul-searching questions.
- 👁️ **Hardcore Visual Distraction Detection**: Frequently checking your phone or leaving your seat while studying? The system uses non-linear sparse sampling from your camera and screen, powered by a robust multimodal AI for **real-time state analysis** to accurately catch your every distraction.
- 💰 **Financial Supervision (The Real Money Test)**: Once caught distracted by the AI and refusing to correct your behavior, a specific fine will be deducted immediately. The realistic balance settlement mechanism builds the strongest defense line for concentration through the pain of losing money.

## 📁 Directory Structure & Tech Stack Overview

- **Frontend (`frontend/`)**: React + TypeScript + Vite, Tailwind CSS v4 (pure `@theme` driven without `tailwind.config.js`), Zustand for state management. Responsible for chat UI, Live2D display, audio recording, and WebSocket communication.
- **Backend (`backend/`)**: FastAPI + Python 3.12, SQLAlchemy. Responsible for core business logic (wallet, penalty settlement), WebSocket gateway routing, local ASR inference, and TTS forwarding. Fully embraces `uv` for ultra-fast package management and execution.
- **Documentation (`docs/`)**: REST API standards and WebSocket protocol documentation.

---

## 🚀 Quick Start & Installation Guide

**Important Note: This project heavily relies on a local ASR model (Sherpa-ONNX). Please be sure to completely download and place the model files according to the guide below.**

### 0. Prerequisites

- **Node.js**: `v20+` and strictly use `pnpm` (`npm` and `yarn` are prohibited in this project).
- **Python**: `3.12+` (Using `uv` for environment and package management is recommended).

### 1. Prepare the Local ASR Model (Sherpa-ONNX SenseVoice)

To achieve ultra-low latency voice interaction, the microphone audio stream is sent to the backend in real-time via WebSocket for local ASR transcription.

1. **Download the model**:
   Go to the official Sherpa-ONNX repository or HuggingFace to get the corresponding model package (`sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17`).
2. **Confirm files are ready**:
   After extracting, make sure the package contains the following key files, and note down their **absolute paths**:
   - `model.int8.onnx`
   - `tokens.txt`

### 2. Backend Configuration & Startup

Enter the backend directory and use `uv` for environment installation and management:

```bash
cd backend
# Install dependencies using uv
uv pip install -r requirements.txt

```

**Configure Environment Variables (`backend/.env`)**:

Copy `.env.example` in the `backend` directory, rename it to `.env`, and fill in your actual configurations:

```env
# Enable local proxy model architecture
AGENT_BACKEND=local

# ----------------- ASR Model Paths -----------------
# (Strictly replace with the actual absolute paths of your extracted files)
MEDIA_AI_SHERPA_MODEL_PATH="/absolute/path/to/sherpa-onnx/model.int8.onnx"
MEDIA_AI_SHERPA_TOKENS_PATH="/absolute/path/to/sherpa-onnx/tokens.txt"

# ----------------- AI Model Configs (Customizable) -----------------
# Chat model configuration
LOCAL_CHAT_API_KEY="xxxxxxxxxxxxxxxxxxxxxxxx"
LOCAL_CHAT_API_BASE="[https://generativelanguage.googleapis.com/v1beta/openai/](https://generativelanguage.googleapis.com/v1beta/openai/)"
LOCAL_CHAT_MODEL="gemini-3.1-flash-lite-preview"

# Vision model configuration
LOCAL_VISION_API_KEY="sk-xxxxxxxxxxxxxxxxxxxxxxxx"
LOCAL_VISION_API_BASE="[https://dashscope.aliyuncs.com/compatible-mode/v1](https://dashscope.aliyuncs.com/compatible-mode/v1)"
LOCAL_VISION_MODEL="qwen3.5-flash"

# System proxy model configuration
LOCAL_AGENT_API_KEY="xxxxxxxxxxxxxxxxxxxxxxxx"
LOCAL_AGENT_API_BASE="[https://generativelanguage.googleapis.com/v1beta/openai/](https://generativelanguage.googleapis.com/v1beta/openai/)"
LOCAL_AGENT_MODEL="gemini-3.1-flash-lite-preview"

```

**Start Backend Service**:

```bash
cd backend
uv run uvicorn app.main:app --host 0.0.0.0 --port 12393 --reload

```

*Tip: The first startup will automatically initialize the database at `backend/reward.db` and create the necessary default accounts.*

**Supplementary Backend Configuration Table** (can override default behaviors in `.env`):

| Variable Name | Description | Default Value |
| --- | --- | --- |
| `DATABASE_URL` | Database file path | `sqlite:///./reward.db` |
| `AUTH_SECRET_KEY` | Auth JWT Secret | Randomly generated per single restart |
| `MEDIA_AI_TTS_PROVIDER` | Voice synthesis provider | `qwen-realtime` |
| `MEDIA_AI_SHERPA_MODEL_TYPE` | Local ASR model type | `sense_voice` |

*Note: If the ASR path is misconfigured or the files cannot be found, the system will not crash at runtime, but every voice input from the user will fallback to blank text.*

### 3. Frontend Configuration & Startup

Please ensure you have `pnpm` installed.

```bash
cd frontend
# Install dependencies
pnpm install

# Start the development server
pnpm run dev

```

Once started, open the corresponding local address in your browser (default is `http://localhost:5173/`). The frontend will automatically connect to `ws://localhost:12393/ws` via WebSocket.

> **Quick Start Tip (Dual-end Joint Startup, recommended for Windows users)**:
> After all dependencies and environments are ready, you can directly run `.\start-dev.cmd` in the project root directory. The script will automatically open dual consoles for joint startup.

---

## 💻 Developer Guide

We strongly welcome developers to contribute. Before submitting a PR, please ensure you follow the coding standards and testing requirements below:

### Frontend Development Commands

* **Code standard check**: `pnpm run lint` (Must ensure no errors before submitting a PR)
* **Run Mock server**: `pnpm run mock` (Used for testing frontend UI independently from the backend)
* **Build production package**: `pnpm run build`

### Backend Development Commands

* **Code formatting and Linting**: We use `ruff` as the sole formatting and static analysis tool:
```bash
cd backend
uv run ruff check .
uv run ruff format .

```


* **Run unit tests**: Use `pytest` to run all tests:
```bash
cd backend
PYTHONPATH=. uv run pytest

```



---

## 📚 Detailed Documentation & Resources

Want to dive deeper into the internal mechanisms and protocols of PocketPledge? Please refer to the following documents:

* 📄 **API Contract**: [docs/api_contract.md](https://www.google.com/search?q=docs/api_contract.md)
* 🔌 **Protocol Description**: [docs/ws_protocol.md](https://www.google.com/search?q=docs/ws_protocol.md)

## 🤝 Acknowledgments

* [Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber) provided valuable reference for the Live2D and voice interaction features of this project.

> *"Once you make a Pledge, please focus on the present."*
