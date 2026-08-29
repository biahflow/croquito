/**
 * A praça de várias folhas na tela (F-046, ADR-0057): leitura pura do estado servido por
 * `GET /v1/valuation-rounds/{round_id}/worksite`.
 *
 * A praça grande não cabe numa folha — vem em planta geral, folhas de detalhe e cortes —,
 * e a legenda quantificada é da OBRA. Este módulo não decide nada: ele traduz o que o
 * servidor já disse sobre cada folha em estado por extenso, símbolo próprio e frase de
 * obra, e nomeia a folha na recusa. Três regras da casa moram aqui:
 *
 * - **Cor nunca é o único indicador.** Todo estado de folha tem símbolo (`✓`, `▲`, `◐`,
 *   `✕`, `○`) e texto por extenso; a cor entra depois, no CSS.
 * - **Nada é somado, multiplicado ou arredondado.** As contagens exibidas são as que o
 *   servidor mandou por folha. O consolidado da praça (`GET .../worksite`) referencia
 *   pacotes por digest e **não** traz quantidade nem dinheiro; quem traz os números é o
 *   BOLETIM (`POST .../calc`, F-046 T4c), com um boletim por folha, e o que este módulo
 *   faz com ele é só *achar a folha certa* — nunca recalcular linha nenhuma.
 * - **Ausência é declarada, nunca preenchida.** Folha sem pacote tem contagem `null`, e
 *   `null` vira frase ("ainda não extraída"), nunca zero.
 *
 * A praça de UMA folha responde como sempre respondeu: `pracaPlural` é falso, e quem
 * consome este módulo não mostra faixa, nem "folha 1 de 1", nem etapa própria (decisão 8
 * do ADR-0057, decisão 13 do pacote de design aprovado).
 */

import type { Valuation } from "@croquito/contracts";

import type {
  CodesResponse,
  TakeoffItemAddress,
  WorksiteResponse,
  WorksiteSheet,
} from "./api";
import { extractionFailureMessage } from "./labels";

/** Estado de uma folha: identidade estável, símbolo próprio e o texto por extenso. */
export type EstadoDaFolha = {
  id: "revisada" | "pendente" | "extraindo" | "falhou" | "nao-extraida";
  /** Símbolo que acompanha o texto; a folha continua legível em preto e branco. */
  symbol: string;
  label: string;
};

const ESTADOS: Record<EstadoDaFolha["id"], EstadoDaFolha> = {
  revisada: { id: "revisada", symbol: "✓", label: "extraída e revisada" },
  pendente: { id: "pendente", symbol: "▲", label: "pendente de revisão" },
  extraindo: { id: "extraindo", symbol: "◐", label: "em extração" },
  falhou: { id: "falhou", symbol: "✕", label: "extração falhou" },
  "nao-extraida": {
    id: "nao-extraida",
    symbol: "○",
    label: "ainda não extraída",
  },
};

/**
 * O estado da folha, na ordem em que ela pode não estar pronta.
 *
 * A presença do PACOTE manda: uma folha com pacote publicado está extraída, mesmo que a
 * coluna de extração da folha ainda diga `running` porque o espelho não foi reescrito. É a
 * mesma ordem que o servidor usa para montar o consolidado — pacote primeiro, estado da
 * fila depois.
 */
export function estadoDaFolha(sheet: WorksiteSheet): EstadoDaFolha {
  if (sheet.takeoff_present) {
    return sheet.review_status === "complete" ? ESTADOS.revisada : ESTADOS.pendente;
  }
  if (sheet.extraction_status === "queued" || sheet.extraction_status === "running") {
    return ESTADOS.extraindo;
  }
  if (sheet.extraction_status === "failed") {
    return ESTADOS.falhou;
  }
  return ESTADOS["nao-extraida"];
}

function plural(count: number, singular: string, many: string): string {
  return `${count} ${count === 1 ? singular : many}`;
}

/**
 * Resumo da folha no cartão: contagens do servidor, nunca deduzidas.
 *
 * Só o que a rota da praça manda por folha aparece aqui — total de itens, decididos e
 * pendentes. A separação entre proposto e ambíguo, que a folha em revisão mostra, não é
 * servida por folha e por isso não é escrita: contar de cabeça o que o servidor não disse
 * seria inventar a leitura de uma prancha que esta tela nem abriu.
 */
