import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { User } from "oidc-client-ts";
import type { CodeSuggestionSet } from "@croquito/contracts";

import {
  associatePlate,
  createEstimate,
  createPlateExtraction,
  getCodes,
  getEstimate,
  getEstimateState,
  getPlate,
  getSuggestions,
  getTakeoff,
  getTakeoffOverlay,
  installCatalog,
  installReferenceCatalog,
  listEstimates,
  listReferenceCatalogs,
  postApproveEstimate,
  postBuildEstimate,
  postCodeClosure,
  postCodeDecision,
  postExportEstimate,
  postSuggestionsRecompute,
  postRegime,
  postTakeoffDecision,
  postTarget,
  removeCascadeSource,
  reorderCascade,
  searchCascade,
  uploadCatalog,
  uploadPlateFile,
  type ApprovalState,
  type CascadeEntry,
  type CascadeSearchResponse,
  type CatalogProvenance,
  type CodesResponse,
  type EstimateResponse,
  type EstimateState,
  type EstimateStateExtraction,
  type EstimateSummary,
  type OverlayResponse,
  type PriceOrigin,
  type PricingRegime,
  type ReferenceCatalogOption,
  type SuggestionsResponse,
  type TakeoffItem,
  type TakeoffResponse,
} from "./api";
import { signOut } from "../auth";
import { canMove, entryOfDigest, reorderedDigests } from "./cascata";
import { derivarEtapas, etapaStatusLabel, type Etapa, type EtapaId } from "./etapas";
import {
  describeError,
  exportBlockedViolations,
  isAbortError,
  isForbidden,
  isSelfApprovalForbidden,
  recusaDeMutacao,
  SELF_APPROVAL_FORBIDDEN_CODE,
  workbookAuditFindings,
} from "./errors";
import {
  formatDecimalText,
  formatMoneyText,
  formatPercentText,
  formatQuantityText,
  formatTimestamp,
  parseDecimalInput,
  shortDigest,
} from "./format";
import {
  ACAO_TABELA_PROPRIA,
  ACAO_VOLTAR_PARA_A_LISTA,
  assignmentStatusLabel,
  AVISO_ACERVO_FILTRADO,
  AVISO_ACERVO_INDISPONIVEL,
  AVISO_ACERVO_NAO_LIDO,
  AVISO_ACERVO_VAZIO,
  AVISO_ASSINAR_NAO_E_DESPACHAR,
  AVISO_BDI,
  AVISO_CANDIDATO_ADITIVO,
  AVISO_CARD_SEM_REGIME,
  AVISO_CASCATA,
  AVISO_CASCATA_SOB_CONTRATO,
  AVISO_CASCATA_TRAVADA,
  AVISO_CONSUMO_COM_BDI,
  AVISO_DESPACHO_FAIL_CLOSED,
  AVISO_IDENTIDADE_DA_SESSAO,
  AVISO_LOCALIZACAO_NAO_CONFIRMADA,
  AVISO_ORCAMENTO,
  AVISO_ORCAMENTO_SEM_RODADA,
  AVISO_ORCAMENTO_SOB_CONTRATO,
  AVISO_PLANILHA_ENDERECADA_PELO_DIGEST,
  AVISO_PROCEDENCIA,
  AVISO_QUANTIDADE_AMBIGUA,
  AVISO_REGIME_ABERTURA,
  AVISO_REGIME_MAO_UNICA,
  AVISO_SEM_PRECO,
  AVISO_TETO_ABERTURA,
  AVISO_TETO_EDICAO,
  AVISO_TETO_ESTOURADO,
  AVISO_TETO_LIMITE,
  cascadePositionLabel,
  CONSEQUENCIAS_DO_ESTOURO,
  CONVITE_TABELA_PROPRIA,
  DESCRICAO_CALCULO_SHORTLIST,
  DESCRICAO_MONTAGEM,
  DESCRICAO_REGIME,
  DESCRICAO_TABELA_PROPRIA,
  DICA_BDI,
  DICA_CANDIDATO_ADITIVO,
  DICA_QUANTIDADE,
  DICA_REGIME,
  DICA_TETO,
  DICA_TETO_DEMANDA,
  errorMessage,
  extractionFailureMessage,
  extractionStatusLabel,
  itemStatusLabel,
  MENSAGEM_APROVACAO_CADUCA,
  MENSAGEM_ORCAMENTO_APROVADO,
  MENSAGEM_ORCAMENTO_DESPACHADO,
  MENSAGEM_ORCAMENTO_MUDOU,
  OPCAO_TABELA_NAO_ESCOLHIDA,
  opcaoDoAcervo,
  origensAceitasNaCascata,
  PERGUNTA_REGIME,
  PERGUNTA_REGIME_ABERTURA,
  priceOriginSeloClass,
  priceSourceLabel,
  procedenciaDaFonte,
  REGIME_OPCAO_PRE_LICITACAO,
  REGIME_OPCAO_SOB_CONTRATO,
  ROTULO_TABELA_DO_ACERVO,
  SELO_REGIME,
  stageLabel,
  tituloDaAprovacao,
  tetoClasse,
  tetoEtiqueta,
  TITULO_ACERVO_VAZIO,
  TITULO_TABELA_PROPRIA,
  unitLabel,
  unitMismatchHint,
} from "./labels";
import { overlayFreshness } from "./overlay";
import { bdiPercentError, tetoAmountError, worksiteKeyError } from "./requests";
import { derivarTeto, type TetoDerivado } from "./teto";

/** Duração do aviso de sucesso; recusa nenhuma expira sozinha. */
const TOAST_MS = 5000;

/** Intervalo do poll do estado enquanto a leitura automática está na fila ou rodando. */
const EXTRACTION_POLL_MS = 3000;

/** Debounce da busca incremental na cascata. */
const BUSCA_DEBOUNCE_MS = 300;

type DecisionAction = "" | "confirm" | "reject";

/**
 * O código escolhido para um item, com a FONTE junto. No orçamento a fonte não é
 * decoração do relatório: ela viaja na decisão (`catalog_sha256`), porque confirmar um
 * código é escolher de qual catálogo, e com que data-base, aquele preço sai.
 */
type CodeChoice = {
  code: string;
  description: string;
  unit: string;
  unit_price: string;
  catalogSha256: string;
  priceOrigin: PriceOrigin;
  /** Vem do servidor quando a escolha saiu da shortlist; `null` quando saiu da busca. */
  unit_compatible: boolean | null;
};

const EMPTY_DECISION = {
  action: "" as DecisionAction,
  quantity: "",
  unit: "",
  note: "",
  itemNote: "",
};

const EMPTY_ESTIMATE_FORM = {
  worksiteKey: "",
  worksiteName: "",
  referenceLabel: "",
  address: "",
  // Teto vazio é o padrão e é "sem teto": ele não pede justificativa e não muda o botão.
  tetoAmount: "",
  tetoLabel: "",
  // Regime vazio é o padrão e é a PRÉ-LICITAÇÃO — que é a ausência do campo, não um valor
  // (ADR-0045). Diferente do painel de declarar depois, escolher o padrão aqui não desliga
  // o botão: abrir a rodada é o ato, e o regime é uma escolha dentro dele.
  regime: "" as "" | PricingRegime,
};

/**
 * Leitura OBSERVACIONAL: a falha dela não derruba o carregamento do orçamento.
 *
 * Vale só para a imagem da prancha e para o overlay das âncoras — os dois ilustram o que
 * já foi decidido e não decidem nada. A ausência de qualquer um deles é declarada na
 * tela, então engolir a recusa aqui não esconde estado nenhum. Decisão, artefato,
 * contagem e preço nunca passam por aqui.
 */
async function leituraObservacional<T>(
  leitura: () => Promise<T>,
): Promise<T | null> {
  try {
    return await leitura();
  } catch {
    return null;
  }
}

/**
 * Selo do regime da rodada (F-033, revisão 1 do Design Approval Package aprovada em
 * 2026-08-22). É o ÚNICO valor visual novo do pacote, e o que ele acrescenta é FORMA, não
 * cor: um selo de contorno, distinto dos selos preenchidos que indicam origem de preço,
 * porque regime da rodada e origem de uma linha são coisas diferentes e não podem ler
 * igual.
 *
 * Ele aparece em DOIS lugares por decisão do pacote: no cabeçalho, porque o regime vale
 * para a rodada inteira; e no painel da Cascata, porque é ali que a regra age e ali que a
 * recusa acontece — um selo só no topo faria a recusa parecer arbitrária a quem está na
 * aba. Daí as duas vestes: `escuro` sobre a topbar, `claro` sobre o painel.
 *
 * Rodada sem regime não tem selo, e não é este componente que decide isso: ausência não é
 * um valor, é a falta dele, e quem não a lê não renderiza nada.
 */
export function SeloRegime({
  variante = "escuro",
}: {
  variante?: "escuro" | "claro";
}) {
  return (
    <span
      className={
        variante === "claro" ? "selo-regime selo-regime-claro" : "selo-regime"
      }
    >
      {SELO_REGIME}
    </span>
  );
}

/**
 * O selo do regime no CARD da lista (F-033, revisão 2, decisão 4): o terceiro lugar do
 * MESMO selo, para a rodada dizer o regime antes de ser aberta.
 *
 * `pricing_regime` vem da listagem (`GET /v1/estimate-rounds`) e `null` é a pré-licitação:
 * card sem selo é rodada sem regime. É o molde do `LinhaTetoDaRodada` — a peça some
 * inteira quando não há o que dizer, em vez de virar "regime: —".
 *
 * O `<p>` é o que põe o selo na PRÓPRIA linha, como o mock da revisão 2 o desenha: a linha
 * de cima é a identidade da obra, e o regime não disputa espaço com ela. Ele usa a margem
 * que a folha da jornada já dá a todo parágrafo — nenhuma regra nova.
 */
export function SeloRegimeDaRodada({
  regime,
}: {
  regime: PricingRegime | null;
}) {
  if (regime === null) {
    return null;
  }
  return (
    <p>
      <SeloRegime variante="claro" />
    </p>
  );
}

/**
 * Declarar o regime: ato próprio, com seletor e botão, no molde do `PainelTetoDaVerba` da
 * F-027 — não caixa de marcar escondida no formulário de abertura (decisão 4 do pacote
 * aprovado).
 *
 * O seletor tem duas opções e mesmo assim não oferece a volta: "Pré-licitação" é onde a
 * rodada JÁ está, e escolhê-la não é um ato (o botão continua desligado). O regime é mão
 * única — o servidor recusa `pre_bid` com `ESTIMATE_REGIME_IRREVERSIBLE` —, e oferecer o
 * caminho de volta seria oferecer o que não existe.
 *
 * Por isso o painel só existe na rodada SEM regime: declarada a rodada, não sobra ato, e
 * um seletor desabilitado seria a mesma promessa vazia. Quem conta o regime dali em diante
 * é o selo, nos dois lugares em que ele aparece.
 */
export function PainelRegimeDaRodada({
  valor,
  versao,
  declarando,
  onValor,
  onDeclarar,
}: {
  valor: "" | PricingRegime;
  versao: number | null;
  declarando: boolean;
  onValor: (value: "" | PricingRegime) => void;
  onDeclarar: () => void;
}) {
  return (
    <section className="painel" aria-label="Regime da rodada">
      <div className="painel-cabecalho">
        <h2>{PERGUNTA_REGIME}</h2>
      </div>
      <form
        className="formulario"
        onSubmit={(event) => {
          event.preventDefault();
          onDeclarar();
        }}
      >
        <p className="dica">{DESCRICAO_REGIME}</p>
        <label className="campo">
          Regime
          <select
            value={valor}
            onChange={(event) =>
              onValor(event.target.value === "" ? "" : "contracted_demand")
            }
            disabled={declarando}
          >
            <option value="">{REGIME_OPCAO_PRE_LICITACAO}</option>
            <option value="contracted_demand">{REGIME_OPCAO_SOB_CONTRATO}</option>
          </select>
        </label>
        <p className="dica">{AVISO_REGIME_MAO_UNICA}</p>
        <div className="acoes-linha">
          <button
            type="submit"
            className="botao-secundario"
            disabled={declarando || valor === ""}
          >
            {declarando ? "Declarando…" : "Declarar"}
          </button>
        </div>
        <p className="dica">{DICA_REGIME}</p>
        {versao === null ? null : (
          <p className="digest">rodada versão {versao} · gravado sobre esta versão</p>
        )}
      </form>
    </section>
  );
}

/**
 * Selo da fonte de um preço: origem por extenso, data-base e a posição na cascata.
 *
 * É o elemento que a medição não tem, e a razão dele é a decisão do pacote aprovado: com
 * mais de uma tabela na rodada, "de onde veio o preço" deixa de ser redundante. A classe
 * de cor é redundância — origem, data-base e posição vão escritas dentro do selo.
 */
export function SeloFonte({
  origin,
  referenceMonth,
  position,
}: {
  origin: PriceOrigin | string;
  referenceMonth?: string | null;
  position?: number | null;
}) {
  return (
    <>
      <span className={`selo ${priceOriginSeloClass(origin)}`}>
        {priceSourceLabel(origin, referenceMonth)}
      </span>
      {position == null ? null : (
        <span className="selo selo-neutro">{cascadePositionLabel(position)}</span>
      )}
    </>
  );
}

/**
 * Procedência da fonte instalada: quem publicou o ARQUIVO (F-037, ADR-0047 decisão 7).
 *
 * Ele fica ao lado do selo de origem e não no lugar dele, porque as duas coisas são
 * diferentes: origem é de onde o PREÇO vem, procedência é de onde o arquivo veio. A marca
 * é a PALAVRA — "DO ACERVO" ou "TABELA PRÓPRIA" —, e a veste do selo é redundância.
 *
 * Fonte instalada antes desta superfície não tem o campo, e a ausência lê como tabela
 * própria: era o único caminho que existia, e nada é reescrito para trás.
 */
export function SeloProcedencia({
  provenance,
}: {
  provenance?: CatalogProvenance;
}) {
  return (
    <span className="selo selo-procedencia">{procedenciaDaFonte(provenance)}</span>
  );
}

/**
 * A escolha da fonte de preço da rodada: a LISTA do acervo como caminho principal, e a
 * tabela própria como alternativa nomeada (F-037, revisão 1 aprovada, telas 2, 3, 5 e 6).
 *
 * Três coisas que este painel NÃO faz, e que são a razão de ele ser assim:
 *
 * - **Não filtra.** A lista chega filtrada do servidor, pelos dois critérios que só ele
 *   conhece (circulação e regime da rodada). Guardar aqui uma cópia da regra do regime só
 *   produziria a divergência que aparece numa recusa — a mesma razão de
 *   `origensAceitasNaCascata` ler `allowed_cascade_origins` em vez de decidir.
 * - **Não esconde o upload.** Quem tem a EMOP licenciada ou o catálogo de um contrato
 *   continua enviando o arquivo, pelo mesmo caminho de sempre; ele só deixa de ser a
 *   primeira coisa que aparece.
 * - **Não trata acervo vazio como erro.** É estado: a plataforma ainda não publicou, e a
 *   tela oferece o caminho que funciona hoje.
 */
