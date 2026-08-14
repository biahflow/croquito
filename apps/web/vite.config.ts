import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// O build servido em homologação vive em `/revisao/` (o nginx do host público serve as
// duas SPAs em subrotas da mesma origem), então os assets precisam nascer com esse
// prefixo. Em desenvolvimento a base continua `/`: o `vite dev` é servido na raiz da
// porta 5173 e nada da rotina local muda.
export default defineConfig(({ mode }) => ({
  base: mode === "development" ? "/" : "/revisao/",
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"]
  }
}));
