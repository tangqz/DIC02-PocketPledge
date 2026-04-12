import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "path";
import basicSsl from "@vitejs/plugin-basic-ssl";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss(), basicSsl()],
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
    host: true,
    port: 5173,
    https: {},
    proxy: {
      '/api': {
        target: 'http://0.0.0.0:12393',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://0.0.0.0:12393',
        ws: true,
      },
    },
  },
});
