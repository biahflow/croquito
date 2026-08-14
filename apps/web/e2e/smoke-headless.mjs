/**
 * Smoke headless da tela de revisão contra o stack local.
 *
 * Vive fora do CI, na mesma família do `make smoke-local`: ele exercita o que teste
 * puro não alcança — o redirect real do Keycloak e o que sobra da URL depois dele.
 *
 * O alvo principal é o `?job`: um link de revisão aberto sem sessão passa pelo login e
 * precisa voltar no mesmo job. Isso só é verificável com um navegador de verdade.
 *
 * Pré-requisitos (ver apps/web/AGENTS.md):
 *
 *     make dev-services && make db-init && make dev
 *     npx playwright install chromium        # uma vez, não roda no postinstall
 *     CROQUITO_SMOKE_JOB=<uuid do job> npm --workspace @croquito/web run smoke:headless
 *
 * Cena opcional da conversa da revisão (`CROQUITO_SMOKE_CHAT=1`, exige o `?job`): ela
 * abre o painel, pergunta, espera a resposta da FIXTURE e confere que "Usar este
 * rascunho" só pré-preenche. A resposta só chega com o consumidor de fixtures rodando —
 * cada execução dele serve UMA mensagem:
 *
 *     make dev-worker-fixtures     # noutro terminal, depois que a pergunta for enviada
 *
 * A fixture cita o par sintético canônico do repositório; contra um job cujo pacote não
 * o contém, o turno é recusado com `CHAT_ACT_UNKNOWN_REFERENCE` — o portão funcionando,
 * e a cena reprova por não ter rascunho para conferir (ADR-0023).
 *
 * Nada de documento, cota, token ou URL assinada é impresso: só passo, estado e IDs
 * opacos, como manda o AGENTS.md da raiz. A pergunta e a resposta da conversa também
 * não são impressas.
 */

import { chromium } from "playwright";

const WEB_URL = process.env.CROQUITO_SMOKE_WEB_URL ?? "http://localhost:5173";
// Usuário do realm local versionado em keycloak/croquito-realm.json. É fixture de
// desenvolvimento, nunca credencial de ambiente real — e nunca é impressa.
const USERNAME = process.env.CROQUITO_SMOKE_USER ?? "engenheiro.local";
const PASSWORD = process.env.CROQUITO_SMOKE_PASSWORD ?? "local-dev-only";
const JOB_ID = process.env.CROQUITO_SMOKE_JOB ?? "";
const TIMEOUT_MS = Number(process.env.CROQUITO_SMOKE_TIMEOUT_MS ?? 30_000);
const CHAT_SCENE = process.env.CROQUITO_SMOKE_CHAT === "1";
// A resposta espera um `make dev-worker-fixtures` humano noutro terminal; o teto é
// generoso de propósito.
const CHAT_TIMEOUT_MS = Number(
  process.env.CROQUITO_SMOKE_CHAT_TIMEOUT_MS ?? 120_000,
);

class SmokeFailure extends Error {}

function step(text) {
  console.log(`· ${text}`);
}

/** O job é ID opaco e pode ser registrado; a URL inteira carrega code/state e não pode. */
function jobFromUrl(url) {
  return new URL(url).searchParams.get("job");
}

/**
 * Cena da conversa: perguntar, esperar a resposta da fixture e confirmar que o rascunho
 * PRÉ-PREENCHE o formulário sem submeter nada. Nenhum texto da conversa é impresso.
 */
