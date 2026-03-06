# DIC02-PocketPledge

本仓库当前主要开发入口是前端项目：`frontend/`（React + TypeScript + Vite）。

## 前端安装与运行

### 1) 环境要求

- Node.js 20+
- npm 10+

### 2) 安装依赖

在仓库根目录执行：

```bash
cd frontend
npm install
```

### 3) 启动开发环境

打开两个终端：

终端 A（前端页面）：

```bash
cd frontend
npm run dev
```

终端 B（本地 Mock WebSocket 服务，可选）：

```bash
cd frontend
npm run mock
```

默认行为：

- 前端默认连接 `ws://localhost:12393/ws`
- 如果你有真实后端，也可不启动 `mock`，直接让真实后端监听该地址

### 4) 生产构建与预览

```bash
cd frontend
npm run build
npm run preview
```

### 5) 常用脚本

- `npm run dev`：启动 Vite 开发服务器
- `npm run mock`：启动本地 WebSocket Mock 服务
- `npm run build`：类型检查 + 生产打包
- `npm run preview`：预览打包产物
- `npm run lint`：运行 ESLint
