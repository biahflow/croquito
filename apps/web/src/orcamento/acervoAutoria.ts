/**
 * A AUTORIA de um acervo de parcelas de canteiro (F-042 T6), do lado da tela — o estado 09
 * do pacote de design aprovado: guardar as parcelas desta rodada como acervo novo ou como
 * versão nova de um acervo que o tenant já tem.
 *
 * É o Human Gate 4 da feature exercido pela tela: **o primeiro acervo é autorado por gente**,
 * a partir de uma praça já feita. O sistema não o infere de planilha antiga nem de rodada
 * passada, e esta é a única razão de este módulo existir.
 *
 * Três coisas que ele carrega, e que não são preferência de interface:
 *
 * 1. **O índice do binding é a ordem do SERVIDOR.** `parameter_bindings` mapeia
 *    `"<índice da parcela standalone>.<nome do operando>"`, e esse índice é a posição da
 *    parcela na matriz **gravada** da revisão corrente, percorrida na ordem dos serviços e,
 *    dentro de cada serviço, na ordem gravada (`standalone_contributions`, lado Python).
 *    Por isso `parcelasAutoraveis` lê uma `CalcMatrix` e nunca o rascunho da tela: o
 *    rascunho pode ter parcela que ainda não foi gravada, e um índice deslocado ligaria o
 *    parâmetro ao operando errado — que é o acervo nascendo errado sem ninguém ver.
 *
 * 2. **Operando não citado vira CONSTANTE, e nada é adivinhado.** `1 x 2` pode ser "uma
 *    unidade por dois meses de obra" ou "duas placas de um metro": o campo do parâmetro
 *    nasce vazio, como o do passo 2 da aplicação (decisão 4 do pacote), e vazio significa
 *    "fica constante" — nunca "decida por mim".
 *
 * 3. **A recusa final é do servidor.** As guardas daqui só evitam a viagem de um pedido que
 *    nem sequer teria forma (nome curto, versão vazia, nada de canteiro para recortar). Nome
 *    repetido é `409 SITE_SETUP_KIT_ALREADY_PUBLISHED` do servidor, que é a autoridade sobre
 *    a regra — o pacote de design deliberadamente não desenhou esse estado, e a tela usa a
 *    superfície de erro comum da jornada em vez de inventar desenho novo.
 *
 * Módulo PURO, no molde de `acervo.ts` e `matrix.ts`: o estado do formulário, a derivação da
 * lista de parâmetros e o corpo do pedido ficam testáveis sem transporte e sem DOM. Nada
 * aqui multiplica, soma ou arredonda: valores de operando são transportados como TEXTO.
 */

import type { CalcMatrix, CalcOperand } from "./matrix";
import type { SiteSetupKit, SiteSetupKitOrigin } from "./acervo";

// --- Espelho do envelope da rota de autoria -----------------------------------

/**
 * O acervo recém-gravado, como a rota devolve no `201`.
 *
 * Não é o mesmo envelope da LISTAGEM (`SiteSetupKit`, em `acervo.ts`): a listagem traz os
 * `parameters` que a aplicação precisa e omite a administração; esta traz a administração
 * (`document_sha256`, `created_by`, `available`) e **não** traz os parâmetros, porque o
 * documento inteiro não sai por aqui. Quem quiser o acervo autorado como opção de aplicação
 * relê a lista — que é o que a tela faz.
 */
export type SiteSetupKitAuthoredResponse = {
  kit_id: string;
  name: string;
  kit_version: string;
  origin: SiteSetupKitOrigin;
  source_label: string;
  parcel_count: number;
  document_sha256: string;
  available: boolean;
  created_by: string;
  created_at: string;
  withdrawn_at: string | null;
};

// --- O que a matriz gravada oferece para virar acervo -------------------------

/**
 * Um operando de uma parcela de canteiro, como a autoria o oferece para declaração.
 *
 * `chave` é literalmente o que vai no corpo (`"0.MESES"`): montá-la aqui, junto da parcela
 * de onde ela saiu, é o que impede a tela de recompor o índice noutro lugar e errar.
 *
 * `tambemDeducao` existe porque um binding vale para o operando **e** para a dedução de
 * mesmo nome dentro da mesma contribuição — o modelo não distingue os dois espaços de nome.
 * Uma linha por nome, portanto, e a linha diz quando o nome também é dedução; duas linhas
 * com o mesmo nome fariam a segunda parecer uma declaração à parte que não existe.
 */
export type OperandoAutoravel = {
  chave: string;
  nome: string;
  /** Decimal em TEXTO, como a matriz o gravou. */
  valor: string;
  unidade: string | null;
  tambemDeducao: boolean;
};

