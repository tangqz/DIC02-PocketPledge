import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "path";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
      "@framework": path.resolve(
        __dirname,
        "src/live2d/WebSDK/Framework/src",
      ),
      "@cubismsdksamples": path.resolve(__dirname, "src/live2d/WebSDK/src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      // Proxy WebSocket connections to local backend in development.
      // In Docker production the nginx reverse proxy handles this instead.
      "/ws": {
        target: "http://localhost:12393",
        ws: true,
        changeOrigin: true,
      },
      "/api": {
        target: "http://localhost:12393",
        changeOrigin: true,
      },
    },
  },
});
