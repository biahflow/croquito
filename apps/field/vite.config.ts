import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { VitePWA } from "vite-plugin-pwa";

// PWA offline-first (ADR-0043, D1/D2): precache do shell da app e manifest mínimo para
// instalação no aparelho do técnico. Nenhum ícone baixado — `public/icon.svg` é gerado no
// próprio repo.
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["icon.svg"],
      manifest: {
        name: "croquito campo",
        short_name: "croquito campo",
        description: "Coleta estruturada de levantamento em campo, offline-first.",
        start_url: "/",
        display: "standalone",
        background_color: "#0f172a",
        theme_color: "#0f172a",
        icons: [
          {
            src: "/icon.svg",
            sizes: "any",
            type: "image/svg+xml",
            purpose: "any maskable",
          },
        ],
      },
      workbox: {
        globPatterns: ["**/*.{js,css,html,svg}"],
      },
    }),
  ],
  build: {
    rollupOptions: {
      // Dois HTMLs, um build (mesmo padrão de `apps/web/vite.config.ts`): o segundo
      // entry é a página mínima do callback de renovação silenciosa do OIDC (Task
      // Contract T10) — sem ela o iframe oculto carregaria o app inteiro e nunca
      // responderia ao pai (incidente de 2026-08-19 documentado em
      // `apps/web/src/auth.ts`).
      input: {
        main: "index.html",
        "silent-renew": "silent-renew.html",
      },
    },
  },
  server: {
    port: 5174,
    strictPort: true,
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
    setupFiles: ["./src/testSetup.ts"],
  },
});
