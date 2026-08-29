import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  DivergenciaDoItem,
  EloComOCroqui,
  EtiquetaDeElemento,
  OrigemDaQuantidade,
  RelatorioDoConfronto,
  ResolucaoDaDivergencia,
} from "./MedicaoApp";
import {
  postDivergenceResolution,
  postSceneLink,
  postSceneQuantities,
  type SceneConfrontationReport,
  type SceneLinkState,
  type TakeoffItem,
} from "./api";
import { divergenceResolutionBody, sceneLinkBody } from "./requests";
import type { QuantityDivergence } from "./cena";

/**
 * A tela da medição depois que a quantidade nasce da cena (F-047 T7b).
 *
 * Os estados 05 a 08 do pacote de design aprovado em 2026-08-28, mais o elo da rodada. O
 * que estes testes vigiam, além da composição, é a regra que não se negocia: **nenhum
 * número desta tela é calculado no navegador**. Todo decimal que aparece no HTML é o texto
 * que o servidor mandou, com a pontuação trocada por `format.ts` — e é por isso que
 * `401.55` sai como `401,55` e `16.55` como `16,55`, sem nenhuma casa a mais ou a menos.
 *
 * Os números são os da Praça do Cedro, fixture sintética do pacote de design.
 */

const BASE = "http://localhost:8000";
const TOKEN = "token-de-teste";
const ROUND = "0197f2a0-0000-7000-8000-000000000001";
const ITEM = "ti_0000000000000003";

const EVIDENCIA = {
  bbox: { left: 0, top: 0, right: 10, bottom: 10 },
  image_sha256: "a".repeat(64),
  page_number: 1,
  plate_id: "PR-01",
};

function item(overrides: Partial<TakeoffItem> = {}): TakeoffItem {
  return {
    id: ITEM,
    label: "Alambrado — quadra poliesportiva",
    raw_text: "ALAMBRADO H=2,00 — 385,00 m",
    unit: "m",
    status: "proposed",
    source: "legend_extraction",
    extractor: "fixture",
    extractor_version: "1.0.0",
    evidence: EVIDENCIA,
    ...overrides,
  } as TakeoffItem;
}

function divergencia(
  overrides: Partial<QuantityDivergence> = {},
): QuantityDivergence {
  return {
    scene: {
      element_ref: "EL-003",
      precision: "derived",
      quantity: "401.55",
      scene_revision_id: "rev-8",
    },
    legend: {
      extractor: "fixture",
      extractor_version: "1.0.0",
      quantity: "385.00",
      read_at: "2026-03-02T12:00:00Z",
      read_by: "orcamentista",
      source: "legend_extraction",
    },
    difference: "16.55",
    tolerance: "3.85",
    relative_tolerance: "3.85",
    absolute_floor: "0.01",
    tolerance_bound: "relative",
    legend_ratio: "4.30",
    ...overrides,
  };
}

const ELO_DECLARADO: SceneLinkState = {
  present: true,
  job_id: "job-cedro",
  scene_revision_id: "rev-8",
  export_id: "exp-1",
  dxf_sha256: "b".repeat(64),
  declared_by: "orcamentista",
  declared_at: "2026-03-04T10:00:00Z",
};

describe("a etiqueta da identidade", () => {
  it("mostra a identidade quando ela existe", () => {
    const html = renderToStaticMarkup(<EtiquetaDeElemento elementRef="EL-003" />);

    expect(html).toContain("EL-003");
    expect(html).not.toContain("etiqueta-elemento-ausente");
  });

  it("a ausência é DITA e tracejada, nunca um campo que some", () => {
    const html = renderToStaticMarkup(<EtiquetaDeElemento elementRef={null} />);

    expect(html).toContain("sem identidade");
    expect(html).toContain("etiqueta-elemento-ausente");
  });
});

