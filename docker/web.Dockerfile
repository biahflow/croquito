# syntax=docker/dockerfile:1

# Imagem da borda pública da homologação (`croquito-web-hml`): a SPA construída e um nginx
# que a serve em subrota e faz o proxy same-origin do resto (`deploy/nginx.conf`).
#
# Uma SPA só, com as duas jornadas dentro (ADR-0028, D9): uma sessão OIDC, um build, um
# `redirect_uri` a autorizar no realm. O contexto é a raiz do monorepo porque `npm ci`
# precisa do lock da raiz — o lock de um workspace não existe isolado.
#
# As quatro `VITE_*` abaixo são de BUILD: elas entram no bundle. Trocar qualquer uma delas
# é reconstruir a imagem, não reconfigurar o serviço. Nenhuma carrega segredo — são
# caminhos relativos da própria origem e o identificador público do client OIDC.

# ---------------------------------------------------------------------------
# Estágio de build: node com os workspaces resolvidos pelo lock da raiz
# ---------------------------------------------------------------------------
FROM node:22-slim AS builder

WORKDIR /app

# Manifests primeiro: mudança em código de app não invalida a instalação das dependências.
# Os dois workspaces precisam estar aqui — `npm ci` confere o lock contra cada um deles.
COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/package.json
COPY packages/contracts/package.json packages/contracts/package.json

# `npm ci` (nunca `npm install`): a esteira instala o que o lock versionado diz, e falha
# se o lock estiver fora de sincronia com os manifests.
RUN npm ci

COPY packages/contracts/ packages/contracts/
COPY apps/ apps/

# Base da API RELATIVA: o navegador fala com a mesma origem e quem sabe onde ficam os
# serviços internos é o nginx, não o bundle.
#
# A base própria da medição saiu daqui: as duas jornadas falam com a MESMA API `/v1`
# autenticada (ADR-0028), e a rodada de medição é recurso dela — não há mais um servidor
# de medição para o bundle endereçar.
ARG VITE_API_BASE_URL=/api
ARG VITE_OIDC_AUTHORITY=https://croquito-hml.biahflow.ai/auth/realms/croquito
ARG VITE_OIDC_CLIENT_ID=croquito-web

ENV VITE_API_BASE_URL=$VITE_API_BASE_URL \
    VITE_OIDC_AUTHORITY=$VITE_OIDC_AUTHORITY \
    VITE_OIDC_CLIENT_ID=$VITE_OIDC_CLIENT_ID

# `check` é `tsc -b && vite build`: o type check estrito roda ANTES do bundle, então erro
# de tipo reprova a imagem em vez de virar defeito de tela. A saída é `apps/web/dist`
# (base `/revisao/`), com as duas jornadas dentro (ADR-0028, D9).
RUN npm run web:check

# ---------------------------------------------------------------------------
# Runtime: nginx servindo as duas SPAs e o proxy same-origin
# ---------------------------------------------------------------------------
FROM nginx:1.29-alpine AS runtime

# A configuração de exemplo da imagem serve a página de boas-vindas na raiz e responde na
# porta 80; as duas coisas estariam erradas aqui.
RUN rm /etc/nginx/conf.d/default.conf
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf

COPY --from=builder /app/apps/web/dist /usr/share/nginx/html/revisao

# 8080 é o `PORT` do Cloud Run e é o que `deploy/nginx.conf` escuta.
EXPOSE 8080
