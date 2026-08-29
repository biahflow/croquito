/**
 * Derivação pura da identidade de elemento na revisão do croqui (F-047 T7a, ADR-0058).
 *
 * O que este módulo faz é LER a cena e dizer, em palavras, o que já está gravado nela:
 * quais entidades foram declaradas como elemento, qual a precisão de cada elemento e se
 * ele atravessa a fronteira para a medição. Ele não escreve nada, não cunha `element_ref`
 * — quem cunha é `POST /v1/jobs/{job_id}/elements`, ato humano do servidor — e não faz
 * conta de quantidade: a regra do `apps/web/AGENTS.md` vale aqui inteira, a tela nunca
 * soma, multiplica nem arredonda quantidade.
 *
 * Classificar precisão NÃO é aritmética: `alimentaAMedicao` é uma tabela de quatro
 * entradas, e o motivo de cada recusa é texto, não cálculo.
 */
import type { SceneRevision } from "@croquito/contracts";

import { precisionLabel } from "./labels";
import type { EntidadeDaCena, PrecisaoDaCena } from "./scenePreview";

/**
 * Nunca são "o elemento": `TEXT` é o rótulo e `DIMENSION`/`DIAMETER_DIMENSION` são a cota.
 *
 * É o MESMO recorte de `croquito_core.element_proposals._ANNOTATION_KINDS` e de
 * `croquito_worker.dxf._write_quantities`. Repetido aqui porque a tela precisa da mesma
 * fronteira para não deixar a precisão de um rótulo decidir se o elemento alimenta a
 * medição: uma anotação `unresolved` ao lado de um polígono `derived` reprovaria um
 * elemento que o servidor considera bom.
 */
const ESPECIES_DE_ANOTACAO: ReadonlySet<string> = new Set([
  "text",
  "dimension",
  "diameter_dimension",
]);

export function ehAnotacao(entity: EntidadeDaCena): boolean {
  return ESPECIES_DE_ANOTACAO.has(String(entity.kind).toLowerCase());
}

/**
 * Precisões que atravessam a fronteira para a medição (ADR-0058, decisão 4, na redação
 * emendada pelo aceite humano de 2026-08-28: `approximate` não alimenta NEM sob aceite
 * explícito).
 */
const PRECISOES_QUE_ALIMENTAM: ReadonlySet<string> = new Set(["exact", "derived"]);

export function alimentaAMedicao(precisao: PrecisaoDaCena | null): boolean {
  return precisao !== null && PRECISOES_QUE_ALIMENTAM.has(precisao);
}

/**
 * O motivo escrito na tela, no lugar onde a pessoa está (Design Approval Package, decisão
 * 5). Não é comentário de código nem tooltip: a quantidade da medição vira dinheiro num
 * boletim que a prefeitura paga, e quem lê a linha precisa ler por que ela não veio da
 * cena.
 */
const MOTIVOS_DE_NAO_ALIMENTAR: Record<string, string> = {
  approximate:
    "A cena deste elemento é aproximada. Multiplicada por preço unitário, uma aproximação " +
    "vira uma linha de R$ que ninguém lê como aproximada — por isso ela não atravessa para " +
    "a medição, nem sob aceite explícito. A legenda lida segue sendo a fonte, e a cena " +
    "continua visível e carimbada como aproximada ao lado.",
  unresolved:
    "A cena deste elemento não está resolvida. Ela não alimenta a medição e continua " +
    "barrando o próprio export do croqui.",
};

const SEM_GEOMETRIA_FISICA =
  "Este elemento só reúne anotação (rótulo ou cota), que não é geometria física. " +
  "Anotação documenta o elemento; ela não é a quantidade dele.";

export function motivoDeNaoAlimentar(precisao: PrecisaoDaCena | null): string | null {
  if (precisao === null) {
    return SEM_GEOMETRIA_FISICA;
  }
  return MOTIVOS_DE_NAO_ALIMENTAR[precisao] ?? null;
}

/**
 * Ordem da mais fraca para a mais forte. Um elemento vale pela precisão MAIS FRACA das
 * entidades físicas dele: se um dos traços é aproximado, o elemento inteiro é aproximado.
 * Falhar fechado é a escolha do produto em toda a cadeia, e aqui ela vale mais ainda,
 * porque do outro lado da fronteira há dinheiro.
 */
const FORCA_DA_PRECISAO: Record<string, number> = {
  unresolved: 0,
  approximate: 1,
  derived: 2,
  exact: 3,
};

