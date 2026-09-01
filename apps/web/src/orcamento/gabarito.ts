/**
 * O GABARITO da prefeitura, do lado da tela (F-043 T3).
 *
 * A planilha do orçamento pode sair de duas formas: na ordem do próprio orçamento, que é o
 * caminho de sempre, ou percorrendo um gabarito declarado — todas as linhas na ordem que a
 * prefeitura publica, inclusive as de quantidade zero. Quem escolhe é a orçamentista, no
 * despacho.
 *
 * Este módulo é puro: nenhuma chamada de rede, nenhum estado de React. O que ele guarda é o
 * que a tela precisa DIZER sobre a escolha — e a regra da jornada é que a tela nunca soma
 * (`apps/web/AGENTS.md`). Todo número aqui é contagem que o servidor já mandou, ou texto.
 */

/** Um gabarito como a rodada o oferece. Espelha `EstimateTemplateOption` da API. */
export type GabaritoOption = {
  estimate_template_id: string;
  name: string;
  template_version: string;
  origin: "platform" | "tenant";
  source_label: string;
  sheet_name: string;
  memory_sheet_name: string;
  row_count: number;
  priced_row_count: number;
  document_sha256: string;
};

export type GabaritoListResponse = {
  round_id: string;
  version: number;
  templates: GabaritoOption[];
};

/**
 * O rótulo da opção no seletor: nome, revisão e tamanho, nessa ordem.
 *
 * A revisão vem junto do nome de propósito — é a decisão 5 do pacote (carimbo de revisão). Um
 * seletor que mostrasse só o nome deixaria duas revisões do mesmo gabarito indistinguíveis
 * exatamente no ponto em que a diferença importa.
 */
export function rotuloDoGabarito(gabarito: GabaritoOption): string {
  const linhas = gabarito.row_count === 1 ? "1 linha" : `${gabarito.row_count} linhas`;
  return `${gabarito.name} · rev. ${gabarito.template_version} · ${linhas}`;
}

/**
 * O que vai no arquivo, como a tela o lê antes de gerar.
 *
 * `comQuantidade` é `null` enquanto o orçamento não foi confrontado com o gabarito: a
 * contagem de linhas que sairão preenchidas depende dos códigos do orçamento, e a tela **não
 * a calcula**. O que ela sabe sozinha é o tamanho do gabarito e quantas linhas dele já trazem
 * preço.
 */
export type ResumoDoArquivo = {
  gabarito: string;
  revisao: string;
  totalDeLinhas: number;
  comPreco: number;
  abas: readonly string[];
};

export function resumoDoArquivo(gabarito: GabaritoOption): ResumoDoArquivo {
  return {
    gabarito: gabarito.name,
    revisao: gabarito.template_version,
    totalDeLinhas: gabarito.row_count,
    comPreco: gabarito.priced_row_count,
    abas: [gabarito.sheet_name, gabarito.memory_sheet_name],
  };
}

/**
 * O gabarito escolhido, ou `null` para "publicar sem gabarito".
 *
 * `""` é a opção "sem gabarito" do seletor, e ela precisa existir: a rodada que não entrega
 * àquela prefeitura publica como sempre publicou, e esconder esse caminho faria a jornada de
 * hoje parecer quebrada.
 */
export function gabaritoEscolhido(
  gabaritos: readonly GabaritoOption[],
  id: string,
): GabaritoOption | null {
  if (id === "") {
    return null;
  }
  return gabaritos.find((item) => item.estimate_template_id === id) ?? null;
}

/**
 * O aviso de revisão, que existe porque **a prefeitura revisa o gabarito e um arquivo gerado
 * na revisão velha parece certo** — é a frase que abre o estado 02 do pacote aprovado.
 *
 * A tela **não decide** que uma revisão está velha: ela não sabe qual é a aceita hoje, e
 * inventar um critério (a mais nova da lista, a mais recente por data) seria a máquina
 * decidindo o que é ato de quem entrega à prefeitura. O que ela faz é sempre pedir a
 * confirmação, nomeando a revisão escolhida.
 */
export function avisoDeRevisao(gabarito: GabaritoOption | null): string | null {
  if (gabarito === null) {
    return null;
  }
  return (
    `O gabarito escolhido é a revisão ${gabarito.template_version}. ` +
    "Confirme com quem entrega à prefeitura que esta ainda é a revisão aceita."
  );
}

/** O corpo do despacho: `estimate_template_id` só viaja quando há gabarito escolhido. */
export function corpoDoDespacho(
  baseVersion: number,
  gabarito: GabaritoOption | null,
): { base_version: number; estimate_template_id?: string } {
  if (gabarito === null) {
    return { base_version: baseVersion };
  }
  return {
    base_version: baseVersion,
    estimate_template_id: gabarito.estimate_template_id,
  };
}

/** O carimbo que a rodada guarda: com qual gabarito a planilha da cabeça foi publicada. */
export type CarimboDoGabarito = {
  estimate_template_id: string;
  name: string;
  template_version: string;
  document_sha256: string;
};

/**
 * O que a tela diz sobre a planilha já publicada.
 *
 * Ausência de carimbo é AFIRMAÇÃO, não silêncio: a planilha saiu na ordem do próprio
 * orçamento. Dizê-lo por extenso é o que impede a leitura de supor um gabarito que não houve.
 */
export function procedenciaDaPlanilha(carimbo: CarimboDoGabarito | null | undefined): string {
  if (!carimbo) {
    return "Publicada sem gabarito: na ordem do próprio orçamento.";
  }
  return `Publicada no gabarito ${carimbo.name}, revisão ${carimbo.template_version}.`;
}
