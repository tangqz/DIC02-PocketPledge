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
  },
});