describe("o elo com o croqui aprovado", () => {
  const props = {
    jobId: "",
    onJobIdChange: () => undefined,
    onDeclarar: () => undefined,
    onConfrontar: () => undefined,
    submitting: false,
    confrontoDisponivel: true,
  };

  it("sem elo, declara a ausência e promete que a jornada segue como hoje", () => {
    const html = renderToStaticMarkup(
      <EloComOCroqui {...props} link={{ present: false }} />,
    );

    expect(html).toContain("Sem croqui declarado");
    expect(html).toContain("continua vindo da legenda lida");
    // Sem elo não existe o botão que grava no takeoff.
    expect(html).not.toContain("Confrontar o takeoff");
    expect(html).toContain("Declarar o croqui desta rodada");
  });

  it("com elo, mostra os três identificadores e o digest do DXF auditado", () => {
    const html = renderToStaticMarkup(
      <EloComOCroqui {...props} link={ELO_DECLARADO} />,
    );

    expect(html).toContain("job-cedro");
    expect(html).toContain("rev-8");
    expect(html).toContain("exp-1");
    expect(html).toContain("sha256 bbbbbbbbbbbb");
    expect(html).toContain("orcamentista");
    expect(html).toContain("Trocar o croqui declarado");
  });

  it("o botão que GRAVA declara o efeito antes do clique", () => {
    const html = renderToStaticMarkup(
      <EloComOCroqui {...props} link={ELO_DECLARADO} />,
    );

    expect(html).toContain("Confrontar o takeoff com a cena aprovada");
    expect(html).toContain("alimenta o item que está sem quantidade");
    expect(html).toContain("grava divergência");
    expect(html).toContain("Nenhum provider é chamado");
  });

  it("sem pacote de takeoff, o confronto fica indisponível com a razão escrita", () => {
    const html = renderToStaticMarkup(
      <EloComOCroqui {...props} link={ELO_DECLARADO} confrontoDisponivel={false} />,
    );

    expect(html).toContain("Disponível depois que a revisão do takeoff");
    expect(html).toContain("disabled");
  });
});

describe("estado 05 — a quantidade chegou da cena, e não há onde redigitá-la", () => {
  const alimentado = item({
    source: "scene_graph",
    element_ref: "EL-001",
    label: "Piso em concreto — quadra",
    unit: "m2",
    quantity: "418.12",
    scene_precision: "derived",
  });

  it("mostra a origem, a identidade e a precisão — e o número como o servidor mandou", () => {
    const html = renderToStaticMarkup(
      <OrigemDaQuantidade item={alimentado} sceneRevisionId="rev-8" />,
    );

    expect(html).toContain("EL-001");
    expect(html).toContain("cena aprovada");
    expect(html).toContain("derivada");
    expect(html).toContain("418,12 m²");
    expect(html).toContain("rev-8");
  });

  it("diz que não existe campo de quantidade, e deixa a ação VISÍVEL e indisponível", () => {
    const html = renderToStaticMarkup(
      <OrigemDaQuantidade item={alimentado} sceneRevisionId={null} />,
    );

    expect(html).toContain("Não existe campo de quantidade");
    expect(html).toContain("Editar quantidade");
    expect(html).toContain("disabled");
    expect(html).toContain("corrija o traçado na jornada do croqui");
    // A ausência do teclado é decisão declarada — não pode virar um input escondido.
    expect(html).not.toContain("<input");
  });

  it("item que não veio da cena não desenha nada: a tela é a de sempre", () => {
    expect(
      renderToStaticMarkup(
        <OrigemDaQuantidade item={item()} sceneRevisionId="rev-8" />,
      ),
    ).toBe("");
  });
});

