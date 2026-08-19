/**
 * Smoke AUTENTICADO da porta de entrada — o teste que atravessa o login real e prova a
 * sessão com uma chamada de API. Nasceu do incidente de 2026-08-19: login fechava no
 * Keycloak, tokens chegavam, e o produto ainda assim não abria — nada na esteira cobria
 * o caminho autenticado, então quem descobria era gente.
 *
 * Roda contra qualquer base (stack local ou homologação):
 *
 *     CROQUITO_SMOKE_WEB_URL=https://croquito-hml.biahflow.ai \
 *     CROQUITO_SMOKE_USER=smoke.hml CROQUITO_SMOKE_PASSWORD=*** \
 *     npm --workspace @croquito/web run smoke:auth
 *
 * O que ele afirma, na ordem da jornada:
 *   1. a raiz termina na porta (`/login`), com a copy aprovada;
 *   2. o Keycloak está VESTIDO (tema croquito), em português e SEM seletor de idioma;
 *   3. credenciais fecham sessão e a casca abre (`Sessão:`);
 *   4. `GET /v1/projects` responde 200 — o teste que teria pego a conta sem tenant;
 *   5. a URL fica estável: nenhum rebote de volta à porta (o loop, se voltar, reprova).
 *
 * Nenhuma senha, token ou URL assinada é impressa — só passo e estado.
 */
import { chromium } from "playwright";

const WEB_URL = process.env.CROQUITO_SMOKE_WEB_URL ?? "http://localhost:5173";
const USERNAME = process.env.CROQUITO_SMOKE_USER ?? "engenheiro.local";
const PASSWORD = process.env.CROQUITO_SMOKE_PASSWORD ?? "local-dev-only";
const TIMEOUT_MS = Number(process.env.CROQUITO_SMOKE_TIMEOUT_MS ?? 45_000);

function step(message) {
  console.log(`· ${message}`);
}

const browser = await chromium.launch();
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  page.setDefaultTimeout(TIMEOUT_MS);

  // 1. A raiz termina na porta, com a copy aprovada.
  await page.goto(`${WEB_URL}/`, { waitUntil: "domcontentloaded" });
  const cta = page.locator("main.login button.login-cta");
  await cta.waitFor({ state: "visible" });
  const porta = await page.evaluate(() => document.body.innerText);
  for (const frase of ["Do croqui ao orçamento.", "Entrar no Croquito"]) {
    if (!porta.includes(frase)) {
      throw new Error(`porta sem a copy aprovada: falta "${frase}"`);
    }
  }
  step("porta de entrada de pé, com a copy aprovada");

  // 2. Keycloak vestido, em português, sem seletor de idioma.
  await cta.click();
  const formulario = page.locator("#kc-form-login, input[name='username']");
  await formulario.first().waitFor({ state: "visible" });
  const kc = await page.evaluate(() => ({
    tema: [...document.querySelectorAll("link[rel=stylesheet]")].some((l) =>
      l.href.includes("/croquito/"),
    ),
    corpo: document.body.innerText,
    seletorDeIdioma: !!document.querySelector(
      "#login-select-toggle, [id*=kc-locale], select",
    ),
  }));
  if (!kc.tema) {
    throw new Error("Keycloak sem o tema croquito");
  }
  if (!kc.corpo.includes("Entrar na sua conta")) {
    throw new Error("Keycloak fora do português (pt-BR único)");
  }
  if (kc.seletorDeIdioma) {
    throw new Error("seletor de idioma presente — pt-BR deve ser único");
  }
  step("Keycloak vestido, em português, sem seletor");

  // 3. Credenciais fecham a sessão e a casca abre.
  await page.fill("input[name='username']", USERNAME);
  await page.fill("input[name='password']", PASSWORD);
  const respostaProjetos = page.waitForResponse(
    (r) => r.url().includes("/v1/projects") && r.request().method() === "GET",
    { timeout: TIMEOUT_MS },
  );
  await page
    .locator("#kc-login, input[type='submit'], button[type='submit']")
    .first()
    .click();
  await page.getByText("Sessão:").waitFor({ state: "visible" });
  step("sessão autenticada estabelecida");

  // 4. A chamada de API autenticada responde 200 — pega conta sem tenant na hora.
  const resposta = await respostaProjetos;
  if (resposta.status() !== 200) {
    const corpo = await resposta.text().catch(() => "");
    throw new Error(
      `GET /v1/projects respondeu ${resposta.status()} — ${corpo.slice(0, 120)}`,
    );
  }
  step("GET /v1/projects respondeu 200 com o token da sessão");

  // 5. URL estável: sem rebote de volta à porta.
  await page.waitForTimeout(3000);
  const url = new URL(page.url());
  if (url.pathname.startsWith("/login")) {
    throw new Error("rebote para /login depois da sessão — o loop voltou");
  }
  step("URL estável depois da sessão (sem loop)");

  console.log("smoke auth: aprovado.");
} catch (error) {
  console.error(`smoke auth: reprovado — ${error.message}`);
  process.exitCode = 1;
} finally {
  await browser.close();
}