export function precisaoMaisFraca(
  precisoes: readonly PrecisaoDaCena[],
): PrecisaoDaCena | null {
  let escolhida: PrecisaoDaCena | null = null;
  for (const precisao of precisoes) {
    if (
      escolhida === null ||
      (FORCA_DA_PRECISAO[precisao] ?? 0) < (FORCA_DA_PRECISAO[escolhida] ?? 0)
    ) {
      escolhida = precisao;
    }
  }
  return escolhida;
}

/** Um elemento declarado na cena, do jeito que a tela precisa lê-lo. */
export type ElementoDeclarado = {
  elementRef: string;
  /**
   * O nome legível que a pessoa deu ao elemento (F-047 T2b), ou `null` sem nome.
   *
   * É apresentação, e a tela o mostra AO LADO do `EL-00N`, nunca no lugar dele: o que
   * identifica o elemento — e o que casa com a legenda — continua sendo só o `element_ref`.
   */
  rotulo: string | null;
  /** Um elemento não mistura camadas — a invariante é do `SceneRevision`, não da tela. */
  camada: string;
  entityIds: string[];
  /** Quantas das entidades são anotação: dito por escrito, nunca escondido. */
  anotacoes: number;
  /** Precisão do elemento: a mais fraca entre as entidades FÍSICAS, ou `null` sem elas. */
  precisao: PrecisaoDaCena | null;
  /** Nome da precisão por extenso; `null` vira palavra também, nunca um traço mudo. */
  precisaoNome: string;
  alimenta: boolean;
  /** Por que não alimenta, escrito. `null` quando alimenta. */
  motivo: string | null;
};

/**
 * Os elementos declarados na cena, na ordem em que o `element_ref` foi cunhado.
 *
 * `EL-001` é cunhado em sequência pelo servidor, então ordenar pela string ordena pelo ato
 * — e uma ordenação alfabética é estável mesmo se a forma do ref mudar para um id opaco.
 */
export function elementosDeclarados(
  entities: readonly EntidadeDaCena[],
  rotulos: Readonly<Record<string, string>> = {},
): ElementoDeclarado[] {
  const porRef = new Map<string, EntidadeDaCena[]>();
  for (const entity of entities) {
    const ref = entity.element_ref ?? null;
    if (ref === null || ref === "") {
      continue;
    }
    const atual = porRef.get(ref);
    if (atual === undefined) {
      porRef.set(ref, [entity]);
    } else {
      atual.push(entity);
    }
  }
  return [...porRef.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([elementRef, doGrupo]) => {
      const fisicas = doGrupo.filter((entity) => !ehAnotacao(entity));
      const precisao = precisaoMaisFraca(
        fisicas.map((entity) => entity.precision as PrecisaoDaCena),
      );
      const alimenta = alimentaAMedicao(precisao);
      return {
        elementRef,
        rotulo: rotulos[elementRef] ?? null,
        camada: String(doGrupo[0]?.layer ?? ""),
        entityIds: doGrupo.map((entity) => entity.id ?? ""),
        anotacoes: doGrupo.length - fisicas.length,
        precisao,
        precisaoNome:
          precisao === null ? "sem geometria física" : precisionLabel(precisao),
        alimenta,
        motivo: alimenta ? null : motivoDeNaoAlimentar(precisao),
      };
    });
}

/** As entidades que ainda não são elemento nenhum, na ordem da cena. */
export function entidadesSemIdentidade(
  entities: readonly EntidadeDaCena[],
): EntidadeDaCena[] {
  return entities.filter(
    (entity) => entity.element_ref === null || entity.element_ref === undefined,
  );
}

/**
 * A cena tem alguma identidade declarada?
 *
 * É a chave do critério 8: sem nenhuma, a revisão do croqui não ganha etiqueta, selo nem
 * contagem de elemento em lugar nenhum — ela fica idêntica à de hoje.
 */
export function cenaTemIdentidade(entities: readonly EntidadeDaCena[]): boolean {
  return entities.some(
    (entity) => entity.element_ref !== null && entity.element_ref !== undefined,
  );
}

/** Rótulo da entidade sem identidade: espécie, camada e precisão, sempre por escrito. */
export function descricaoDaEntidade(entity: EntidadeDaCena): string {
  const especie = ehAnotacao(entity) ? `${String(entity.kind)} · anotação` : String(entity.kind);
  return `${especie} · camada ${String(entity.layer)} · ${precisionLabel(entity.precision)}`;
}

/**
 * O sinal que gerou a proposta, dito em palavras (critério de aceite 2). O selo diz que
 * é proposta; esta frase diz POR QUE ela foi proposta, que é o que permite recusá-la com
 * conhecimento de causa.
 */