describe("estado 06 — a divergência, a tolerância nomeada e o item bloqueado", () => {
  const divergente = item({ element_ref: "EL-003", scene_divergence: divergencia() });

  it("mostra os dois números lado a lado com as suas origens", () => {
    const html = renderToStaticMarkup(<DivergenciaDoItem item={divergente} />);

    expect(html).toContain("401,55 m");
    expect(html).toContain("385,00 m");
    expect(html).toContain("cena aprovada");
    expect(html).toContain("legenda lida");
    expect(html).toContain("derivada");
    expect(html).toContain("EL-003");
  });

  it("a diferença, a tolerância e a razão são as do servidor, e a conta aparece por extenso", () => {
    const html = renderToStaticMarkup(<DivergenciaDoItem item={divergente} />);

    expect(html).toContain("16,55 m");
    expect(html).toContain("3,85 m");
    expect(html).toContain("maior entre 1% da quantidade da legenda e 0,01");
    expect(html).toContain("a tela não refaz nenhuma conta");
    // O percentual é o número que a fixture gravou em `legend_ratio` — a tela só troca a
    // pontuação e junta o "%": não há divisão de `difference` por `legend.quantity` em
    // nenhum lugar deste componente.
    expect(html).toContain("4,30% do valor da legenda");
    expect(html).toContain("1% × 385,00 m = 3,85 m");
    expect(html).toContain("piso de unidade = 0,01 m");
    expect(html).toContain("1% mandou");
  });

  it("o bloqueio é dito por palavra e por forma, nunca só por cor", () => {
    const html = renderToStaticMarkup(<DivergenciaDoItem item={divergente} />);

    expect(html).toContain("divergência aberta");
    expect(html).toContain("⚠");
    expect(html).toContain("não fecha");
    expect(html).toContain('role="alert"');
    expect(html).toContain("bloqueado");
    expect(html).toContain("Nenhuma origem apaga a outra");
  });

  it("item sem divergência não desenha nada", () => {
    expect(renderToStaticMarkup(<DivergenciaDoItem item={item()} />)).toBe("");
  });
});

describe("estado 07 — a resolução é decisão humana registrada", () => {
  const divergente = item({ element_ref: "EL-003", scene_divergence: divergencia() });

  const props = {
    escolha: "" as const,
    motivo: "",
    submitting: false,
    onEscolha: () => undefined,
    onMotivo: () => undefined,
    onRegistrar: () => undefined,
    onCancelar: () => undefined,
  };

  it("oferece DUAS escolhas, e a terceira aparece indisponível com a razão escrita", () => {
    const html = renderToStaticMarkup(
      <ResolucaoDaDivergencia {...props} item={divergente} />,
    );

    expect(html).toContain("Vale a cena: 401,55 m");
    expect(html).toContain("Vale a legenda: 385,00 m");
    expect(html).toContain("Nenhuma das duas");
    expect(html).toContain("seria a redigitação que esta feature existe para eliminar");
    // A terceira opção é um rádio DESABILITADO: ela existe na tela e não pode ser marcada.
    expect(html).toContain('<input type="radio" disabled="" name="divergencia" value="none"/>');
  });

  it("nada nasce pré-marcado, e sem escolha e sem motivo não se registra", () => {
    const html = renderToStaticMarkup(
      <ResolucaoDaDivergencia {...props} item={divergente} />,
    );

    expect(html).not.toContain("checked");
    expect(html).toContain("(obrigatório)");
    // Dois `disabled`: a terceira opção e o botão que grava.
    expect(html.match(/disabled=""/g)?.length).toBe(2);
  });

  it("com escolha e motivo, o botão que grava fica disponível", () => {
    const html = renderToStaticMarkup(
      <ResolucaoDaDivergencia
        {...props}
        item={divergente}
        escolha="scene"
        motivo="Traçado ajustado em 04/03; a legenda é da prancha anterior."
      />,
    );

    expect(html).toContain("Registrar decisão");
    expect(html).toContain("Manter aberta");
    // Só a terceira opção continua indisponível.
    expect(html.match(/disabled=""/g)?.length).toBe(1);
  });

  it("resolvida, o carimbo mostra a escolha E o número preterido ainda gravado", () => {
    const resolvido = item({
      element_ref: "EL-003",
      scene_divergence: divergencia({
        resolution: {
          choice: "scene",
          resolved_at: "2026-03-05T12:14:00Z",
          reviewer_id: "orcamentista",
          reviewer_role: "orcamentista",
          note: "Traçado ajustado em 04/03; a legenda é da prancha anterior.",
        },
      }),
    });
    const html = renderToStaticMarkup(<DivergenciaDoItem item={resolvido} />);

    expect(html).toContain("divergência resolvida");
    expect(html).toContain("vale a cena");
    expect(html).toContain("401,55 m");
    expect(html).toContain("Preterida: 385,00 m");
    expect(html).toContain("continua gravada");
    expect(html).toContain("Traçado ajustado em 04/03");
    expect(html).toContain("nenhuma origem");
  });

  it("resolvida, o formulário de escolha some — decisão não se sobrescreve aqui", () => {
    const resolvido = item({
      scene_divergence: divergencia({
        resolution: {
          choice: "legend",
          resolved_at: "2026-03-05T12:14:00Z",
          reviewer_id: "orcamentista",
          reviewer_role: "orcamentista",
        },
      }),
    });

    expect(
      renderToStaticMarkup(
        <ResolucaoDaDivergencia {...props} item={resolvido} />,
      ),
    ).toBe("");
  });
});

