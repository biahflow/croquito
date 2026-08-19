import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// O build servido em homologação vive em `/revisao/` (o nginx do host público serve as
// duas SPAs em subrotas da mesma origem), então os assets precisam nascer com esse
// prefixo. Em desenvolvimento a base continua `/`: o `vite dev` é servido na raiz da
// porta 5173 e nada da rotina local muda.
export default defineConfig(({ mode }) => ({
  base: mode === "development" ? "/" : "/revisao/",
  plugins: [react()],
  build: {
    rollupOptions: {
      // Dois HTMLs, UM build (ADR-0028 D9 preservado): o segundo entry é a página mínima
      // do callback de renovação silenciosa — sem ele o iframe carregaria a SPA inteira,
      // que foi o defeito do incidente de 2026-08-19.
      input: {
        main: "index.html",
        "silent-renew": "silent-renew.html"
      }
    }
  },
  server: {
    port: 5173,
    strictPort: true
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"]
  }
}));