export function PainelEscolhaDeFonte({
  acervo,
  acervoAviso,
  escolhida,
  arquivo,
  tabelaPropria,
  regimeAceita,
  sobContrato,
  instalando,
  onEscolher,
  onArquivo,
  onTabelaPropria,
  onInstalarDoAcervo,
  onInstalarArquivo,
}: {
  /** `null` é "ainda não lido", que não é a mesma coisa que acervo vazio. */
  acervo: ReferenceCatalogOption[] | null;
  acervoAviso: string | null;
  escolhida: string;
  arquivo: File | null;
  tabelaPropria: boolean;
  regimeAceita: string | null;
  sobContrato: boolean;
  instalando: boolean;
  onEscolher: (referenceCatalogId: string) => void;
  onArquivo: (file: File | null) => void;
  onTabelaPropria: (value: boolean) => void;
  onInstalarDoAcervo: () => void;
  onInstalarArquivo: () => void;
}) {
  if (tabelaPropria) {
    return (
      <form
        className="formulario"
        onSubmit={(event) => {
          event.preventDefault();
          onInstalarArquivo();
        }}
      >
        <h3>{TITULO_TABELA_PROPRIA}</h3>
        <p className="dica">{DESCRICAO_TABELA_PROPRIA}</p>
        <label className="campo">
          Catálogo de preços (JSON)
          <span className="campo-dica">
            Entra no FIM da cascata. Uma origem só entra uma vez.
          </span>
          {/* Quais origens a instalação aceitaria, LIDAS do servidor. A tela não
              guarda a própria cópia da regra: se ela guardasse, a divergência só
              apareceria numa recusa. */}
          {regimeAceita === null ? null : (
            <span className="campo-dica">{regimeAceita}</span>
          )}
          <input
            type="file"
            accept=".json,application/json"
            onChange={(event) => onArquivo(event.target.files?.[0] ?? null)}
          />
        </label>
        <div className="acoes-linha">
          <button
            type="submit"
            className="botao-primario"
            disabled={instalando || arquivo === null}
          >
            {instalando ? "Instalando…" : "Instalar catálogo"}
          </button>
          <button
            type="button"
            className="botao-secundario"
            onClick={() => onTabelaPropria(false)}
            disabled={instalando}
          >
            {ACAO_VOLTAR_PARA_A_LISTA}
          </button>
        </div>
      </form>
    );
  }

  // Acervo vazio é estado, não erro — e a saída fica oferecida na mesma tela.
  if (acervo !== null && acervo.length === 0) {
    return (
      <div className="formulario">
        <h3>{TITULO_ACERVO_VAZIO}</h3>
        <p className="dica">{AVISO_ACERVO_VAZIO}</p>
        {sobContrato ? <p className="dica">{AVISO_ACERVO_FILTRADO}</p> : null}
        <div className="acoes-linha">
          <button
            type="button"
            className="botao-primario"
            onClick={() => onTabelaPropria(true)}
            disabled={instalando}
          >
            {TITULO_TABELA_PROPRIA}
          </button>
        </div>
      </div>
    );
  }

  return (
    <form
      className="formulario"
      onSubmit={(event) => {
        event.preventDefault();
        onInstalarDoAcervo();
      }}
    >
      <label className="campo">
        {ROTULO_TABELA_DO_ACERVO}
        <span className="campo-dica">
          Entra no FIM da cascata. Uma origem só entra uma vez.
        </span>
        {/* A regra do regime continua vindo do servidor, escrita ao lado do campo em que
            ela age — a lista já chega filtrada por ela. */}
        {regimeAceita === null ? null : (
          <span className="campo-dica">{regimeAceita}</span>
        )}
        <select
          value={escolhida}
          onChange={(event) => onEscolher(event.target.value)}
          disabled={instalando || acervo === null}
        >
          <option value="">{OPCAO_TABELA_NAO_ESCOLHIDA}</option>
          {(acervo ?? []).map((catalogo) => (
            <option
              key={catalogo.reference_catalog_id}
              value={catalogo.reference_catalog_id}
            >
              {opcaoDoAcervo(catalogo)}
            </option>
          ))}
        </select>
      </label>
      {acervo === null && acervoAviso === null ? (
        <p className="campo-dica">{AVISO_ACERVO_NAO_LIDO}</p>
      ) : null}
      {acervoAviso === null ? null : (
        <p className="campo-aviso" role="alert">
          {acervoAviso}
        </p>
      )}
      <div className="acoes-linha">
        <button
          type="submit"
          className="botao-primario"
          disabled={instalando || escolhida === ""}
        >
          {instalando ? "Instalando…" : "Instalar tabela"}
        </button>
      </div>
      {/* Por que a lista pode estar mais curta do que o acervo — depois do ato, como o
          pacote aprovado a compõe (tela 5). Silêncio aqui pareceria acervo pobre, não
          regime. */}
      {sobContrato ? <p className="dica">{AVISO_ACERVO_FILTRADO}</p> : null}
      <p className="dica">
        {CONVITE_TABELA_PROPRIA}{" "}
        <button
          type="button"
          className="botao-texto"
          onClick={() => onTabelaPropria(true)}
          disabled={instalando}
        >
          {ACAO_TABELA_PROPRIA}
        </button>
        .
      </p>
    </form>
  );
}

/**
 * Item confirmado que nenhuma fonte da cascata precifica. Ele é DECLARADO, nunca
 * precificado por fora: aparece aqui e ganha bloco próprio na planilha.
 */
