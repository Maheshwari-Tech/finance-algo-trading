import { defineConfig } from "vite";

export default defineConfig({
  // API_PORT is set by scripts/dev.sh; 8123 otherwise.
  server: { port: 5173, proxy: { "/api": `http://127.0.0.1:${process.env.API_PORT ?? "8123"}` } },
});