export function resumoDaFolha(sheet: WorksiteSheet): string {
  const estado = estadoDaFolha(sheet);
  if (estado.id === "falhou") {
    return extractionFailureMessage(sheet.extraction_failure_code);
  }
  if (estado.id === "extraindo") {
    return "Leitura da legenda em curso nesta folha.";
  }
  if (estado.id === "nao-extraida") {
    return `Página ${sheet.page_number} do documento; leitura da legenda ainda não disparada.`;
  }
  const total = sheet.item_count ?? 0;
  const pendentes = sheet.pending_items ?? 0;
  const decididos = total - pendentes;
  const partes = [
    plural(total, "item", "itens"),
    `${decididos} ${decididos === 1 ? "decidido" : "decididos"}`,
  ];
  if (pendentes > 0) {
    partes.push(`${pendentes} ${pendentes === 1 ? "pendente" : "pendentes"}`);
  }
  return partes.join(" · ");
}

/** "folha 2 de 3" — a posição que o servidor deu, sobre o total de folhas da praça. */
export function folhaLabel(position: number, total: number): string {
  return `folha ${position} de ${total}`;
}

/**
 * A praça é plural? O plural, a faixa de folhas e a etapa própria nascem no momento em que
 * a SEGUNDA folha é acrescentada, e não antes (pacote de design, decisão 13).
 */
export function pracaPlural(worksite: WorksiteResponse | null): boolean {
  return (worksite?.plates.length ?? 0) > 1;
}

/** A folha em foco: a escolhida, ou a primeira da praça enquanto ninguém escolheu. */
export function folhaEmFoco(
  worksite: WorksiteResponse | null,
  plateId: string,
): WorksiteSheet | null {
  const folhas = worksite?.plates ?? [];
  return folhas.find((folha) => folha.plate_id === plateId) ?? folhas[0] ?? null;
}

/**
 * A folha a nomear nas chamadas — ou `undefined`, que é "a primeira folha".
 *
 * `undefined` na praça de UMA folha é a regra que mantém a rodada de uma prancha idêntica
 * à de antes da praça (ADR-0057, decisão 8): a URL e o corpo saem sem `plate_id`, byte a
 * byte como saíam. Na praça plural a folha é sempre nomeada, inclusive quando é a
 * primeira — uma chamada que não diz de qual folha fala é uma chamada que o próximo leitor
 * tem de adivinhar.
 */
export function folhaDaChamada(
  worksite: WorksiteResponse | null,
  plateId: string,
): string | undefined {
  if (!pracaPlural(worksite)) {
    return undefined;
  }
  return folhaEmFoco(worksite, plateId)?.plate_id;
}

/** A recusa da praça, com as folhas que a causaram nomeadas. */
export type RecusaDaPraca = {
  /** Código estável do servidor; ele vai à tela ao lado da frase. */
  code: string | null;
  message: string;
  /** As folhas citadas, já com "folha N de M" e a `plate_id`. */
  folhas: string[];
};

function nomeDaFolha(sheet: WorksiteSheet, total: number): string {
  return `${folhaLabel(sheet.position, total)} — ${sheet.plate_id}`;
}

/**
 * Por que a praça não fecha, nomeando QUAL folha falta (pacote de design, decisão 12).
 *
 * Meia praça somada parece uma praça inteira: a recusa tem que dizer qual metade falta, e
 * as duas maneiras de faltar são diferentes — folha que ainda não virou pacote e folha
 * extraída com item sem decisão. As duas listas saem do que o servidor mandou por folha.
 *
 * Devolve `null` quando o consolidado está presente: aí não há recusa nenhuma a mostrar.
 */
export function recusaDaPraca(worksite: WorksiteResponse | null): RecusaDaPraca | null {
  if (worksite === null || worksite.consolidated.present) {
    return null;
  }
  const total = worksite.plates.length;
  if (total === 0) {
    return {
      code: worksite.consolidated.refusal_code,
      message: "A praça ainda não tem folha nenhuma.",
      folhas: [],
    };
  }
  const semPacote = worksite.plates.filter((folha) => !folha.takeoff_present);
  const comPendencia = worksite.plates.filter(
    (folha) => folha.takeoff_present && (folha.pending_items ?? 0) > 0,
  );
  const frases: string[] = [];
  const folhas: string[] = [];
  for (const folha of comPendencia) {
    const pendentes = folha.pending_items ?? 0;
    frases.push(
      `${nomeDaFolha(folha, total)} tem ${plural(
        pendentes,
        "item sem decisão",
        "itens sem decisão",
      )}`,
    );
    folhas.push(nomeDaFolha(folha, total));
  }
  for (const folha of semPacote) {
    const estado = estadoDaFolha(folha);
    frases.push(`${nomeDaFolha(folha, total)} ${estado.label}`);
    folhas.push(nomeDaFolha(folha, total));
  }
  const motivo =
    frases.length === 0
      ? "o servidor ainda não montou o consolidado desta praça"
      : frases.join("; ");
  return {
    code: worksite.consolidated.refusal_code,
    message: `A praça não fecha com folha pendente: ${motivo}. Termine a revisão dessas folhas para montar o boletim da praça.`,
    folhas,
  };
}

