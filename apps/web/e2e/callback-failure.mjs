/**
 * Regressão do incidente de 2026-08-19: retorno do OIDC com `code`+`state` que falham na
 * troca NÃO pode virar rebote mudo para a porta.
 *
 * O modo de falha real: `readSession()` engolia a falha do callback, o `finally` limpava a
 * URL, e o rebote (ADR-0032, D4) mandava para `/login` sem mensagem — com o SSO do
 * Keycloak vivo, cada "Entrar" voltava com código novo que falhava de novo: um loop
 * fechado e silencioso. O conserto faz a falha subir quando não há sessão armazenada; a
 * porta a mostra como aviso.
 *
 * Este cenário só precisa do dev server do web (sem Keycloak): um código falso falha a
 * troca do mesmo jeito. Pré-requisito: `npm --workspace @croquito/web run dev`.
 *
 *     npm --workspace @croquito/web run smoke:callback
 */
import { chromium } from "playwright";

const WEB_URL = process.env.CROQUITO_SMOKE_WEB_URL ?? "http://localhost:5173";
const TIMEOUT_MS = Number(process.env.CROQUITO_SMOKE_TIMEOUT_MS ?? 30_000);

function step(message) {
  console.log(`· ${message}`);
}

const browser = await chromium.launch();
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  page.setDefaultTimeout(TIMEOUT_MS);

  await page.goto(`${WEB_URL}/?job=abc&state=falso&code=falso`, {
    waitUntil: "domcontentloaded",
  });
  step("retorno com code+state inválidos aberto");

  // A porta aparece — e com o AVISO da falha, nunca em silêncio.
  await page.locator("main.login").waitFor({ state: "visible" });
  const alerta = page.locator(".login-alert");
  await alerta.first().waitFor({ state: "visible" });
  const texto = (await alerta.first().textContent()) ?? "";
  if (!texto.includes("Não foi possível validar a sessão OIDC")) {
    throw new Error(`aviso presente mas com outro texto: ${texto.slice(0, 120)}`);
  }
  step("falha de callback visível na porta (sem rebote mudo)");

  // O ?job sobreviveu ao salto: o link entregue continua valendo para a próxima tentativa.
  const url = new URL(page.url());
  if (!url.pathname.startsWith("/login") || url.searchParams.get("job") !== "abc") {
    throw new Error(`URL final inesperada: ${page.url()}`);
  }
  step("?job preservado no salto para /login");

  console.log("smoke callback-failure: aprovado.");
} catch (error) {
  console.error(`smoke callback-failure: reprovado — ${error.message}`);
  process.exitCode = 1;
} finally {
  await browser.close();
}