export function SemPrecoNaCascata({ rotulos }: { rotulos: readonly string[] }) {
  if (rotulos.length === 0) {
    return null;
  }
  return (
    <div className="confirmados">
      <h3>Sem preço em nenhuma fonte</h3>
      <p className="dica">{AVISO_SEM_PRECO}</p>
      <ul className="confirmados-lista">
        {/* A chave leva o índice porque dois itens da legenda podem ter rótulo e
            quantidade idênticos — é o caso do mesmo serviço repetido em dois trechos. */}
        {rotulos.map((rotulo, index) => (
          <li key={`${index}:${rotulo}`}>
            {rotulo}{" "}
            <span className="selo selo-fonte-ausente">sem preço na cascata</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * Estado da leitura automática da legenda, os cinco estados do pacote aprovado: ociosa,
 * na fila, em curso, concluída e falhou. A frase da falha é escrita a partir do
 * `failure_code` estável da rodada — a API não manda mensagem pronta, e inventar uma sem
 * código seria pior do que dizer o que se sabe.
 */
export function EstadoExtracao({
  extraction,
  onRun,
  running,
}: {
  extraction: EstimateStateExtraction;
  onRun: () => void;
  running: boolean;
}) {
  return (
    <div className="extracao-status">
      <p className="dica">
        Leitura automática da legenda: {extractionStatusLabel(extraction.status)}.
      </p>
      {extraction.status === "queued" || extraction.status === "running" ? (
        <p className="dica" role="status">
          {extraction.status === "queued"
            ? "Pedido na fila; o processamento começa em instantes."
            : "Lendo a legenda da prancha… isso pode levar alguns instantes."}
        </p>
      ) : extraction.status === "done" ? (
        <p className="dica">
          Leitura concluída
          {extraction.lineage_present
            ? " — o lineage da chamada (modelo, tokens, custo) ficou registrado na rodada."
            : "."}
        </p>
      ) : extraction.status === "failed" ? (
        <>
          <p className="banner-erro" role="alert">
            {extractionFailureMessage(extraction.failure_code)}
            {extraction.failure_code === null ? null : (
              <>
                {" "}
                <span className="mono">({extraction.failure_code})</span>
              </>
            )}
          </p>
          <button
            type="button"
            className="botao-secundario"
            onClick={onRun}
            disabled={running}
          >
            Tentar leitura novamente
          </button>
        </>
      ) : (
        <>
          <p className="dica">
            Prancha enviada; a leitura automática ainda não foi disparada.
          </p>
          <p className="aviso-fixo aviso-inline">
            Disparar a leitura é uma chamada paga de IA, autorizada por contrato do seu
            tenant.
          </p>
          <button
            type="button"
            className="botao-secundario"
            onClick={onRun}
            disabled={running}
          >
            Disparar leitura automática
          </button>
        </>
      )}
    </div>
  );
}

/**
 * Overlay das âncoras, com a IDADE dele declarada em palavra (ADR-0030). Espelho do que a
 * medição já faz: o desenho é reconstruído por comando de fila e, entre a decisão e o
 * re-render, o que está aqui é do pacote anterior.
 */
export function OverlayDoTakeoff({
  overlay,
  onRefresh,
}: {
  overlay: OverlayResponse;
  onRefresh?: () => void;
}) {
  const estado = overlayFreshness(overlay);
  if (estado === null) {
    return null;
  }
  return (
    <details className={`overlay-bloco ${estado.stale ? "overlay-vencido" : ""}`}>
      <summary>Overlay das âncoras — {estado.label}</summary>
      <p className="dica">{estado.explanation}</p>
      {estado.stale ? (
        <p className="aviso-fixo aviso-inline" role="status">
          Desenho vencido: ele é do pacote{" "}
          <span className="digest">{shortDigest(overlay.overlay_packet_sha256)}</span> e o
          pacote atual é{" "}
          <span className="digest">{shortDigest(overlay.packet_sha256)}</span>.
        </p>
      ) : null}
      {overlay.present ? (
        <img
          className="overlay-imagem"
          src={overlay.image_url}
          alt={`Overlay das âncoras sobre a prancha — ${estado.label}`}
          draggable={false}
        />
      ) : null}
      {onRefresh === undefined ? null : (
        <button type="button" className="botao-secundario" onClick={onRefresh}>
          Atualizar desenho
        </button>
      )}
    </details>
  );
}

/**
 * Banner do `409 REVISION_CONFLICT`. Ele não é o alerta comum de erro: o orçamento andou,
 * o ato não foi gravado, e o caminho é recarregar — com o que já estava escrito no
 * formulário intacto.
 */
export function BannerOrcamentoMudou({ onReload }: { onReload?: () => void }) {
  return (
    <div className="banner-conflito" role="alert">
      <p>{MENSAGEM_ORCAMENTO_MUDOU}</p>
      {onReload === undefined ? null : (
        <button type="button" className="botao-primario" onClick={onReload}>
          Recarregar estado atual
        </button>
      )}
    </div>
  );
}

/**
 * `403` da rota, como TELA e **sem nomear papel**.
 *
 * Qual papel autoriza esta jornada é decisão humana ainda aberta (Design Approval
 * Package, "questões em aberto"): um texto que nomeasse um papel afirmaria uma decisão
 * que ninguém tomou. Quem autoriza continua sendo o backend — a jornada é montada pela
 * rota, e quem chega por link direto lê o motivo em vez de encontrar tela vazia.
 */
export function PainelSemAcesso({ detalhe }: { detalhe?: string | null }) {
  return (
    <section className="painel" aria-label="Sem acesso ao orçamento">
      <div className="painel-cabecalho">
        <h2>Sem acesso ao orçamento</h2>
      </div>
      <p role="alert">
        Sua conta não tem o papel que autoriza a jornada de orçamento neste tenant. Peça a
        quem administra o acesso da sua organização.
      </p>
      {detalhe ? <p className="digest">{detalhe}</p> : null}
    </section>
  );
}

/**
 * Auditoria da planilha reprovada, como TELA e não rodapé (ADR-0038).
 *
 * O arquivo é gravado, reaberto e reconferido antes de qualquer publicação: quando a
 * conferência falha, nada vai ao object store e nenhuma revisão nasce. Dizer isso por
 * extenso é o que separa "falhou" de "publicou algo que ninguém conferiu". Só os CÓDIGOS
 * dos achados aparecem — `expected`/`found` são preço e quantidade do cliente, e a rota
 * não os devolve.
 */
export function TelaAuditoriaReprovada({
  findings,
  onDismiss,
}: {
  findings: readonly string[];
  onDismiss?: () => void;
}) {
  return (
    <section className="painel" aria-label="Auditoria da planilha reprovada">
      <div className="painel-cabecalho">
        <h2>A auditoria reprovou a planilha — nada foi publicado</h2>
      </div>
      <p className="banner-erro" role="alert">
        A conferência da planilha reprovou. <strong>Nada foi publicado</strong>: o arquivo
        foi descartado, o object store não recebeu nada, a aprovação continua válida e o
        orçamento não mudou.
      </p>
      <ProgressoDoDespacho estado="reprovado" />
      {findings.length === 0 ? null : (
        <div className="confirmados">
          {/* Título próprio: sem ele os achados encostam na lista numerada dos passos e
              leem como um quinto passo do despacho. */}
          <h3>Divergências encontradas na reconferência</h3>
          <ul className="confirmados-lista">
            {findings.map((code) => (
              <li key={code} className="digest">
                {code}
              </li>
            ))}
          </ul>
        </div>
      )}
      <p className="dica">
        O portão é o mesmo da medição: o arquivo só é publicado depois de reaberto e
        reconferido, e falha do auditor não publica nada. Despachar de novo é seguro.
      </p>
      {onDismiss === undefined ? null : (
        <div className="acoes-linha">
          <button type="button" className="botao-secundario" onClick={onDismiss}>
            Voltar à aprovação e despacho
          </button>
        </div>
      )}
    </section>
  );
}

/**
 * O ato nominal de aprovação do orçamento (F-035, ADR-0046), em DOIS atos explícitos.
 *
 * A forma é a mesma da medição, deliberadamente (decisão 1 do pacote aprovado): duas
 * assinaturas no mesmo produto têm de ler como assinatura. O que muda é a consequência, que
 * aqui fala de DESPACHO. Três decisões do desenho vivem neste componente e não podem ser
 * "simplificadas":
 *
 * - **a consequência vem antes do botão, e por extenso** — três frases fixas: publica o
 *   nome de quem aprova, libera o despacho, vale só para este conteúdo exato;
 * - **a identidade é mostrada, nunca digitável** — não existe campo de nome do aprovador
 *   nesta tela, porque o servidor lê a identidade do token e recusa qualquer nome que venha
 *   do cliente; um campo aqui prometeria um efeito que ele não tem;
 * - **confirmar exige um segundo ato**, e o segundo passo REPETE a consequência em vez de
 *   perguntar "tem certeza?".
 *
 * Enquanto grava, os dois botões ficam indisponíveis: repetir o clique não criaria
 * aprovação nova (a mutação leva chave de idempotência), mas a tela também não pode sugerir
 * que criaria.
 */
export function AtoDeAprovacao({
  titulo,
  identidade,
  contentDigest,
  confirmando,
  gravando,
  onAprovar,
  onConfirmar,
  onCancelar,
}: {
  titulo: string;
  identidade: string;
  /** Digest do CONTEÚDO que será assinado (`current_digest`), não o do documento gravado. */
  contentDigest: string | null;
  confirmando: boolean;
  gravando: boolean;
  onAprovar: () => void;
  onConfirmar: () => void;
  onCancelar: () => void;
}) {
  const digestCurto = shortDigest(contentDigest);
  return (
    <div className="ato">
      <span className="ato-etiqueta">Ato nominal · orçamento</span>
      <h3>{titulo}</h3>
      {confirmando ? null : (
        <>
          <p>Antes de aprovar, o que aprovar faz:</p>
          <ul className="ato-consequencia">
            <li>
              <strong>Publica o seu nome.</strong> A aprovação fica registrada
              como sua, com data e hora, e é o que autoriza este orçamento a
              sair.
            </li>
            <li>
              <strong>Libera o despacho.</strong> Sem aprovação nominal válida,
              a rota de despacho recusa — não é convenção, é recusa do servidor.
              Nenhuma planilha é escrita antes da assinatura.
            </li>
            <li>
              <strong>
                Vale só para este orçamento, exatamente como ele está agora
              </strong>{" "}
              (
              <span className="mono" title={contentDigest ?? undefined}>
                sha256 {digestCurto}
              </span>
              ). Qualquer mudança depois disso derruba a aprovação e exige
              aprovar de novo.
            </li>
          </ul>
        </>
      )}
      <div className="ato-identidade">
        <b>Você aprova como</b>
        <span className="mono">{identidade}</span>
        <p className="campo-dica">
          Papel aprovador · identidade da sessão. {AVISO_IDENTIDADE_DA_SESSAO}
        </p>
      </div>
      {confirmando ? (
        <div className="ato-confirmacao">
          <p>
            <strong>Confirmar a aprovação nominal?</strong> O nome{" "}
            <span className="mono">{identidade}</span> fica registrado como quem
            aprovou este orçamento, no conteúdo{" "}
            <span className="mono" title={contentDigest ?? undefined}>
              sha256 {digestCurto}
            </span>
            , e o despacho da planilha fica liberado.
          </p>
          <div className="acoes-linha">
            <button
              type="button"
              className="botao-primario"
              onClick={onConfirmar}
              disabled={gravando}
            >
              {gravando ? "Aprovando…" : "Confirmar aprovação nominal"}
            </button>
            <button
              type="button"
              className="botao-secundario"
              onClick={onCancelar}
              disabled={gravando}
            >
              Cancelar
            </button>
          </div>
          {gravando ? (
            <p className="dica" role="status">
              Enquanto grava, os dois botões ficam indisponíveis: repetir o
              clique não cria aprovação nova, porque o ato vai com chave de
              idempotência.
            </p>
          ) : null}
        </div>
      ) : (
        <div className="acoes-linha">
          <button
            type="button"
            className="botao-primario"
            onClick={onAprovar}
            disabled={gravando}
          >
            Aprovar este orçamento
          </button>
        </div>
      )}
    </div>
  );
}

/**
 * Registro da aprovação: quem, quando e sobre qual conteúdo — e o estado CADUCO.
 *
 * `approved` e `stale` são lidos juntos, porque na aprovação caduca os dois valem ao mesmo
 * tempo. O registro velho não é apagado: ele fica visível, marcado como caduco, porque foi
 * um ato humano que aconteceu — e é essa diferença entre "caduca" e "nunca aprovada" que dá
 * à tela a única saída correta, aprovar de novo. O digest não é enfeite de auditoria: é o
 * vínculo que faz a aprovação caducar sozinha, e por isso os dois aparecem lado a lado.
 *
 * A marca do estado é a PALAVRA na etiqueta; o tracejado âmbar é redundância dela.
 */
export function RegistroDaAprovacao({ approval }: { approval: ApprovalState }) {
  if (approval.approved_by === null && !approval.approved) {
    return null;
  }
  const etiqueta = !approval.approved
    ? "Decisão registrada sem aprovação"
    : approval.stale
      ? "Aprovação caduca"
      : "Aprovada";
  return (
    <div className={`registro ${approval.stale ? "registro-caduca" : ""}`}>
      <span className="registro-etiqueta">{etiqueta}</span>
      <dl>
        <dt>Quem aprovou</dt>
        <dd>
          <span className="mono">
            {approval.approved_by ?? "não declarado"}
          </span>{" "}
          · papel aprovador
        </dd>
        <dt>Quando</dt>
        <dd>
          {approval.approved_at === null
            ? "não declarado"
            : formatTimestamp(approval.approved_at)}
        </dd>
        {approval.stale ? null : (
          <>
            <dt>Conteúdo aprovado</dt>
            <dd>
              <span
                className="mono"
                title={approval.approved_digest ?? undefined}
              >
                sha256 {shortDigest(approval.approved_digest)}
              </span>{" "}
              — igual ao do orçamento atual
            </dd>
          </>
        )}
      </dl>
      {approval.stale ? (
        <>
          <div className="digest-par">
            <div>
              <b>Conteúdo aprovado</b>
              <span
                className="mono"
                title={approval.approved_digest ?? undefined}
              >
                sha256 {shortDigest(approval.approved_digest)}
              </span>
              <p className="campo-dica">
                o que foi assinado no ato registrado acima
              </p>
            </div>
            <div>
              <b>Conteúdo atual</b>
              <span
                className="mono"
                title={approval.current_digest ?? undefined}
              >
                sha256 {shortDigest(approval.current_digest)}
              </span>
              <p className="campo-aviso">
                o orçamento como está agora, depois da remontagem
              </p>
            </div>
          </div>
          <p className="digest">APPROVAL_CONTENT_MISMATCH</p>
        </>
      ) : null}
    </div>
  );
}

/**
 * Selo do estado do despacho da rodada. A palavra é a marca; a veste é redundância dela.
 *
 * Ele diz "DESPACHADO" sem data, e a ausência é declarada: nenhuma rota do orçamento
 * devolve o instante do despacho — nem `GET .../estimate`, nem o estado da rodada —, e o
 * `updated_at` da rodada é o último ato QUALQUER, não este. Carimbar aquela data aqui
 * daria a um número que muda a cada mutação a aparência de registro de publicação.
 */
export function SeloDespacho({ despachado }: { despachado: boolean }) {
  return (
    <span className="selo-despacho">
      {despachado ? "DESPACHADO" : "NÃO DESPACHADO"}
    </span>
  );
}

/** Os quatro passos do despacho, na ordem em que o servidor os executa. */
const PASSOS_DO_DESPACHO = [
  "portão de domínio: a assinatura confere com o conteúdo atual",
  "planilha escrita em arquivo temporário",
  "reaberta e reconferida centavo a centavo contra o orçamento",
  "publicação",
];

/**
 * Estado de cada passo, pelo que a tela REALMENTE sabe.
 *
 * Os quatro passos correm dentro de uma chamada só: enquanto ela está em voo, o cliente não
 * observa em qual deles o servidor está, e fingir uma progressão seria inventar estado — a
 * rendição aprovada mostra o terceiro passo "em curso", e essa é a única coisa dela que a
 * tela não pode reproduzir sem mentir. O que se sabe com certeza é o DESFECHO: publicado
 * significa os quatro feitos; auditoria reprovada significa que o arquivo foi montado e
 * gravado, que a reconferência recusou e que a publicação não chegou a acontecer.
 */
function estadosDosPassos(
  estado: "em-voo" | "publicado" | "reprovado",
): string[] {
  if (estado === "publicado") {
    return ["concluído", "concluído", "concluído", "concluído"];
  }
  if (estado === "reprovado") {
    return ["concluído", "concluído", "reprovado", "não iniciado"];
  }
  return ["no servidor", "no servidor", "no servidor", "no servidor"];
}

/**
 * Progresso do despacho como LISTA ESCRITA de quatro passos, nunca como barra (decisão 6
 * do pacote aprovado).
 *
 * Três dos quatro passos acontecem antes de existir arquivo publicado; uma barra sugeriria
 * que o arquivo já está quase pronto quando ele ainda pode ser descartado no passo três.
 */
export function ProgressoDoDespacho({
  estado,
}: {
  estado: "em-voo" | "publicado" | "reprovado";
}) {
  const estados = estadosDosPassos(estado);
  return (
    <>
      <ol className="progresso">
        {PASSOS_DO_DESPACHO.map((passo, index) => (
          <li key={passo}>
            <span className="passo-estado">{estados[index]}</span> — {passo}
          </li>
        ))}
      </ol>
      {estado === "em-voo" ? (
        <p className="dica" role="status">
          Os quatro passos correm no servidor, numa chamada só, e a tela não
          observa em qual deles ele está. Nada é publicado antes do quarto
          passo: se a reconferência do passo 3 falhar, o arquivo do passo 2 é
          descartado.
        </p>
      ) : null}
    </>
  );
}

/**
 * `403` da rota de ASSINATURA, que não é a falta de acesso à jornada.
 *
 * Quem chega aqui lê o orçamento inteiro — a leitura aceita `orcamentista` ou `aprovador`
 * (ADR-0046, decisão 5) — e só não pode exercer o ato. Trocar isto pela tela de "sem acesso"
 * esconderia a jornada de alguém que a enxerga, e mandaria a pessoa pedir um acesso que ela
 * já tem.
 *
 * A tela não antecipa esta recusa desabilitando o botão: quem decide papel é o servidor, e
 * a jornada é montada pela ROTA, não pelo papel. O desenho aprovado mostra o botão já
 * desabilitado; isso exigiria a lista de papéis da sessão, que nenhuma rota do orçamento
 * devolve.
 */
export function PainelSemPapelDeAprovador({
  detalhe,
}: {
  detalhe?: string | null;
}) {
  return (
    <div
      className="violacoes"
      aria-label="Assinatura recusada por falta de papel"
    >
      <p className="banner-erro" role="alert">
        Aprovar exige o papel aprovador, e a sua sessão não o tem. Você vê o
        orçamento e o estado da assinatura; assinar é de quem tem o papel. Nada
        foi gravado — o orçamento segue como estava.
      </p>
      {detalhe ? <p className="digest">{detalhe}</p> : null}
    </div>
  );
}

/**
 * `403` da rota de DESPACHO, que também não é a falta de acesso à jornada.
 *
 * Desde a F-035 a leitura aceita `orcamentista` ou `aprovador` (ADR-0046, decisão 5), então
 * quem só assina abre a jornada inteira e chega até aqui — e o despacho exige
 * `orcamentista` (decisão 7). Mandar essa pessoa para a tela de "sem acesso" seria dizer
 * que ela não pode ler o que ela acabou de ler, e apagaria a assinatura da vista.
 */
export function PainelSemPapelDeOrcamentista({
  detalhe,
}: {
  detalhe?: string | null;
}) {
  return (
    <div
      className="violacoes"
      aria-label="Despacho recusado por falta de papel"
    >
      <p className="banner-erro" role="alert">
        Despachar exige o papel orcamentista, e a sua sessão não o tem. A
        aprovação registrada continua valendo: o que falta é quem opere o envio.
        Nada foi publicado — o orçamento segue como estava.
      </p>
      {detalhe ? <p className="digest">{detalhe}</p> : null}
    </div>
  );
}

/**
 * Auto-aprovação recusada (tela 6 do pacote aprovado): quem montou não assina.
 *
 * A frase EXPLICA a regra em vez de só negar, porque a primeira reação de quem é recusado
 * é procurar o papel que falta — e aqui não falta papel nenhum: a comparação é de
 * identidade contra quem montou, e acumular `orcamentista` e `aprovador` não contorna.
 *
 * O desenho aprovado nomeia quem montou ("montado por marina.gestora"). Nenhuma rota do
 * orçamento devolve esse nome — nem a recusa, de propósito, para não transformar um `403`
 * num diretório de usuários do tenant —, então a tela diz a regra sem o nome em vez de
 * inventá-lo.
 */
export function PainelAutoAprovacaoRecusada({
  detalhe,
}: {
  detalhe?: string | null;
}) {
  return (
    <div
      className="violacoes"
      aria-label="Auto-aprovação recusada pelo servidor"
    >
      <p className="banner-erro" role="alert">
        {errorMessage(SELF_APPROVAL_FORBIDDEN_CODE)}
      </p>
      {detalhe ? <p className="digest">{detalhe}</p> : null}
    </div>
  );
}


/**
 * Consumo do teto na "Prévia do orçamento", colado ao Total geral (ADR-0040, F-027).
 *
 * Ele mora aqui porque é uma LEITURA daquele número: separar os dois na tela abriria
 * espaço para se contradizerem. Três estados, dois deles o mesmo estado de domínio —
 * "dentro do teto" e "no limite exato" compartilham a veste, e o que os distingue é a
 * palavra, que no limite exato diz por extenso que aquilo não é estouro.
 *
 * `null` é o caso da rodada sem teto (ADR-0040, decisão 6): nenhum bloco, nenhuma etiqueta
 * "sem teto", nenhum espaço reservado. Ausência de teto não é um estado a comunicar.
 *
 * Nenhum número daqui é calculado pela tela, com uma exceção declarada: o percentual, que
 * é razão e não dinheiro, e que o payload não traz. Teto, consumo, restante e excedente
 * são o texto do servidor.
 */
export function BlocoConsumoDoTeto({ teto }: { teto: TetoDerivado | null }) {
  if (teto === null) {
    return null;
  }
  const resultado = teto.estado === "estourado" ? teto.excedente : teto.restante;
  return (
    <div className={`teto-consumo ${tetoClasse(teto.estado)}`}>
      <span className="teto-etiqueta">{tetoEtiqueta(teto.estado)}</span>
      <ul className="teto-linhas">
        <li>
          <span className="teto-rotulo">
            Teto da verba
            {teto.rotulo === null ? null : (
              <span className="teto-origem">{teto.rotulo}</span>
            )}
          </span>
          <span className="teto-valor">{formatMoneyText(teto.teto)}</span>
        </li>
        <li>
          <span className="teto-rotulo">
            Consumo — total com BDI
            {teto.percentualConsumido === null ? null : (
              <span className="teto-origem">
                {formatPercentText(teto.percentualConsumido)} do teto
              </span>
            )}
          </span>
          <span className="teto-valor">{formatMoneyText(teto.consumo)}</span>
        </li>
        {resultado === null ? null : (
          <li className="teto-resultado">
            <span className="teto-rotulo">
              {teto.estado === "estourado" ? "Acima do teto" : "Restante"}
            </span>
            <span className="teto-valor">{formatMoneyText(resultado)}</span>
          </li>
        )}
      </ul>
      {teto.estado === "estourado" ? (
        <ul className="teto-consequencia">
          {CONSEQUENCIAS_DO_ESTOURO.map((consequencia) => (
            <li key={consequencia.destaque}>
              <strong>{consequencia.destaque}</strong> {consequencia.texto}
            </li>
          ))}
        </ul>
      ) : (
        <p className="dica">
          {teto.estado === "limite" ? AVISO_TETO_LIMITE : AVISO_CONSUMO_COM_BDI}
        </p>
      )}
    </div>
  );
}

/**
 * Aviso permanente do estouro, de largura inteira e **sem nenhum botão** — a decisão mais
 * declarada do pacote aprovado.
 *
 * Toda saída do estouro é decisão humana FORA desta tela: cortar escopo, remanejar
 * quantitativo, pedir verba suplementar. Um "ajustar para caber" seria o corte automático
 * que o contrato proíbe; um "rever o teto" colado ao aviso ensinaria a saída errada —
 * subir o número até o aviso sumir. Editar o teto continua sendo ato do painel de teto, na
 * etapa de montagem, sem estar oferecido como remédio.
 *
 * Ele é CONDIÇÃO da rodada, não episódio: por isso é renderizado uma vez só, fora da etapa
 * visível, e acompanha todas as etapas enquanto o consumo passar o teto — inclusive a
 * Planilha, ao lado da exportação que continua funcionando (ADR-0040, decisão 4).
 */
export function FaixaTetoEstourado({ teto }: { teto: TetoDerivado | null }) {
  if (teto === null || teto.estado !== "estourado" || teto.excedente === null) {
    return null;
  }
  return (
    <div className="teto-faixa" role="status">
      <span className="teto-faixa-etiqueta">{tetoEtiqueta(teto.estado)}</span>
      <div>
        <p>
          O orçamento montado passa a verba declarada em{" "}
          <span className="teto-faixa-numero">
            {formatMoneyText(teto.excedente)}
          </span>
          {teto.percentualAcima === null
            ? ", acima do teto de "
            : ` — ${formatPercentText(teto.percentualAcima)} acima do teto de `}
          {formatMoneyText(teto.teto)}
          {teto.rotulo === null ? null : ` (${teto.rotulo})`}.
        </p>
        <p>
          <strong>{AVISO_TETO_ESTOURADO.destaque}</strong>{" "}
          {AVISO_TETO_ESTOURADO.texto}
        </p>
      </div>
    </div>
  );
}

/**
 * Painel "Teto da verba" na etapa de montagem, ao lado do BDI: os dois são o mesmo tipo de
 * coisa — parâmetro da rodada sob o qual o orçamento é montado —, e por isso ficam no
 * mesmo lugar. Uma etapa própria "Teto" foi recusada no pacote aprovado: não há nada a
 * *fazer* com o teto que justifique um passo da cadeia.
 *
 * Ele aparece em toda rodada aberta, **inclusive sem teto declarado**, e essa é a única
 * exceção ao "rodada sem teto é exatamente como hoje": sem o painel, uma rodada aberta sem
 * teto nunca poderia ganhar um. Ele não avisa, não bloqueia e não marca nada.
 *
 * Não há botão de remover: apagar um teto já declarado é questão que o ADR-0040 não
 * decidiu, e inventá-la aqui seria decidi-la. Gravar é botão SECUNDÁRIO — o ato primário
 * desta etapa é montar o orçamento.
 */
export function PainelTetoDaVerba({
  valor,
  rotulo,
  versao,
  gravando,
  onValor,
  onRotulo,
  onGravar,
}: {
  valor: string;
  rotulo: string;
  versao: number | null;
  gravando: boolean;
  onValor: (value: string) => void;
  onRotulo: (value: string) => void;
  onGravar: () => void;
}) {
  const erro = tetoAmountError(valor);
  return (
    <section className="painel" aria-label="Teto da verba">
      <div className="painel-cabecalho">
        <h2>Teto da verba</h2>
      </div>
      <form
        className="formulario"
        onSubmit={(event) => {
          event.preventDefault();
          onGravar();
        }}
      >
        <label className="campo">
          Teto da verba (opcional)
          <span className="campo-dica">{DICA_TETO}</span>
          <input
            type="text"
            inputMode="decimal"
            value={valor}
            onChange={(event) => onValor(event.target.value)}
            aria-invalid={erro !== null}
            disabled={gravando}
          />
        </label>
        {erro === null ? null : (
          <p className="campo-erro" role="alert">
            {erro}
          </p>
        )}
        <label className="campo">
          Demanda de origem (opcional)
          <span className="campo-dica">{DICA_TETO_DEMANDA}</span>
          <input
            type="text"
            value={rotulo}
            onChange={(event) => onRotulo(event.target.value)}
            disabled={gravando}
          />
        </label>
        <p className="dica">{AVISO_TETO_EDICAO}</p>
        <div className="acoes-linha">
          <button
            type="submit"
            className="botao-secundario"
            disabled={gravando || erro !== null || valor.trim().length === 0}
          >
            {gravando ? "Gravando…" : "Gravar teto"}
          </button>
        </div>
        {versao === null ? null : (
          <p className="digest">rodada versão {versao} · gravado sobre esta versão</p>
        )}
      </form>
    </section>
  );
}

/**
 * A linha do teto na lista de orçamentos do tenant — presente SÓ na rodada que tem teto.
 * A rodada sem teto não ganha "sem teto", "teto: —" nem espaço reservado: ausência de teto
 * não é um estado a comunicar (ADR-0040, decisão 6).
 */
export function LinhaTetoDaRodada({
  amount,
  label,
}: {
  amount: string | null;
  label: string | null;
}) {
  // Ausência de teto chega como `null` da API, e texto vazio nunca é teto: nos dois casos
  // a linha simplesmente não existe.
  if (!amount) {
    return null;
  }
  return (
    <p className="dica">
      Teto {formatMoneyText(amount)}
      {label ? ` · ${label}` : null}
    </p>
  );
}

/**
 * Veste do selo da decisão de código. Ela é REDUNDÂNCIA do texto que vai dentro do selo —
 * "código confirmado", "sem código na cascata", "candidato a aditivo" —, e nenhuma leitura
 * depende de distinguir a cor.
 *
 * A pastilha âmbar é a mesma do `.blocked` da casca, que o pacote de design cita como
 * procedência do sinal de candidato a aditivo. Fora do regime ela não aparece: rejeição de
 * pré-licitação continua sendo rejeição, e nada mais.
 */
function seloDaDecisao(status: string, sobContrato: boolean): string {
  if (status === "rejected") {
    return sobContrato ? "selo-aditivo" : "selo-neutro";
  }
  return status === "confirmed" ? "selo-ok" : "selo-neutro";
}

/** Um item confirmado sem decisão de código ainda não tem preço: rótulo para a lista. */
function rotuloDoItem(label: string, quantity: string | null, unit: string): string {
  return `${label} · ${formatQuantityText(quantity, unitLabel(unit))}`;
}

/** Item cuja âncora não passou pelo registro fino; a tela diz isso por extenso. */
function itemAnchor(item: TakeoffItem): "registered" | "raw" {
  return item.anchor === "registered" ? "registered" : "raw";
}

/**
 * Jornada do orçamento-base sobre a API `/v1` autenticada (F-020, ADR-0027/ADR-0038).
 *
 * A sessão é da casca, não desta jornada: quem lê o OIDC, consome o authorization code
 * (que é de uso único) e renova o token é `App.tsx`. Aqui ela chega pronta — e sem ela
 * nada é chamado, porque toda rota do orçamento é autenticada e por tenant.
 *
 * `roundId` é o orçamento aberto, declarado na URL pela casca (`?orcamento=`); `null` é
 * "jornada do orçamento, nenhum orçamento aberto", que é a tela de escolher ou abrir.
 *
 * O que esta tela NÃO faz, e a fronteira é a mesma da medição: ela não soma, não
 * multiplica e não arredonda dinheiro nem quantidade — exibe as strings decimais que o
 * servidor mandou. O único decimal que ela escreve é o que a orçamentista digitou, e ele
 * viaja como texto.
 */
export function OrcamentoApp({
  session,
  roundId = null,
  onOpenEstimate,
}: {
  session: User | null;
  roundId?: string | null;
  onOpenEstimate?: (roundId: string | null) => void;
}) {
  // O token é lido no instante da chamada (o `automaticSilentRenew` da casca troca o
  // objeto da sessão sem avisar quem já capturou o valor), então os handlers consultam
  // esta ref em vez de fechar sobre a sessão do render em que nasceram.
  const sessionRef = useRef<User | null>(session);
  sessionRef.current = session;
  const tokenDaSessao = useCallback(
    (): string | null => sessionRef.current?.access_token ?? null,
    [],
  );
  const autenticado = session !== null;

  // Orçamento aberto. A URL é a fonte declarada (`?orcamento=`), mas quem navega dentro
  // da jornada é esta tela: o estado local segue a prop e avisa a casca ao mudar.
  const [orcamento, setOrcamento] = useState<string | null>(roundId);
  useEffect(() => setOrcamento(roundId), [roundId]);

  // Estado servido pela rodada; nada aqui é derivado de cálculo local.
  const [state, setState] = useState<EstimateState | null>(null);
  // Versão da rodada: token de concorrência de TODA a cadeia. Ele vem da última resposta
  // lida, e é ele que a próxima mutação cita em `base_version`.
  const [version, setVersion] = useState<number | null>(null);
  const [takeoff, setTakeoff] = useState<TakeoffResponse | null>(null);
  const [overlay, setOverlay] = useState<OverlayResponse | null>(null);
  const [plateSrc, setPlateSrc] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<SuggestionsResponse | null>(null);
  const [codes, setCodes] = useState<CodesResponse | null>(null);
  const [estimate, setEstimate] = useState<EstimateResponse | null>(null);

  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [alertMessage, setAlertMessage] = useState<string | null>(null);
  const [revisionConflict, setRevisionConflict] = useState(false);
  const [semAcesso, setSemAcesso] = useState<string | null>(null);
  const [auditoriaReprovada, setAuditoriaReprovada] = useState<string[] | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [openStep, setOpenStep] = useState<EtapaId | null>(null);

  // Escolha e abertura de orçamento.
  const [lista, setLista] = useState<EstimateSummary[] | null>(null);
  const [listaCursor, setListaCursor] = useState<string | null>(null);
  const [form, setForm] = useState(EMPTY_ESTIMATE_FORM);

  // Cascata e prancha.
  const [catalogFile, setCatalogFile] = useState<File | null>(null);
  const [plateFile, setPlateFile] = useState<File | null>(null);

  // Acervo de tabelas da plataforma (F-037). `null` é "ainda não lido", que NÃO é a mesma
  // coisa que acervo vazio: um é ausência de leitura, o outro é a plataforma não ter
  // publicado nada que sirva a esta rodada, e a tela diz coisas diferentes nos dois casos.
  const [acervo, setAcervo] = useState<ReferenceCatalogOption[] | null>(null);
  // Falha de leitura do acervo vira aviso AO LADO do campo, e não o alerta global: a lista
  // é secundária ao ato, e o caminho da tabela própria continua aberto sem ela.
  const [acervoAviso, setAcervoAviso] = useState<string | null>(null);
  const [tabelaEscolhida, setTabelaEscolhida] = useState("");
  // A alternativa nomeada é um MODO da mesma seção, não um painel a mais: os dois lado a
  // lado empatariam os dois caminhos, e a lista é o principal (decisão 1 do pacote).
  const [tabelaPropria, setTabelaPropria] = useState(false);

  // Revisão do takeoff.
  const [selectedItemId, setSelectedItemId] = useState("");
  const [decision, setDecision] = useState(EMPTY_DECISION);

  // Códigos.
  const [selectedPendingId, setSelectedPendingId] = useState("");
  const [codeChoice, setCodeChoice] = useState<CodeChoice | null>(null);
  const [codeNote, setCodeNote] = useState("");
  const [query, setQuery] = useState("");
  const [searchResult, setSearchResult] = useState<CascadeSearchResponse | null>(null);
  // A busca incremental nunca toca `submitting` (cada tecla congelaria a tela inteira) e
  // nunca escreve no alerta global — erro transitório vira aviso ao lado do campo.
  const [buscando, setBuscando] = useState(false);
  const [buscaAviso, setBuscaAviso] = useState<string | null>(null);
  const buscaAbortRef = useRef<AbortController | null>(null);
  const buscaTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // BDI e montagem.
  const [bdiInput, setBdiInput] = useState("");

  // Aprovação e despacho (F-035, ADR-0046). `confirmandoAprovacao` é o SEGUNDO ato
  // explícito do desenho aprovado, não preferência de interface: o primeiro clique abre a
  // consequência, o segundo assina.
  const [confirmandoAprovacao, setConfirmandoAprovacao] = useState(false);
  const [despachando, setDespachando] = useState(false);
  // Violações abertas do portão de domínio do despacho. O servidor recusa por TODAS de uma
  // vez, e mostrar só a primeira faria a orçamentista assinar de novo para tropeçar na
  // seguinte.
  const [violacoesDoDespacho, setViolacoesDoDespacho] = useState<
    string[] | null
  >(null);
  // As duas recusas de `403` da assinatura, em estados SEPARADOS porque não significam a
  // mesma coisa: uma é falta do papel `aprovador`, a outra é a segregação entre quem monta
  // e quem assina — quem cai na segunda tem o papel e continua sem poder assinar este
  // orçamento. Nenhuma das duas é a tela de "sem acesso": as duas leem a jornada inteira.
  const [semPapelDeAprovador, setSemPapelDeAprovador] = useState<string | null>(
    null,
  );
  const [autoAprovacaoRecusada, setAutoAprovacaoRecusada] = useState<
    string | null
  >(null);
  // `403` do DESPACHO: falta do papel `orcamentista`. Também não é a tela de "sem acesso" —
  // quem só tem `aprovador` lê a jornada inteira e assina; o que ele não faz é publicar.
  const [semPapelDeOrcamentista, setSemPapelDeOrcamentista] = useState<
    string | null
  >(null);

  // Teto da verba da rodada (ADR-0040): parâmetro da rodada, editado na mesma etapa.
  const [tetoInput, setTetoInput] = useState("");
  const [tetoLabelInput, setTetoLabelInput] = useState("");

  // Regime da rodada (ADR-0045). `""` é onde toda rodada começa — a pré-licitação, que é
  // a ausência do regime e não um valor gravado. O seletor não nasce pré-marcado no ato.
  const [regimeInput, setRegimeInput] = useState<"" | PricingRegime>("");

  useEffect(() => {
    if (toast === null) {
      return;
    }
    const timer = setTimeout(() => setToast(null), TOAST_MS);
    return () => clearTimeout(timer);
  }, [toast]);

  /** Aplica a versão que a resposta declarou; ela é a base da próxima mutação. */
  const aplicarVersao = useCallback((proxima: number) => {
    setVersion(proxima);
    setState((current) =>
      current === null ? current : { ...current, version: proxima },
    );
  }, []);

  /** Recusa de LEITURA: `403` vira tela própria, o resto vira o alerta comum. */
  const registrarFalhaDeLeitura = useCallback((error: unknown) => {
    if (isForbidden(error)) {
      setSemAcesso(error instanceof Error ? error.message : null);
      return;
    }
    setAlertMessage(describeError(error));
  }, []);

  const carregarLista = useCallback(async () => {
    const token = tokenDaSessao();
    if (token === null) {
      return;
    }
    setLoading(true);
    try {
      const page = await listEstimates(token);
      setLista(page.items);
      setListaCursor(page.next_cursor);
      setAlertMessage(null);
      setSemAcesso(null);
    } catch (error) {
      registrarFalhaDeLeitura(error);
    } finally {
      setLoading(false);
    }
  }, [registrarFalhaDeLeitura, tokenDaSessao]);

  const carregarMais = async () => {
    const token = tokenDaSessao();
    if (token === null || listaCursor === null) {
      return;
    }
    setLoading(true);
    try {
      const page = await listEstimates(token, { cursor: listaCursor });
      setLista((current) => [...(current ?? []), ...page.items]);
      setListaCursor(page.next_cursor);
    } catch (error) {
      registrarFalhaDeLeitura(error);
    } finally {
      setLoading(false);
    }
  };

  const carregarEstado = useCallback(async () => {
    const token = tokenDaSessao();
    if (token === null || orcamento === null) {
      return;
    }
    setLoading(true);
    try {
      const next = await getEstimateState(token, orcamento);
      setState(next);
      setVersion(next.version);
      setRevisionConflict(false);
      setAlertMessage(null);
      setSemAcesso(null);
      // O teto gravado preenche os campos para conferência e edição, e SÓ enquanto
      // ninguém escreveu neles — mesma forma funcional do BDI mais abaixo, que é o que
      // mantém `carregarEstado` fora da dependência do texto digitado. É também o que
      // preserva o valor escrito quando o `409` chega: a leitura seguinte não o
      // sobrescreve.
      const tetoDaRodada = next.target;
      if (tetoDaRodada !== undefined) {
        setTetoInput((atual) =>
          atual.trim().length === 0 ? tetoDaRodada.amount : atual,
        );
        setTetoLabelInput((atual) =>
          atual.trim().length === 0 ? (tetoDaRodada.label ?? "") : atual,
        );
      }
      if (next.takeoff.present) {
        setTakeoff(await getTakeoff(token, orcamento));
        setCodes(await getCodes(token, orcamento));
        setOverlay(
          await leituraObservacional(() => getTakeoffOverlay(token, orcamento)),
        );
      } else {
        setTakeoff(null);
        setCodes(null);
        setOverlay(null);
      }
      // A URL da imagem é assinada e de curta duração: ela é relida junto com o estado e
      // vai direto no `src`, sem header nenhum e sem nunca aparecer em log.
      setPlateSrc(
        next.plate.present
          ? ((await leituraObservacional(() => getPlate(token, orcamento)))
              ?.image_url ?? null)
          : null,
      );
      // A shortlist só é buscada quando já existe na rodada: a primeira leitura
      // **calcula e grava** o artefato, e isso é ato da orçamentista, não efeito
      // colateral de abrir a tela.
      setSuggestions(
        next.codes.suggestions_present
          ? await getSuggestions(token, orcamento)
          : null,
      );
      const montado = next.estimate.present
        ? await leituraObservacional(() => getEstimate(token, orcamento))
        : null;
      setEstimate(montado);
      if (montado !== null) {
        // O BDI gravado preenche o campo para conferência, e SÓ enquanto ninguém escreveu
        // nada. A forma funcional é o que mantém `carregarEstado` fora da dependência do
        // texto digitado: com `bdiInput` na lista, cada tecla no campo reconstruiria a
        // função e, com ela, o intervalo do poll da extração que depende dela. O valor
        // continua sendo texto e nenhum dígito é acrescentado.
        setBdiInput((atual) =>
          atual.trim().length === 0 ? montado.bdi_percent : atual,
        );
      }
    } catch (error) {
      registrarFalhaDeLeitura(error);
    } finally {
      setLoading(false);
    }
  }, [orcamento, registrarFalhaDeLeitura, tokenDaSessao]);

  useEffect(() => {
    if (!autenticado) {
      return;
    }
    if (orcamento === null) {
      void carregarLista();
    } else {
      void carregarEstado();
    }
  }, [autenticado, carregarEstado, carregarLista, orcamento]);

  /**
   * O acervo desta rodada: leitura pura, sem `Idempotency-Key` e sem gravar nada.
   *
   * Ela não entra em `carregarEstado` de propósito. O estado é relido a cada mutação e a
   * cada volta do poll da extração; pendurar o acervo ali faria a lista ser buscada de três
   * em três segundos para responder sempre a mesma coisa. Quem a invalida é o REGIME, que é
   * o filtro do servidor — e é ele que a relê, no efeito abaixo.
   */
  const carregarAcervo = useCallback(async () => {
    const token = tokenDaSessao();
    if (token === null || orcamento === null) {
      return;
    }
    try {
      const disponivel = await listReferenceCatalogs(token, orcamento);
      setAcervo(disponivel.catalogs);
      setAcervoAviso(null);
    } catch (error) {
      // Falha aqui não toma a tela nem apaga a escolha: a lista fica declaradamente não
      // lida, o motivo aparece ao lado do campo e o caminho do arquivo próprio segue de pé.
      setAcervo(null);
      setAcervoAviso(`${AVISO_ACERVO_INDISPONIVEL} ${describeError(error)}`);
    }
  }, [orcamento, tokenDaSessao]);

  useEffect(() => {
    if (!autenticado || orcamento === null) {
      return;
    }
    void carregarAcervo();
    // O regime da rodada é dependência REAL: é ele que filtra a lista no servidor, e uma
    // rodada declarada depois da leitura passa a oferecer menos do que ofereceu.
  }, [autenticado, carregarAcervo, orcamento, state?.regime?.value]);

  /**
   * Busca em voo não sobrevive à saída da tela: o timer do debounce e a consulta pendente
   * são cancelados, e o cancelamento nunca vira alerta (`isAbortError`).
   */
  useEffect(
    () => () => {
      if (buscaTimerRef.current !== null) {
        clearTimeout(buscaTimerRef.current);
      }
      buscaAbortRef.current?.abort();
    },
    [],
  );

  /** Poll do estado enquanto a chamada paga está na fila ou rodando. */
  useEffect(() => {
    const status = state?.extraction.status;
    if (status !== "queued" && status !== "running") {
      return;
    }
    const timer = setInterval(() => void carregarEstado(), EXTRACTION_POLL_MS);
    return () => clearInterval(timer);
  }, [carregarEstado, state?.extraction.status]);

  const abrirOrcamento = useCallback(
    (next: string | null) => {
      setOrcamento(next);
      setState(null);
      setVersion(null);
      setTakeoff(null);
      setOverlay(null);
      setCodes(null);
      setSuggestions(null);
      setEstimate(null);
      setPlateSrc(null);
      setOpenStep(null);
      setSelectedItemId("");
      setSelectedPendingId("");
      setCodeChoice(null);
      setCodeNote("");
      setSearchResult(null);
      setQuery("");
      setBdiInput("");
      setTetoInput("");
      setTetoLabelInput("");
      // O acervo é filtrado PELA rodada: a lista da rodada anterior não vale para a nova.
      setAcervo(null);
      setAcervoAviso(null);
      setTabelaEscolhida("");
      setTabelaPropria(false);
      setAuditoriaReprovada(null);
      // Os desfechos da assinatura são do orçamento que estava aberto; levá-los para o
      // próximo faria uma recusa de outra rodada aparecer sobre esta.
      setConfirmandoAprovacao(false);
      setViolacoesDoDespacho(null);
      setSemPapelDeAprovador(null);
      setSemPapelDeOrcamentista(null);
      setAutoAprovacaoRecusada(null);
      setRevisionConflict(false);
      setAlertMessage(null);
      onOpenEstimate?.(next);
    },
    [onOpenEstimate],
  );

  /** Envelope comum das mutações: conflito, auditoria reprovada e alerta comum. */
  const registrarRecusa = useCallback((error: unknown) => {
    if (isForbidden(error)) {
      setSemAcesso(error instanceof Error ? error.message : null);
      return;
    }
    const recusa = recusaDeMutacao(error);
    setRevisionConflict(recusa.conflito);
    if (recusa.auditoria) {
      setAuditoriaReprovada(workbookAuditFindings(error));
      return;
    }
    setAlertMessage(recusa.conflito ? null : recusa.mensagem);
  }, []);

  const criarOrcamento = async () => {
    const token = tokenDaSessao();
    if (token === null) {
      return;
    }
    setSubmitting(true);
    try {
      const created = await createEstimate(token, {
        worksiteKey: form.worksiteKey,
        worksiteName: form.worksiteName,
        referenceLabel: form.referenceLabel,
        address: form.address,
        targetAmount: form.tetoAmount,
        targetLabel: form.tetoLabel,
        // Pré-licitação é a ausência do campo: `undefined` não vira chave no corpo, e é
        // assim que a rodada nasce sem regime, como sempre nasceu.
        pricingRegime: form.regime === "" ? undefined : form.regime,
      });
      setForm(EMPTY_ESTIMATE_FORM);
      setToast("Orçamento aberto. A próxima etapa é instalar a cascata de fontes.");
      abrirOrcamento(created.round_id);
    } catch (error) {
      registrarRecusa(error);
    } finally {
      setSubmitting(false);
    }
  };

  /**
   * A tabela PRÓPRIA do cliente: o caminho que já existia, inteiro e sem mudança de
   * comportamento. Ele deixou de ser a primeira coisa que aparece, não de existir.
   */
  const instalarCatalogo = async () => {
    const token = tokenDaSessao();
    if (token === null || orcamento === null || version === null || catalogFile === null) {
      return;
    }
    setSubmitting(true);
    try {
      const uploadId = await uploadCatalog(token, catalogFile);
      const cascade = await installCatalog(token, orcamento, uploadId, version);
      aplicarVersao(cascade.version);
      setCatalogFile(null);
      setAlertMessage(null);
      setRevisionConflict(false);
      setToast("Fonte instalada no fim da cascata.");
      await carregarEstado();
    } catch (error) {
      registrarRecusa(error);
    } finally {
      setSubmitting(false);
    }
  };

  /**
   * A tabela do ACERVO: mesma rota, mesmas regras de cascata, nenhum arquivo. A escolha só
   * é limpa quando o servidor confirmou a instalação — recusa preserva o que foi escolhido,
   * como o resto da jornada faz com o formulário.
   */
  const instalarDoAcervo = async () => {
    const token = tokenDaSessao();
    if (
      token === null ||
      orcamento === null ||
      version === null ||
      tabelaEscolhida === ""
    ) {
      return;
    }
    setSubmitting(true);
    try {
      const cascade = await installReferenceCatalog(
        token,
        orcamento,
        tabelaEscolhida,
        version,
      );
      aplicarVersao(cascade.version);
      setTabelaEscolhida("");
      setAlertMessage(null);
      setRevisionConflict(false);
      setToast("Tabela do acervo instalada no fim da cascata.");
      await carregarEstado();
    } catch (error) {
      registrarRecusa(error);
    } finally {
      setSubmitting(false);
    }
  };

  const moverFonte = async (entry: CascadeEntry, move: "up" | "down") => {
    const token = tokenDaSessao();
    if (token === null || orcamento === null || version === null || state === null) {
      return;
    }
    const cascade = reorderedDigests(state.cascade, entry.source_sha256, move);
    if (cascade === null) {
      return;
    }
    setSubmitting(true);
    try {
      const next = await reorderCascade(token, orcamento, {
        cascade,
        baseVersion: version,
      });
      aplicarVersao(next.version);
      setAlertMessage(null);
      setRevisionConflict(false);
      setToast("Ordem da cascata alterada; a próxima shortlist já sai nela.");
      await carregarEstado();
    } catch (error) {
      registrarRecusa(error);
    } finally {
      setSubmitting(false);
    }
  };

  const removerFonte = async (entry: CascadeEntry) => {
    const token = tokenDaSessao();
    if (token === null || orcamento === null || version === null) {
      return;
    }
    setSubmitting(true);
    try {
      const next = await removeCascadeSource(token, orcamento, {
        sourceSha256: entry.source_sha256,
        baseVersion: version,
      });
      aplicarVersao(next.version);
      setAlertMessage(null);
      setRevisionConflict(false);
      setToast(`${entry.source_label} removida da cascata.`);
      await carregarEstado();
    } catch (error) {
      registrarRecusa(error);
    } finally {
      setSubmitting(false);
    }
  };

  const enviarPrancha = async () => {
    const token = tokenDaSessao();
    if (token === null || orcamento === null || version === null || plateFile === null) {
      return;
    }
    setSubmitting(true);
    try {
      const uploadId = await uploadPlateFile(token, plateFile);
      const plate = await associatePlate(token, orcamento, uploadId, version);
      aplicarVersao(plate.version);
      setPlateFile(null);
      setAlertMessage(null);
      setRevisionConflict(false);
      setToast("Prancha associada ao orçamento.");
      await carregarEstado();
    } catch (error) {
      registrarRecusa(error);
    } finally {
      setSubmitting(false);
    }
  };

  const dispararExtracao = async () => {
    const token = tokenDaSessao();
    if (token === null || orcamento === null || version === null) {
      return;
    }
    setSubmitting(true);
    try {
      const response = await createPlateExtraction(token, orcamento, version);
      aplicarVersao(response.version);
      setAlertMessage(null);
      setRevisionConflict(false);
      setToast("Leitura automática enfileirada.");
      await carregarEstado();
    } catch (error) {
      registrarRecusa(error);
    } finally {
      setSubmitting(false);
    }
  };

  const decidirItem = async () => {
    const token = tokenDaSessao();
    if (
      token === null ||
      orcamento === null ||
      version === null ||
      selectedItemId === "" ||
      decision.action === ""
    ) {
      return;
    }
    const quantidade =
      decision.quantity.trim().length === 0
        ? undefined
        : (parseDecimalInput(decision.quantity) ?? undefined);
    if (decision.quantity.trim().length > 0 && quantidade === undefined) {
      setAlertMessage(
        "A quantidade escrita não é um decimal exato; nada foi enviado. " +
          DICA_QUANTIDADE,
      );
      return;
    }
    setSubmitting(true);
    try {
      const response = await postTakeoffDecision(token, orcamento, {
        itemId: selectedItemId,
        action: decision.action,
        baseVersion: version,
        quantity: quantidade,
        unit: decision.unit,
        note: decision.note,
        itemNote: decision.itemNote,
      });
      aplicarVersao(response.version);
      setTakeoff(response);
      setDecision(EMPTY_DECISION);
      setSelectedItemId("");
      setAlertMessage(null);
      setRevisionConflict(false);
      setToast("Decisão registrada.");
      await carregarEstado();
    } catch (error) {
      registrarRecusa(error);
    } finally {
      setSubmitting(false);
    }
  };

  const calcularShortlist = async (recompute: boolean) => {
    const token = tokenDaSessao();
    if (token === null || orcamento === null) {
      return;
    }
    setSubmitting(true);
    try {
      const response =
        recompute && version !== null
          ? await postSuggestionsRecompute(token, orcamento, version)
          : await getSuggestions(token, orcamento);
      setSuggestions(response);
      aplicarVersao(response.version);
      setAlertMessage(null);
      setRevisionConflict(false);
    } catch (error) {
      registrarRecusa(error);
    } finally {
      setSubmitting(false);
    }
  };

  /**
   * Busca incremental na cascata: cada tecla cancela a consulta anterior. O cancelamento
   * não é falha de rede e não vira alerta (`isAbortError`).
   */
  const agendarBusca = (texto: string) => {
    setQuery(texto);
    if (buscaTimerRef.current !== null) {
      clearTimeout(buscaTimerRef.current);
    }
    if (texto.trim().length === 0) {
      setSearchResult(null);
      setBuscaAviso(null);
      return;
    }
    buscaTimerRef.current = setTimeout(() => {
      void (async () => {
        const token = tokenDaSessao();
        if (token === null || orcamento === null) {
          return;
        }
        buscaAbortRef.current?.abort();
        const controller = new AbortController();
        buscaAbortRef.current = controller;
        setBuscando(true);
        try {
          setSearchResult(
            await searchCascade(token, orcamento, texto, 20, {
              signal: controller.signal,
            }),
          );
          setBuscaAviso(null);
        } catch (error) {
          if (!isAbortError(error)) {
            setBuscaAviso(describeError(error));
          }
        } finally {
          setBuscando(false);
        }
      })();
    }, BUSCA_DEBOUNCE_MS);
  };

  const decidirCodigo = async (action: "confirm" | "reject") => {
    const token = tokenDaSessao();
    if (
      token === null ||
      orcamento === null ||
      version === null ||
      selectedPendingId === ""
    ) {
      return;
    }
    setSubmitting(true);
    try {
      const response = await postCodeDecision(token, orcamento, {
        itemId: selectedPendingId,
        action,
        baseVersion: version,
        code: action === "confirm" ? codeChoice?.code : undefined,
        catalogSha256:
          action === "confirm" ? codeChoice?.catalogSha256 : undefined,
        note: codeNote,
      });
      aplicarVersao(response.version);
      setCodes(response);
      setCodeChoice(null);
      setCodeNote("");
      // O item SEGUE selecionado depois de confirmar: o elemento pode disparar mais de um
      // serviço, e limpar a seleção aqui obrigaria a reencontrá-lo na lista a cada código.
      // A rejeição encerra o item sozinha, e aí sim a seleção sai.
      if (action === "reject") {
        setSelectedPendingId("");
      }
      setAlertMessage(null);
      setRevisionConflict(false);
      setToast(
        action === "confirm"
          ? "Código confirmado, com a fonte citada. Feche o pacote quando não houver mais serviços."
          : "Item declarado sem preço na cascata.",
      );
      await carregarEstado();
    } catch (error) {
      registrarRecusa(error);
    } finally {
      setSubmitting(false);
    }
  };

  const fecharPacote = async () => {
    const token = tokenDaSessao();
    if (
      token === null ||
      orcamento === null ||
      version === null ||
      selectedPendingId === ""
    ) {
      return;
    }
    setSubmitting(true);
    try {
      const response = await postCodeClosure(token, orcamento, {
        itemId: selectedPendingId,
        baseVersion: version,
        note: codeNote,
      });
      aplicarVersao(response.version);
      setCodes(response);
      setCodeChoice(null);
      setCodeNote("");
      setSelectedPendingId("");
      setAlertMessage(null);
      setRevisionConflict(false);
      setToast("Pacote de serviços declarado completo.");
      await carregarEstado();
    } catch (error) {
      registrarRecusa(error);
    } finally {
      setSubmitting(false);
    }
  };

  const montarOrcamento = async () => {
    const token = tokenDaSessao();
    if (token === null || orcamento === null || version === null) {
      return;
    }
    const erroBdi = bdiPercentError(bdiInput);
    if (erroBdi !== null) {
      setAlertMessage(erroBdi);
      return;
    }
    setSubmitting(true);
    setAuditoriaReprovada(null);
    try {
      const response = await postBuildEstimate(token, orcamento, bdiInput, version);
      aplicarVersao(response.version);
      setEstimate(response);
      setAlertMessage(null);
      setRevisionConflict(false);
      setToast(
        "Orçamento montado. Nenhuma planilha foi publicada: despachar é ato próprio, na etapa “Aprovação e despacho”.",
      );
      await carregarEstado();
    } catch (error) {
      registrarRecusa(error);
    } finally {
      setSubmitting(false);
    }
  };

  /** Limpa os desfechos da etapa antes de um ato novo; nenhum deles expira sozinho. */
  const limparDesfechosDaAprovacao = () => {
    setViolacoesDoDespacho(null);
    setSemPapelDeAprovador(null);
    setSemPapelDeOrcamentista(null);
    setAutoAprovacaoRecusada(null);
    setAuditoriaReprovada(null);
  };

  /**
   * Assina nominalmente o orçamento da cabeça (F-035, ADR-0046).
   *
   * A tela não decide autorização nenhuma aqui: ela pede, e o servidor responde. Os dois
   * `403` possíveis têm desfecho próprio porque não significam a mesma coisa — falta do
   * papel `aprovador` é uma coisa, e "quem montou não assina" é outra, que o papel não
   * resolve. Nenhum dos dois é a tela de "sem acesso": quem chega aqui já leu o orçamento.
   *
   * O corpo é só `base_version`. A identidade não viaja, e é por isso que não existe campo
   * de nome no ato.
   */
  const aprovarOrcamento = async () => {
    const token = tokenDaSessao();
    if (token === null || orcamento === null || version === null) {
      return;
    }
    setSubmitting(true);
    setAlertMessage(null);
    limparDesfechosDaAprovacao();
    try {
      const response = await postApproveEstimate(token, orcamento, version);
      aplicarVersao(response.version);
      setEstimate(response);
      setConfirmandoAprovacao(false);
      setRevisionConflict(false);
      setToast(MENSAGEM_ORCAMENTO_APROVADO);
      await carregarEstado();
    } catch (error) {
      // As duas recusas de papel voltam ao PRIMEIRO passo do ato: repetir "Confirmar"
      // colheria a mesma recusa, e deixar o âmbar aberto sugeriria que o ato ainda está
      // ao alcance de mais um clique.
      if (isSelfApprovalForbidden(error)) {
        setConfirmandoAprovacao(false);
        // `""` é "recusado, sem detalhe legível": `null` aqui significaria "não houve
        // recusa", e a tela esconderia a única coisa que ela precisa dizer.
        setAutoAprovacaoRecusada(error instanceof Error ? error.message : "");
        return;
      }
      if (isForbidden(error)) {
        setConfirmandoAprovacao(false);
        setSemPapelDeAprovador(error instanceof Error ? error.message : "");
        return;
      }
      const recusa = recusaDeMutacao(error);
      if (recusa.conflito) {
        setRevisionConflict(true);
      } else {
        setAlertMessage(recusa.mensagem);
      }
    } finally {
      setSubmitting(false);
    }
  };

  /**
   * Despacha a planilha. A tela não decide nada aqui: ela pede, e os dois portões do
   * servidor — o do domínio e o da auditoria de round-trip — decidem se existe arquivo.
   *
   * Cada desfecho tem forma própria porque eles não significam a mesma coisa: violação do
   * portão é lista de motivos abertos (o servidor recusa por todos de uma vez), auditoria
   * reprovada é tela com "nada foi publicado" por extenso, e `409` é o banner da rodada.
   *
   * A releitura depois do sucesso não é zelo: a URL assinada da planilha **só** existe na
   * leitura, e sem ela a tela teria arquivo publicado e nenhum caminho para baixá-lo.
   */
  const despacharPlanilha = async () => {
    const token = tokenDaSessao();
    if (token === null || orcamento === null || version === null) {
      return;
    }
    setSubmitting(true);
    setDespachando(true);
    setAlertMessage(null);
    limparDesfechosDaAprovacao();
    try {
      const response = await postExportEstimate(token, orcamento, version);
      aplicarVersao(response.version);
      setEstimate(
        (await leituraObservacional(() => getEstimate(token, orcamento))) ??
          response,
      );
      setRevisionConflict(false);
      setToast(MENSAGEM_ORCAMENTO_DESPACHADO);
      await carregarEstado();
    } catch (error) {
      // `403` aqui é falta do papel do DESPACHO, não falta de acesso à rodada: quem chegou
      // até este botão leu a jornada inteira, e a tela de "sem acesso" apagaria a
      // assinatura da vista para dizer o contrário.
      if (isForbidden(error)) {
        setSemPapelDeOrcamentista(error instanceof Error ? error.message : "");
        return;
      }
      const violacoes = exportBlockedViolations(error);
      if (violacoes.length > 0) {
        setViolacoesDoDespacho(violacoes);
        return;
      }
      const recusa = recusaDeMutacao(error);
      if (recusa.conflito) {
        setRevisionConflict(true);
      } else if (recusa.auditoria) {
        setAuditoriaReprovada(workbookAuditFindings(error));
      } else {
        setAlertMessage(recusa.mensagem);
      }
    } finally {
      setDespachando(false);
      setSubmitting(false);
    }
  };

  /**
   * Declara ou edita o teto da rodada. Mutação como qualquer outra desta jornada: cita
   * `base_version`, manda `Idempotency-Key` e não toca no orçamento montado — o documento
   * continua o mesmo, e é o consumo que passa a ser lido contra o teto novo.
   */
  const gravarTeto = async () => {
    const token = tokenDaSessao();
    if (token === null || orcamento === null || version === null) {
      return;
    }
    const erroTeto = tetoAmountError(tetoInput);
    if (erroTeto !== null || tetoInput.trim().length === 0) {
      setAlertMessage(
        erroTeto ??
          "Informe o teto de verba desta rodada; apagar um teto já declarado não é ato desta tela.",
      );
      return;
    }
    setSubmitting(true);
    try {
      const response = await postTarget(
        token,
        orcamento,
        version,
        tetoInput,
        tetoLabelInput,
      );
      aplicarVersao(response.version);
      setAlertMessage(null);
      setRevisionConflict(false);
      setToast(
        "Teto gravado na rodada. O orçamento montado não mudou — mudou a régua do consumo.",
      );
      await carregarEstado();
    } catch (error) {
      registrarRecusa(error);
    } finally {
      setSubmitting(false);
    }
  };

  /**
   * Declara que a rodada corre sob contrato licitado (ADR-0045). Mutação como as outras:
   * cita `base_version`, manda `Idempotency-Key` e não reescreve cascata nenhuma.
   *
   * A tela não antecipa a recusa da cascata suja. Quem conhece a cascata gravada é o
   * servidor, e `ESTIMATE_REGIME_CASCADE_DIRTY` chega por extenso, dizendo que nada foi
   * gravado e que remover a fonte é o caminho — o estado da rodada não muda na tela porque
   * ele não mudou no servidor.
   */
  const declararRegime = async () => {
    const token = tokenDaSessao();
    if (token === null || orcamento === null || version === null) {
      return;
    }
    // Pré-licitação não é ato: ela é onde a rodada já está, e mandá-la ao servidor só
    // colheria `ESTIMATE_REGIME_IRREVERSIBLE` para dizer o que a tela já sabe.
    if (regimeInput === "") {
      return;
    }
    setSubmitting(true);
    try {
      const response = await postRegime(token, orcamento, version);
      aplicarVersao(response.version);
      setRegimeInput("");
      setAlertMessage(null);
      setRevisionConflict(false);
      setToast(
        "Regime declarado: a rodada corre sob contrato licitado, e a cascata passa a aceitar só a tabela do contrato.",
      );
      await carregarEstado();
    } catch (error) {
      registrarRecusa(error);
    } finally {
      setSubmitting(false);
    }
  };

  const jornada = useMemo(() => derivarEtapas(state), [state]);
  const etapaVisivel: EtapaId | "resumo" = openStep ?? "resumo";

  const abrirEtapa = (etapa: Etapa) => {
    if (etapa.status === "blocked") {
      return;
    }
    setOpenStep(etapa.id);
  };

  const cascade = state?.cascade ?? [];
  const cascataTravada = state?.codes.assignments_present ?? false;
  // O regime lido da rodada, e nada além dele: ausência do bloco é a rodada de sempre —
  // pré-licitação, cascata livre, tela de hoje —, e `null` aqui não é um estado a
  // comunicar. A lista de origens aceitas vem junto porque a regra é do servidor.
  const regime = state?.regime ?? null;
  const sobContrato = regime !== null;
  const regimeAceita =
    regime === null
      ? null
      : origensAceitasNaCascata(regime.allowed_cascade_origins);
  const itens = takeoff?.packet.items ?? [];
  const itemSelecionado = itens.find((item) => item.id === selectedItemId) ?? null;
  const pendingItems = codes?.pending_items ?? [];
  /** Os códigos já confirmados do item selecionado — o pacote que está sendo montado. */
  const pacoteDoItem = (codes?.assignments?.assignments ?? []).filter(
    (assignment) =>
      assignment.item_id === selectedPendingId &&
      assignment.status === "confirmed",
  );
  const itemPendente =
    pendingItems.find((item) => item.item_id === selectedPendingId) ?? null;
  const candidatos: CodeSuggestionSet.CodeCandidate[] =
    suggestions?.suggestions.suggestions.find(
      (suggestion) => suggestion.item_id === selectedPendingId,
    )?.candidates ?? [];
  const semCandidato = (suggestions?.suggestions.unmatched_item_ids ?? []).filter(
    (itemId) => pendingItems.some((item) => item.item_id === itemId),
  );
  const bdiErro = bdiInput.trim().length === 0 ? null : bdiPercentError(bdiInput);
  // O bloco do teto é derivado do ESTADO da rodada, que é a leitura autoritativa: o
  // servidor manda `{target, consumed, remaining, over}` pronto, e `null` aqui é a rodada
  // sem teto — nada a acrescentar à prévia nem à barra de etapas.
  const tetoDerivado = useMemo(() => derivarTeto(state), [state]);
  const tetoErroAbertura = tetoAmountError(form.tetoAmount);

  // Identidade da sessão como a tela a MOSTRA no ato nominal. Ela não é campo e não entra
  // no corpo da mutação: quem carimba é o servidor, lendo o subject do token.
  const identidadeDaSessao =
    session === null
      ? ""
      : (session.profile.preferred_username ?? session.profile.sub);
  // O bloco de aprovação vem do documento já lido e, na falta dele, do estado da rodada: as
  // duas leituras são do servidor e derivam a caducidade do mesmo par de digests. `null` é
  // "não há orçamento legível na cabeça", que a etapa trata como "nada a assinar".
  const aprovacao: ApprovalState | null =
    estimate?.approval ?? state?.approval ?? null;
  // `approved` e `stale` juntos, sempre: na aprovação caduca os dois valem, e ler só o
  // primeiro ofereceria um despacho que a rota já sabe que vai recusar.
  const aprovacaoValida =
    aprovacao !== null && aprovacao.approved && !aprovacao.stale;

  // Sem sessão a jornada não chama nada e não inventa orçamento: quem tem a tela de
  // entrar é a casca (`App.tsx`), e as rotas do orçamento são autenticadas e por tenant.
  if (!autenticado) {
    return (
      <div className="jornada-orcamento">
        <section className="painel" aria-label="Orçamento-base">
          {/* Sem sessão não há rodada, e sem rodada não há regime a afirmar: o sufixo do
              momento só aparece dentro de uma rodada aberta (F-033, revisão 2, tela 2).
              Veste CLARA porque este é o único eyebrow da jornada que vive sobre painel
              branco, e o token do eyebrow é a tinta da topbar escura. */}
          <span className="eyebrow eyebrow-claro">ORÇAMENTO-BASE</span>
          <h1>Entre para abrir um orçamento</h1>
          <p>
            O orçamento-base é autenticado e por tenant: cascata, prancha e decisões só são
            lidos com a sessão de quem decide.
          </p>
          <p className="aviso-fixo">{AVISO_ORCAMENTO_SEM_RODADA}</p>
        </section>
      </div>
    );
  }

  if (semAcesso !== null) {
    return (
      <div className="jornada-orcamento">
        <header className="topbar">
          <div>
            {/* A recusa é de acesso ao tenant: nenhuma rodada foi lida, e o rótulo não
                afirma o momento de uma rodada que ele não tem. */}
            <span className="eyebrow">ORÇAMENTO-BASE</span>
            <h1>Orçamento-base</h1>
          </div>
          <p className="aviso-fixo">{AVISO_ORCAMENTO_SEM_RODADA}</p>
        </header>
        <main className="conteudo">
          <PainelSemAcesso detalhe={semAcesso} />
        </main>
      </div>
    );
  }

  // Nenhum orçamento aberto: a jornada começa escolhendo — ou abrindo — um.
  if (orcamento === null) {
    const keyErro = worksiteKeyError(form.worksiteKey);
    return (
      <div className="jornada-orcamento">
        <header className="topbar">
          <div>
            {/* Nenhuma rodada aberta é justamente a tela que afirmava um regime sobre nada
                (F-033, revisão 2): o momento é da rodada, e aqui não há rodada. */}
            <span className="eyebrow">ORÇAMENTO-BASE</span>
            <h1>Nenhum orçamento aberto</h1>
            <p className="topbar-meta">
              Escolha um orçamento da lista ou abra um novo.
            </p>
          </div>
          <p className="aviso-fixo">{AVISO_ORCAMENTO_SEM_RODADA}</p>
        </header>

        {alertMessage === null ? null : (
          <p className="banner-erro" role="alert">
            {alertMessage}
          </p>
        )}
        {toast === null ? null : (
          <p className="banner-sucesso" role="status">
            {toast}
          </p>
        )}

        <main className="conteudo">
          <div className="workspace duas-colunas">
            <section className="painel" aria-label="Orçamentos do tenant">
              <div className="painel-cabecalho">
                <h2>Orçamentos do tenant</h2>
                <div className="cabecalho-controles">
                  <button
                    type="button"
                    className="botao-secundario"
                    onClick={() => void carregarLista()}
                    disabled={loading}
                  >
                    {loading ? "Carregando…" : "Recarregar lista"}
                  </button>
                </div>
              </div>
              {lista === null ? (
                <p className="dica">
                  {loading
                    ? "Carregando orçamentos…"
                    : "A lista de orçamentos ainda não foi lida."}
                </p>
              ) : lista.length === 0 ? (
                <p className="dica">
                  Nenhum orçamento neste tenant ainda. Abra o primeiro ao lado — ele começa
                  pela cascata de catálogos.
                </p>
              ) : (
                <ul className="rodadas-lista">
                  {lista.map((item) => (
                    <li key={item.round_id} className="rodada-linha">
                      <div>
                        <strong>{item.worksite_name}</strong>{" "}
                        <span className="mono">({item.worksite_key})</span>
                        {/* Terceiro lugar do MESMO selo (decisão 4 da revisão 2): o card
                            diz o regime antes de a pessoa abrir a rodada. Nenhuma pastilha
                            nova é inventada, e rodada sem regime não ganha selo — a
                            ausência é a pré-licitação, e ela não tem veste própria. */}
                        <SeloRegimeDaRodada regime={item.pricing_regime} />
                        {/* `.dica`, e não `.topbar-meta`: a cor do `.topbar-meta` é a
                            tinta do topbar ESCURO (`--dark-ink-soft`) e some sobre a
                            superfície clara do painel. Defeito de legibilidade herdado da
                            F-020, consertado aqui porque o mock aprovado da F-027 o expôs
                            nesta mesma lista. */}
                        <p className="dica">
                          {item.reference_label} · etapa {stageLabel(item.stage)} ·
                          leitura da legenda{" "}
                          {extractionStatusLabel(item.extraction_status)} · versão{" "}
                          {item.version}
                        </p>
                        <p className="dica">
                          Cascata:{" "}
                          {item.cascade_origins.length === 0
                            ? "nenhuma fonte instalada"
                            : item.cascade_origins
                                .map(
                                  (origin, index) =>
                                    `${index + 1}. ${priceSourceLabel(origin)}`,
                                )
                                .join(" · ")}
                        </p>
                        <LinhaTetoDaRodada
                          amount={item.target_amount}
                          label={item.target_label}
                        />
                        <p className="dica">
                          Atualizado em {formatTimestamp(item.updated_at)}
                        </p>
                      </div>
                      <button
                        type="button"
                        className="botao-primario"
                        onClick={() => abrirOrcamento(item.round_id)}
                      >
                        Abrir orçamento
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              {/* Por que um card não tem selo, dito uma vez ao pé da lista: sem esta linha
                  a ausência do selo leria como dado que faltou carregar. */}
              {lista !== null && lista.length > 0 ? (
                <p className="dica">{AVISO_CARD_SEM_REGIME}</p>
              ) : null}
              {listaCursor === null ? null : (
                <button
                  type="button"
                  className="botao-secundario"
                  onClick={() => void carregarMais()}
                  disabled={loading}
                >
                  Carregar mais orçamentos
                </button>
              )}
            </section>

            <section className="painel" aria-label="Abrir orçamento novo">
              <div className="painel-cabecalho">
                <h2>Abrir orçamento novo</h2>
              </div>
              <form
                className="formulario"
                onSubmit={(event) => {
                  event.preventDefault();
                  void criarOrcamento();
                }}
              >
                <p className="dica">
                  O catálogo não é pedido aqui: a cascata é a etapa seguinte, e ela aceita
                  mais de uma fonte, em ordem declarada.
                </p>
                <label className="campo">
                  Chave da obra
                  <span className="campo-dica">
                    minúsculas, números e hífen (ex.: praca-do-exemplo). É ela que amarra
                    os artefatos.
                  </span>
                  <input
                    type="text"
                    value={form.worksiteKey}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        worksiteKey: event.target.value,
                      }))
                    }
                    aria-invalid={form.worksiteKey.length > 0 && keyErro !== null}
                    required
                  />
                </label>
                {form.worksiteKey.length > 0 && keyErro !== null ? (
                  <p className="campo-erro" role="alert">
                    {keyErro}
                  </p>
                ) : null}
                <label className="campo">
                  Nome da obra
                  <input
                    type="text"
                    value={form.worksiteName}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        worksiteName: event.target.value,
                      }))
                    }
                    required
                  />
                </label>
                <label className="campo">
                  Rótulo do orçamento
                  <span className="campo-dica">
                    como aparece na planilha (ex.: ORÇAMENTO-BASE 2026)
                  </span>
                  <input
                    type="text"
                    value={form.referenceLabel}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        referenceLabel: event.target.value,
                      }))
                    }
                    required
                  />
                </label>
                <label className="campo">
                  Endereço (opcional)
                  <input
                    type="text"
                    value={form.address}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        address: event.target.value,
                      }))
                    }
                  />
                </label>
                {/* Teto de verba (ADR-0040): opcional de verdade — campo vazio é o padrão,
                    não pede justificativa e não muda o botão. */}
                <label className="campo">
                  Teto da verba (opcional)
                  <span className="campo-dica">{DICA_TETO}</span>
                  <input
                    type="text"
                    inputMode="decimal"
                    value={form.tetoAmount}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        tetoAmount: event.target.value,
                      }))
                    }
                    aria-invalid={tetoErroAbertura !== null}
                  />
                </label>
                {tetoErroAbertura === null ? null : (
                  <p className="campo-erro" role="alert">
                    {tetoErroAbertura}
                  </p>
                )}
                <label className="campo">
                  Demanda de origem (opcional)
                  <span className="campo-dica">{DICA_TETO_DEMANDA}</span>
                  <input
                    type="text"
                    value={form.tetoLabel}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        tetoLabel: event.target.value,
                      }))
                    }
                  />
                </label>
                <p className="dica">{AVISO_TETO_ABERTURA}</p>
                {/* Regime da rodada na abertura (ADR-0045; F-033, revisão 2, tela 3). O
                    campo tem o peso do Teto — pergunta antes, consequência e mão única
                    depois —, porque o que a revisão 1 recusou foi a caixa ESCONDIDA, não
                    declarar na abertura.

                    Duas diferenças em relação ao painel de declarar depois, e as duas são
                    de propósito: aqui a pré-licitação é o PADRÃO, e escolhê-la não desliga
                    o botão — simplesmente não se manda o campo; e o ato desta tela é abrir
                    a rodada, não declarar. */}
                <label className="campo campo-regime">
                  Regime
                  <span className="campo-dica">{PERGUNTA_REGIME_ABERTURA}</span>
                  <select
                    value={form.regime}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        regime:
                          event.target.value === "" ? "" : "contracted_demand",
                      }))
                    }
                  >
                    <option value="">{REGIME_OPCAO_PRE_LICITACAO}</option>
                    <option value="contracted_demand">
                      {REGIME_OPCAO_SOB_CONTRATO}
                    </option>
                  </select>
                  <span className="campo-dica">
                    <strong>{AVISO_REGIME_ABERTURA.destaque}</strong>
                    {AVISO_REGIME_ABERTURA.texto}
                  </span>
                  {/* O que a declaração NÃO garante, nos DOIS lugares em que se declara: o
                      caminho que virou principal não pode ser o que cala sobre a lacuna. */}
                  <span className="campo-dica">{DICA_REGIME}</span>
                </label>
                <button
                  type="submit"
                  className="botao-primario"
                  disabled={submitting || tetoErroAbertura !== null}
                >
                  {submitting ? "Abrindo…" : "Abrir orçamento"}
                </button>
              </form>
            </section>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="jornada-orcamento">
      <header className="topbar">
        <div>
          {/* A sobrescrita declara o MOMENTO da rodada, e o momento mudou: sob contrato
              licitado o preço já está fixado, e a cascata deixou de ser livre. Rodada sem
              regime lê exatamente o que lia antes. */}
          <span className="eyebrow">
            {sobContrato
              ? "ORÇAMENTO-BASE · DEMANDA SOB CONTRATO"
              : "ORÇAMENTO-BASE · PRÉ-LICITAÇÃO"}
          </span>
          <h1>{state === null ? "Orçamento não carregado" : state.worksite_name}</h1>
          {state === null ? (
            <p className="topbar-meta">
              O estado deste orçamento ainda não foi lido da API.
            </p>
          ) : (
            <>
              <p className="topbar-meta mono">
                {state.worksite_key} · orçamento {shortDigest(state.round_id)}
              </p>
              {/* O BDI só é afirmado quando o orçamento montado foi lido: `present` diz
                  que ele existe na rodada, mas o percentual vem do documento, e um
                  "BDI %" vazio seria pior do que dizer que ele ainda não foi lido. */}
              <p className="topbar-meta">
                {state.reference_label} · versão {state.version} ·{" "}
                {estimate !== null
                  ? `BDI ${formatPercentText(estimate.bdi_percent)}`
                  : state.estimate.present
                    ? "BDI ainda não lido"
                    : "BDI não declarado"}
              </p>
            </>
          )}
        </div>
        {/* Primeiro dos dois lugares do selo (decisão 1 do pacote aprovado): o regime vale
            para a rodada inteira, e é aqui que ele é lido antes de qualquer etapa. */}
        {sobContrato ? <SeloRegime /> : null}
        {/* Aviso permanente: ele não fecha, não recolhe e não expira. */}
        <p className="aviso-fixo">
          {sobContrato ? AVISO_ORCAMENTO_SOB_CONTRATO : AVISO_ORCAMENTO}
        </p>
        <div className="topbar-acoes">
          <button
            type="button"
            className="topbar-link topbar-link-botao"
            onClick={() => abrirOrcamento(null)}
          >
            Trocar de orçamento
          </button>
          {session === null ? null : (
            <>
              <span className="topbar-meta">
                Sessão: {session.profile.preferred_username ?? session.profile.sub}
              </span>
              <button
                type="button"
                className="topbar-link topbar-link-botao"
                onClick={() => void signOut()}
              >
                Sair
              </button>
            </>
          )}
        </div>
      </header>

      <nav className="etapas" aria-label="Etapas do orçamento">
        <button
          type="button"
          className={`etapa-tab ${etapaVisivel === "resumo" ? "ativa" : ""}`}
          onClick={() => setOpenStep(null)}
          aria-current={etapaVisivel === "resumo"}
        >
          Resumo
        </button>
        {jornada.etapas.map((etapa) => (
          <button
            key={etapa.id}
            type="button"
            className={`etapa-tab ${etapaVisivel === etapa.id ? "ativa" : ""} ${
              etapa.status
            }`}
            onClick={() => abrirEtapa(etapa)}
            disabled={etapa.status === "blocked"}
            aria-current={etapaVisivel === etapa.id}
            title={etapa.blockedReason ?? etapa.summary}
          >
            {etapa.title} · {etapaStatusLabel(etapa.status)}
          </button>
        ))}
        <button
          type="button"
          className="botao-secundario recarregar"
          onClick={() => void carregarEstado()}
          disabled={loading}
        >
          {loading ? "Recarregando…" : "Recarregar estado atual"}
        </button>
      </nav>

      {/* Uma vez só, FORA da etapa visível: o estouro é condição da rodada, não da etapa
          em que o número foi calculado, e acompanha todas elas enquanto durar. */}
      <FaixaTetoEstourado teto={tetoDerivado} />

      {revisionConflict ? (
        <BannerOrcamentoMudou onReload={() => void carregarEstado()} />
      ) : null}

      {alertMessage === null ? null : (
        <p className="banner-erro" role="alert">
          {alertMessage}
        </p>
      )}

      {toast === null ? null : (
        <p className="banner-sucesso" role="status">
          {toast}
        </p>
      )}

      <main className="conteudo">
        {auditoriaReprovada !== null ? (
          <TelaAuditoriaReprovada
            findings={auditoriaReprovada}
            onDismiss={() => setAuditoriaReprovada(null)}
          />
        ) : etapaVisivel === "resumo" ? (
          <section className="painel" aria-label="Situação do orçamento">
            <h2>Situação do orçamento</h2>
            <ul className="cartoes">
              {jornada.etapas.map((etapa) => (
                <li key={etapa.id} className={`cartao ${etapa.status}`}>
                  <h3>{etapa.title}</h3>
                  <p className="cartao-status">
                    Etapa {etapaStatusLabel(etapa.status)}
                  </p>
                  <p>{etapa.summary}</p>
                  {etapa.blockedReason === undefined ? null : (
                    <p className="cartao-motivo">
                      Bloqueada porque {etapa.blockedReason}.
                    </p>
                  )}
                </li>
              ))}
            </ul>
          </section>
        ) : etapaVisivel === "cascata" ? (
          <div className="coluna-empilhada">
            <section className="painel" aria-label="Cascata de fontes de preço">
              <div className="painel-cabecalho">
                <h2>Cascata de fontes de preço</h2>
              </div>
              <p className="dica">
                {sobContrato ? AVISO_CASCATA_SOB_CONTRATO : AVISO_CASCATA}
              </p>
              {/* Segundo lugar do selo (decisão 1 do pacote aprovado): é aqui que a regra
                  age e aqui que a recusa acontece. Sem ele, a recusa da instalação pareceria
                  arbitrária a quem está na aba. */}
              {sobContrato ? (
                <div className="codigo-selos">
                  <SeloRegime variante="claro" />
                </div>
              ) : null}
              {cascataTravada ? (
                <p className="aviso-fixo aviso-inline">{AVISO_CASCATA_TRAVADA}</p>
              ) : null}
              {cascade.length === 0 ? (
                <p className="dica">
                  Nenhuma fonte instalada. Um orçamento sem cascata não precifica nada —
                  comece pelo catálogo oficial da prefeitura.
                </p>
              ) : (
                <ol className="cascata">
                  {cascade.map((entry) => (
                    <li key={entry.source_sha256}>
                      <span className="cascata-ordem" aria-hidden="true">
                        {entry.position}
                      </span>
                      <div className="cascata-corpo">
                        <h4>{entry.source_label}</h4>
                        <div className="codigo-selos">
                          <SeloFonte
                            origin={entry.origin}
                            referenceMonth={entry.reference_month}
                            position={entry.position}
                          />
                          <SeloProcedencia provenance={entry.provenance} />
                          {entry.summary.entries === undefined ? null : (
                            <span className="selo selo-neutro">
                              {entry.summary.entries} itens
                            </span>
                          )}
                        </div>
                        <p className="digest" title={entry.source_sha256}>
                          sha256 {shortDigest(entry.source_sha256)}
                        </p>
                      </div>
                      <div className="cascata-controles">
                        <button
                          type="button"
                          onClick={() => void moverFonte(entry, "up")}
                          disabled={
                            submitting ||
                            cascataTravada ||
                            !canMove(cascade, entry.source_sha256, "up")
                          }
                          aria-label={`Subir ${entry.source_label} na cascata`}
                        >
                          Subir
                        </button>
                        <button
                          type="button"
                          onClick={() => void moverFonte(entry, "down")}
                          disabled={
                            submitting ||
                            cascataTravada ||
                            !canMove(cascade, entry.source_sha256, "down")
                          }
                          aria-label={`Descer ${entry.source_label} na cascata`}
                        >
                          Descer
                        </button>
                        <button
                          type="button"
                          onClick={() => void removerFonte(entry)}
                          disabled={submitting || cascataTravada}
                          aria-label={`Remover ${entry.source_label} da cascata`}
                        >
                          Remover
                        </button>
                      </div>
                    </li>
                  ))}
                </ol>
              )}
              {cascade.length === 0 ? null : (
                <p className="dica">{AVISO_PROCEDENCIA}</p>
              )}
              <PainelEscolhaDeFonte
                acervo={acervo}
                acervoAviso={acervoAviso}
                escolhida={tabelaEscolhida}
                arquivo={catalogFile}
                tabelaPropria={tabelaPropria}
                regimeAceita={regimeAceita}
                sobContrato={sobContrato}
                instalando={submitting}
                onEscolher={setTabelaEscolhida}
                onArquivo={setCatalogFile}
                onTabelaPropria={setTabelaPropria}
                onInstalarDoAcervo={() => void instalarDoAcervo()}
                onInstalarArquivo={() => void instalarCatalogo()}
              />
            </section>
            {/* Declarar é ato da rodada SEM regime. Declarada, não sobra ato — o regime é
                mão única, e um painel com seletor desabilitado ofereceria o que não existe. */}
            {sobContrato ? null : (
              <PainelRegimeDaRodada
                valor={regimeInput}
                versao={version}
                declarando={submitting}
                onValor={setRegimeInput}
                onDeclarar={() => void declararRegime()}
              />
            )}
          </div>
        ) : etapaVisivel === "prancha" ? (
          <section className="painel" aria-label="Prancha e extração">
            <div className="painel-cabecalho">
              <h2>Prancha</h2>
            </div>
            {state?.plate.present ? (
              <>
                <p className="dica">
                  Prancha associada{" "}
                  {state.plate.page_count === null
                    ? ""
                    : `· ${state.plate.page_count} páginas`}{" "}
                  ·{" "}
                  <span className="digest" title={state.plate.source_sha256 ?? ""}>
                    sha256 {shortDigest(state.plate.source_sha256)}
                  </span>
                </p>
                {plateSrc === null ? (
                  <p className="dica">
                    Imagem da página ainda não publicada pelo processamento.
                  </p>
                ) : (
                  <img
                    className="overlay-imagem"
                    src={plateSrc}
                    alt="Página promovida da prancha deste orçamento"
                    draggable={false}
                  />
                )}
                <EstadoExtracao
                  extraction={state.extraction}
                  onRun={() => void dispararExtracao()}
                  running={submitting}
                />
              </>
            ) : (
              <form
                className="formulario"
                onSubmit={(event) => {
                  event.preventDefault();
                  void enviarPrancha();
                }}
              >
                <p className="dica">
                  Um orçamento é uma prancha. O PDF sobe direto para o armazenamento; a
                  API recebe só o identificador do envio.
                </p>
                <label className="campo">
                  Prancha do projetista (PDF)
                  <input
                    type="file"
                    accept=".pdf,application/pdf"
                    onChange={(event) => setPlateFile(event.target.files?.[0] ?? null)}
                  />
                </label>
                <div className="acoes-linha">
                  <button
                    type="submit"
                    className="botao-primario"
                    disabled={submitting || plateFile === null}
                  >
                    {submitting ? "Enviando…" : "Enviar prancha"}
                  </button>
                </div>
              </form>
            )}
          </section>
        ) : etapaVisivel === "revisao" ? (
          <div className="workspace duas-colunas">
            <section className="painel" aria-label="Prancha do orçamento">
              <div className="painel-cabecalho">
                <h2>Prancha</h2>
              </div>
              {plateSrc === null ? (
                <p className="dica">Imagem da prancha ainda não publicada.</p>
              ) : (
                <img
                  className="overlay-imagem"
                  src={plateSrc}
                  alt="Página promovida da prancha deste orçamento"
                  draggable={false}
                />
              )}
              {overlay === null ? null : <OverlayDoTakeoff overlay={overlay} />}
            </section>

            <section className="painel" aria-label="Itens da legenda">
              <div className="painel-cabecalho">
                <h2>Itens da legenda</h2>
              </div>
              <ul className="itens">
                {itens.map((item, index) => (
                  <li
                    key={item.id}
                    className={`item ${item.status} ${
                      item.id === selectedItemId ? "selecionado" : ""
                    }`}
                  >
                    <button
                      type="button"
                      className="item-botao"
                      onClick={() => {
                        setSelectedItemId(item.id);
                        setDecision(EMPTY_DECISION);
                      }}
                      aria-pressed={item.id === selectedItemId}
                    >
                      <span className="item-numero" aria-hidden="true">
                        {index + 1}
                      </span>
                      <span className="item-corpo">
                        <span className="item-rotulo">{item.label}</span>
                        <span className="item-estado">
                          {itemStatusLabel(item.status)}
                        </span>
                        <span className="item-quantidade">
                          {formatQuantityText(
                            item.quantity ?? null,
                            unitLabel(item.unit),
                          )}
                        </span>
                        {item.raw_text ? (
                          <span className="item-raw">
                            lido da legenda: “{item.raw_text}”
                          </span>
                        ) : null}
                        {itemAnchor(item) === "registered" ? null : (
                          <span className="item-nota">
                            {AVISO_LOCALIZACAO_NAO_CONFIRMADA}
                          </span>
                        )}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>

              {itemSelecionado === null ? (
                <p className="dica">
                  Escolha um item da lista para decidir. Nada nasce pré-marcado e não
                  existe “confirmar tudo”.
                </p>
              ) : (
                <form
                  className="formulario"
                  onSubmit={(event) => {
                    event.preventDefault();
                    void decidirItem();
                  }}
                >
                  <h3>{itemSelecionado.label}</h3>
                  {itemSelecionado.status === "ambiguous" ? (
                    <p className="campo-aviso">{AVISO_QUANTIDADE_AMBIGUA}</p>
                  ) : null}
                  <div className="acoes">
                    <label>
                      <input
                        type="radio"
                        name="decisao-item"
                        checked={decision.action === "confirm"}
                        onChange={() =>
                          setDecision((current) => ({ ...current, action: "confirm" }))
                        }
                      />
                      Confirmar
                    </label>
                    <label>
                      <input
                        type="radio"
                        name="decisao-item"
                        checked={decision.action === "reject"}
                        onChange={() =>
                          setDecision((current) => ({ ...current, action: "reject" }))
                        }
                      />
                      Rejeitar
                    </label>
                  </div>
                  <label className="campo">
                    Quantidade
                    <span className="campo-dica">{DICA_QUANTIDADE}</span>
                    <input
                      type="text"
                      value={decision.quantity}
                      onChange={(event) =>
                        setDecision((current) => ({
                          ...current,
                          quantity: event.target.value,
                        }))
                      }
                    />
                  </label>
                  <label className="campo">
                    Unidade
                    <input
                      type="text"
                      value={decision.unit}
                      onChange={(event) =>
                        setDecision((current) => ({
                          ...current,
                          unit: event.target.value,
                        }))
                      }
                    />
                  </label>
                  <label className="campo">
                    Nota da decisão
                    <textarea
                      value={decision.note}
                      onChange={(event) =>
                        setDecision((current) => ({
                          ...current,
                          note: event.target.value,
                        }))
                      }
                    />
                  </label>
                  <div className="acoes-linha">
                    <button
                      type="submit"
                      className="botao-primario"
                      disabled={submitting || decision.action === ""}
                    >
                      {submitting ? "Registrando…" : "Registrar decisão"}
                    </button>
                  </div>
                </form>
              )}
            </section>
          </div>
        ) : etapaVisivel === "codigos" ? (
          <div className="workspace duas-colunas">
            <section className="painel" aria-label="Decisões de código">
              <div className="painel-cabecalho">
                <h2>Decisões</h2>
                <div className="cabecalho-controles">
                  <button
                    type="button"
                    className="botao-secundario"
                    onClick={() => void calcularShortlist(suggestions !== null)}
                    disabled={submitting}
                  >
                    {suggestions === null
                      ? "Calcular shortlist"
                      : "Recalcular shortlist"}
                  </button>
                </div>
              </div>
              <p className="dica">{DESCRICAO_CALCULO_SHORTLIST}</p>
              {(suggestions?.semantic_notes ?? []).map((note) => (
                <p key={note} className="dica">
                  {note}
                </p>
              ))}

              {/* Sob contrato, a rejeição muda de nome, e a tela diz de onde o nome vem:
                  do julgamento de quem revisou, nunca de uma conferência contra um
                  contrato que o orçamento não modela (ADR-0045, decisão 5). */}
              {sobContrato ? (
                <p className="dica">{AVISO_CANDIDATO_ADITIVO}</p>
              ) : null}

              <ul className="confirmados-lista">
                {(codes?.assignments?.assignments ?? []).map((assignment) => {
                  const fonte = entryOfDigest(cascade, assignment.catalog_sha256);
                  return (
                    <li key={assignment.item_id}>
                      <strong>{assignment.item_id}</strong>{" "}
                      {assignment.code ? (
                        <span className="mono">{assignment.code}</span>
                      ) : null}
                      <div className="codigo-selos">
                        <span
                          className={`selo ${seloDaDecisao(assignment.status, sobContrato)}`}
                        >
                          {assignmentStatusLabel(assignment.status, sobContrato)}
                        </span>
                        {fonte === null ? null : (
                          <SeloFonte
                            origin={fonte.origin}
                            referenceMonth={fonte.reference_month}
                            position={fonte.position}
                          />
                        )}
                      </div>
                    </li>
                  );
                })}
              </ul>
              {sobContrato ? (
                <p className="dica">{DICA_CANDIDATO_ADITIVO}</p>
              ) : null}

              <h3>Itens sem decisão de código</h3>
              <ul className="itens">
                {pendingItems.map((item) => (
                  <li
                    key={item.item_id}
                    className={`item ${item.status} ${
                      item.item_id === selectedPendingId ? "selecionado" : ""
                    }`}
                  >
                    <button
                      type="button"
                      className="item-botao"
                      onClick={() => {
                        setSelectedPendingId(item.item_id);
                        setCodeChoice(null);
                        setCodeNote("");
                      }}
                      aria-pressed={item.item_id === selectedPendingId}
                    >
                      <span className="item-corpo">
                        <span className="item-rotulo">{item.label}</span>
                        <span className="item-quantidade">
                          {formatQuantityText(item.quantity, unitLabel(item.unit))}
                        </span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>

              <SemPrecoNaCascata
                rotulos={semCandidato.map((itemId) => {
                  const item = pendingItems.find(
                    (pending) => pending.item_id === itemId,
                  );
                  return item === undefined
                    ? itemId
                    : rotuloDoItem(item.label, item.quantity, item.unit);
                })}
              />
            </section>

            <section className="painel" aria-label="Candidatos de código">
              <div className="painel-cabecalho">
                <h2>
                  {itemPendente === null
                    ? "Escolha um item"
                    : itemPendente.label}
                </h2>
              </div>
              {itemPendente === null ? (
                <p className="dica">
                  Confirmar um código é escolher de qual fonte da cascata, e com que
                  data-base, o preço daquele item sai.
                </p>
              ) : (
                <>
                  <div className="busca">
                    <label className="campo">
                      Buscar na cascata
                      <input
                        type="text"
                        value={query}
                        onChange={(event) => agendarBusca(event.target.value)}
                      />
                    </label>
                    {buscando ? <span className="dica">Buscando…</span> : null}
                  </div>
                  {buscaAviso === null ? null : (
                    <p className="campo-aviso" role="alert">
                      {buscaAviso}
                    </p>
                  )}

                  <ul className="codigos">
                    {candidatos.map((candidate) => {
                      const fonte = entryOfDigest(
                        cascade,
                        candidate.catalog_sha256 ?? null,
                      );
                      const escolhido = codeChoice?.code === candidate.code;
                      return (
                        <li
                          key={`${candidate.catalog_sha256 ?? ""}:${candidate.code}`}
                          className={`codigo-card ${escolhido ? "escolhido" : ""}`}
                        >
                          <div className="codigo-topo">
                            <span className="codigo-code">{candidate.code}</span>
                            <span className="mono">
                              {formatMoneyText(candidate.unit_price)} /{" "}
                              {unitLabel(candidate.unit)}
                            </span>
                          </div>
                          <div className="codigo-selos">
                            <SeloFonte
                              origin={candidate.catalog_origin ?? "sco"}
                              referenceMonth={fonte?.reference_month}
                              position={fonte?.position}
                            />
                            <span
                              className={`selo ${
                                candidate.unit_compatible ? "selo-ok" : "selo-atencao"
                              }`}
                            >
                              {candidate.unit_compatible
                                ? "unidade compatível"
                                : "unidade diferente da do item"}
                            </span>
                          </div>
                          <p className="codigo-descricao">{candidate.description}</p>
                          <button
                            type="button"
                            className="botao-secundario"
                            disabled={fonte === null}
                            onClick={() =>
                              fonte === null
                                ? undefined
                                : setCodeChoice({
                                    code: candidate.code,
                                    description: candidate.description,
                                    unit: candidate.unit,
                                    unit_price: candidate.unit_price,
                                    catalogSha256: fonte.source_sha256,
                                    priceOrigin: fonte.origin,
                                    unit_compatible: candidate.unit_compatible,
                                  })
                            }
                          >
                            {escolhido ? "Escolhido" : "Escolher este código"}
                          </button>
                          {fonte === null ? (
                            <p className="campo-aviso">
                              Este candidato cita um catálogo que não está na cascata
                              deste orçamento; ele não pode ser confirmado.
                            </p>
                          ) : null}
                        </li>
                      );
                    })}
                    {(searchResult?.results ?? []).map((result) => {
                      const escolhido =
                        codeChoice?.code === result.code &&
                        codeChoice?.catalogSha256 === result.catalog_sha256;
                      return (
                        <li
                          key={`busca:${result.catalog_sha256}:${result.code}`}
                          className={`codigo-card ${escolhido ? "escolhido" : ""}`}
                        >
                          <div className="codigo-topo">
                            <span className="codigo-code">{result.code}</span>
                            <span className="mono">
                              {formatMoneyText(result.unit_price)} /{" "}
                              {unitLabel(result.unit)}
                            </span>
                          </div>
                          <div className="codigo-selos">
                            <SeloFonte
                              origin={result.price_origin}
                              referenceMonth={
                                entryOfDigest(cascade, result.catalog_sha256)
                                  ?.reference_month
                              }
                              position={result.cascade_position}
                            />
                          </div>
                          <p className="codigo-descricao">{result.description}</p>
                          <button
                            type="button"
                            className="botao-secundario"
                            onClick={() =>
                              setCodeChoice({
                                code: result.code,
                                description: result.description,
                                unit: result.unit,
                                unit_price: result.unit_price,
                                catalogSha256: result.catalog_sha256,
                                priceOrigin: result.price_origin,
                                unit_compatible: null,
                              })
                            }
                          >
                            {escolhido ? "Escolhido" : "Escolher este código"}
                          </button>
                        </li>
                      );
                    })}
                  </ul>

                  <section className="pacote-do-item">
                    <h4>Pacote de serviços deste elemento</h4>
                    {pacoteDoItem.length === 0 ? (
                      <p className="campo-dica">
                        Nenhum código confirmado ainda. Um elemento pode disparar mais de um
                        serviço: confirme quantos forem e feche o pacote no fim.
                      </p>
                    ) : (
                      <>
                        {/* Estado em TEXTO, e não só em cor: pacote aberto é o que separa
                            "item resolvido" de "item pela metade". */}
                        <p className="campo-dica">
                          Pacote em aberto, com {pacoteDoItem.length}{" "}
                          {pacoteDoItem.length === 1 ? "serviço" : "serviços"}. Ele só conta
                          como resolvido depois do fechamento.
                        </p>
                        <ul className="lista-simples">
                          {pacoteDoItem.map((assignment) => (
                            <li key={assignment.code}>
                              <code>{assignment.code}</code>
                              {assignment.unit_compatible ? null : (
                                <span className="campo-aviso">
                                  {" "}
                                  unidade diferente da do elemento
                                </span>
                              )}
                            </li>
                          ))}
                        </ul>
                      </>
                    )}
                  </section>

                  {codeChoice !== null &&
                  codeChoice.unit.trim().toLowerCase() !==
                    itemPendente.unit.trim().toLowerCase() ? (
                    <p className="campo-aviso">
                      {unitMismatchHint(itemPendente.unit, codeChoice.unit)}
                    </p>
                  ) : null}

                  <label className="campo">
                    Nota da decisão
                    <span className="campo-dica">
                      Obrigatória na rejeição: é ela que registra por que nenhuma fonte
                      precifica o item. Opcional ao confirmar um código ou ao fechar o
                      pacote.
                    </span>
                    <textarea
                      value={codeNote}
                      onChange={(event) => setCodeNote(event.target.value)}
                    />
                  </label>
                  <div className="acoes-linha">
                    <button
                      type="button"
                      className="botao-primario"
                      onClick={() => void decidirCodigo("confirm")}
                      disabled={submitting || codeChoice === null}
                    >
                      Confirmar código
                    </button>
                    <button
                      type="button"
                      className="botao-secundario"
                      onClick={() => void decidirCodigo("reject")}
                      disabled={
                        submitting ||
                        codeNote.trim().length === 0 ||
                        pacoteDoItem.length > 0
                      }
                    >
                      Rejeitar com nota
                    </button>
                    <button
                      type="button"
                      className="botao-secundario"
                      onClick={() => void fecharPacote()}
                      disabled={submitting || pacoteDoItem.length === 0}
                    >
                      Fechar pacote de serviços
                    </button>
                  </div>
                </>
              )}
            </section>
          </div>
        ) : etapaVisivel === "montagem" ? (
          <div className="workspace duas-colunas">
            <div className="coluna-empilhada">
              <section className="painel" aria-label="BDI do orçamento">
                <div className="painel-cabecalho">
                  <h2>BDI</h2>
                </div>
                <form
                  className="formulario"
                  onSubmit={(event) => {
                    event.preventDefault();
                    void montarOrcamento();
                  }}
                >
                  <label className="campo">
                    Percentual de BDI
                    <span className="campo-dica">{DICA_BDI}</span>
                    <input
                      type="text"
                      inputMode="decimal"
                      value={bdiInput}
                      onChange={(event) => setBdiInput(event.target.value)}
                      aria-invalid={bdiErro !== null}
                      required
                    />
                  </label>
                  {bdiErro === null ? null : (
                    <p className="campo-erro" role="alert">
                      {bdiErro}
                    </p>
                  )}
                  <p className="dica">{AVISO_BDI}</p>
                  <p className="dica">{DESCRICAO_MONTAGEM}</p>
                  <div className="acoes-linha">
                    <button
                      type="submit"
                      className="botao-primario"
                      disabled={submitting || bdiPercentError(bdiInput) !== null}
                    >
                      {submitting ? "Montando…" : "Montar orçamento"}
                    </button>
                  </div>
                </form>
              </section>

              <PainelTetoDaVerba
                valor={tetoInput}
                rotulo={tetoLabelInput}
                versao={version}
                gravando={submitting}
                onValor={setTetoInput}
                onRotulo={setTetoLabelInput}
                onGravar={() => void gravarTeto()}
              />
            </div>

            <section className="painel" aria-label="Prévia do orçamento">
              <div className="painel-cabecalho">
                <h2>Prévia do orçamento</h2>
              </div>
              {estimate === null ? (
                <p className="dica">
                  Nenhum orçamento montado ainda: os totais aparecem aqui depois da
                  montagem, exatamente como o servidor os recomputou.
                </p>
              ) : (
                <ul className="confirmados-lista">
                  <li>
                    {estimate.estimate.lines.length} itens precificados ·{" "}
                    {estimate.unpriced_item_ids.length} sem preço
                  </li>
                  <li>
                    Total sem BDI ·{" "}
                    <span className="mono">
                      {formatMoneyText(estimate.total_amount_without_bdi)}
                    </span>
                  </li>
                  <li>
                    BDI ({formatPercentText(estimate.bdi_percent)}) ·{" "}
                    <span className="mono">
                      diferença entre os dois totais truncados
                    </span>
                  </li>
                  <li>
                    Total geral ·{" "}
                    <span className="mono">
                      {formatMoneyText(estimate.total_amount)}
                    </span>
                  </li>
                </ul>
              )}
              {/* Colado ao Total geral, porque o consumo é uma leitura dele. */}
              <BlocoConsumoDoTeto teto={tetoDerivado} />
            </section>
          </div>
        ) : (
          <div className="coluna-empilhada">
            {/*
              A etapa "Aprovação e despacho" SUBSTITUIU "Planilha" (F-035, ADR-0046 e a
              questão 1 do pacote aprovado): com a montagem deixando de publicar, a planilha
              passa a nascer do despacho, e uma etapa sobre um arquivo que ainda não existe
              não teria o que mostrar.
            */}
            <section
              className="painel"
              aria-label="Aprovação e despacho do orçamento"
            >
              <span className="eyebrow eyebrow-claro">
                APROVAÇÃO E DESPACHO
              </span>
              {estimate === null || aprovacao === null ? (
                <>
                  <h2>Nada a aprovar nesta rodada</h2>
                  <p className="dica">
                    O orçamento desta rodada ainda não foi montado ou não foi
                    lido. Monte-o na etapa “BDI e montagem”: aprovar decide
                    sobre o orçamento que existe, e não há o que decidir antes
                    dele.
                  </p>
                </>
              ) : (
                <>
                  <h2>
                    {despachando
                      ? "Publicando a planilha"
                      : tituloDaAprovacao(
                          aprovacao.approved,
                          aprovacao.stale,
                          estimate.workbook_present,
                        )}
                  </h2>
                  {/*
                    A frase é do estado 1 do desenho — montado e ainda não assinado. Na
                    caducidade ela não entra: ali o assunto é o que MUDOU depois da
                    assinatura, e repetir "foi montado e conferido" empurraria o registro
                    caduco para baixo com uma frase que já não é a notícia.
                  */}
                  {aprovacao.approved || aprovacao.stale ? null : (
                    <p>
                      O orçamento foi montado e conferido pelo domínio. A
                      planilha ainda não foi publicada: publicar é ato próprio,
                      e depende da assinatura.
                    </p>
                  )}
                  {/* A palavra é a marca do estado; a veste é redundância dela. */}
                  <SeloDespacho despachado={estimate.workbook_present} />
                  <p
                    className="dica"
                    title={aprovacao.current_digest ?? undefined}
                  >
                    Total {formatMoneyText(estimate.total_amount)} · BDI{" "}
                    {formatPercentText(estimate.bdi_percent)} · conteúdo{" "}
                    <span className="mono">
                      sha256 {shortDigest(aprovacao.current_digest)}
                    </span>
                  </p>

                  {aprovacao.stale ? (
                    <p className="banner-erro" role="alert">
                      {MENSAGEM_APROVACAO_CADUCA}
                    </p>
                  ) : null}

                  <RegistroDaAprovacao approval={aprovacao} />

                  {autoAprovacaoRecusada === null ? null : (
                    <PainelAutoAprovacaoRecusada
                      detalhe={autoAprovacaoRecusada}
                    />
                  )}

                  {semPapelDeAprovador === null ? null : (
                    <PainelSemPapelDeAprovador detalhe={semPapelDeAprovador} />
                  )}

                  {semPapelDeOrcamentista === null ? null : (
                    <PainelSemPapelDeOrcamentista
                      detalhe={semPapelDeOrcamentista}
                    />
                  )}

                  {violacoesDoDespacho === null ? null : (
                    <section
                      className="violacoes"
                      aria-label="Motivos abertos do portão de despacho"
                    >
                      <h3>O portão de despacho recusou — nada foi publicado</h3>
                      {violacoesDoDespacho.map((code) => (
                        <div key={code}>
                          <p className="banner-erro" role="alert">
                            {errorMessage(code)}
                          </p>
                          <p className="digest">{code}</p>
                        </div>
                      ))}
                    </section>
                  )}

                  {aprovacaoValida ? null : (
                    <AtoDeAprovacao
                      titulo={`Aprovar o orçamento${
                        state === null ? "" : ` de ${state.worksite_name}`
                      }`}
                      identidade={identidadeDaSessao}
                      contentDigest={aprovacao.current_digest}
                      confirmando={confirmandoAprovacao}
                      gravando={submitting}
                      onAprovar={() => setConfirmandoAprovacao(true)}
                      onConfirmar={() => void aprovarOrcamento()}
                      onCancelar={() => setConfirmandoAprovacao(false)}
                    />
                  )}

                  {aprovacaoValida ? (
                    <section
                      className="despacho"
                      aria-label="Despacho da planilha"
                    >
                      <h3>Despacho da planilha</h3>
                      {estimate.workbook_present ? (
                        <>
                          <div className="acoes-linha">
                            {estimate.workbook_url ? (
                              <a
                                className="botao-primario"
                                href={estimate.workbook_url}
                                download="orcamento.xlsx"
                              >
                                Baixar planilha
                              </a>
                            ) : null}
                            <button
                              type="button"
                              className="botao-secundario"
                              onClick={() => void despacharPlanilha()}
                              disabled={submitting || version === null}
                            >
                              {despachando
                                ? "Despachando…"
                                : "Despachar de novo"}
                            </button>
                          </div>
                          <p
                            className="digest"
                            title={estimate.workbook_sha256 ?? undefined}
                          >
                            planilha · sha256{" "}
                            {shortDigest(estimate.workbook_sha256)}
                          </p>
                          {/* O hint da tela 9 é este, e só este: o que o digest no
                              endereço do arquivo garante. Os dois avisos de ANTES do
                              clique não se repetem depois dele. */}
                          <p className="dica">
                            {AVISO_PLANILHA_ENDERECADA_PELO_DIGEST}
                          </p>
                          {estimate.workbook_url ? null : (
                            <p className="dica">
                              O link de download não veio nesta leitura;
                              recarregue o estado atual para pedir uma URL
                              assinada nova.
                            </p>
                          )}
                        </>
                      ) : (
                        <>
                          <p>Nenhuma planilha publicada nesta rodada.</p>
                          <div className="acoes-linha">
                            <button
                              type="button"
                              className="botao-primario"
                              onClick={() => void despacharPlanilha()}
                              disabled={submitting || version === null}
                            >
                              {despachando
                                ? "Despachando…"
                                : "Despachar: publicar a planilha"}
                            </button>
                          </div>
                        </>
                      )}
                      {despachando ? (
                        <ProgressoDoDespacho estado="em-voo" />
                      ) : null}
                      {estimate.workbook_present ? null : (
                        <>
                          <p className="dica">
                            {AVISO_ASSINAR_NAO_E_DESPACHAR}
                          </p>
                          <p className="dica">{AVISO_DESPACHO_FAIL_CLOSED}</p>
                        </>
                      )}
                    </section>
                  ) : (
                    <p className="dica">
                      Despachar é o passo depois de aprovar: sem aprovação
                      nominal válida o botão de publicar a planilha não aparece
                      aqui, e a rota recusaria de qualquer forma. A defesa é do
                      servidor; esta tela só a espelha.
                    </p>
                  )}
                </>
              )}
            </section>

            {/*
              O desenho aprovado não mostra a tabela, porque ele desenha o ATO. Ela fica: é
              o único lugar da jornada onde as linhas precificadas aparecem, e assinar sem
              poder ler o que se assina seria carimbo. Ela vem DEPOIS do ato, como conteúdo
              da assinatura e não como o assunto da etapa.
            */}
            {estimate === null ? null : (
              <section className="painel" aria-label="Linhas do orçamento">
                <div className="painel-cabecalho">
                  <h2>Linhas do orçamento</h2>
                </div>
                <table className="tabela">
                  <caption>
                    Linhas do orçamento como o servidor as recomputou; a tela não soma.
                  </caption>
                  <thead>
                    <tr>
                      <th>Item</th>
                      <th>Cód.</th>
                      <th>Fonte</th>
                      <th>Descrição</th>
                      <th>Un</th>
                      <th className="numero">Valor unit.</th>
                      <th className="numero">Valor unit. c/ BDI</th>
                      <th className="numero">Quant.</th>
                      <th className="numero">Total</th>
                    </tr>
                  </thead>
                  <tbody>
                    {estimate.estimate.lines.map((line) => (
                      <tr key={line.item_number}>
                        <td className="numero">{line.item_number}</td>
                        <td className="mono">{line.code}</td>
                        <td>
                          {priceSourceLabel(line.price_origin, line.reference_month)}
                        </td>
                        <td className="celula-descricao">{line.description}</td>
                        <td>{unitLabel(line.unit)}</td>
                        <td className="numero">{formatDecimalText(line.unit_price)}</td>
                        <td className="numero">
                          {formatDecimalText(line.unit_price_with_bdi)}
                        </td>
                        <td className="numero">{formatDecimalText(line.quantity)}</td>
                        <td className="numero">{formatDecimalText(line.total)}</td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr>
                      <td colSpan={8}>Total sem BDI</td>
                      <td className="numero">
                        {formatDecimalText(estimate.total_amount_without_bdi)}
                      </td>
                    </tr>
                    <tr>
                      <td colSpan={8}>
                        Total geral (BDI {formatPercentText(estimate.bdi_percent)})
                      </td>
                      <td className="numero">
                        {formatDecimalText(estimate.total_amount)}
                      </td>
                    </tr>
                  </tfoot>
                </table>

                {estimate.unpriced_item_ids.length === 0 ? null : (
                  <div className="confirmados">
                    <h3>Itens sem preço na cascata</h3>
                    <p className="dica">{AVISO_SEM_PRECO}</p>
                    <ul className="confirmados-lista">
                      {estimate.unpriced_item_ids.map((itemId) => (
                        <li key={itemId} className="mono">
                          {itemId}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                <p className="digest" title={estimate.estimate_sha256}>
                  documento gravado {shortDigest(estimate.estimate_sha256)}
                </p>
              </section>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