/**
 * Páginas do documento que já viraram folha desta praça.
 *
 * Serve para o lote de promoção não oferecer de novo a página que já está na praça — o
 * servidor recusaria (`ROUND_PLATE_ALREADY_PRESENT`), e oferecer o que já se sabe recusado
 * é convidar ao erro. A comparação é por digest da ORIGEM: a mesma página de outro
 * documento é outra folha.
 */
export function paginasPromovidas(
  worksite: WorksiteResponse | null,
  sourceSha256: string | null,
): number[] {
  if (worksite === null || sourceSha256 === null) {
    return [];
  }
  const digest = sourceSha256.toLowerCase();
  return worksite.plates
    .filter((folha) => folha.source_sha256.toLowerCase() === digest)
    .map((folha) => folha.page_number)
    .sort((left, right) => left - right);
}

/** Quantas folhas ainda cabem na praça, pelo teto que o servidor declarou. */
export function folhasQueAindaCabem(worksite: WorksiteResponse | null): number {
  if (worksite === null) {
    return 0;
  }
  return Math.max(0, worksite.plate_limit - worksite.plates.length);
}

/**
 * O texto do botão de promover, com o número de folhas escrito nele.
 *
 * O custo por folha não pode aparecer só na fatura (pacote de design, decisão 4): o número
 * de folhas que o ato acrescenta — e, portanto, de leituras pagas que ele torna possíveis —
 * fica no próprio botão, antes do clique.
 */
export function rotuloDoLoteDePromocao(selecionadas: number): string {
  if (selecionadas === 0) {
    return "Escolha as páginas que viram prancha";
  }
  return `Acrescentar ${plural(selecionadas, "folha", "folhas")} à praça`;
}

/** O texto do botão de extrair, com o número de chamadas pagas escrito nele. */
export function rotuloDoLoteDeExtracao(selecionadas: number): string {
  if (selecionadas === 0) {
    return "Escolha as folhas que vão para a leitura";
  }
  return `Ler a legenda de ${plural(selecionadas, "folha", "folhas")} · ${plural(
    selecionadas,
    "chamada paga",
    "chamadas pagas",
  )}`;
}

/** O aviso ao lado do botão de promover; repete o número que está no botão. */
export function avisoDoLoteDePromocao(selecionadas: number): string {
  return (
    `${plural(selecionadas, "página selecionada", "páginas selecionadas")}. ` +
    "A seleção é em lote e a confirmação é uma só; promover não lê legenda nenhuma — a " +
    "leitura é ato à parte, e é ela que custa."
  );
}

/**
 * A chave do boletim de uma folha, espelho exato de `worksite_calc._plate_labels`.
 *
 * Com UMA folha, a praça É a folha e a chave passa intacta — é isso que mantém a rodada de
 * uma prancha byte-idêntica (ADR-0057, decisão 8). Com mais de uma, cada folha ganha o
 * sufixo `-pN` da posição dela, porque `Valuation` recusa dois boletins com a mesma chave.
 *
 * Espelhar aqui é deliberado e é a alternativa MENOS ruim: a resposta do boletim não
 * carrega `plate_id`, e casar por chave detecta o boletim vencido (montado antes de a
 * folha entrar na praça), coisa que casar por posição na lista esconderia — ele
 * simplesmente rotularia o boletim da folha 1 com o cabeçalho da folha 2.
 */
export function chaveDoBoletimDaFolha(
  worksiteKey: string,
  position: number,
  total: number,
): string {
  return total <= 1 ? worksiteKey : `${worksiteKey}-p${position}`;
}

