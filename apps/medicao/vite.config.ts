import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    // 5174 é a porta que o servidor local de homologação libera no CORS; mudá-la aqui
    // sem mudar `LOCAL_WEB_ORIGINS` deixaria a UI sem falar com o servidor.
    port: 5174,
    strictPort: true
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"]
  }
});