describe("estado 08 — o relatório diz quem não recebeu nada, e por quê", () => {
  const relatorio: SceneConfrontationReport = {
    job_id: "job-cedro",
    scene_revision_id: "rev-8",
    export_id: "exp-1",
    changed: true,
    fed: 1,
    divergences_recorded: 1,
    unchanged: 3,
    items: [
      {
        item_id: "ti_0000000000000001",
        element_ref: "EL-001",
        outcome: "fed",
        reason: null,
        scene_quantity: "418.12",
        scene_precision: "derived",
      },
      {
        item_id: "ti_0000000000000005",
        element_ref: null,
        outcome: "unchanged",
        reason: "item_without_element_ref",
        scene_quantity: null,
        scene_precision: null,
      },
      {
        item_id: "ti_0000000000000009",
        element_ref: "EL-009",
        outcome: "unchanged",
        reason: "element_ref_absent_from_scene",
        scene_quantity: null,
        scene_precision: null,
      },
      {
        item_id: "ti_0000000000000006",
        element_ref: "EL-005",
        outcome: "unchanged",
        reason: "precision_not_eligible",
        scene_quantity: null,
        scene_precision: null,
      },
    ],
  };

  const itens = [
    item({ id: "ti_0000000000000001", label: "Piso em concreto — quadra", unit: "m2" }),
    item({ id: "ti_0000000000000005", label: "Piso sem identidade", unit: "m2" }),
    item({ id: "ti_0000000000000009", label: "Bancos de concreto", unit: "un" }),
    item({ id: "ti_0000000000000006", label: "Canteiro gramado — faixa norte", unit: "m2" }),
  ];

  it("lista TODOS os itens, inclusive os que não mudaram", () => {
    const html = renderToStaticMarkup(
      <RelatorioDoConfronto relatorio={relatorio} itens={itens} />,
    );

    expect(html).toContain("Piso em concreto — quadra");
    expect(html).toContain("Piso sem identidade");
    expect(html).toContain("Bancos de concreto");
    expect(html).toContain("Canteiro gramado — faixa norte");
  });

  it("as contagens são as do servidor, exibidas como vieram", () => {
    const html = renderToStaticMarkup(
      <RelatorioDoConfronto relatorio={relatorio} itens={itens} />,
    );

    expect(html).toContain("1 item(ns) alimentado(s) pela cena");
    expect(html).toContain("1 divergência(s) gravada(s)");
    expect(html).toContain("3 sem mudança");
  });

  it("diz de que LADO falta a identidade, um lado de cada vez", () => {
    const html = renderToStaticMarkup(
      <RelatorioDoConfronto relatorio={relatorio} itens={itens} />,
    );

    expect(html).toContain("não está declarada na legenda");
    expect(html).toContain("não aparece em nenhuma linha do quantitativos.csv");
    expect(html).toContain("Número igual não é identidade");
  });

  it("aproximada aparece como 'não alimenta a medição', com o motivo escrito", () => {
    const html = renderToStaticMarkup(
      <RelatorioDoConfronto relatorio={relatorio} itens={itens} />,
    );

    expect(html).toContain("aproximada ou não resolvida");
    expect(html).toContain("não alimenta a medição e também não compara");
  });

  it("a quantidade que a cena ofereceu sai com a unidade do item, sem recontagem", () => {
    const html = renderToStaticMarkup(
      <RelatorioDoConfronto relatorio={relatorio} itens={itens} />,
    );

    expect(html).toContain("418,12 m²");
  });

  it("sem confronto executado, o bloco não existe", () => {
    expect(
      renderToStaticMarkup(<RelatorioDoConfronto relatorio={null} itens={itens} />),
    ).toBe("");
  });
});