/**
 * Uma parcela `STANDALONE` da matriz gravada, na ORDEM em que o servidor a enumera.
 *
 * `indice` é o número que os bindings citam, e ele conta a lista inteira — não reinicia a
 * cada serviço.
 */
export type ParcelaAutoravel = {
  indice: number;
  code: string;
  label: string;
  /**
   * A versão do acervo de onde a parcela nasceu, ou `null` quando ela foi autorada à mão.
   *
   * A matriz gravada leva `{kit_version, parcel_id}` e **não** leva a identidade do acervo,
   * então é a versão — e só ela — que a tela pode afirmar sobre a origem, exatamente como no
   * selo do painel de canteiro.
   */
  kitVersion: string | null;
  operandos: OperandoAutoravel[];
};

/**
 * As parcelas de canteiro da matriz GRAVADA, na ordem que o servidor percorre.
 *
 * Espelho de `standalone_contributions` (`services/api/src/croquito_api/site_setup_kits.py`):
 * serviços na ordem da matriz e, dentro de cada serviço, contribuições na ordem gravada,
 * ficando só as de base `standalone`. Contribuição com origem em elemento da prancha não
 * entra — o acervo é só do que não tem origem geométrica, por definição da feature.
 *
 * Matriz ausente (`null`, o regime legado) devolve lista vazia: rodada sem matriz não tem
 * canteiro gravado, e inventar parcela a partir do rascunho seria recortar o acervo de algo
 * que o servidor não vai enxergar.
 */
export function parcelasAutoraveis(matriz: CalcMatrix | null): ParcelaAutoravel[] {
  if (matriz === null) {
    return [];
  }
  const parcelas: ParcelaAutoravel[] = [];
  for (const servico of matriz.services) {
    for (const contribuicao of servico.contributions) {
      if (contribuicao.basis !== "standalone") {
        continue;
      }
      const indice = parcelas.length;
      parcelas.push({
        indice,
        code: servico.code,
        label: contribuicao.label,
        kitVersion: contribuicao.kit_origin?.kit_version ?? null,
        operandos: operandosAutoraveis(
          indice,
          contribuicao.operands,
          contribuicao.deductions,
        ),
      });
    }
  }
  return parcelas;
}

/** Um operando por NOME distinto: o binding é por nome, e nomeá-lo duas vezes mentiria. */
function operandosAutoraveis(
  indice: number,
  operandos: readonly CalcOperand[],
  deducoes: readonly CalcOperand[],
): OperandoAutoravel[] {
  const nomesDeDeducao = new Set(deducoes.map((deducao) => deducao.name));
  const linhas: OperandoAutoravel[] = [];
  for (const operando of [...operandos, ...deducoes]) {
    if (linhas.some((linha) => linha.nome === operando.name)) {
      continue;
    }
    linhas.push({
      chave: `${indice}.${operando.name}`,
      nome: operando.name,
      valor: operando.value,
      unidade: operando.unit ?? null,
      tambemDeducao: nomesDeDeducao.has(operando.name),
    });
  }
  return linhas;
}

// --- O estado do formulário ---------------------------------------------------

/**
 * O que está sendo salvo: acervo novo, ou versão nova de um acervo do próprio tenant.
 *
 * `""` é "ainda não escolhido", e é o estado inicial: escolher é ato, e um modo pré-marcado
 * poderia criar um acervo novo quando a intenção era versionar o que já existe.
 */
export type ModoDeAutoria = "" | "novo" | "versao";

export type FluxoDeAutoria = {
  modo: ModoDeAutoria;
  /** O acervo que ganha versão nova; `""` no modo `novo` e enquanto nada foi escolhido. */
  kitId: string;
  nome: string;
  versao: string;
  /**
   * Chave do binding → nome do parâmetro. Ausente ou vazio é o operando que fica
   * **constante**: é o default do domínio, e por isso é o default daqui.
   */
  bindings: Record<string, string>;
};

/** O formulário recém-aberto: nada escolhido, nada declarado, nenhum binding. */
export function autoriaInicial(): FluxoDeAutoria {
  return { modo: "", kitId: "", nome: "", versao: "", bindings: {} };
}

/**
 * Escolhe o modo. Trocar de modo limpa o que era do outro: o nome do modo `versao` é a
 * identidade do acervo escolhido, e arrastá-lo para o modo `novo` faria a pessoa publicar
 * sob um nome que ela não digitou.
 *
 * Os bindings SOBREVIVEM à troca: eles são declarações sobre os operandos desta rodada, e
 * não sobre o acervo de destino — apagá-los faria a pessoa redigitar tudo por ter mudado de
 * ideia sobre o nome.
 */
export function escolherModoDeAutoria(
  fluxo: FluxoDeAutoria,
  modo: ModoDeAutoria,
): FluxoDeAutoria {
  if (fluxo.modo === modo) {
    return fluxo;
  }
  return { ...fluxo, modo, kitId: "", nome: "" };
}

