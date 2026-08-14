import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Mesma regra do `apps/web`: o build de homologação é servido em `/medicao/` pelo nginx
// do host público, e em desenvolvimento a base segue `/`.
//
// A API deste app mora em `/medicao/api/` — dentro do prefixo da SPA. Quem separa os dois
// é o nginx (`location ^~ /medicao/api/` tem precedência sobre a SPA), e o Vite ajuda
// mantendo tudo o que ele gera sob `/medicao/assets/`.
export default defineConfig(({ mode }) => ({
  base: mode === "development" ? "/" : "/medicao/",
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
}));
