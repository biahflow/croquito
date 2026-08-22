import { readFileSync } from "node:fs";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { VitePWA } from "vite-plugin-pwa";

/**
 * TLS do servidor de DEV (teste em aparelho real na rede local): câmera, microfone e
 * instalação de PWA exigem origem segura no celular. Com
 * `CROQUITO_DEV_TLS_CERT`/`CROQUITO_DEV_TLS_KEY` apontando para um par mkcert, o dev
 * server sobe em https e aceita conexões da LAN. Sem as envs, nada muda (localhost http,
 * como sempre). Só afeta `vite dev` — o build de produção ignora `server.*`.
 */
const devTlsCert = process.env.CROQUITO_DEV_TLS_CERT;
const devTlsKey = process.env.CROQUITO_DEV_TLS_KEY;
const devHttps =
  devTlsCert && devTlsKey
    ? { cert: readFileSync(devTlsCert), key: readFileSync(devTlsKey) }
    : undefined;

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
        // Grafite da marca (T17, DAP rev.2) — mesmo fundo do `icon.svg` e de
        // `--color-dark` (apps/field/src/styles.css), substituindo o azul do scaffold.
        background_color: "#0e1116",
        theme_color: "#0e1116",
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
    // LAN + https quando o par de TLS de dev está presente (teste em aparelho real).
    host: devHttps ? true : undefined,
    https: devHttps,
    // O celular fala https com o dev server; a API local é http. O proxy evita mixed
    // content: o app chama `${origin}/v1/...` e o dev server repassa para a API.
    proxy: {
      "/v1": {
        target: process.env.CROQUITO_DEV_API_TARGET ?? "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
    setupFiles: ["./src/testSetup.ts"],
  },
});