const SINAIS_DA_PROPOSTA: Record<string, string> = {
  provenance:
    "mesma camada e mesma procedência de detecção — o mesmo lote descreveu mais de um traço",
  label_proximity:
    "mesma camada e o mesmo rótulo mais próximo — o texto que documenta os dois é o mesmo",
};

export function sinalDaProposta(signal: string): string {
  return SINAIS_DA_PROPOSTA[signal] ?? signal;
}

/**
 * O aviso que acompanha toda proposta. Proposta não é identidade: camada é vocabulário de
 * CAD, e dois elementos distintos moram na mesma camada com frequência. Aceitar um
 * agrupamento automático somaria quantidades de elementos diferentes sem ninguém ter
 * declarado nada.
 */
export const AVISO_DA_PROPOSTA =
  "Proposta não é identidade: ela nasce não resolvida, não alimenta quantidade nenhuma e " +
  "não vale nada até alguém declarar. Camada é vocabulário de CAD — dois elementos " +
  "distintos podem morar na mesma camada, e é por isso que a recusa existe.";

/** Motivo mínimo aceito pelo servidor em qualquer ato de identidade (`min_length=3`). */
export const MOTIVO_MINIMO = 3;

/** Teto de entidades num grupo, o mesmo que o servidor aceita (`max_length=200`). */
export const MAXIMO_DE_ENTIDADES = 200;

/** Teto do rótulo legível, o mesmo do contrato (`ELEMENT_LABEL_MAX_LENGTH`). */
export const MAXIMO_DO_ROTULO = 120;

/**
 * O que impede enviar o rótulo, dito em palavras — ou `null` quando nada impede.
 *
 * Rótulo em branco NÃO é impedimento: o campo é opcional, e não escrever nada é declarar o
 * elemento sem nome, que é cena válida. O que a tela evita é mandar `"   "`, que o servidor
 * recusa com `ELEMENT_LABEL_INVALID` — e o teto, que ela pode conferir sem adivinhar nada.
 */
export function problemaDoRotulo(rotulo: string): string | null {
  if (rotulo.length > 0 && rotulo.trim().length === 0) {
    return "O rótulo não pode ser só espaços. Para declarar sem nome, deixe o campo vazio.";
  }
  if (rotulo.trim().length > MAXIMO_DO_ROTULO) {
    return `O rótulo tem no máximo ${MAXIMO_DO_ROTULO} caracteres; este tem ${rotulo.trim().length}.`;
  }
  return null;
}

export type SelecaoDeEntidades = readonly string[];

/** Marca ou desmarca uma entidade, preservando a ordem de seleção. */
export function alternarEntidade(
  selecao: SelecaoDeEntidades,
  entityId: string,
): string[] {
  return selecao.includes(entityId)
    ? selecao.filter((item) => item !== entityId)
    : [...selecao, entityId];
}

/** As camadas distintas de uma seleção, em ordem, para o aviso de mistura de camadas. */
export function camadasDaSelecao(
  entities: readonly EntidadeDaCena[],
  selecao: SelecaoDeEntidades,
): string[] {
  const camadas: string[] = [];
  for (const entityId of selecao) {
    const entity = entities.find((item) => (item.id ?? "") === entityId);
    if (entity === undefined) {
      continue;
    }
    const camada = String(entity.layer);
    if (!camadas.includes(camada)) {
      camadas.push(camada);
    }
  }
  return camadas.sort((a, b) => a.localeCompare(b));
}

/**
 * O que impede o envio, dito em palavras — ou `null` quando nada impede.
 *
 * Mistura de camadas NÃO aparece aqui de propósito: quem recusa é o servidor
 * (`ELEMENT_REF_LAYER_MISMATCH`), e o client não duplica a autoridade dele. O aviso de
 * mistura existe na tela como AVISO (`avisoDeCamadasMisturadas`), não como bloqueio.
 */
export function problemaDaDeclaracao(
  selecao: SelecaoDeEntidades,
  motivo: string,
): string | null {
  if (selecao.length === 0) {
    return "Escolha ao menos uma entidade: quem declara o grupo é você, nunca a proximidade no desenho.";
  }
  if (selecao.length > MAXIMO_DE_ENTIDADES) {
    return `Um elemento reúne no máximo ${MAXIMO_DE_ENTIDADES} entidades; este grupo tem ${selecao.length}.`;
  }
  if (motivo.trim().length < MOTIVO_MINIMO) {
    return "Escreva a justificativa do agrupamento: a declaração fica gravada com autor e instante.";
  }
  return null;
}