/**
 * Escolhe o acervo que ganha versão nova. O NOME vem dele e não é digitado: o servidor
 * chaveia por `(name, kit_version)` dentro do tenant, então um nome diferente não seria
 * versão nova — seria acervo novo com cara de versão.
 */
export function escolherAcervoBase(
  fluxo: FluxoDeAutoria,
  kit: SiteSetupKit,
): FluxoDeAutoria {
  return { ...fluxo, modo: "versao", kitId: kit.kit_id, nome: kit.name };
}

/** Declara o nome do acervo novo. Sem efeito no modo `versao`, onde o nome é do acervo. */
export function declararNomeDoAcervo(
  fluxo: FluxoDeAutoria,
  nome: string,
): FluxoDeAutoria {
  return { ...fluxo, nome };
}

export function declararVersaoDoAcervo(
  fluxo: FluxoDeAutoria,
  versao: string,
): FluxoDeAutoria {
  return { ...fluxo, versao };
}

/**
 * Declara que UM operando vira referência a um parâmetro de obra. Texto vazio devolve o
 * operando à condição de constante, e é por isso que a chave é removida em vez de guardada
 * vazia: `""` não é nome de parâmetro, e mandá-lo faria o servidor recusar por um campo que
 * a pessoa apagou.
 */
export function declararBinding(
  fluxo: FluxoDeAutoria,
  chave: string,
  parametro: string,
): FluxoDeAutoria {
  const bindings = { ...fluxo.bindings };
  if (parametro.trim().length === 0) {
    delete bindings[chave];
  } else {
    bindings[chave] = parametro;
  }
  return { ...fluxo, bindings };
}

/**
 * Os bindings como o corpo os leva: chave → nome do parâmetro, já sem espaço em volta.
 *
 * Chave sem valor é OMITIDA, no padrão de `parametrosDoCorpo`: a ausência do binding é o que
 * diz ao servidor que aquele operando fica constante.
 */
export function bindingsDoCorpo(
  fluxo: FluxoDeAutoria,
): Record<string, string> {
  const corpo: Record<string, string> = {};
  for (const [chave, parametro] of Object.entries(fluxo.bindings)) {
    const escrito = parametro.trim();
    if (escrito.length > 0) {
      corpo[chave] = escrito;
    }
  }
  return corpo;
}

// --- Os parâmetros que a versão vai citar -------------------------------------

/**
 * Um parâmetro que o acervo em autoria vai citar, como o painel da direita o lista.
 *
 * `unidade` é a do PRIMEIRO operando que cita o parâmetro, e `null` quando os operandos
 * discordam entre si — a mesma regra que a listagem de acervos já usa no servidor: escolher
 * uma faria o campo ser rotulado com uma unidade que metade das parcelas desmente.
 *
 * `novo` só existe no modo `versao`: é o parâmetro que a versão passa a citar e que o acervo
 * de base não citava. No modo `novo` não há base contra o que comparar, e marcar tudo como
 * novidade não diria nada.
 */
export type ParametroDaAutoria = {
  nome: string;
  unidade: string | null;
  citadoPor: number;
  novo: boolean;
};

/**
 * A lista de parâmetros derivada dos bindings declarados, na ordem de aparição.
 *
 * Ela é o resultado do que foi declarado, nunca uma sugestão: sem binding nenhum ela é
 * vazia, e o acervo nasce com todos os operandos constantes — o que é uma receita legítima
 * (uma parcela `2,00 × 1,40` de placa de obra não cita parâmetro nenhum).
 */
export function parametrosDaAutoria(
  fluxo: FluxoDeAutoria,
  parcelas: readonly ParcelaAutoravel[],
  kitBase: SiteSetupKit | null,
): ParametroDaAutoria[] {
  const declarados = bindingsDoCorpo(fluxo);
  const daBase = new Set((kitBase?.parameters ?? []).map((parametro) => parametro.name));
  const lista: ParametroDaAutoria[] = [];
  // A ordem é a das parcelas, não a das chaves do objeto: é a ordem em que a pessoa lê a
  // lista de operandos logo ao lado, e a de um objeto não é a de leitura de nada.
  for (const parcela of parcelas) {
    for (const operando of parcela.operandos) {
      const nome = declarados[operando.chave];
      if (nome === undefined) {
        continue;
      }
      const existente = lista.find((entrada) => entrada.nome === nome);
      if (existente === undefined) {
        lista.push({
          nome,
          unidade: operando.unidade,
          citadoPor: 1,
          novo: kitBase !== null && !daBase.has(nome),
        });
        continue;
      }
      existente.citadoPor += 1;
      if (existente.unidade !== operando.unidade) {
        existente.unidade = null;
      }
    }
  }
  return lista;
}

