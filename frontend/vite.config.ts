import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: "127.0.0.1",
    proxy: {
      "/api": process.env.VITE_API_PROXY ?? "http://localhost:8000",
      "/health": process.env.VITE_API_PROXY ?? "http://localhost:8000",
    },
  },
});
