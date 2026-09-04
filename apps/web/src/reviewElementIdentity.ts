/**
 * Derivação pura da identidade de elemento na REVISÃO (F-051 T6, ADR-0063).
 *
 * O irmão, uma etapa antes, de `elementIdentity.ts`: lá a identidade mora na cena resolvida,
 * aqui ela mora sobre as propostas de geometria, antes do solve. Este módulo só LÊ — ele não
 * cunha `element_ref` (quem cunha é `POST /v1/jobs/{id}/review/elements`), não decide
 * associação e não inventa candidata: as candidatas por identidade já vieram persistidas da
 * revisão (F-051 T4), e o que se faz aqui é agrupá-las para a tela dizer de QUAL elemento
 * cada uma veio.
 *
 * Sobre o casamento hint↔rótulo: a autoridade é do servidor
 * (`croquito_worker.element_identity_matching`), que é quem cunha a candidata. A comparação
 * daqui é EQUIVALENTE e existe só para escrever a frase que explica o casamento; ela nunca
 * cria, esconde ou ordena candidata. Duas diferenças declaradas, e nenhuma delas muda o que
 * a tela mostra: `toLowerCase` não é `casefold` (o servidor normaliza casos que o JavaScript
 * deixa passar), e o dono de cada candidata é achado pelo `proposal_id` — fato gravado —, e
 * não pelo casamento de texto.
 */
import type { ReviewElementDeclaration, ReviewReading, VisionProposal } from "./api";
import { MOTIVO_MINIMO } from "./elementIdentity";

/** O valor de `relation` que a T4 cunhou para a candidata por identidade. */
export const RELACAO_POR_IDENTIDADE = "element_identity";

/** A palavra que acompanha o chip do hint — sugestão nunca se veste de identidade. */
export const ROTULO_DO_HINT = "elemento (hint do modelo)";

/**
 * Separadores que quebram um rótulo em palavras, além do espaço. Espelho declarado de
 * `LABEL_TOKEN_SEPARATORS` (`element_identity_matching.py`): `"B — fecho da área de lazer"`,
 * `"grade B / lateral"`, `"B: arquibancada"`.
 */
const SEPARADORES_DE_ROTULO = ["—", "-", "·", ":", "/"];

/** A forma comparável de um rótulo: sem espaço nas pontas, sem distinção de caixa. */
export function normalizarRotuloDeElemento(valor: string): string {
  return valor.trim().toLowerCase();
}

function palavrasDoRotulo(rotuloNormalizado: string): string[] {
  let texto = rotuloNormalizado;
  for (const separador of SEPARADORES_DE_ROTULO) {
    texto = texto.split(separador).join(" ");
  }
  return texto.split(/\s+/).filter((palavra) => palavra.length > 0);
}

/**
 * O hint da cota-balão aponta para este elemento? Espelho de `hint_matches_label`.
 *
 * Verdadeiro em dois casos, ambos exatos: igualdade normalizada, ou o hint como palavra
 * inteira do rótulo (`"B"` casa com `"grade B"`). Falso em tudo o mais — nunca há
 * parecença, distância de edição ou prefixo. A relação é assimétrica de propósito: o hint
 * procura pelo rótulo, não o contrário.
 */
export function hintCasaComORotulo(hint: string, rotulo: string): boolean {
  const hintNormalizado = normalizarRotuloDeElemento(hint);
  if (hintNormalizado === "") {
    return false;
  }
  const rotuloNormalizado = normalizarRotuloDeElemento(rotulo);
  if (hintNormalizado === rotuloNormalizado) {
    return true;
  }
  return palavrasDoRotulo(rotuloNormalizado).includes(hintNormalizado);
}

/** O rótulo estruturado que o modelo leu no balão, aparado; `null` quando não veio. */
export function hintDoModelo(reading: ReviewReading): string | null {
  const rotulo = (reading.target_entity_label ?? "").trim();
  return rotulo === "" ? null : rotulo;
}

/** As identidades que valem agora. A revogada fica na lista, mas não é identidade. */
export function identidadesAtivas(
  declaracoes: readonly ReviewElementDeclaration[],
): ReviewElementDeclaration[] {
  return declaracoes.filter((item) => item.status === "active");
}

/**
 * Propostas já cobertas por identidade ATIVA — espelho de `_review_declared_proposal_ids`.
 *
 * Revogada não conta: revogar libera as propostas, e elas voltam a poder ser declaradas.
 */
export function propostasDeclaradas(
  declaracoes: readonly ReviewElementDeclaration[],
): Set<string> {
  const cobertas = new Set<string>();
  for (const declaracao of identidadesAtivas(declaracoes)) {
    for (const proposalId of declaracao.proposal_ids) {
      cobertas.add(proposalId);
    }
  }
  return cobertas;
}