/** Aviso (não bloqueio) quando a seleção mistura camadas. */
export function avisoDeCamadasMisturadas(camadas: readonly string[]): string | null {
  if (camadas.length < 2) {
    return null;
  }
  return (
    `Este grupo mistura as camadas ${camadas.join(", ")}. Um elemento não mistura camadas — ` +
    "o servidor vai recusar e dizer quais foram misturadas."
  );
}

/** O mesmo problema, para a recusa de uma proposta. */
export function problemaDaRecusa(motivo: string): string | null {
  if (motivo.trim().length < MOTIVO_MINIMO) {
    return "Escreva por que a proposta não descreve um elemento: a recusa fica registrada.";
  }
  return null;
}

/**
 * Envelope de erro do servidor traduzido para a tela (critério de aceite 7).
 *
 * `ELEMENT_REF_LAYER_MISMATCH` é o caso que o critério nomeia: o backend já recusa e já
 * diz QUAIS camadas foram misturadas em `details.layers`. Perder isso num "falha na API"
 * genérico transformaria uma recusa que ensina numa que só irrita.
 */
export function mensagemDoErroDeIdentidade(erro: {
  code: string | null;
  detail: string | null;
  details: Record<string, unknown>;
  message: string;
}): string {
  const camadas = erro.details["layers"];
  const entidades = erro.details["entity_ids"];
  switch (erro.code) {
    case "ELEMENT_REF_LAYER_MISMATCH":
      return (
        "Um elemento não mistura camadas; declare um grupo por camada." +
        (Array.isArray(camadas) && camadas.length > 0
          ? ` Camadas misturadas: ${camadas.map((item) => String(item)).join(", ")}.`
          : "")
      );
    case "ELEMENT_ALREADY_DECLARED":
      return (
        "Entidade já declarada em outro elemento. Mover uma entidade de um elemento para " +
        "outro são dois atos: revogue a identidade anterior e declare a nova." +
        (Array.isArray(entidades) && entidades.length > 0
          ? ` Entidades: ${entidades.map((item) => String(item)).join(", ")}.`
          : "")
      );
    case "ELEMENT_REF_NOT_ASSIGNABLE":
      return (
        "O nome do elemento é cunhado pelo servidor no ato. Você declara QUAIS entidades " +
        "são o elemento, nunca qual é o nome dele."
      );
    case "REVISION_CONFLICT":
      return (
        "A cena mudou desde que esta tela a leu — outra pessoa declarou algo antes. " +
        "Recarregue a cena e refaça a declaração sobre a revisão corrente."
      );
    case "ELEMENT_PROPOSAL_NOT_FOUND":
      return (
        "Esta proposta não é mais oferecida: ela já foi recusada, já virou elemento, ou a " +
        "cena mudou. Recarregue as propostas."
      );
    case "ELEMENT_NOT_DECLARED":
      return "Esta revisão não tem elemento declarado com este nome.";
    case "ELEMENT_LABEL_INVALID":
      return (
        "O rótulo do elemento não pode ser vazio nem só de espaços. Para declarar o " +
        "elemento sem nome, deixe o campo do rótulo em branco."
      );
    case "JOB_NOT_READY":
      return "Ainda não há cena resolvida: a identidade de elemento é declarada sobre a geometria.";
    case "FORBIDDEN":
      return "Declarar identidade de elemento exige papel de revisão, que esta conta não tem.";
    default:
      return erro.detail ?? erro.message;
  }
}

/**
 * O carimbo do ato, como a tela o escreve (Design Approval Package, decisão 4).
 *
 * A API devolve o PAPEL profissional de quem declarou, nunca o subject — o pacote de
 * design desenha um nome de pessoa (fixture), e o contrato do produto qualifica o ato em
 * vez de identificar a pessoa. A tela escreve o que a API manda.
 */
export function carimboDoAto(
  ato: {
    element_ref: string;
    acted_by_role: string;
    entity_ids: readonly string[];
    label?: string | null;
  },
  instante: string,
  sceneVersion: number,
): string {
  const entidades =
    ato.entity_ids.length === 1 ? "1 entidade" : `${ato.entity_ids.length} entidades`;
  // O rótulo entra no carimbo entre aspas e DEPOIS do ref: quem lê confere o nome que
  // escreveu sem que ele se confunda com a identidade, que é a etiqueta à esquerda.
  const rotulo =
    ato.label === null || ato.label === undefined ? "" : ` “${ato.label}”`;
  return (
    `${ato.element_ref}${rotulo} declarado por ${ato.acted_by_role} em ${instante}, ` +
    `sobre a revisão v${sceneVersion} da cena · ${entidades}.`
  );
}

/** Entidades da cena, tipadas pelo contrato gerado — nunca redeclaradas aqui. */
export type CenaDaIdentidade = SceneRevision.CroquitoSceneRevision;
