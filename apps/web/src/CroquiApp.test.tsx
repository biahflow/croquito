import { renderToStaticMarkup } from "react-dom/server";
import type { User } from "oidc-client-ts";
import { describe, expect, it } from "vitest";
import {
  AppAlert,
  CroquiApp,
  JobStatusBand,
  jobFailureMessage,
} from "./CroquiApp";

/**
 * Sessão sintética: a jornada recebe a sessão pronta da casca, e a renderização estática
 * não dispara efeito nenhum — nada é pedido à API por este teste.
 */
const session = {
  access_token: "sessao-sintetica-de-teste",
  profile: { sub: "revisor-de-teste" },
} as unknown as User;

describe("CroquiApp", () => {
  it("abre a área do tenant sem fabricar revisão, cena ou evidência", () => {
    const html = renderToStaticMarkup(
      <CroquiApp session={session} onSessionLost={() => undefined} />,
    );

    expect(html).toContain("Projetos e revisões");
    expect(html).not.toContain("DXF bloqueado");
    expect(html).not.toContain("Campo do Guaxindiba");
    expect(html).not.toContain("Simulação de decisão");
  });

  /**
   * A sessão tem um dono só (`readSession` consome um authorization code de uso único),
   * e é a casca. Esta jornada não desenha topbar, identidade nem Entrar/Sair.
   */
  it("não desenha a casca: sessão e navegação são da App", () => {
    const html = renderToStaticMarkup(
      <CroquiApp session={session} onSessionLost={() => undefined} />,
    );

    expect(html).not.toContain('class="topbar"');
    expect(html).not.toContain("Sessão:");
    expect(html).not.toContain(">Entrar<");
    expect(html).not.toContain(">Sair<");
    expect(html).not.toContain("revisor-de-teste");
    // O token nunca chega ao HTML.
    expect(html).not.toContain("sessao-sintetica-de-teste");
  });
});

/**
 * A faixa de acompanhamento é derivada do job, e não uma mensagem: derivada, o texto é o
 * mesmo entre duas voltas do poll de 2 s, o DOM não desmonta e a faixa não pisca.
 */
describe("JobStatusBand", () => {
  it("mostra o estado do job em processamento com role=status, sem cara de erro", () => {
    const html = renderToStaticMarkup(
      <JobStatusBand
        job={{ status: "PROCESSING", stage: "VISION" }}
        hasReview={false}
      />,
    );

    expect(html).toContain('role="status"');
    expect(html).toContain('class="app-status"');
    expect(html).toContain(
      "Em processamento. A revisão será aberta automaticamente quando estiver disponível.",
    );
    expect(html).not.toContain('role="alert"');
    expect(html).not.toContain("app-alert");
    // Estado não se fecha: some sozinho quando a revisão abre.
    expect(html).not.toContain("Fechar aviso");
  });

  it("some quando a revisão abre", () => {
    const html = renderToStaticMarkup(
      <JobStatusBand
        job={{ status: "REVIEW_REQUIRED", stage: "REVIEW" }}
        hasReview
      />,
    );

    expect(html).toBe("");
  });

  it("não desenha nada sem job aberto", () => {
    const html = renderToStaticMarkup(
      <JobStatusBand job={null} hasReview={false} />,
    );

    expect(html).toBe("");
  });

  it("não absorve a falha: job que falhou não vira faixa de estado", () => {
    const html = renderToStaticMarkup(
      <JobStatusBand job={{ status: "FAILED", stage: "VISION" }} hasReview={false} />,
    );

    expect(html).toBe("");
  });
});

describe("falha do job", () => {
  it("continua sendo aviso, em .app-alert com role=alert", () => {
    const message = jobFailureMessage({ status: "FAILED" });
    expect(message).toBe(
      "Este processamento falhou. Consulte a equipe responsável para repetir a etapa segura.",
    );

    const html = renderToStaticMarkup(
      <AppAlert message={message ?? ""} onClose={() => undefined} />,
    );

    expect(html).toContain('class="app-alert"');
    expect(html).toContain('role="alert"');
    expect(html).toContain("Este processamento falhou.");
    expect(html).toContain("Fechar aviso");
  });

  it("estado do ciclo de vida não vira mensagem", () => {
    expect(jobFailureMessage({ status: "PROCESSING" })).toBeNull();
    expect(jobFailureMessage({ status: "UPLOADED" })).toBeNull();
    expect(jobFailureMessage({ status: "REVIEW_REQUIRED" })).toBeNull();
  });
});