/** As propostas que ainda não são elemento nenhum, na ordem do snapshot. */
export function propostasSemIdentidade(
  propostas: readonly VisionProposal[],
  declaracoes: readonly ReviewElementDeclaration[],
): VisionProposal[] {
  const cobertas = propostasDeclaradas(declaracoes);
  return propostas.filter((proposta) => !cobertas.has(proposta.id));
}

/**
 * A candidata como a tela precisa lê-la. Estrutural de propósito: o objeto que chega da API
 * carrega mais campos (score, alinhamento) e a tela nunca ordena, filtra ou decide por eles.
 */
export type CandidataDaLeitura = {
  proposal_id: string;
  relation: string;
};

export type GrupoDeIdentidade = {
  /** Chave de render; o `element_ref` quando há dono, `sem-dono` no grupo de resíduo. */
  chave: string;
  elementRef: string | null;
  rotulo: string | null;
  /** Dono revogado ainda sustenta candidata de associação confirmada — dito por escrito. */
  revogada: boolean;
  rotuloDoGrupo: string;
  candidatas: CandidataDaLeitura[];
};

export type CandidatasAgrupadas = {
  /** Os grupos por identidade, na ordem em que os refs foram cunhados. */
  grupos: GrupoDeIdentidade[];
  /** Todo o resto, na ordem em que a revisão as persistiu — o ranking não muda. */
  proximidade: CandidataDaLeitura[];
};

/** O nome do elemento como a tela o escreve: etiqueta e rótulo, nunca um sem o outro. */
function nomeDoElemento(elementRef: string, rotulo: string | null): string {
  return rotulo === null ? `◇ ${elementRef} · sem rótulo` : `◇ ${elementRef} · ${rotulo}`;
}

function rotuloDoGrupo(dono: ReviewElementDeclaration | null): string {
  if (dono === null) {
    // Resíduo honesto: a candidata é por identidade (o contrato o diz), mas a tela não
    // conseguiu ler de qual elemento — não inventa um ref para preencher o rótulo.
    return "Pela identidade do elemento declarado";
  }
  const nome = nomeDoElemento(dono.element_ref, dono.label);
  return dono.status === "revoked"
    ? `Pela identidade — ${nome} (identidade revogada)`
    : `Pela identidade — ${nome}`;
}

/**
 * Quem é o dono de uma proposta: a identidade ATIVA que a contém e, na falta dela, a
 * revogada.
 *
 * A revogada entra porque a candidata que SUSTENTA uma associação já confirmada permanece
 * na revisão depois da revogação (contrato da rota de revogação) — e o grupo precisa dizer
 * isso por escrito, em vez de aparecer sem dono ou, pior, como identidade viva.
 */
function donoDaProposta(
  proposalId: string,
  declaracoes: readonly ReviewElementDeclaration[],
): ReviewElementDeclaration | null {
  const ativa = identidadesAtivas(declaracoes).find((item) =>
    item.proposal_ids.includes(proposalId),
  );
  if (ativa !== undefined) {
    return ativa;
  }
  return (
    declaracoes.find(
      (item) => item.status === "revoked" && item.proposal_ids.includes(proposalId),
    ) ?? null
  );
}

/**
 * Separa as candidatas da leitura em grupos por identidade e no resto, por PROXIMIDADE.
 *
 * Sem candidata por identidade, `grupos` volta vazio — e é isso que garante o estado 09 do
 * pacote de design: nenhum grupo vazio aparece no seletor, e a lista sai plana como hoje.
 * A ordem interna de cada lista é a da revisão: a tela não reordena candidata nenhuma.
 */
export function agruparCandidatas(
  candidatas: readonly CandidataDaLeitura[],
  declaracoes: readonly ReviewElementDeclaration[],
): CandidatasAgrupadas {
  const proximidade: CandidataDaLeitura[] = [];
  const porChave = new Map<string, GrupoDeIdentidade>();
  for (const candidata of candidatas) {
    if (candidata.relation !== RELACAO_POR_IDENTIDADE) {
      proximidade.push(candidata);
      continue;
    }
    const dono = donoDaProposta(candidata.proposal_id, declaracoes);
    const chave = dono === null ? "sem-dono" : dono.element_ref;
    const existente = porChave.get(chave);
    if (existente === undefined) {
      porChave.set(chave, {
        chave,
        elementRef: dono?.element_ref ?? null,
        rotulo: dono?.label ?? null,
        revogada: dono?.status === "revoked",
        rotuloDoGrupo: rotuloDoGrupo(dono),
        candidatas: [candidata],
      });
    } else {
      existente.candidatas.push(candidata);
    }
  }
  const grupos = [...porChave.values()].sort((a, b) => {
    // O resíduo sem dono fica por último; o resto na ordem em que os refs foram cunhados.
    if (a.elementRef === null) {
      return b.elementRef === null ? 0 : 1;
    }
    if (b.elementRef === null) {
      return -1;
    }
    return a.elementRef.localeCompare(b.elementRef);
  });
  return { grupos, proximidade };
}