// --- O que entra no acervo, e o que ficou de fora -----------------------------

/** Quantas parcelas entram, e de onde elas vieram — o que a frase do estado 09 conta. */
export type ResumoDoQueEntra = {
  total: number;
  doAcervo: number;
  aMao: number;
};

/**
 * Conta as parcelas gravadas por origem.
 *
 * Não há exclusão individual aqui, e é de propósito: a remoção da prévia existe porque
 * aplicar materializa quantidade na praça; guardar recorta a RECEITA do que a rodada já tem,
 * e uma parcela que não devesse entrar no acervo não deveria estar na rodada.
 */
export function resumoDoQueEntra(
  parcelas: readonly ParcelaAutoravel[],
): ResumoDoQueEntra {
  const doAcervo = parcelas.filter((parcela) => parcela.kitVersion !== null).length;
  return { total: parcelas.length, doAcervo, aMao: parcelas.length - doAcervo };
}

/**
 * Os acervos que o tenant pode versionar: só os DELE.
 *
 * Acervo de plataforma é leitura para o tenant (ADR-0060): a rota da rodada grava sempre um
 * acervo `origin: "tenant"`, então "versão nova" de um acervo de plataforma criaria um
 * homônimo do tenant — uma bifurcação com aparência de continuação. Quem publica versão de
 * acervo de plataforma é o operador, por outra rota.
 */
export function acervosVersionaveis(
  kits: readonly SiteSetupKit[],
): SiteSetupKit[] {
  return kits.filter((kit) => kit.origin === "tenant");
}

// --- O portão do ato ----------------------------------------------------------

/**
 * Por que salvar está indisponível — ou `null` quando ele está disponível.
 *
 * Os códigos são estáveis e a frase é de `labels.ts`, como no resto da jornada. Eles cobrem
 * só o que impede o pedido de ter forma; **nome repetido não está aqui de propósito**: essa
 * é a recusa `SITE_SETUP_KIT_ALREADY_PUBLISHED` do servidor, que é a autoridade sobre a
 * regra, e reimplementá-la no cliente criaria duas.
 */
export type MotivoDeAutoriaIndisponivel =
  | "sem-parcelas"
  | "sem-modo"
  | "sem-acervo-base"
  | "sem-nome"
  | "sem-versao";

export function motivoDeAutoriaIndisponivel(
  fluxo: FluxoDeAutoria,
  parcelas: readonly ParcelaAutoravel[],
): MotivoDeAutoriaIndisponivel | null {
  if (parcelas.length === 0) {
    return "sem-parcelas";
  }
  if (fluxo.modo === "") {
    return "sem-modo";
  }
  if (fluxo.modo === "versao" && fluxo.kitId === "") {
    return "sem-acervo-base";
  }
  // 3 caracteres é o mínimo do contrato (`AuthorSiteSetupKitRequest.name`), não um gosto:
  // um nome de dois caracteres viajaria só para voltar como erro de validação de corpo.
  if (fluxo.nome.trim().length < 3) {
    return "sem-nome";
  }
  if (fluxo.versao.trim().length === 0) {
    return "sem-versao";
  }
  return null;
}

/** `true` quando o pedido tem forma; o servidor continua sendo o portão final. */
export function podeAutorar(
  fluxo: FluxoDeAutoria,
  parcelas: readonly ParcelaAutoravel[],
): boolean {
  return motivoDeAutoriaIndisponivel(fluxo, parcelas) === null;
}

/** O corpo do pedido de autoria, sem a `base_version` — quem a cita é o transporte. */
export function pedidoDaAutoria(fluxo: FluxoDeAutoria): {
  name: string;
  kitVersion: string;
  parameterBindings: Record<string, string>;
} {
  return {
    name: fluxo.nome.trim(),
    kitVersion: fluxo.versao.trim(),
    parameterBindings: bindingsDoCorpo(fluxo),
  };
}

// --- O acervo recém-salvo -----------------------------------------------------

/**
 * O que a tela guarda do acervo que acabou de nascer — nome, versão e quantas parcelas.
 *
 * É o mesmo desenho do carimbo da aplicação (`AplicacaoDeAcervo`): registro de LEITURA, que
 * não semeia campo nenhum e não substitui a lista de acervos relida do servidor.
 */
export type AcervoAutorado = {
  kitId: string;
  nome: string;
  versao: string;
  parcelas: number;
};

/** Espelha a resposta `201` da rota, sem recontar nada: `parcel_count` é do servidor. */
export function registrarAutoria(
  resposta: SiteSetupKitAuthoredResponse,
): AcervoAutorado {
  return {
    kitId: resposta.kit_id,
    nome: resposta.name,
    versao: resposta.kit_version,
    parcelas: resposta.parcel_count,
  };
}