/**
 * O boletim gravado DESTA folha, ou `null` quando o boletim não fala dela.
 *
 * `null` é estado honesto e frequente: a praça que ganhou folha depois do último `calc`
 * tem boletim que não a cobre. Quem consome escreve isso — nunca mostra o boletim de outra
 * folha sob este cabeçalho, que é a mesma regra da imagem da prancha.
 */
export function boletimDaFolha(
  valuation: Valuation.CroquitoValuation | null,
  worksiteKey: string,
  folha: WorksiteSheet,
  total: number,
): Valuation.WorksiteBulletin | null {
  if (valuation === null) {
    return null;
  }
  const chave = chaveDoBoletimDaFolha(worksiteKey, folha.position, total);
  return valuation.bulletins.find((boletim) => boletim.worksite_key === chave) ?? null;
}

/**
 * A memória de cálculo de um boletim: as parcelas da folha, na ordem do servidor.
 *
 * A memória mora na folha onde a leitura foi feita — é o que faz a parcela continuar
 * dizendo de onde veio, inclusive a leitura absorvida por um vínculo, que continua
 * impressa com subtotal zero na folha dela.
 */
export function memoriaDaFolha(
  valuation: Valuation.CroquitoValuation | null,
  chave: string,
): Valuation.CalcSheet[] {
  if (valuation === null) {
    return [];
  }
  return valuation.calc_sheets.filter((sheet) => sheet.worksite_key === chave);
}

/** O que falta codificar numa folha, com as contagens que o servidor mandou dela. */
export type CodificacaoDaFolha = {
  plateId: string;
  position: number;
  /** Pares `(item, código)` confirmados nesta folha. */
  confirmed: number;
  /** Elementos com o pacote de serviços declarado completo nesta folha. */
  closed: number;
  /** Elementos ainda sem pacote fechado; é o que trava o boletim da praça. */
  pending: number;
};

/**
 * O andamento da codificação por folha, a partir do que cada leitura por folha devolveu.
 *
 * Nenhum número é derivado: `confirmed`, `closed` e o tamanho de `pending_items` são do
 * servidor, uma leitura por folha. Folha que ainda não foi lida simplesmente não entra —
 * ausência declarada, nunca zero fabricado.
 */
export function codificacaoDasFolhas(
  worksite: WorksiteResponse | null,
  porFolha: Readonly<Record<string, CodesResponse>>,
): CodificacaoDaFolha[] {
  return (worksite?.plates ?? []).flatMap((folha) => {
    const codes = porFolha[folha.plate_id];
    if (codes === undefined) {
      return [];
    }
    return [
      {
        plateId: folha.plate_id,
        position: folha.position,
        confirmed: codes.confirmed,
        closed: codes.closed,
        pending: codes.pending_items.length,
      },
    ];
  });
}

/** A frase de uma folha na lista de andamento da codificação. */
export function resumoDaCodificacao(
  folha: CodificacaoDaFolha,
  total: number,
): string {
  const partes = [
    `${folhaLabel(folha.position, total)}`,
    plural(folha.closed, "elemento fechado", "elementos fechados"),
    plural(folha.confirmed, "código confirmado", "códigos confirmados"),
  ];
  partes.push(
    folha.pending === 0
      ? "nada pendente"
      : plural(folha.pending, "elemento pendente", "elementos pendentes"),
  );
  return partes.join(" · ");
}

/**
 * Por que este vínculo não pode nem ser pré-visualizado — ou `null` quando ele pode.
 *
 * Só as recusas que **não dependem do servidor**: endereço incompleto e as duas leituras
 * na mesma folha (`WORKSITE_LINK_SAME_PLATE`). Elas evitam a viagem; a recusa do servidor
 * continua sendo a autoridade, e nenhuma outra é antecipada aqui — alvo inexistente e
 * cadeia de vínculos são dele, e adivinhá-las aqui seria decidir no lugar dele.
 */
export function recusaDoVinculo(
  kept: TakeoffItemAddress,
  discarded: TakeoffItemAddress,
): string | null {
  if (
    kept.plate_id === "" ||
    kept.item_id === "" ||
    discarded.plate_id === "" ||
    discarded.item_id === ""
  ) {
    return "Escolha as duas leituras: a que fica e a que é absorvida.";
  }
  if (kept.plate_id === discarded.plate_id) {
    return (
      "O vínculo de identidade é entre folhas diferentes: duas leituras da mesma folha " +
      "são dois itens da legenda, e item repetido dentro de uma folha se resolve " +
      "rejeitando um deles na revisão."
    );
  }
  return null;
}