describe("o transporte das três rotas", () => {
  type Chamada = { url: string; init: RequestInit | undefined };
  const chamadas: Chamada[] = [];

  beforeEach(() => {
    chamadas.length = 0;
    vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
      chamadas.push({ url, init });
      return Promise.resolve(
        new Response(JSON.stringify({}), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function headers(): Record<string, string> {
    return (chamadas[0]?.init?.headers ?? {}) as Record<string, string>;
  }

  function corpo(): Record<string, unknown> {
    return JSON.parse(String(chamadas[0]?.init?.body ?? "{}"));
  }

  it("o elo cita a rodada, manda a versão-base e a chave de idempotência", async () => {
    await postSceneLink(TOKEN, ROUND, { jobId: "  job-cedro  ", baseVersion: 7 });

    expect(chamadas[0].url).toBe(`${BASE}/v1/valuation-rounds/${ROUND}/scene-link`);
    expect(headers().Authorization).toBe(`Bearer ${TOKEN}`);
    expect(headers()["Idempotency-Key"]).toBeTruthy();
    // Só o job viaja: revisão, export, digest e carimbo são do servidor.
    expect(corpo()).toEqual({ base_version: 7, job_id: "job-cedro" });
  });

  it("o confronto é do pacote inteiro: o corpo é só a guarda de concorrência", async () => {
    await postSceneQuantities(TOKEN, ROUND, 8);

    expect(chamadas[0].url).toBe(
      `${BASE}/v1/valuation-rounds/${ROUND}/takeoff/scene-quantities`,
    );
    expect(corpo()).toEqual({ base_version: 8 });
  });

  it("a resolução manda item, escolha e motivo aparado", async () => {
    await postDivergenceResolution(TOKEN, ROUND, {
      itemId: ITEM,
      choice: "scene",
      baseVersion: 9,
      note: "  traçado ajustado  ",
    });

    expect(chamadas[0].url).toBe(
      `${BASE}/v1/valuation-rounds/${ROUND}/takeoff/divergences/resolutions`,
    );
    expect(corpo()).toEqual({
      base_version: 9,
      item_id: ITEM,
      choice: "scene",
      note: "traçado ajustado",
    });
  });
});

describe("os corpos puros", () => {
  it("o elo nunca carrega revisão, export, digest nem carimbo", () => {
    expect(sceneLinkBody({ jobId: "job-cedro", baseVersion: 3 })).toEqual({
      base_version: 3,
      job_id: "job-cedro",
    });
  });

  it("motivo em branco NÃO viaja: string vazia é um motivo vazio, não a ausência dele", () => {
    expect(
      divergenceResolutionBody({
        itemId: ITEM,
        choice: "legend",
        baseVersion: 4,
        note: "   ",
      }),
    ).toEqual({ base_version: 4, item_id: ITEM, choice: "legend" });
  });

  it("a escolha só tem dois valores, e nenhum deles carrega quantidade", () => {
    const cena = divergenceResolutionBody({
      itemId: ITEM,
      choice: "scene",
      baseVersion: 4,
    });

    expect(cena).toEqual({ base_version: 4, item_id: ITEM, choice: "scene" });
    expect(cena).not.toHaveProperty("quantity");
  });
});