async function runChatScene(page) {
  const panel = page.getByText("Conversa sobre a folha", { exact: true }).first();
  // O painel acompanha as etapas de decisões e traçado. Numa revisão já concluída a
  // jornada abre na exportação, e reabrir a etapa de decisões é o mesmo clique que o
  // revisor daria.
  if ((await panel.count()) === 0) {
    await page.getByRole("button", { name: /^1\. Decisões/ }).click();
    step("etapa de decisões reaberta para alcançar o painel");
  }
  await panel.waitFor({ state: "visible" });
  await panel.click();
  step("painel da conversa aberto");

  await page
    .getByLabel("Pergunta sobre a folha")
    .fill("Essa cota mede a borda do patamar ou a mureta desenhada por cima?");
  await page.getByRole("button", { name: "Perguntar" }).click();
  step("pergunta enviada; aguardando o worker de fixtures responder");
  console.log(
    "· execute `make dev-worker-fixtures` noutro terminal para servir este turno.",
  );

  await page
    .getByText("o agente respondeu", { exact: true })
    .first()
    .waitFor({ timeout: CHAT_TIMEOUT_MS });
  step("resposta do agente recebida");

  const draft = page.getByRole("region", { name: /^Rascunho \d+ desta resposta$/ });
  if ((await draft.count()) === 0) {
    throw new SmokeFailure(
      "a resposta chegou sem cartão de rascunho para conferir.",
    );
  }
  step(`${await draft.count()} cartão(ões) de rascunho ancorado(s) na evidência`);

  // Cartão sobre leitura já decidida vem com o botão desligado de propósito: o primeiro
  // rascunho utilizável é o que a cena exercita.
  const usable = page
    .getByRole("button", { name: "Usar este rascunho" })
    .and(page.locator("button:not([disabled])"))
    .first();
  if ((await usable.count()) === 0) {
    throw new SmokeFailure(
      "todos os rascunhos vieram bloqueados; não há o que pré-preencher.",
    );
  }
  await usable.click();

  // O único desfecho aceitável é pré-preenchimento: nenhum ato pode ter sido registrado.
  // Um aviso só ("Decisão registrada.") já reprovaria a cena, porque o aviso do envio é
  // outro e o esperado abaixo nunca apareceria.
  const outcome = page
    .getByText(/Rascunho no formulário de decisão|Sugestão aplicada ao aceite/)
    .first();
  await outcome.waitFor().catch(() => {
    throw new SmokeFailure(
      "o rascunho não chegou ao formulário nem ao aceite de traçado.",
    );
  });
  const prefilledDecision = (await outcome.textContent())?.includes(
    "formulário de decisão",
  );
  if ((await page.getByText("Decisão registrada.", { exact: true }).count()) > 0) {
    throw new SmokeFailure(
      "o rascunho submeteu uma decisão; ele só pode pré-preencher.",
    );
  }
  if (prefilledDecision) {
    const justification = page.getByLabel(/^Justificativa da decisão/);
    if (!(await justification.inputValue())) {
      throw new SmokeFailure(
        "o formulário de decisão não recebeu a justificativa sugerida.",
      );
    }
    step("formulário de decisão pré-preenchido, sem envio");
  } else {
    step("aceite de traçado recebeu a sugestão, sem envio");
  }
}

async function run() {
  const target = JOB_ID
    ? `${WEB_URL}/?job=${encodeURIComponent(JOB_ID)}`
    : `${WEB_URL}/`;
  step(JOB_ID ? `abrindo a revisão do job ${JOB_ID}` : "abrindo a tela sem job");

  const browser = await chromium.launch();
  const context = await browser.newContext();
  const page = await context.newPage();
  page.setDefaultTimeout(TIMEOUT_MS);

  try {
    await page.goto(target, { waitUntil: "domcontentloaded" });

    const signIn = page.getByRole("button", { name: "Entrar" });
    await signIn.waitFor({ state: "visible" });
    if (await page.getByText("OIDC não está configurado").isVisible()) {
      throw new SmokeFailure(
        "OIDC não está configurado no web: copie apps/web/.env.local.example para apps/web/.env.local.",
      );
    }
    step("tela anônima de pé; entrando pelo Keycloak");
    await signIn.click();

    // Formulário de login do Keycloak; os campos têm os nomes padrão do tema.
    await page.waitForSelector("#kc-form-login, input[name='username']");
    await page.fill("input[name='username']", USERNAME);
    await page.fill("input[name='password']", PASSWORD);
    await page.click("input[type='submit'], button[type='submit']");

    // Volta à aplicação: a sessão aparece na barra e o code/state já saiu da URL.
    await page.getByText("Sessão:", { exact: false }).waitFor();
    await page.waitForFunction(
      () => !new URLSearchParams(window.location.search).has("code"),
      undefined,
      { timeout: TIMEOUT_MS },
    );
    step("sessão autenticada estabelecida");

    if (JOB_ID) {
      // (b) o alvo principal: o job sobreviveu ao redirect do OIDC.
      const preserved = jobFromUrl(page.url());
      if (preserved !== JOB_ID) {
        throw new SmokeFailure(
          `o ?job não sobreviveu ao redirect: esperado ${JOB_ID}, veio ${preserved ?? "nada"}.`,
        );
      }
      step("?job preservado depois do redirect OIDC");

      // (a) a jornada renderizou para esse job.
      await page
        .getByRole("navigation", { name: "Jornada da revisão" })
        .waitFor();
      step("jornada da revisão renderizada");

      if (CHAT_SCENE) {
        await runChatScene(page);
      }
    } else {
      if (CHAT_SCENE) {
        throw new SmokeFailure(
          "a cena da conversa exige CROQUITO_SMOKE_JOB: ela roda dentro de uma revisão.",
        );
      }
      await page.getByRole("heading", { name: "Projetos e revisões" }).waitFor();
      step("área autenticada renderizada (sem job informado)");
      console.log(
        "· aviso: sem CROQUITO_SMOKE_JOB o teste do ?job não é executado.",
      );
    }

    console.log("smoke headless: aprovado.");
  } finally {
    await context.close();
    await browser.close();
  }
}

run().catch((error) => {
  const detail =
    error instanceof SmokeFailure ? error.message : String(error?.message ?? error);
  console.error(`smoke headless: reprovado — ${detail}`);
  process.exitCode = 1;
});