/**
 * A frase sob o seletor que diz POR QUE aquelas candidatas estão ali (DAP, decisão 5).
 *
 * `null` quando não há o que explicar. Nunca cita score nem distância: a tela não ordena
 * nem decide por eles, e escrevê-los aqui os transformaria em critério aos olhos de quem lê.
 */
export function dicaDoCasamento(
  hint: string | null,
  grupos: readonly GrupoDeIdentidade[],
): string | null {
  if (grupos.length === 0) {
    return null;
  }
  const nomes = grupos.map((grupo) =>
    grupo.elementRef === null
      ? "um elemento declarado desta revisão"
      : nomeDoElemento(grupo.elementRef, grupo.rotulo),
  );
  const lista =
    nomes.length === 1
      ? nomes[0]
      : `${nomes.slice(0, -1).join(", ")} e ${nomes[nomes.length - 1]}`;
  const sujeito =
    hint === null
      ? "A identidade declarada alcança"
      : `O hint “${hint}” casa com ${nomes.length === 1 ? "o elemento declarado" : "os elementos declarados"}`;
  return (
    `${sujeito} ${lista} — as propostas ${nomes.length === 1 ? "dele" : "deles"} entram como ` +
    "candidatas pela identidade, independente de distância."
  );
}

/**
 * A frase do estado 07: o hint existe, há elemento declarado, e nenhum deles é o referente.
 *
 * Só fala quando há declaração ATIVA no job. Sem nenhuma, a etapa é a de hoje e um aviso
 * aqui seria ruído sobre uma feature que aquele job não usa (DAP, decisão 12).
 */
export function dicaDeHintSemCasamento(
  hint: string | null,
  declaracoes: readonly ReviewElementDeclaration[],
  grupos: readonly GrupoDeIdentidade[],
): string | null {
  if (hint === null || grupos.length > 0 || identidadesAtivas(declaracoes).length === 0) {
    return null;
  }
  return (
    `Nenhum elemento declarado tem o rótulo “${hint}” — nenhuma candidata nova. O hint fica ` +
    "visível, esperando ou uma declaração ou uma correção."
  );
}

/** Teto do motivo em qualquer ato de identidade, o mesmo do contrato (`max_length=500`). */
export const MAXIMO_DO_MOTIVO = 500;

/**
 * O que impede declarar, dito em palavras — ou `null` quando nada impede.
 *
 * O irmão de `problemaDaDeclaracao` (cena) sobre propostas. Rótulo NÃO entra aqui: ele é
 * opcional, tem impedimento próprio (`problemaDoRotulo`), e a unicidade entre identidades
 * ativas é do servidor (`ELEMENT_LABEL_ALREADY_USED`) — o client não duplica a autoridade.
 */
export function problemaDaDeclaracaoDaRevisao(
  selecao: readonly string[],
  motivo: string,
): string | null {
  if (selecao.length === 0) {
    return (
      "Escolha ao menos uma proposta: um elemento da revisão é declarado sobre geometria " +
      "proposta, e o balão que o CV nunca propôs continua sendo anotação da folha."
    );
  }
  return problemaDoMotivo(
    motivo,
    "Escreva a justificativa do agrupamento: a declaração fica gravada com autor e instante.",
  );
}

/** O motivo mínimo (e máximo) de qualquer ato de identidade da revisão. */
export function problemaDoMotivo(motivo: string, ausente: string): string | null {
  const aparado = motivo.trim();
  if (aparado.length < MOTIVO_MINIMO) {
    return ausente;
  }
  if (aparado.length > MAXIMO_DO_MOTIVO) {
    return `O motivo tem no máximo ${MAXIMO_DO_MOTIVO} caracteres; este tem ${aparado.length}.`;
  }
  return null;
}

/** O que impede revogar: o motivo fica gravado, como em toda identidade desfeita. */
export function problemaDaRevogacao(motivo: string): string | null {
  return problemaDoMotivo(
    motivo,
    "Escreva por que a identidade deixa de valer: a revogação fica registrada, e o histórico não se apaga.",
  );
}

/** O que impede renomear: rótulo obrigatório (renomear para nada seria revogar o nome). */
export function problemaDoRenomear(rotulo: string, motivo: string): string | null {
  if (rotulo.trim().length === 0) {
    return "Escreva o rótulo novo: renomear exige um nome, e apagar o nome não é renomear.";
  }
  return problemaDoMotivo(
    motivo,
    "Escreva por que o nome muda: renomear é ato declarado, não edição silenciosa.",
  );
}

/**
 * O carimbo do ato da revisão, como a tela o escreve — papel profissional, nunca o usuário.
 *
 * Irmão de `carimboDoAto` (cena): lá o ato cita a versão da CENA e conta entidades; aqui
 * cita a versão do PACOTE DE REVISÃO e conta propostas, porque é sobre propostas que a
 * identidade nasce uma etapa antes.
 */
export function carimboDoAtoDaRevisao(
  ato: {
    act: "declared" | "revoked" | "relabeled";
    element_ref: string;
    acted_by_role: string;
    proposal_ids: readonly string[];
    label?: string | null;
    review_version: number;
  },
  instante: string,
): string {
  const verbo =
    ato.act === "declared"
      ? "declarado"
      : ato.act === "revoked"
        ? "revogado"
        : "renomeado";
  const propostas =
    ato.proposal_ids.length === 1 ? "1 proposta" : `${ato.proposal_ids.length} propostas`;
  const rotulo =
    ato.label === null || ato.label === undefined ? "" : ` “${ato.label}”`;
  return (
    `${ato.element_ref}${rotulo} ${verbo} por ${ato.acted_by_role} em ${instante}, ` +
    `sobre a revisão v${ato.review_version} do pacote de revisão · ${propostas}.`
  );
}

/**
 * Envelope de erro do servidor traduzido para a tela — a camada da REVISÃO.
 *
 * Devolve `null` no código que esta camada não precisa reescrever, e quem chama cai em
 * `mensagemDoErroDeIdentidade` (cena) para ele: uma segunda tabela com as mesmas entradas
 * envelheceria pela metade. O que está aqui, está por um motivo — ou o código só existe na
 * revisão (`ELEMENT_LABEL_ALREADY_USED`, `PROPOSALS_NOT_READY`,
 * `REVIEW_ELEMENT_SUGGESTION_NOT_FOUND`), ou a frase da cena fala de ENTIDADE onde a revisão
 * fala de PROPOSTA, e mandar o revisor procurar entidade nesta etapa seria mandá-lo procurar
 * o que ainda não existe.
 */
export function mensagemDoErroDaRevisao(erro: {
  code: string | null;
  detail: string | null;
  details: Record<string, unknown>;
  message: string;
}): string | null {
  const elementRef = erro.details["element_ref"];
  const propostas = erro.details["proposal_ids"];
  switch (erro.code) {
    case "ELEMENT_LABEL_ALREADY_USED":
      return (
        "Este rótulo já é de outra identidade ativa deste job. O casamento por identidade " +
        "precisa de referente inequívoco: renomeie o elemento existente ou use outro rótulo." +
        (typeof elementRef === "string" ? ` Já usado por ${elementRef}.` : "")
      );
    case "ELEMENT_ALREADY_DECLARED":
      return (
        "Proposta já declarada em outro elemento. Mover uma proposta de um elemento para " +
        "outro são dois atos: revogue a identidade anterior e declare a nova." +
        (Array.isArray(propostas) && propostas.length > 0
          ? ` Propostas: ${propostas.map((item) => String(item)).join(", ")}.`
          : "")
      );
    case "ELEMENT_NOT_DECLARED":
      return (
        "Esta revisão não tem elemento ativo com este nome — ele nunca existiu ou já foi " +
        "revogado. Recarregue a revisão atual."
      );
    case "REVISION_CONFLICT":
      return (
        "A revisão mudou desde que esta tela a leu — outra pessoa gravou algo antes. " +
        "Recarregue a revisão atual e refaça o ato sobre ela."
      );
    case "PROPOSALS_NOT_READY":
      return (
        "Esta revisão ainda não tem propostas de geometria. A identidade da revisão é " +
        "declarada sobre proposta; sem nenhuma, o caminho continua sendo a anotação da folha."
      );
    case "REVIEW_ELEMENT_SUGGESTION_NOT_FOUND":
      return (
        "Esta sugestão não é mais oferecida: ela já foi recusada, já virou elemento, ou a " +
        "revisão mudou. Recarregue a revisão atual."
      );
    case "DOMAIN_VALIDATION_FAILED":
      return (
        "O grupo cita proposta que não pertence ao snapshot desta revisão." +
        (Array.isArray(propostas) && propostas.length > 0
          ? ` Propostas: ${propostas.map((item) => String(item)).join(", ")}.`
          : "")
      );
    case "FORBIDDEN":
      return "Declarar identidade de elemento exige papel de revisão, que esta conta não tem.";
    default:
      return null;
  }
}
