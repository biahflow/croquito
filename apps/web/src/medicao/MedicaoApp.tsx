import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from "react";
import type { User } from "oidc-client-ts";
import type { CodeAssignmentSet, CodeSuggestionSet } from "@croquito/contracts";

import {
  ApiError,
  appendPlates,
  associatePlate,
  createPlateExtraction,
  createPlatesExtraction,
  createRound,
  declareIdentityLink,
  getBulletin,
  getCodes,
  getDossier,
  getPlate,
  getRoundState,
  getSuggestions,
  getTakeoff,
  getTakeoffOverlay,
  getWorksite,
  listRounds,
  listValuationOrigins,
  postApprove,
  postBulletinExport,
  postCalcBuild,
  postCodeClosure,
  postCodeRevocation,
  postCodeDecision,
  postDivergenceResolution,
  postDossierBuild,
  postSceneLink,
  postSceneQuantities,
  postSuggestionsRecompute,
  postTakeoffDecision,
  previewIdentityLink,
  searchCatalog,
  uploadCatalog,
  uploadPlateFile,
  type ApprovalState,
  type BulletinResponse,
  type CatalogSearchResponse,
  type CodesResponse,
  type DossierResponse,
  type IdentityLinkPreviewResponse,
  type OverlayResponse,
  type RoundState,
  type RoundStateExtraction,
  type RoundSummary,
  type SuggestionsResponse,
  type TakeoffItem,
  type TakeoffItemAddress,
  type TakeoffResponse,
  type PlateResponse,
  type ValuationOrigin,
  type PriceAdjustmentDraft,
  type AmendmentDraft,
  type WorksiteResponse,
  type WorksiteSheet,
} from "./api";
import {
  divergenciaAberta,
  divergenciaDoItem,
  divergenciaResolvida,
  frasePorFaltaDePar,
  itensComDivergenciaAberta,
  motivoDeBloqueio,
  numeroEscolhido,
  numeroPreterido,
  vemDaCena,
  type DivergenceChoice,
  type SceneConfrontationReport,
  type SceneLinkState,
} from "./cena";
import { signOut } from "../auth";
import {
  abrirDesfazer,
  desfazerDoItem,
  desfeitosDoItem,
  pacoteFechado,
  pedidoDeDesfazer,
  podeDesfazer,
  type CaixaDeDesfazer,
  type CodigoDesfeito,
} from "../codeRevocation";
import { BUSCA_DEBOUNCE_MS, consultaIncremental, resumoDaBusca } from "./busca";
import {
  BOLETIM_VENCIDO,
  REMONTAR_CADUCA_A_APROVACAO,
  derivarEtapas,
  etapaStatusLabel,
  type Etapa,
  type EtapaId,
} from "./etapas";
import {
  avisoDoLoteDePromocao,
  boletimDaFolha,
  chaveDoBoletimDaFolha,
  codificacaoDasFolhas,
  estadoDaFolha,
  folhaDaChamada,
  folhaEmFoco,
  folhaLabel,
  folhasQueAindaCabem,
  memoriaDaFolha,
  paginasPromovidas,
  pracaPlural,
  recusaDaPraca,
  recusaDoVinculo,
  resumoDaCodificacao,
  resumoDaFolha,
  rotuloDoLoteDeExtracao,
  rotuloDoLoteDePromocao,
} from "./praca";
import {
  describeError,
  exportBlockedViolations,
  isAbortError,
  isForbidden,
  recusaDeMutacao,
  workbookAuditFindings,
  type ExportViolation,
} from "./errors";
import { classifyExecucao } from "./execucao";
import { overlayFreshness } from "./images";
import { extractInclusoes, type Inclusao } from "./inclusoes";
import {
  formatDecimalText,
  formatMoneyText,
  formatQuantityText,
  formatTimestamp,
  parseQuantityInput,
  shortDigest,
} from "./format";
import {
  assignmentStatusLabel,
  AVISO_ADITIVO,
  AVISO_DOSSIE_GERADO,
  AVISO_DOSSIE_PREVIA,
  AVISO_EXPORTACAO_FAIL_CLOSED,
  AVISO_LOCALIZACAO_NAO_CONFIRMADA,
  AVISO_DIVERGENCIA_ABERTA,
  AVISO_MEDICAO,
  AVISO_QUANTIDADE_AMBIGUA,
  DESCRICAO_CALCULO_SHORTLIST,
  DESFAZER_AVISO_PACOTE_FECHADO,
  DESFAZER_BOTAO,
  DESFAZER_CANCELAR,
  DESFAZER_MOTIVO_LABEL,
  DESFAZER_NAO_BANE,
  DESFEITOS_TITULO,
  DESFEITO_SELO,
  DICA_QUANTIDADE,
  fraseDesfazerConfirmar,
  fraseDesfazerTitulo,
  fraseDesfeitoGravado,
  frasesEfeitoDesfazer,
  errorMessage,
  extractionFailureMessage,
  extractionStatusLabel,
  itemStatusLabel,
  MENSAGEM_APROVACAO_CADUCA,
  MENSAGEM_AUDITORIA_REPROVADA,
  MENSAGEM_MEDICAO_APROVADA,
  MENSAGEM_RODADA_MUDOU,
  MENSAGEM_SEM_ACESSO,
  originSignatureHint,
  originSignatureLabel,
  recipeLabel,
  stageLabel,
  unitLabel,
  unitMismatchHint,
  violationDetailLine,
  divergenceChoiceLabel,
  FORMULA_DA_TOLERANCIA,
  precisionLabel,
  quantitySourceLabel,
  RAZAO_SEM_CAMPO_DE_QUANTIDADE,
  RAZAO_SEM_TERCEIRA_ESCOLHA,
  sceneOutcomeLabel,
  sceneReasonLabel,
} from "./labels";
import { DICA_NOME_DA_OBRA, codeSearchTerm, worksiteKeyError } from "./requests";
import { DICA_FATOR, REAJUSTE_OPCOES, reajusteIssue } from "./reajuste";
import { DICA_DELTA, reRaIssue } from "./reratificacao";
import { itemAnchor } from "./takeoff";
import {
  bboxRect,
  clampZoom,
  MAX_ZOOM,
  MIN_ZOOM,
  panScrollOffset,
  PIN_DIAMETER_PX,
  pinPlacement,
  stageStyle,
  zoomAfterWheel,
  ZOOM_STEP,
  type PanOrigin,
} from "./viewport";

/** Duração do aviso de sucesso; recusa nenhuma expira sozinha. */
const TOAST_MS = 5000;

/** Intervalo do poll do estado enquanto a leitura automática está na fila ou rodando. */
const EXTRACTION_POLL_MS = 3000;

/** Intervalo do poll do overlay enquanto ele está vencido (ADR-0030). */
const OVERLAY_POLL_MS = 3000;

/**
 * Teto de tentativas do poll do overlay. Ele existe porque overlay vencido NÃO é erro: sem
 * worker consumindo a fila o desenho fica vencido para sempre, e uma tela que consultasse
 * o servidor a cada três segundos indefinidamente esconderia esse fato atrás de tráfego.
 * Atingido o teto, a marca continua na tela e a atualização passa a ser um gesto.
 */
const OVERLAY_POLL_MAX = 10;

type DecisionAction = "" | "confirm" | "reject";

type CodeChoice = {
  code: string;
  description: string;
  unit: string;
  unit_price: string;
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

const EMPTY_ROUND_FORM = {
  worksiteKey: "",
  worksiteName: "",
  periodNumber: "",
  referenceLabel: "",
  address: "",
  contractLabel: "",
};

/**
 * A escolha do orçamento assinado que vai originar a medição (F-036, ADR-0048).
 *
 * Três estados, e nenhum deles inventa o outro: `null` é "ainda lendo", lista vazia é "não
 * há", e a lista traz também os orçamentos que ainda não servem — com o motivo por extenso,
 * porque quem procura um orçamento que sabe existir precisa achá-lo e entender.
 *
 * Obra, catálogo e contratado aparecem como procedência LIDA, nunca como campo: é a tradução
 * visual da regra de que nenhum número do consolidado é informado por humano.
 */
export function OrigemDoOrcamento({
  origens,
  escolhida,
  onEscolher,
}: {
  origens: ValuationOrigin[] | null;
  escolhida: string | null;
  onEscolher: (roundId: string) => void;
}) {
  if (origens === null) {
    return <p className="campo-dica">Lendo os orçamentos assinados…</p>;
  }
  if (origens.length === 0) {
    return (
      <p className="campo-dica">
        Nenhum orçamento assinado sob demanda contratada neste cliente. Uma medição aberta
        do zero funciona como hoje — ela só não confere contra contratado nenhum, e a rodada
        dirá isso.
      </p>
    );
  }
  const selecionada = origens.find((origem) => origem.round_id === escolhida) ?? null;
  return (
    <>
      <div className="campo">
        <span>Orçamento assinado</span>
        <ul className="origem-lista">
          {origens.map((origem) => {
            const disponivel = origem.signature === "signed";
            const motivo = originSignatureHint(origem.signature);
            return (
              <li
                key={origem.round_id}
                className="origem-item"
                data-escolhido={origem.round_id === escolhida ? "sim" : "nao"}
                data-disponivel={disponivel ? "sim" : "nao"}
              >
                <input
                  type="radio"
                  name="orcamento-de-origem"
                  checked={origem.round_id === escolhida}
                  disabled={!disponivel}
                  onChange={() => onEscolher(origem.round_id)}
                  aria-label={`${origem.worksite_name} — ${origem.reference_label}`}
                />
                <span className="origem-corpo">
                  <span className="origem-titulo">
                    <strong>
                      {origem.worksite_name} — {origem.reference_label}
                    </strong>
                    <span
                      className={`selo ${disponivel ? "selo-ok" : "selo-atencao"}`}
                    >
                      {originSignatureLabel(origem.signature)}
                    </span>
                    <span className="selo selo-neutro">Demanda sob contrato</span>
                  </span>
                  <span className="campo-dica">
                    {origem.approved_by === null
                      ? `${origem.code_count} códigos · ${formatMoneyText(origem.total_amount)}`
                      : `Assinado por ${origem.approved_by}${
                          origem.approved_at === null
                            ? ""
                            : ` em ${formatTimestamp(origem.approved_at)}`
                        } · ${origem.code_count} códigos · ${formatMoneyText(origem.total_amount)}`}
                  </span>
                  {origem.estimate_digest === null ? null : (
                    <span className="digest">
                      digest {shortDigest(origem.estimate_digest)}
                    </span>
                  )}
                  {motivo === null ? null : (
                    <span className="campo-aviso">{motivo}</span>
                  )}
                </span>
              </li>
            );
          })}
        </ul>
      </div>
      {selecionada === null ? null : (
        <>
          <dl className="procedencia">
            <div>
              <dt>Obra</dt>
              <dd>{selecionada.worksite_name}</dd>
            </div>
            <div>
              <dt>Catálogo</dt>
              <dd>o mesmo do orçamento</dd>
            </div>
            <div>
              <dt>Contratado</dt>
              <dd>
                {selecionada.code_count} códigos ·{" "}
                {formatMoneyText(selecionada.total_amount)}
              </dd>
            </div>
            <div>
              <dt>Saldo inicial</dt>
              <dd>igual ao contratado</dd>
            </div>
          </dl>
          <p className="campo-dica">
            A obra, o catálogo e o contratado vêm do orçamento assinado e não são digitados
            aqui. O que a rodada ainda precisa é o número da medição e a referência.
          </p>
        </>
      )}
    </>
  );
}

/**
 * Contra o que esta rodada confere (F-036, ADR-0048 decisão 9).
 *
 * As duas variantes são o MESMO lugar da tela dizendo coisas opostas, e é essa a exigência
 * do ADR: rodada com vínculo e rodada sem vínculo têm garantias diferentes e não podem
 * parecer iguais. A ausência de contratado é DECLARADA, não deduzida de um campo que some —
 * quem lê precisa saber que ali não se confere saldo, e não descobrir isso por omissão.
 */
export function RegimeDeConferencia({
  contracted,
}: {
  contracted: RoundState["contracted"];
}) {
  if (contracted.origin !== "signed_estimate") {
    return (
      <p className="aviso-fixo aviso-inline" role="alert">
        <span className="selo selo-neutro">Sem contratado de origem</span> Esta rodada não
        foi aberta a partir de um orçamento assinado. Ela confere o boletim contra o catálogo
        instalado, e não contra um contratado: saldo, período e código fora do contrato não
        são verificados aqui.
      </p>
    );
  }
  const codigos = contracted.code_count;
  return (
    <div className="decisao-registrada">
      <p>
        <span className="selo selo-ok">Confere contra o orçamento assinado</span> O
        contratado desta medição vem de um orçamento assinado
        {codigos === undefined || codigos === null ? "" : `, com ${codigos} códigos`}. Código
        fora do contratado, quantidade acima do saldo ou preço diferente do assinado recusam
        o fechamento desta medição.
      </p>
      {contracted.estimate_digest === null ? null : (
        <p className="digest" title={contracted.estimate_digest}>
          digest do conteúdo assinado {shortDigest(contracted.estimate_digest)}
        </p>
      )}
      <ReajusteDeclarado contracted={contracted} />
      <ReRatificacaoDeclarada contracted={contracted} />
    </div>
  );
}

/**
 * A RE-RA do contrato, e a conta de QUANTIDADE que ela produz (F-040, ADR-0056).
 *
 * Espelho de `ReajusteDeclarado`: não aparece sem re-ratificação — a ausência já está
 * declarada na resposta, e a tela não precisa falar dela. O vigente aparece como resultado de
 * uma conta visível (contratado → vigente), nunca como um número escrito à parte: é a decisão
 * 3 do ADR-0056 tornada impossível de contornar pela interface. A cor nunca é o único
 * indicador — o selo diz "re-ratificada" por escrito (decisão 9 do pacote de design).
 */
export function ReRatificacaoDeclarada({
  contracted,
}: {
  contracted: RoundState["contracted"];
}) {
  const declaradas = contracted.amendments ?? [];
  if (declaradas.length === 0) {
    return null;
  }
  const reRatificados = (contracted.quantities ?? []).filter((q) => q.re_ratified);
  return (
    <div className="rera-declarada">
      {declaradas.map((rera, indice) => (
        <p key={`${rera.declared_at ?? rera.label}-${indice}`} className="rera-linha">
          <span className="selo selo-rera">re-ratificada</span>{" "}
          {rera.label}
          {rera.reference_period ? ` · ${rera.reference_period}` : ""}{" "}
          {rera.declared_by ? (
            <span className="rera-autoria">declarada por {rera.declared_by}</span>
          ) : null}
        </p>
      ))}
      {reRatificados.length === 0 ? null : (
        <table className="rera-tabela">
          <thead>
            <tr>
              <th>Item</th>
              <th>Descrição</th>
              <th className="numero">Contratado</th>
              <th className="numero">Vigente</th>
              <th className="numero">Saldo</th>
            </tr>
          </thead>
          <tbody>
            {reRatificados.map((q) => (
              <tr key={q.code}>
                <td>{q.item_number}</td>
                <td>{q.description}</td>
                <td className="numero">{q.contracted_quantity}</td>
                <td className="numero">{q.current_quantity}</td>
                <td className="numero">{q.current_balance_quantity}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="dica">
        A quantidade vigente é derivada do contratado pela declaração acima. Período já medido
        guarda a quantidade que valeu nele.
      </p>
    </div>
  );
}

const RERA_LINHA_VAZIA = { code: "", quantityDelta: "" };
const RERA_DRAFT_VAZIO: AmendmentDraft = {
  label: "",
  referencePeriod: "",
  lines: [RERA_LINHA_VAZIA],
};

/**
 * A declaração da RE-RA na abertura (F-040), isolada em componente próprio: a lista de linhas
 * é dinâmica, e mantê-la aqui deixa a forma testável fora do App inteiro.
 *
 * `null` é "sem RE-RA" e é o padrão — não re-ratificar é o caminho normal. O item novo não
 * informa preço: o servidor o materializa do catálogo contratual (ADR-0056, decisão 7).
 */
export function ReRatificacaoFieldset({
  value,
  onChange,
}: {
  value: AmendmentDraft | null;
  onChange: (value: AmendmentDraft | null) => void;
}) {
  const ativo = value !== null;
  const draft = value ?? RERA_DRAFT_VAZIO;
  const set = (patch: Partial<AmendmentDraft>) => onChange({ ...draft, ...patch });
  const setLinha = (indice: number, patch: Partial<(typeof draft.lines)[number]>) =>
    set({
      lines: draft.lines.map((linha, j) => (j === indice ? { ...linha, ...patch } : linha)),
    });
  return (
    <fieldset className="rera-do-contrato">
      <legend>Re-ratificação (RE-RA)</legend>
      <p className="dica">
        A RE-RA vale deste período em diante. Período já aprovado não é reescrito, e o vigente
        é derivado do contratado mais o efeito declarado.
      </p>
      <label className="rera-toggle">
        <input
          type="checkbox"
          checked={ativo}
          onChange={(event) => onChange(event.target.checked ? draft : null)}
        />
        Declarar uma RE-RA nesta abertura
      </label>
      {!ativo ? null : (
        <div className="rera-campos">
          <label>
            Nome curto
            <input
              value={draft.label}
              onChange={(event) => set({ label: event.target.value })}
              placeholder="1ª RE-RA"
            />
          </label>
          <label>
            Processo ou publicação
            <input
              value={draft.referencePeriod}
              onChange={(event) => set({ referencePeriod: event.target.value })}
              placeholder="Processo 123/2026"
            />
          </label>
          {draft.lines.map((linha, indice) => (
            <div key={indice} className="rera-linha-campos">
              <input
                aria-label={`Código da linha ${indice + 1}`}
                value={linha.code}
                onChange={(event) => setLinha(indice, { code: event.target.value })}
                placeholder="CE04100010(/)"
              />
              <input
                aria-label={`Efeito da linha ${indice + 1}`}
                value={linha.quantityDelta}
                onChange={(event) => setLinha(indice, { quantityDelta: event.target.value })}
                placeholder="-4 ou +6"
              />
              <label className="rera-item-novo">
                <input
                  type="checkbox"
                  checked={linha.isNewItem ?? false}
                  onChange={(event) => setLinha(indice, { isNewItem: event.target.checked })}
                />
                item novo
              </label>
              {draft.lines.length > 1 ? (
                <button
                  type="button"
                  className="rera-remover"
                  onClick={() =>
                    set({ lines: draft.lines.filter((_, j) => j !== indice) })
                  }
                >
                  remover
                </button>
              ) : null}
            </div>
          ))}
          <button
            type="button"
            className="rera-adicionar"
            onClick={() => set({ lines: [...draft.lines, { ...RERA_LINHA_VAZIA }] })}
          >
            adicionar código
          </button>
          <p className="dica">
            {DICA_DELTA} Item novo não informa preço — o servidor o materializa do catálogo
            contratual.
          </p>
        </div>
      )}
    </fieldset>
  );
}

/**
 * O reajuste do contrato, e a conta que ele produz (F-039).
 *
 * Não aparece quando não há reajuste: rodada sem declaração imprime o que sempre imprimiu, e
 * uma seção vazia dizendo "sem reajuste" empurraria o assunto para quem não tem esse assunto.
 * A ausência já está declarada na resposta — a tela é que não precisa falar dela.
 */
export function ReajusteDeclarado({
  contracted,
}: {
  contracted: RoundState["contracted"];
}) {
  const declarados = contracted.price_adjustments ?? [];
  if (declarados.length === 0) {
    return null;
  }
  const reajustados = (contracted.prices ?? []).filter((preco) => preco.adjusted);
  return (
    <div className="reajuste-declarado">
      {declarados.map((reajuste, indice) => (
        <p key={`${reajuste.declared_at}-${indice}`} className="reajuste-linha">
          <span className="selo selo-reajuste">reajustado</span>{" "}
          {reajuste.kind === "index_factor"
            ? `${reajuste.index_label} · ${reajuste.reference_period} · fator ${reajuste.factor}`
            : `${reajuste.catalog_label} · ${reajuste.reference_period}`}{" "}
          <span className="reajuste-autoria">
            declarado por {reajuste.declared_by}
          </span>
        </p>
      ))}
      {reajustados.length === 0 ? null : (
        <table className="reajuste-tabela">
          <thead>
            <tr>
              <th>Item</th>
              <th>Descrição</th>
              <th className="numero">Contratado</th>
              <th className="numero">Vigente</th>
            </tr>
          </thead>
          <tbody>
            {reajustados.map((preco) => (
              <tr key={preco.code}>
                <td>{preco.item_number}</td>
                <td>{preco.description}</td>
                <td className="numero">{preco.contracted_unit_price}</td>
                <td className="numero">{preco.current_unit_price}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="dica">
        O preço vigente é derivado do contratado pela declaração acima. Período já medido
        guarda o valor que valeu nele.
      </p>
    </div>
  );
}

/**
 * Leitura OBSERVACIONAL: a falha dela não derruba o carregamento da rodada.
 *
 * Vale só para a imagem da prancha e para o overlay das âncoras — os dois ilustram o que
 * já foi decidido e não decidem nada. A ausência de qualquer um deles é declarada na tela
 * ("imagem ainda não publicada", "sem desenho publicado"), então engolir a recusa aqui não
 * esconde estado nenhum; o que ela evita é uma rodada inteira ficar sem boletim e sem
 * dossiê na tela porque um PNG não estava publicado. Decisão, artefato e contagem nunca
 * passam por aqui.
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

/** Confirmado e com código — o único caso em que faz sentido buscar a descrição dele. */
/**
 * A caixa de desfazer um código confirmado (F-045, pacote de design revisão 2).
 *
 * Gêmea da do orçamento-base, e de propósito: é o mesmo ato, na mesma etapa, e duas formas
 * criariam dois vocabulários para a mesma coisa. A diferença está na copy — aqui não há a
 * linha do precedente, porque o índice é da pré-licitação e prometê-lo aqui seria falso.
 */
export function CaixaDeDesfazerCodigo({
  caixa,
  pacoteFechado: fechado,
  submitting,
  onChange,
  onDesfazer,
  onCancelar,
}: {
  caixa: CaixaDeDesfazer | null;
  pacoteFechado: boolean;
  submitting: boolean;
  onChange: (caixa: CaixaDeDesfazer) => void;
  onDesfazer: () => void;
  onCancelar: () => void;
}) {
  if (caixa === null) {
    return null;
  }
  return (
    <section className="desfazer-caixa" aria-label={fraseDesfazerTitulo(caixa.code)}>
      <h4>{fraseDesfazerTitulo(caixa.code)}</h4>
      <div className="campo">
        <label htmlFor="desfazer-motivo">{DESFAZER_MOTIVO_LABEL}</label>
        <textarea
          id="desfazer-motivo"
          value={caixa.motivo}
          onChange={(event) => onChange({ ...caixa, motivo: event.target.value })}
          maxLength={500}
          rows={3}
        />
      </div>
      {fechado ? <p className="aviso-atencao">{DESFAZER_AVISO_PACOTE_FECHADO}</p> : null}
      <p className="dica">O que este clique faz:</p>
      <ul className="lista-simples">
        {frasesEfeitoDesfazer(caixa.code).map((frase) => (
          <li key={frase}>{frase}</li>
        ))}
      </ul>
      <div className="acoes">
        <button
          type="button"
          className="botao-secundario"
          onClick={onCancelar}
          disabled={submitting}
        >
          {DESFAZER_CANCELAR}
        </button>
        <button
          type="button"
          className="botao-secundario"
          onClick={onDesfazer}
          disabled={submitting || !podeDesfazer(caixa)}
        >
          {fraseDesfazerConfirmar(fechado)}
        </button>
      </div>
      <p className="dica">{DESFAZER_NAO_BANE}</p>
    </section>
  );
}

/**
 * O que foi desfeito e continua desfeito, no próprio item (F-045).
 *
 * Lista vazia não desenha nada. Ela existe porque "nunca decidido" e "decidido e desfeito"
 * produzem a mesma ausência de código, e quem revisa a medição precisa distinguir os dois
 * sem comparar revisões.
 */
export function ListaDeDesfeitos({
  desfeitos,
}: {
  desfeitos: readonly CodigoDesfeito[];
}) {
  if (desfeitos.length === 0) {
    return null;
  }
  return (
    <section className="desfeitos" aria-label={DESFEITOS_TITULO}>
      <h4>{DESFEITOS_TITULO}</h4>
      <ul className="lista-simples">
        {desfeitos.map((desfeito) => (
          <li key={desfeito.revocation_id}>
            <code className="codigo-desfeito">{desfeito.code}</code>{" "}
            <span className="selo selo-neutro">{DESFEITO_SELO}</span>{" "}
            <span className="dica">
              “{desfeito.note}” · {desfeito.reviewer_id}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function isConfirmedWithCode(
  assignment: CodeAssignmentSet.CodeAssignment,
): assignment is CodeAssignmentSet.CodeAssignment & { code: string } {
  return (
    assignment.status === "confirmed" &&
    typeof assignment.code === "string" &&
    assignment.code.length > 0
  );
}

/** Unidades divergem? A resposta do servidor manda; a comparação textual é o fallback. */
function unidadesDivergem(itemUnit: string, choice: CodeChoice): boolean {
  if (choice.unit_compatible !== null) {
    return !choice.unit_compatible;
  }
  return itemUnit.trim().toLowerCase() !== choice.unit.trim().toLowerCase();
}

/** Selo de leitura da descrição; o `title` carrega a explicação da heurística. */
function SeloExecucao({ description }: { description: string }) {
  const hint = classifyExecucao(description);
  return (
    <span className={`selo selo-${hint.kind}`} title={hint.explanation}>
      {hint.label}
    </span>
  );
}

/** Tamanho de leitura de relance; trunca só a exibição — o dado (`title`, expandir) fica inteiro. */
const CHIP_TRUNCATE_LENGTH = 90;

function truncarChip(text: string): { curto: string; truncado: boolean } {
  if (text.length <= CHIP_TRUNCATE_LENGTH) {
    return { curto: text, truncado: false };
  }
  return { curto: `${text.slice(0, CHIP_TRUNCATE_LENGTH).trimEnd()}…`, truncado: true };
}

/**
 * Chip de inclusão/exclusão: citação literal do catálogo (`inclusoes.ts`), nunca só
 * cor — o prefixo por extenso ("Inclui:"/"Não inclui:") acompanha sempre o texto. Texto
 * longo trunca só na exibição; `title` e o clique (`<details>`) sempre dão acesso ao
 * texto inteiro.
 */
function ChipInclusao({
  prefixo,
  texto,
  tom,
}: {
  prefixo: string;
  texto: string;
  tom: "inclui" | "nao_inclui";
}) {
  const { curto, truncado } = truncarChip(texto);
  if (!truncado) {
    return (
      <span className={`chip chip-${tom}`} title={texto}>
        {prefixo} {texto}
      </span>
    );
  }
  return (
    <details className={`chip chip-${tom} chip-expansivel`}>
      <summary title={texto}>
        {prefixo} {curto}
      </summary>
      <p className="chip-texto-completo">{texto}</p>
    </details>
  );
}

/**
 * Linha de chips do que a descrição diz que inclui/não inclui, extraída por
 * `extractInclusoes`. Sem marcador conhecido, não mostra a seção — nunca inventa leitura.
 */
function Inclusoes({ description }: { description: string }) {
  const inclusoes = useMemo(() => extractInclusoes(description), [description]);
  if (inclusoes.length === 0) {
    return null;
  }
  return (
    <div
      className="inclusoes-lista"
      aria-label="O que a descrição diz que inclui ou não inclui"
    >
      {inclusoes.map((item: Inclusao, index) =>
        item.kind === "so_fornecimento" ? (
          <span key={index} className="chip chip-so-fornecimento">
            somente fornecimento — execução fora deste código
          </span>
        ) : (
          <ChipInclusao
            key={index}
            prefixo={item.kind === "inclui" ? "Inclui:" : "Não inclui:"}
            texto={item.text}
            tom={item.kind}
          />
        ),
      )}
    </div>
  );
}

function CartaoCodigo({
  code,
  description,
  unit,
  unitPrice,
  score,
  inContract,
  unitCompatible,
  selected,
  onChoose,
}: {
  code: string;
  description: string;
  unit: string;
  unitPrice: string;
  score: number | null;
  inContract: boolean | null;
  unitCompatible: boolean | null;
  selected: boolean;
  onChoose: () => void;
}) {
  return (
    <li className={`codigo-card ${selected ? "escolhido" : ""}`}>
      <div className="codigo-topo">
        <span className="codigo-code">{code}</span>
        <span className="codigo-preco">
          {formatMoneyText(unitPrice)} / {unitLabel(unit)}
        </span>
      </div>
      {/* Descrição inteira, com rolagem própria: cortá-la esconderia justamente a
          diferença entre fornecer e executar. */}
      <p className="codigo-descricao">{description}</p>
      <div className="codigo-selos">
        <SeloExecucao description={description} />
        {unitCompatible === null ? null : (
          <span className={`selo ${unitCompatible ? "selo-ok" : "selo-atencao"}`}>
            {unitCompatible ? "unidade compatível" : "unidade diferente da do item"}
          </span>
        )}
        {inContract === null ? null : (
          <span className={`selo ${inContract ? "selo-ok" : "selo-atencao"}`}>
            {inContract ? "no contrato" : "fora do contrato"}
          </span>
        )}
        {score === null ? null : (
          <span className="selo selo-neutro">
            afinidade lexical {score.toFixed(2).replace(".", ",")}
          </span>
        )}
      </div>
      <Inclusoes description={description} />
      <button type="button" className="botao-secundario" onClick={onChoose}>
        {selected ? "Escolhido" : "Escolher este código"}
      </button>
    </li>
  );
}

/**
 * Estado da leitura automática da legenda na etapa "Prancha". `done` fica discreto;
 * `queued`/`running`/`failed` ganham mais destaque, porque são os estados em que o
 * orçamentista precisa agir ou esperar. A frase da falha é escrita a partir do
 * `failure_code` estável da rodada — a API não manda mensagem pronta, e inventar uma sem
 * código seria pior do que dizer o que se sabe.
 *
 * `porFolha` é a praça plural: ali o disparo singular **não é oferecido**, porque a rota
 * singular relê sempre a PRIMEIRA folha — numa praça de N folhas ele seria uma chamada
 * paga na prancha errada. O caminho certo é o lote, que nomeia as folhas e escreve no
 * botão quantas chamadas pagas ele dispara.
 */
function EstadoExtracao({
  extraction,
  onRetry,
  retrying,
  porFolha = false,
}: {
  extraction: RoundStateExtraction;
  onRetry: () => void;
  retrying: boolean;
  porFolha?: boolean;
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
          {porFolha ? (
            <p className="dica">
              Nesta praça a releitura é por folha, no lote abaixo: ele nomeia quais folhas
              vão para a leitura e escreve no botão quantas chamadas pagas o ato dispara.
            </p>
          ) : (
            <button
              type="button"
              className="botao-secundario"
              onClick={onRetry}
              disabled={retrying}
            >
              Tentar leitura novamente
            </button>
          )}
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
          {porFolha ? (
            <p className="dica">
              Nesta praça a leitura é por folha, no lote abaixo.
            </p>
          ) : (
            <button
              type="button"
              className="botao-secundario"
              onClick={onRetry}
              disabled={retrying}
            >
              Disparar leitura automática
            </button>
          )}
        </>
      )}
    </div>
  );
}

/**
 * Overlay das âncoras: o desenho que o worker publica sobre a prancha, com a IDADE dele
 * declarada em palavra (ADR-0030).
 *
 * Ele é reconstruído fora do request path, por comando de fila: entre a decisão do
 * orçamentista e o desenho novo, o que está aqui é do pacote anterior. Marcá-lo é melhor
 * do que escondê-lo — um desenho vencido engana com a autoridade de um desenho —, e a
 * marca é texto no `summary`, não só a borda tracejada.
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
 * A etiqueta da identidade de elemento, ou a ausência dela dita por escrito (F-047).
 *
 * Espelha `.etiqueta-elemento` da jornada do croqui na FORMA — monoespaçada, cantos
 * quadrados —, porque é a mesma coisa nas duas telas e ler as duas como coisas diferentes
 * seria pior. A ausência é tracejada E diz "sem identidade": ausência é estado, nunca um
 * campo que some.
 */
export function EtiquetaDeElemento({ elementRef }: { elementRef?: string | null }) {
  if (!elementRef) {
    return (
      <span className="etiqueta-elemento etiqueta-elemento-ausente">
        — sem identidade
      </span>
    );
  }
  return <span className="etiqueta-elemento">◇ {elementRef}</span>;
}

/**
 * O elo declarado entre esta rodada e o croqui aprovado que a alimenta (F-047 T4b).
 *
 * Duas variantes do MESMO lugar da tela, e a diferença entre elas é o ponto: rodada sem elo
 * é rodada em que a quantidade continua vindo da legenda lida, exatamente como antes desta
 * feature, e isso é dito — não deduzido de um bloco que sumiu.
 *
 * O elo cita o EXPORT, e não só o job: o `quantitativos.csv` é conteúdo de um pacote
 * publicado a partir de uma revisão aprovada específica. Por isso a tela mostra os três
 * identificadores e o digest do DXF auditado: quem confere a medição meses depois precisa
 * saber QUAL desenho a alimentou.
 */
export function EloComOCroqui({
  link,
  jobId,
  onJobIdChange,
  onDeclarar,
  onConfrontar,
  submitting,
  confrontoDisponivel,
}: {
  link: SceneLinkState;
  jobId: string;
  onJobIdChange: (value: string) => void;
  onDeclarar: () => void;
  onConfrontar: () => void;
  submitting: boolean;
  confrontoDisponivel: boolean;
}) {
  return (
    <div className="elo-croqui">
      <h3>Croqui aprovado desta rodada</h3>
      {link.present ? (
        <>
          <p className="elo-linha">
            <span className="selo selo-cena">◇ croqui declarado</span> A quantidade desta
            rodada pode nascer da cena aprovada, sem ninguém redigitar.
          </p>
          <dl className="procedencia">
            <div>
              <dt>Croqui</dt>
              <dd className="mono">{link.job_id}</dd>
            </div>
            <div>
              <dt>Revisão da cena</dt>
              <dd className="mono">{link.scene_revision_id}</dd>
            </div>
            <div>
              <dt>Pacote publicado</dt>
              <dd className="mono">{link.export_id}</dd>
            </div>
            <div>
              <dt>DXF auditado</dt>
              <dd className="digest" title={link.dxf_sha256 ?? undefined}>
                {link.dxf_sha256 === null
                  ? "não declarado por este pacote"
                  : `sha256 ${shortDigest(link.dxf_sha256)}`}
              </dd>
            </div>
            <div>
              <dt>Declarado por</dt>
              <dd>
                {link.declared_by} em {formatTimestamp(link.declared_at)}
              </dd>
            </div>
          </dl>
        </>
      ) : (
        <p className="aviso-fixo aviso-inline" role="status">
          <span className="selo selo-neutro">Sem croqui declarado</span> Esta rodada não está
          ligada a nenhum croqui aprovado. A quantidade continua vindo da legenda lida, como
          antes: nada nesta jornada muda enquanto ninguém declarar o elo.
        </p>
      )}

      <form
        className="formulario"
        onSubmit={(event) => {
          event.preventDefault();
          onDeclarar();
        }}
      >
        <label className="campo">
          {link.present ? "Trocar o croqui declarado" : "Croqui aprovado que alimenta esta rodada"}
          <span className="campo-dica">
            O elo nunca é adivinhado: nem por obra de mesmo nome, nem por data próxima, nem
            por semelhança de rótulo. Informe o identificador do croqui — o pacote citado
            será o último publicado por ele, e um pacote novo não troca o elo sozinho.
          </span>
          <input
            type="text"
            value={jobId}
            onChange={(event) => onJobIdChange(event.target.value)}
            aria-label="Identificador do croqui aprovado"
          />
        </label>
        <button
          type="submit"
          className="botao-secundario"
          disabled={submitting || jobId.trim().length === 0}
        >
          {link.present ? "Trocar o croqui declarado" : "Declarar o croqui desta rodada"}
        </button>
      </form>

      {link.present ? (
        <div className="elo-confronto">
          <p className="campo-dica">
            O confronto lê o <span className="mono">quantitativos.csv</span> do pacote
            declarado e, item a item: alimenta o item que está sem quantidade, grava
            divergência onde os dois números discordam além da tolerância, e deixa intacto o
            resto — dizendo por quê. Nenhum provider é chamado, e repetir o ato não
            realimenta nem regrava nada.
          </p>
          <button
            type="button"
            className="botao-secundario"
            onClick={onConfrontar}
            disabled={submitting || !confrontoDisponivel}
          >
            Confrontar o takeoff com a cena aprovada
          </button>
          {confrontoDisponivel ? null : (
            <p className="campo-dica">
              Disponível depois que a revisão do takeoff desta rodada existir: é o pacote de
              itens que o confronto percorre.
            </p>
          )}
        </div>
      ) : null}
    </div>
  );
}

/**
 * O relatório do confronto, item a item (F-047 T4b).
 *
 * TODOS os itens aparecem, inclusive os que não mudaram, com o motivo nomeado. Mostrar só
 * os que mudaram deixaria a AUSÊNCIA responder por "a cena não tinha esse número", que é
 * exatamente o palpite silencioso que esta feature existe para não fazer.
 *
 * Nenhuma contagem é feita aqui: `fed`, `divergences_recorded` e `unchanged` vêm do
 * servidor, que confrontou. Sem confronto executado o bloco não existe, e a etapa fica
 * idêntica à de antes da feature.
 */
export function RelatorioDoConfronto({
  relatorio,
  itens,
}: {
  relatorio: SceneConfrontationReport | null;
  itens: TakeoffItem[];
}) {
  if (relatorio === null) {
    return null;
  }
  const doPacote = new Map(itens.map((item) => [item.id, item]));
  return (
    <div className="confronto-relatorio">
      <h3>Confronto com a cena aprovada</h3>
      <p className="campo-dica">
        {relatorio.fed} item(ns) alimentado(s) pela cena · {relatorio.divergences_recorded}{" "}
        divergência(s) gravada(s) · {relatorio.unchanged} sem mudança. Revisão da cena{" "}
        <span className="mono">{relatorio.scene_revision_id}</span>, pacote{" "}
        <span className="mono">{relatorio.export_id}</span>.
      </p>
      {relatorio.changed ? null : (
        <p className="campo-dica">
          Nada mudou neste confronto, então nenhuma revisão nova foi gravada. O relatório
          abaixo continua valendo: ele diz o que aconteceu com cada item.
        </p>
      )}
      <ul className="lista-confronto">
        {relatorio.items.map((linha) => {
          const item = doPacote.get(linha.item_id) ?? null;
          return (
          <li key={linha.item_id} className={`confronto-linha confronto-${linha.outcome}`}>
            <span className="confronto-cabeca">
              <EtiquetaDeElemento elementRef={linha.element_ref} />{" "}
              <span className="confronto-rotulo">{item?.label ?? linha.item_id}</span>{" "}
              <span className="selo selo-neutro">{sceneOutcomeLabel(linha.outcome)}</span>
            </span>
            {linha.scene_quantity === null ? null : (
              <span className="confronto-numero">
                A cena ofereceu{" "}
                {formatQuantityText(
                  linha.scene_quantity,
                  item === null ? "" : unitLabel(item.unit),
                )}
                {linha.scene_precision === null
                  ? ""
                  : ` · precisão ${precisionLabel(linha.scene_precision)}`}
                .
              </span>
            )}
            {linha.reason === null ? null : (
              <span className="confronto-motivo">
                Não recebeu quantidade da cena porque {sceneReasonLabel(linha.reason)}.
              </span>
            )}
            {frasePorFaltaDePar(linha) === null ? null : (
              <span className="confronto-sem-par">{frasePorFaltaDePar(linha)}</span>
            )}
          </li>
          );
        })}
      </ul>
    </div>
  );
}

/**
 * A origem da quantidade que veio da cena — e o lugar onde havia um campo de digitação.
 *
 * A origem OCUPA o lugar do `input` (ADR-0058, decisões 5 e 7): a redigitação era onde o
 * erro entrava, e o jeito de eliminá-la é não oferecer o teclado. "Editar quantidade" fica
 * desabilitado e VISÍVEL, com a razão ao lado, para que a ausência seja lida como decisão
 * e não como falta.
 *
 * Item que não veio da cena não desenha nada: sem confronto, a tela é a de sempre.
 */
export function OrigemDaQuantidade({
  item,
  sceneRevisionId,
}: {
  item: TakeoffItem;
  sceneRevisionId: string | null;
}) {
  if (!vemDaCena(item)) {
    return null;
  }
  return (
    <div className="origem-cena">
      <p className="elo-linha">
        <EtiquetaDeElemento elementRef={item.element_ref} />{" "}
        <span className="selo selo-cena">
          ◇ origem: {quantitySourceLabel(item.source)}
        </span>
      </p>
      <dl className="procedencia">
        <div>
          <dt>Quantidade</dt>
          <dd>{formatQuantityText(item.quantity ?? null, unitLabel(item.unit))}</dd>
        </div>
        <div>
          <dt>Origem</dt>
          <dd>
            {quantitySourceLabel(item.source)}
            {sceneRevisionId === null ? "" : ` · revisão ${sceneRevisionId}`}
          </dd>
        </div>
        <div>
          <dt>Precisão de origem</dt>
          <dd>
            {item.scene_precision === null || item.scene_precision === undefined
              ? "não declarada por este pacote"
              : precisionLabel(item.scene_precision)}
          </dd>
        </div>
      </dl>
      <p className="aviso-fixo aviso-inline" role="status">
        {RAZAO_SEM_CAMPO_DE_QUANTIDADE}
      </p>
      <p className="origem-acao">
        <button type="button" className="botao-secundario" disabled>
          Editar quantidade
        </button>{" "}
        <span className="campo-dica">
          Indisponível porque a quantidade veio da cena aprovada. Para mudá-la, corrija o
          traçado na jornada do croqui e declare o elo de novo.
        </span>
      </p>
    </div>
  );
}

/**
 * A divergência entre a cena e a legenda: os dois números, a diferença e a tolerância.
 *
 * Três blocos de peso IGUAL, cada um com a sua origem escrita, para que nenhum pareça o
 * principal — nenhum dos dois sobrescreve o outro. A tolerância aparece como fórmula por
 * extenso E como resultado; a diferença e a tolerância chegam prontas do servidor, que as
 * recomputa e confere na gravação. Nenhuma conta acontece aqui.
 *
 * Enquanto a divergência estiver aberta o item aparece BLOQUEADO, e o bloqueio é dito por
 * palavra e por forma (borda esquerda âmbar), nunca só por cor. Bloqueio é diagnóstico, não
 * recusa: por isso âmbar, e não vermelho.
 */
export function DivergenciaDoItem({ item }: { item: TakeoffItem }) {
  const divergencia = divergenciaDoItem(item);
  if (divergencia === null) {
    return null;
  }
  const resolvida = divergenciaResolvida(item);
  const aberta = resolvida === null;
  const unidade = unitLabel(item.unit);
  const resolucao = resolvida?.resolution ?? null;
  const escolhido = resolvida === null ? null : numeroEscolhido(resolvida);
  const preterido = resolvida === null ? null : numeroPreterido(resolvida);
  return (
    <div className={`divergencia ${aberta ? "divergencia-aberta" : "divergencia-resolvida"}`}>
      <p className="elo-linha">
        <EtiquetaDeElemento elementRef={item.element_ref} />{" "}
        <span className="item-rotulo">{item.label}</span>{" "}
        <span className={`selo ${aberta ? "selo-atencao" : "selo-ok"}`}>
          {aberta ? "⚠ divergência aberta" : "divergência resolvida"}
        </span>
      </p>

      <div className="duplo">
        <div className="duplo-bloco duplo-cena">
          <span className="selo selo-cena">◇ cena aprovada</span>
          <span className="duplo-numero">
            {formatQuantityText(divergencia.scene.quantity, unidade)}
          </span>
          <span className="duplo-origem">
            precisão {precisionLabel(divergencia.scene.precision)} · identidade{" "}
            <span className="mono">{divergencia.scene.element_ref}</span>
            {divergencia.scene.scene_revision_id
              ? ` · revisão ${divergencia.scene.scene_revision_id}`
              : ""}
          </span>
        </div>
        <div className="duplo-bloco duplo-legenda">
          <span className="selo selo-neutro">
            {quantitySourceLabel(divergencia.legend.source)}
          </span>
          <span className="duplo-numero">
            {formatQuantityText(divergencia.legend.quantity, unidade)}
          </span>
          <span className="duplo-origem">
            extrator <span className="mono">{divergencia.legend.extractor}</span>{" "}
            {divergencia.legend.extractor_version}
            {divergencia.legend.read_by
              ? ` · decisão humana de ${divergencia.legend.read_by}`
              : " · ainda sem decisão humana sobre a leitura"}
            {divergencia.legend.read_at
              ? ` em ${formatTimestamp(divergencia.legend.read_at)}`
              : ""}
          </span>
        </div>
        <div className="duplo-bloco duplo-diferenca">
          <span className="selo selo-atencao">⚠ fora da tolerância</span>
          <span className="duplo-numero">
            {formatQuantityText(divergencia.difference, unidade)}
          </span>
          {divergencia.legend_ratio ? (
            <span className="duplo-origem">
              {formatDecimalText(divergencia.legend_ratio)}% do valor da legenda
            </span>
          ) : null}
          <span className="duplo-origem">
            tolerância desta divergência:{" "}
            {formatQuantityText(divergencia.tolerance, unidade)}
          </span>
        </div>
      </div>

      <p className="tolerancia-formula">
        {FORMULA_DA_TOLERANCIA}.{" "}
        {divergencia.relative_tolerance &&
        divergencia.absolute_floor &&
        divergencia.tolerance_bound ? (
          <>
            1% × {formatQuantityText(divergencia.legend.quantity, unidade)} ={" "}
            {formatQuantityText(divergencia.relative_tolerance, unidade)} · piso de
            unidade = {formatQuantityText(divergencia.absolute_floor, unidade)} ·
            tolerância = {formatQuantityText(divergencia.tolerance, unidade)} (
            {divergencia.tolerance_bound === "relative" ? "1% mandou" : "o piso segurou"}
            ).{" "}
          </>
        ) : null}
        Os dois números desta linha — a diferença e a tolerância — são os que o servidor
        gravou e confere a cada leitura; a tela não refaz nenhuma conta.
      </p>

      {aberta ? (
        <p className="bloqueado" role="alert">
          <strong>{motivoDeBloqueio(item)}</strong> {AVISO_DIVERGENCIA_ABERTA}
        </p>
      ) : null}

      {resolucao && escolhido && preterido ? (
        <div className="carimbo-resolucao">
          <p>
            <strong>{resolucao.reviewer_id}</strong> em{" "}
            {formatTimestamp(resolucao.resolved_at)} decidiu que{" "}
            <strong>{divergenceChoiceLabel(resolucao.choice)}</strong>:{" "}
            {formatQuantityText(escolhido.quantity, unidade)}.
          </p>
          {resolucao.note ? <p>Motivo: “{resolucao.note}”</p> : null}
          <p>
            Preterida: {formatQuantityText(preterido.quantity, unidade)} ·{" "}
            {preterido.origem === "scene"
              ? quantitySourceLabel("scene_graph")
              : quantitySourceLabel(divergencia.legend.source)}{" "}
            — <strong>continua gravada</strong>. Resolver não é sobrescrever: nenhuma origem
            foi apagada.
          </p>
        </div>
      ) : null}
    </div>
  );
}

/**
 * A resolução da divergência: escolha humana registrada, com motivo, autor e instante.
 *
 * Duas escolhas, e só duas. A terceira aparece DESABILITADA e com a razão escrita, em vez
 * de sumir: digitar uma terceira quantidade aqui seria a redigitação que esta feature
 * existe para eliminar, e ver a opção indisponível ensina isso — a ausência calada, não.
 *
 * Nada nasce pré-marcado: a escolha vem do clique, nunca do default.
 */
export function ResolucaoDaDivergencia({
  item,
  escolha,
  motivo,
  submitting,
  onEscolha,
  onMotivo,
  onRegistrar,
  onCancelar,
}: {
  item: TakeoffItem;
  escolha: DivergenceChoice | "";
  motivo: string;
  submitting: boolean;
  onEscolha: (choice: DivergenceChoice) => void;
  onMotivo: (value: string) => void;
  onRegistrar: () => void;
  onCancelar: () => void;
}) {
  const divergencia = divergenciaAberta(item);
  if (divergencia === null) {
    return null;
  }
  const unidade = unitLabel(item.unit);
  const bloqueado = submitting || escolha === "" || motivo.trim().length === 0;
  return (
    <form
      className="formulario resolucao-divergencia"
      onSubmit={(event) => {
        event.preventDefault();
        onRegistrar();
      }}
    >
      <fieldset className="acoes">
        <legend>Resolver a divergência de {item.label}</legend>
        <label>
          <input
            type="radio"
            name="divergencia"
            value="scene"
            checked={escolha === "scene"}
            onChange={() => onEscolha("scene")}
          />
          Vale a cena: {formatQuantityText(divergencia.scene.quantity, unidade)} ·{" "}
          precisão {precisionLabel(divergencia.scene.precision)}
        </label>
        <label>
          <input
            type="radio"
            name="divergencia"
            value="legend"
            checked={escolha === "legend"}
            onChange={() => onEscolha("legend")}
          />
          Vale a legenda: {formatQuantityText(divergencia.legend.quantity, unidade)} ·{" "}
          {quantitySourceLabel(divergencia.legend.source)}
        </label>
        <label className="escolha-indisponivel">
          <input type="radio" name="divergencia" value="none" disabled />
          Nenhuma das duas
          <span className="campo-dica">{RAZAO_SEM_TERCEIRA_ESCOLHA}</span>
        </label>
      </fieldset>
      <label className="campo">
        Motivo da decisão (obrigatório)
        <span className="campo-dica">
          É o que fica na memória de cálculo ao lado dos dois números; quem conferir a
          medição meses depois lê aqui por que uma origem prevaleceu.
        </span>
        <input
          type="text"
          value={motivo}
          onChange={(event) => onMotivo(event.target.value)}
        />
      </label>
      <div className="acoes-linha">
        <button type="submit" className="botao-primario" disabled={bloqueado}>
          Registrar decisão
        </button>
        <button
          type="button"
          className="botao-secundario"
          onClick={onCancelar}
          disabled={submitting}
        >
          Manter aberta
        </button>
      </div>
    </form>
  );
}

/**
 * Banner do `409 REVISION_CONFLICT`. Ele não é o alerta comum de erro: a rodada andou, o
 * ato não foi gravado, e o caminho é recarregar — com o que já estava escrito no
 * formulário intacto.
 */
export function BannerRodadaMudou({ onReload }: { onReload?: () => void }) {
  return (
    <div className="banner-conflito" role="alert">
      <p>{MENSAGEM_RODADA_MUDOU}</p>
      {onReload === undefined ? null : (
        <button type="button" className="botao-primario" onClick={onReload}>
          Recarregar estado atual
        </button>
      )}
    </div>
  );
}

/**
 * O boletim gravado deixou de descrever a praça, e a saída (F-046 T5c).
 *
 * Quem declara o vencimento é o SERVIDOR (`bulletin.stale` do estado da rodada), comparando
 * as fontes que geraram a medição com as de agora; esta tela só o diz por extenso e oferece
 * o único ato que o resolve. Até aqui o botão de montar desaparecia assim que havia boletim
 * gravado: o toast do ato mandava "montar o boletim de novo" e a tela não oferecia como, o
 * que tornava a ordem do pacote aprovado — montar, ver a dupla contagem, declarar a
 * identidade, ver o total novo — impercorrível numa rodada só.
 *
 * Aprovação em vigor ganha a frase própria ANTES do botão: remontar leva a assinatura
 * adiante já caduca (preservar não é aprovar), e um efeito desses não pode ser descoberto
 * depois do clique.
 *
 * Âmbar de aviso, o mesmo de `BannerRodadaMudou`, e o estado dito por extenso: cor nunca é
 * o único indicador.
 */
export function BannerBoletimVencido({
  aprovada,
  submitting,
  onRemontar,
}: {
  aprovada: boolean;
  submitting: boolean;
  onRemontar: () => void;
}) {
  return (
    <div className="banner-conflito banner-vencido" role="alert">
      <div>
        <p>{BOLETIM_VENCIDO}</p>
        {aprovada ? <p>{REMONTAR_CADUCA_A_APROVACAO}</p> : null}
      </div>
      <button
        type="button"
        className="botao-primario"
        onClick={onRemontar}
        disabled={submitting}
      >
        {submitting ? "Montando…" : "Montar o boletim de novo"}
      </button>
    </div>
  );
}

/**
 * `403` da rota, como TELA e **sem nomear papel**.
 *
 * Qual papel a mensagem deve citar é decisão de copy e de autorização ainda aberta no
 * pacote de design aprovado da F-028: um texto que nomeasse um papel afirmaria uma decisão
 * que ninguém tomou. Quem autoriza continua sendo o backend — a etapa é montada pelo
 * estado da rodada, e quem chega sem autorização lê o motivo em vez de achar tela vazia.
 */
export function PainelSemAcesso() {
  return (
    <section className="painel" aria-label="Sem acesso a esta rodada">
      <div className="painel-cabecalho">
        <h2>Sem acesso a esta rodada</h2>
      </div>
      <p role="alert">{MENSAGEM_SEM_ACESSO}</p>
      <p className="dica">
        Vale para ler e para aprovar: quem não pode ler a rodada também não exerce o ato de
        aprovação nela.
      </p>
    </section>
  );
}

/**
 * O ato nominal de aprovação (VAL-05), em DOIS atos explícitos.
 *
 * Três decisões do desenho aprovado vivem aqui e não podem ser "simplificadas":
 *
 * - **a consequência vem antes do botão, e por extenso** — três frases fixas: publica o
 *   nome de quem aprova, libera a exportação, vale só para este conteúdo exato;
 * - **a identidade é mostrada, nunca digitável** — não existe campo de nome do aprovador
 *   nesta tela, porque o servidor lê a identidade do token e recusa qualquer nome que
 *   venha do cliente; um campo aqui prometeria um efeito que ele não tem;
 * - **confirmar exige um segundo ato**, e o segundo passo REPETE a consequência em vez de
 *   perguntar "tem certeza?" — decisão humana de 2026-08-20, mantida.
 *
 * Enquanto grava, os dois botões ficam indisponíveis: repetir o clique não criaria
 * aprovação nova (a mutação leva chave de idempotência), mas a tela também não pode
 * sugerir que criaria.
 */
export function AtoDeAprovacao({
  titulo,
  identidade,
  papel,
  contentDigest,
  confirmando,
  gravando,
  onAprovar,
  onConfirmar,
  onCancelar,
}: {
  titulo: string;
  identidade: string;
  papel: string;
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
      <span className="ato-etiqueta">Ato nominal · VAL-05</span>
      <h3>{titulo}</h3>
      {confirmando ? null : (
        <>
          <p>Antes de aprovar, o que aprovar faz:</p>
          <ul className="ato-consequencia">
            <li>
              <strong>Publica o seu nome.</strong> A aprovação fica registrada como sua,
              com data e hora, e acompanha o boletim exportado.
            </li>
            <li>
              <strong>Libera a exportação.</strong> Sem aprovação nominal válida, a rota de
              exportação recusa — não é convenção, é recusa do servidor.
            </li>
            <li>
              <strong>
                Vale só para esta medição, exatamente como ela está agora
              </strong>{" "}
              (
              <span className="mono" title={contentDigest ?? undefined}>
                sha256 {digestCurto}
              </span>
              ). Qualquer mudança depois disso derruba a aprovação e exige aprovar de novo.
            </li>
          </ul>
        </>
      )}
      <div className="ato-identidade">
        <b>Você aprova como</b>
        <span className="mono">{identidade}</span>
        <p className="campo-dica">
          Papel {papel} · identidade da sessão. Não existe campo de nome nesta tela: quem
          aprova é quem entrou, e o servidor lê a identidade do token e recusa qualquer nome
          que venha do cliente.
        </p>
      </div>
      {confirmando ? (
        <div className="ato-confirmacao">
          <p>
            <strong>Confirmar a aprovação nominal?</strong> O nome{" "}
            <span className="mono">{identidade}</span> fica registrado como quem aprovou
            esta medição, no conteúdo{" "}
            <span className="mono" title={contentDigest ?? undefined}>
              sha256 {digestCurto}
            </span>
            , e a exportação do boletim fica liberada.
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
              Enquanto grava, os dois botões ficam indisponíveis: repetir o clique não cria
              aprovação nova, porque o ato vai com chave de idempotência.
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
            Aprovar esta medição
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
 * um ato humano que aconteceu — e é essa diferença entre "caduca" e "nunca aprovada" que
 * dá à tela a única saída correta, aprovar de novo. O digest não é enfeite de auditoria: é
 * o vínculo que faz a aprovação caducar sozinha, e por isso os dois aparecem lado a lado.
 *
 * A marca do estado é a PALAVRA na etiqueta; o tracejado âmbar é redundância dela.
 */
export function RegistroDaAprovacao({
  approval,
  papel,
}: {
  approval: ApprovalState;
  papel: string;
}) {
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
          <span className="mono">{approval.approved_by ?? "não declarado"}</span> · papel{" "}
          {papel}
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
              <span className="mono" title={approval.approved_digest ?? undefined}>
                sha256 {shortDigest(approval.approved_digest)}
              </span>{" "}
              — igual ao da medição atual
            </dd>
          </>
        )}
      </dl>
      {approval.stale ? (
        <>
          <div className="digest-par">
            <div>
              <b>Conteúdo aprovado</b>
              <span className="mono" title={approval.approved_digest ?? undefined}>
                sha256 {shortDigest(approval.approved_digest)}
              </span>
              <p className="campo-dica">o que foi assinado no ato registrado acima</p>
            </div>
            <div>
              <b>Conteúdo atual</b>
              <span className="mono" title={approval.current_digest ?? undefined}>
                sha256 {shortDigest(approval.current_digest)}
              </span>
              <p className="campo-aviso">
                diferente do aprovado — a medição mudou depois da aprovação
              </p>
            </div>
          </div>
          <p className="digest">APPROVAL_CONTENT_MISMATCH</p>
        </>
      ) : null}
    </div>
  );
}

/** Os quatro passos do portão de exportação, na ordem em que o servidor os executa. */
const PASSOS_DA_EXPORTACAO = [
  "Montar a planilha no modelo da prefeitura",
  "Gravar o arquivo",
  "Reabrir e reconferir célula a célula",
  "Publicar",
];

/**
 * Estado de cada passo, pelo que a tela REALMENTE sabe.
 *
 * Os quatro passos correm dentro de uma chamada só: enquanto ela está em voo, o cliente
 * não observa em qual deles o servidor está, e fingir uma progressão seria inventar
 * estado. O que se sabe com certeza é o DESFECHO — publicado significa os quatro feitos;
 * auditoria reprovada significa que o arquivo foi montado e gravado, que a reconferência
 * recusou e que a publicação não chegou a acontecer.
 */
function estadosDosPassos(
  estado: "em-voo" | "publicado" | "reprovado",
): string[] {
  if (estado === "publicado") {
    return ["feito", "feito", "feito", "feito"];
  }
  if (estado === "reprovado") {
    return ["feito", "feito", "reprovado", "não iniciado"];
  }
  return ["no servidor", "no servidor", "no servidor", "no servidor"];
}

/**
 * Progresso da exportação como LISTA ESCRITA de quatro passos, nunca como barra.
 *
 * Três dos quatro passos acontecem antes de existir arquivo publicado; uma barra sugeriria
 * que o arquivo já está quase pronto quando ele ainda pode ser descartado no passo três.
 */
export function ProgressoExportacao({
  estado,
}: {
  estado: "em-voo" | "publicado" | "reprovado";
}) {
  const estados = estadosDosPassos(estado);
  return (
    <>
      <ol className="progresso">
        {PASSOS_DA_EXPORTACAO.map((passo, index) => (
          <li key={passo}>
            {passo} — <span className="passo-estado">{estados[index]}</span>
          </li>
        ))}
      </ol>
      {estado === "em-voo" ? (
        <p className="dica" role="status">
          Os quatro passos correm no servidor, numa chamada só. Nada foi publicado até a
          resposta chegar; se a reconferência do passo 3 falhar, o arquivo do passo 2 é
          descartado.
        </p>
      ) : null}
    </>
  );
}

/**
 * Auditoria da planilha reprovada, como TELA e não rodapé.
 *
 * O arquivo é gravado, reaberto e reconferido antes de qualquer publicação: quando a
 * conferência falha, nada vai ao object store e nenhuma revisão nasce. Dizer isso por
 * extenso é o que separa "falhou" de "publicou algo que ninguém conferiu".
 *
 * Só os CÓDIGOS dos achados aparecem. O desenho aprovado mostra também a célula divergente
 * com valor esperado e encontrado, e esses dois campos **não viajam**: eles são o preço, a
 * quantidade e o total da obra do cliente, e a rota não os devolve numa mensagem de erro.
 * A tela declara essa ausência em vez de deixar uma coluna vazia parecendo defeito.
 */
export function TelaAuditoriaReprovada({
  findings,
  onDismiss,
}: {
  findings: readonly string[];
  onDismiss?: () => void;
}) {
  return (
    <section className="painel" aria-label="Auditoria do boletim reprovada">
      <div className="painel-cabecalho">
        <h2>A auditoria reprovou a planilha — nada foi publicado</h2>
      </div>
      <p className="banner-erro" role="alert">
        {MENSAGEM_AUDITORIA_REPROVADA}
      </p>
      <ProgressoExportacao estado="reprovado" />
      {findings.length === 0 ? null : (
        <table className="tabela">
          <caption>Divergências encontradas na reconferência</caption>
          <thead>
            <tr>
              <th scope="col">Código do achado</th>
              <th scope="col">O que ele diz</th>
            </tr>
          </thead>
          <tbody>
            {findings.map((code) => (
              <tr key={code}>
                <td className="mono">{code}</td>
                <td>{errorMessage(code)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="dica">
        O valor esperado e o encontrado de cada célula não voltam do servidor: eles são
        preço, quantidade e total da obra, e não viajam em mensagem de erro. Um centavo de
        diferença basta para não publicar — o portão é o mesmo do CLI e o mesmo do
        orçamento-base.
      </p>
      {onDismiss === undefined ? null : (
        <div className="acoes-linha">
          <button type="button" className="botao-secundario" onClick={onDismiss}>
            Voltar à etapa de aprovação
          </button>
        </div>
      )}
    </section>
  );
}

/**
 * A faixa de folhas da praça: uma LISTA de folhas, não um explorador de arquivos.
 *
 * Cada folha é um cartão com nome, `plate_id`, estado por extenso e contagem de itens; a
 * folha em foco traz a marca `▸ em foco` e a barra à esquerda. Uma árvore de arquivos
 * convidaria a pensar em páginas de PDF, e a praça não é um arquivo — é o conjunto de
 * folhas que a orçamentista declarou (pacote de design aprovado, decisão 1).
 *
 * A cor nunca é o único indicador: o estado tem símbolo próprio (`✓`, `▲`, `◐`, `✕`, `○`)
 * e texto ao lado, e o foco é dito em palavra antes de ser desenhado.
 */
export function FaixaDeFolhas({
  folhas,
  emFoco,
  onFocar,
}: {
  folhas: WorksiteSheet[];
  emFoco: string;
  onFocar: (plateId: string) => void;
}) {
  const total = folhas.length;
  return (
    <section className="folhas" aria-label="Folhas da praça">
      <ul className="folhas-faixa">
        {folhas.map((folha) => {
          const estado = estadoDaFolha(folha);
          const foco = folha.plate_id === emFoco;
          return (
            <li
              key={folha.plate_id}
              className={`folha-chip folha-${estado.id} ${foco ? "em-foco" : ""}`}
            >
              <button
                type="button"
                className="folha-botao"
                onClick={() => onFocar(folha.plate_id)}
                aria-current={foco}
              >
                {foco ? <span className="folha-foco">▸ em foco</span> : null}
                <span className="folha-titulo">
                  Folha {folha.position} de {total}
                </span>
                <span className="mono folha-id">{folha.plate_id}</span>
                <span className="folha-estado">
                  <span aria-hidden="true">{estado.symbol}</span> {estado.label}
                </span>
                <span className="folha-resumo">{resumoDaFolha(folha)}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

/**
 * O ato de acrescentar folha: seleção de páginas em lote, nada marcado por padrão.
 *
 * Três coisas são deliberadas (pacote de design aprovado, decisões 3 e 4): a seleção é em
 * lote e a confirmação é uma só; nenhuma página vem marcada, porque quadro de áreas, lista
 * de materiais e carimbo não são legenda quantificada; e o número de folhas que o ato
 * acrescenta fica escrito no próprio botão, porque o custo por folha não pode aparecer só
 * na fatura.
 *
 * Página que já é folha desta praça aparece desabilitada e dita: o servidor a recusaria
 * (`ROUND_PLATE_ALREADY_PRESENT`), e oferecer o que já se sabe recusado convida ao erro.
 */
export function AcrescentarFolhas({
  paginas,
  jaPromovidas,
  selecionadas,
  aindaCabem,
  onAlternar,
  onConfirmar,
  submitting,
}: {
  paginas: number;
  jaPromovidas: number[];
  selecionadas: number[];
  aindaCabem: number;
  onAlternar: (pagina: number) => void;
  onConfirmar: () => void;
  submitting: boolean;
}) {
  const numeros = Array.from({ length: paginas }, (_, index) => index + 1);
  const excedeu = selecionadas.length > aindaCabem;
  return (
    <div className="acrescentar-folhas">
      <h3>Escolha as páginas que viram prancha</h3>
      <p className="dica">
        A praça <strong>não</strong> é um arquivo: é o conjunto de folhas que você
        declarou. O documento tem {paginas} {paginas === 1 ? "página" : "páginas"} e{" "}
        <strong>nenhuma vem marcada por padrão</strong>; página não é prancha — quadro de
        áreas, lista de materiais e carimbo não são legenda quantificada.
      </p>
      <ul className="paginas-grade">
        {numeros.map((pagina) => {
          const promovida = jaPromovidas.includes(pagina);
          const marcada = selecionadas.includes(pagina);
          return (
            <li key={pagina} className={`pagina-opcao ${marcada ? "marcada" : ""}`}>
              <label className="campo-checkbox">
                <input
                  type="checkbox"
                  checked={marcada}
                  disabled={promovida || submitting}
                  onChange={() => onAlternar(pagina)}
                />
                <span className="pagina-numero">Página {pagina}</span>
                {promovida ? (
                  <span className="pagina-estado">já é folha desta praça</span>
                ) : null}
              </label>
            </li>
          );
        })}
      </ul>
      {excedeu ? (
        <p className="banner-erro" role="alert">
          A praça ainda comporta {aindaCabem}{" "}
          {aindaCabem === 1 ? "folha" : "folhas"}; desmarque{" "}
          {selecionadas.length - aindaCabem} para caber no limite da rodada.
        </p>
      ) : null}
      <div className="acoes-linha">
        <button
          type="button"
          className="botao-primario"
          onClick={onConfirmar}
          disabled={selecionadas.length === 0 || submitting || excedeu}
        >
          {submitting ? "Acrescentando…" : rotuloDoLoteDePromocao(selecionadas.length)}
        </button>
      </div>
      <p className="aviso-fixo aviso-inline">
        {avisoDoLoteDePromocao(selecionadas.length)}
      </p>
    </div>
  );
}

/**
 * O lote de leitura: quais folhas vão para a chamada paga, com o número no próprio botão.
 *
 * Cada folha é uma chamada paga de IA, e a lista marcada é a autorização. Nada vem marcado
 * por padrão aqui pelo mesmo motivo da promoção — o número de extrações é escolha
 * declarada de quem paga, e não efeito colateral de abrir a tela.
 */
export function LerFolhasEmLote({
  folhas,
  selecionadas,
  onAlternar,
  onConfirmar,
  submitting,
}: {
  folhas: WorksiteSheet[];
  selecionadas: string[];
  onAlternar: (plateId: string) => void;
  onConfirmar: () => void;
  submitting: boolean;
}) {
  if (folhas.length === 0) {
    return null;
  }
  return (
    <div className="ler-folhas">
      <h3>Ler a legenda das folhas escolhidas</h3>
      <ul className="paginas-grade">
        {folhas.map((folha) => (
          <li
            key={folha.plate_id}
            className={`pagina-opcao ${
              selecionadas.includes(folha.plate_id) ? "marcada" : ""
            }`}
          >
            <label className="campo-checkbox">
              <input
                type="checkbox"
                checked={selecionadas.includes(folha.plate_id)}
                disabled={submitting}
                onChange={() => onAlternar(folha.plate_id)}
              />
              <span className="pagina-numero">Folha {folha.position}</span>
              <span className="mono folha-id">{folha.plate_id}</span>
            </label>
          </li>
        ))}
      </ul>
      <div className="acoes-linha">
        <button
          type="button"
          className="botao-primario"
          onClick={onConfirmar}
          disabled={selecionadas.length === 0 || submitting}
        >
          {submitting ? "Enfileirando…" : rotuloDoLoteDeExtracao(selecionadas.length)}
        </button>
      </div>
      <p className="aviso-fixo aviso-inline">
        Cada folha é uma chamada paga de IA, autorizada por contrato do seu tenant. O
        número de folhas que a leitura dispara está escrito no botão.
      </p>
    </div>
  );
}

/**
 * A folha em foco que ainda não virou pacote — não há o que revisar nela.
 *
 * Desde a F-046 T4c a `/v1` serve prancha, overlay e itens POR FOLHA, então esta tela
 * deixou de ser "a folha que a API não alcança" e passou a ser o que sempre deveria ter
 * sido: o estado honesto de uma folha que ainda não foi lida. Nada de outra folha é
 * desenhado aqui — uma imagem de outra folha engana com a autoridade de um desenho.
 */
export function FolhaSemPacote({
  folha,
  total,
}: {
  folha: WorksiteSheet;
  total: number;
}) {
  const estado = estadoDaFolha(folha);
  return (
    <article className="painel prancha-painel">
      <div className="painel-cabecalho">
        <h2>
          Prancha e legenda — <strong>{folhaLabel(folha.position, total)}</strong> ·{" "}
          <span className="mono">{folha.plate_id}</span>
        </h2>
      </div>
      <p className="folha-estado">
        <span aria-hidden="true">{estado.symbol}</span> {estado.label} ·{" "}
        {resumoDaFolha(folha)}
      </p>
      <p className="banner-erro" role="alert">
        Esta folha ainda não tem pacote de takeoff: não há item para revisar nela. Dispare
        a leitura da legenda desta folha na etapa das pranchas — é chamada paga, e o
        número delas está escrito no botão.
      </p>
      <p className="dica">
        Não existe overlay da praça: cada retângulo está em pixels da imagem desta folha,
        conferida pelo digest dela. O consolidado endereça os overlays das suas folhas; ele
        não desenha nada.
      </p>
    </article>
  );
}

/**
 * O re-render do overlay ainda é só da PRIMEIRA folha — e a tela diz isso.
 *
 * Limitação declarada da `/v1` (F-046 T4c): o comando de fila desenha o pacote de
 * `takeoff_packet_json` e ainda não conhece a praça, então uma decisão tomada na folha 2
 * em diante deixa o overlay daquela folha vencido para sempre. Isso é desfecho
 * fail-closed, não erro — o desenho anterior continua sendo a única visão de onde cada
 * número foi lido —, e esconder a divergência seria pior que declará-la
 * ([ADR-0030](../../docs/adr/0030-overlay-do-takeoff-reconstruido-na-fila.md)).
 */
export function OverlaySemRerender({ folha, total }: { folha: WorksiteSheet; total: number }) {
  return (
    <p className="aviso-fixo aviso-inline" role="status">
      O desenho das âncoras desta folha ({folhaLabel(folha.position, total)}) não é
      refeito depois de uma decisão: o re-render em fila ainda é o da primeira folha da
      praça. O overlay aqui fica <strong>vencido</strong> e declarado como tal — os itens,
      as quantidades e o boletim continuam corretos; só o desenho envelhece.
    </p>
  );
}

/**
 * O andamento da codificação, folha por folha (F-046, ADR-0057, decisão 6).
 *
 * A etapa de códigos é por folha porque o conjunto é por PRANCHA, e sem esta lista a
 * orçamentista veria "nada pendente" na folha aberta sem saber que outra folha trava o
 * boletim da praça. Cada número aqui é o que a leitura DAQUELA folha devolveu — nenhum é
 * somado, deduzido ou completado por esta tela.
 */
export function AndamentoDaCodificacao({
  folhas,
  total,
  emFoco,
  onFocar,
}: {
  folhas: ReturnType<typeof codificacaoDasFolhas>;
  total: number;
  emFoco: string;
  onFocar: (plateId: string) => void;
}) {
  if (folhas.length === 0) {
    return null;
  }
  return (
    <section className="codificacao-folhas" aria-label="Codificação por folha">
      <h3>O que falta codificar em cada folha</h3>
      <ul className="praca-lista">
        {folhas.map((folha) => (
          <li
            key={folha.plateId}
            className={`codificacao-folha ${folha.plateId === emFoco ? "em-foco" : ""}`}
          >
            <button
              type="button"
              className="folha-botao"
              onClick={() => onFocar(folha.plateId)}
              aria-current={folha.plateId === emFoco}
            >
              {folha.plateId === emFoco ? (
                <span className="folha-foco">▸ codificando esta</span>
              ) : null}
              <span className="folha-titulo">{resumoDaCodificacao(folha, total)}</span>
              <span className="mono folha-id">{folha.plateId}</span>
            </button>
          </li>
        ))}
      </ul>
      <p className="dica">
        O conjunto de códigos é de cada prancha, e o boletim da praça é a{" "}
        <strong>união</strong> deles. Folha com elemento pendente trava o boletim inteiro —
        meia praça somada parece uma praça inteira.
      </p>
    </section>
  );
}

/** O vínculo em digitação: as duas leituras escolhidas e o motivo. */
export type RascunhoDeVinculo = {
  kept: TakeoffItemAddress;
  discarded: TakeoffItemAddress;
  note: string;
};

/** Rascunho vazio; nada nasce escolhido — fundir é ato declarado, nunca sugestão. */
export const VINCULO_VAZIO: RascunhoDeVinculo = {
  kept: { plate_id: "", item_id: "" },
  discarded: { plate_id: "", item_id: "" },
  note: "",
};

/** `true` quando a prévia à vista é exatamente do par que está no rascunho. */
export function previaConfere(
  previa: IdentityLinkPreviewResponse | null,
  rascunho: RascunhoDeVinculo,
): boolean {
  return (
    previa !== null &&
    previa.kept.plate_id === rascunho.kept.plate_id &&
    previa.kept.item_id === rascunho.kept.item_id &&
    previa.discarded.plate_id === rascunho.discarded.plate_id &&
    previa.discarded.item_id === rascunho.discarded.item_id
  );
}

/** Uma parcela da prévia, com a quantidade que o SERVIDOR calculou. */
function ParcelaDaPrevia({
  parcela,
  papel,
}: {
  parcela: IdentityLinkPreviewResponse["kept"];
  papel: string;
}) {
  return (
    <li className="previa-parcela">
      <p className="praca-selo">{papel}</p>
      <p>
        <strong>{parcela.label}</strong> —{" "}
        {formatQuantityText(parcela.quantity, unitLabel(parcela.unit))}
      </p>
      <p className="mono">
        {parcela.plate_id} · {parcela.item_id}
      </p>
      <p className="dica">leitura {itemStatusLabel(parcela.status)}</p>
    </li>
  );
}

/**
 * Declarar que duas leituras de folhas diferentes são o MESMO elemento (ADR-0057, D4;
 * pacote de design aprovado, decisão 11).
 *
 * O ato só é oferecido **com a prévia do efeito no total**, e a prévia vem do servidor
 * (`POST .../worksite/identity-links/preview`): a tela de medição não soma, e sem a rota a
 * orçamentista só descobriria o efeito depois de declarar. Foi por faltar essa rota que a
 * T5 se recusou a oferecer o ato; ela existe desde a T4c, e o ato voltou.
 *
 * Três coisas são deliberadas:
 *
 * - **nada nasce escolhido** — fundir por rótulo, unidade ou proximidade é exatamente o
 *   que o ADR-0057 proíbe, e um par pré-selecionado seria essa proibição contornada pela
 *   tela;
 * - **declarar exige a prévia DAQUELE par** — trocar a leitura depois de pré-visualizar
 *   apaga a prévia, porque um número conferido de outro par é pior que número nenhum;
 * - **o motivo é obrigatório**, como no desfazer: quem confere depois precisa ler por que
 *   duas leituras viraram uma.
 */
export function DeclararIdentidade({
  folhas,
  itensPorFolha,
  rascunho,
  previa,
  onRascunho,
  onPrever,
  onDeclarar,
  previewing,
  submitting,
}: {
  folhas: WorksiteSheet[];
  itensPorFolha: Readonly<Record<string, TakeoffItem[]>>;
  rascunho: RascunhoDeVinculo;
  previa: IdentityLinkPreviewResponse | null;
  onRascunho: (proximo: RascunhoDeVinculo) => void;
  onPrever: () => void;
  onDeclarar: () => void;
  previewing: boolean;
  submitting: boolean;
}) {
  const recusa = recusaDoVinculo(rascunho.kept, rascunho.discarded);
  // A prévia só vale para o par que ESTÁ no rascunho: trocar a leitura depois de
  // pré-visualizar apaga o número da tela, porque um total conferido de outro par é pior
  // que total nenhum.
  const previaDoPar = previaConfere(previa, rascunho) ? previa : null;
  const motivo = rascunho.note.trim();
  const seletorDeFolha = (
    papel: "kept" | "discarded",
    rotulo: string,
    dica: string,
  ) => {
    const endereco = rascunho[papel];
    const itens = itensPorFolha[endereco.plate_id] ?? [];
    return (
      <fieldset className="vinculo-lado">
        <legend>{rotulo}</legend>
        <p className="dica">{dica}</p>
        <label className="campo">
          Folha
          <select
            value={endereco.plate_id}
            disabled={submitting}
            onChange={(event) =>
              onRascunho({
                ...rascunho,
                [papel]: { plate_id: event.target.value, item_id: "" },
              })
            }
          >
            <option value="">escolha a folha</option>
            {folhas.map((folha) => (
              <option key={folha.plate_id} value={folha.plate_id}>
                {folhaLabel(folha.position, folhas.length)} — {folha.plate_id}
              </option>
            ))}
          </select>
        </label>
        <label className="campo">
          Leitura
          <select
            value={endereco.item_id}
            disabled={submitting || endereco.plate_id === ""}
            onChange={(event) =>
              onRascunho({
                ...rascunho,
                [papel]: { ...endereco, item_id: event.target.value },
              })
            }
          >
            <option value="">escolha a leitura</option>
            {itens.map((item) => (
              <option key={item.id} value={item.id}>
                {item.label} —{" "}
                {formatQuantityText(item.quantity ?? null, unitLabel(item.unit))}
              </option>
            ))}
          </select>
        </label>
        {endereco.plate_id !== "" && itens.length === 0 ? (
          <p className="campo-aviso">
            O pacote desta folha ainda não foi lido nesta tela; abra a folha na etapa das
            pranchas para carregá-lo.
          </p>
        ) : null}
      </fieldset>
    );
  };

  return (
    <div className="declarar-identidade">
      <h3>Declarar que duas leituras são o mesmo elemento</h3>
      <p className="dica">
        A planta geral e a folha de detalhe desenham o mesmo alambrado, e sem esta
        declaração ele conta duas vezes. Nada funde sozinho: o sistema não usa rótulo,
        unidade nem proximidade, e errar para o lado de somar demais é o erro que aparece.
      </p>
      <div className="vinculo-lados">
        {seletorDeFolha(
          "kept",
          "A parcela que fica",
          "É a leitura que governa a quantidade quando as duas divergirem.",
        )}
        {seletorDeFolha(
          "discarded",
          "A leitura absorvida",
          "Ela continua impressa na memória da folha onde foi lida, com subtotal zero.",
        )}
      </div>
      {recusa === null ? null : (
        <p className="campo-aviso" role="status">
          {recusa}
        </p>
      )}
      <div className="acoes-linha">
        <button
          type="button"
          className="botao-secundario"
          onClick={onPrever}
          disabled={recusa !== null || previewing || submitting}
        >
          {previewing ? "Calculando…" : "Ver o efeito no total antes de declarar"}
        </button>
      </div>
      {previaDoPar === null ? (
        <p className="dica">
          O efeito no total é calculado pelo servidor — esta tela nunca soma. Sem a prévia
          deste par, a declaração não é oferecida.
        </p>
      ) : (
        <div className="previa-vinculo">
          <h4>Efeito desta fusão no total da praça</h4>
          <ul className="previa-parcelas">
            <ParcelaDaPrevia parcela={previaDoPar.kept} papel="a parcela que fica" />
            <ParcelaDaPrevia
              parcela={previaDoPar.discarded}
              papel="fundida, não contribui"
            />
          </ul>
          {previaDoPar.unit_mismatch || previaDoPar.total_before === null ? (
            <p className="banner-erro" role="alert">
              {previaDoPar.unit_mismatch
                ? "As duas leituras estão em unidades diferentes: não há soma a mostrar, e nenhum total é escrito aqui. Confira se elas são mesmo o mesmo elemento."
                : "Uma das leituras ainda não tem quantidade: não há soma a mostrar, e nenhum total é escrito aqui."}
            </p>
          ) : (
            <table className="tabela previa-tabela">
              <caption>
                Totais calculados pelo servidor para este par de leituras
              </caption>
              <tbody>
                <tr>
                  <th scope="row">Total hoje, sem o vínculo</th>
                  <td className="numero">
                    {formatQuantityText(
                      previaDoPar.total_before,
                      unitLabel(previaDoPar.kept.unit),
                    )}
                  </td>
                </tr>
                <tr>
                  <th scope="row">Total depois do vínculo</th>
                  <td className="numero">
                    {formatQuantityText(
                      previaDoPar.total_after,
                      unitLabel(previaDoPar.kept.unit),
                    )}
                  </td>
                </tr>
              </tbody>
            </table>
          )}
          <label className="campo">
            Por que estas duas leituras são o mesmo elemento
            <textarea
              value={rascunho.note}
              rows={2}
              disabled={submitting}
              onChange={(event) =>
                onRascunho({ ...rascunho, note: event.target.value })
              }
            />
          </label>
          <p className="dica">
            O motivo é obrigatório: o vínculo muda o total da praça, e quem confere depois
            precisa ler por que duas leituras viraram uma. Autor e instante são carimbados
            pelo servidor.
          </p>
          <div className="acoes-linha">
            <button
              type="button"
              className="botao-primario"
              onClick={onDeclarar}
              disabled={submitting || motivo.length === 0}
            >
              {submitting ? "Declarando…" : "Declarar identidade"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * A etapa Praça: o consolidado da praça e os NÚMEROS que o boletim dela já traz.
 *
 * O consolidado (`GET .../worksite`) referencia o pacote de cada folha por `plate_id` e
 * digest e **não contém itens**. Os números vêm do boletim da praça (`POST .../calc`,
 * F-046 T4c): um boletim por folha, com as linhas já consolidadas por código e a memória
 * de cada parcela na folha onde a leitura foi feita. Tudo o que aparece aqui é string que
 * o servidor mandou — esta tela nunca soma, multiplica nem arredonda.
 *
 * A recusa nomeia a folha (pacote de design aprovado, decisão 12): meia praça somada
 * parece uma praça inteira.
 */
export function PainelDaPraca({
  worksite,
  bulletin,
  children,
}: {
  worksite: WorksiteResponse;
  /** O boletim GRAVADO da praça; `null` enquanto ninguém montou a medição. */
  bulletin: BulletinResponse | null;
  /** O ato de declarar identidade, montado por quem tem os pacotes das folhas em mãos. */
  children?: ReactNode;
}) {
  const recusa = recusaDaPraca(worksite);
  const total = worksite.plates.length;
  const consolidado = worksite.consolidated;
  const valuation = bulletin?.valuation ?? null;
  return (
    <section className="painel praca-painel" aria-label="Consolidado da praça">
      <h2>Praça {worksite.worksite_name}</h2>
      <p className="dica">
        <span className="mono">{worksite.worksite_key}</span> · {total} folhas ·{" "}
        {consolidado.present ? (
          <>
            consolidado sha256{" "}
            <span
              className="digest"
              title={consolidado.worksite_takeoff_sha256 ?? undefined}
            >
              {shortDigest(consolidado.worksite_takeoff_sha256)}
            </span>
          </>
        ) : (
          "consolidado ainda não montado"
        )}
        .
      </p>

      {recusa === null ? null : (
        <div className="banner-erro" role="alert">
          <p>{recusa.message}</p>
          {recusa.code === null ? null : (
            <p className="mono praca-codigo">{recusa.code}</p>
          )}
        </div>
      )}

      {consolidado.document === null ? null : (
        <div className="praca-folhas">
          <h3>Folhas do consolidado</h3>
          <ul className="praca-lista">
            {consolidado.document.plates.map((referencia) => (
              <li key={referencia.plate_id}>
                <span className="mono">{referencia.plate_id}</span> · pacote{" "}
                <span className="digest" title={referencia.packet_digest}>
                  {shortDigest(referencia.packet_digest)}
                </span>
              </li>
            ))}
          </ul>
          <p className="dica">
            O consolidado <strong>não contém itens</strong>: ele referencia o pacote de
            cada folha por prancha e digest. Cada parcela aponta para o item na folha de
            onde foi lida — o total é explicável por composição, nunca por reextração.
          </p>
        </div>
      )}

      <div className="praca-numeros">
        <h3>Total por código e memória, folha por folha</h3>
        {bulletin === null || valuation === null ? (
          <p className="dica">
            Esta praça ainda não tem boletim montado, e por isso não há número nenhum a
            mostrar aqui. Monte o boletim na etapa seguinte: é ele que traz o total por
            código e a memória de cada parcela, calculados no servidor.
          </p>
        ) : (
          <>
            <p className="total-geral">
              Total da praça: {formatMoneyText(bulletin.total_amount)}
            </p>
            <p className="dica">
              Medição {valuation.period_number} · {valuation.reference_label} · sha256{" "}
              <span className="digest" title={bulletin.valuation_sha256}>
                {shortDigest(bulletin.valuation_sha256)}
              </span>
              . Um boletim <strong>por folha</strong>, com a leitura fundida por
              declaração contando uma vez só.
            </p>
            {worksite.plates.map((folha) => {
              const chave = chaveDoBoletimDaFolha(
                worksite.worksite_key,
                folha.position,
                total,
              );
              const boletim = boletimDaFolha(
                valuation,
                worksite.worksite_key,
                folha,
                total,
              );
              return (
                <div key={folha.plate_id} className="praca-folha-numeros">
                  <h4>
                    {folhaLabel(folha.position, total)} ·{" "}
                    <span className="mono">{folha.plate_id}</span>
                  </h4>
                  {boletim === null ? (
                    <p className="banner-erro" role="alert">
                      O boletim gravado não cobre esta folha (
                      <span className="mono">{chave}</span>): ele foi montado antes de ela
                      entrar na praça. Monte o boletim de novo para medir a praça inteira —
                      nada desta folha é somado aqui enquanto isso.
                    </p>
                  ) : (
                    <>
                      <table className="tabela">
                        <caption>
                          Boletim desta folha, já consolidado por código pelo servidor
                        </caption>
                        <thead>
                          <tr>
                            <th scope="col">Item</th>
                            <th scope="col">Código</th>
                            <th scope="col">Un</th>
                            <th scope="col">Quant.</th>
                            <th scope="col">Total</th>
                          </tr>
                        </thead>
                        <tbody>
                          {boletim.lines.map((line) => (
                            <tr key={line.item_number}>
                              <td>{line.item_number}</td>
                              <td className="mono">{line.code}</td>
                              <td>{unitLabel(line.unit)}</td>
                              <td className="numero">
                                {formatDecimalText(line.quantity)}
                              </td>
                              <td className="numero">{formatMoneyText(line.total)}</td>
                            </tr>
                          ))}
                        </tbody>
                        <tfoot>
                          <tr>
                            <th scope="row" colSpan={4}>
                              Total desta folha
                            </th>
                            <td className="numero">
                              {formatMoneyText(boletim.total_amount)}
                            </td>
                          </tr>
                        </tfoot>
                      </table>
                      <h5>Memória desta folha</h5>
                      <ul className="memoria">
                        {memoriaDaFolha(valuation, chave).map((sheet) => (
                          <li key={sheet.item_number}>
                            <p>
                              <strong>Item {sheet.item_number}</strong> — total{" "}
                              {formatDecimalText(sheet.total_quantity)}
                            </p>
                            <ul>
                              {sheet.blocks.map((block, index) => (
                                <li key={`${sheet.item_number}-${index}`}>
                                  {block.label} ({recipeLabel(block.recipe)}) ={" "}
                                  {formatDecimalText(block.subtotal)}
                                </li>
                              ))}
                            </ul>
                          </li>
                        ))}
                      </ul>
                    </>
                  )}
                </div>
              );
            })}
            <p className="dica">
              Cada número acima é a string que o servidor mandou; nada é somado,
              multiplicado ou arredondado aqui. O mesmo código medido em duas folhas
              aparece nas duas, e a <strong>soma dele entre as folhas</strong> — mais a
              deriva de centavo que o truncamento por linha pode produzir (ADR-0062) — é
              escrita pela PLANILHA GERAL na exportação, com o laudo dela; esta tela não a
              calcula e não a estima.
            </p>
          </>
        )}
      </div>

      <div className="praca-vinculos">
        <h3>Vínculos de identidade declarados</h3>
        {worksite.identity_links.length === 0 ? (
          <p className="dica">
            Nenhum vínculo declarado nesta praça. Sem declaração humana, duas leituras do
            mesmo elemento em folhas diferentes <strong>contam as duas</strong>: o sistema
            não funde por rótulo, unidade nem proximidade, e errar para o lado de somar
            demais é erro que aparece.
          </p>
        ) : (
          <ul className="praca-lista">
            {worksite.identity_links.map((link) => (
              <li
                key={`${link.kept.plate_id}:${link.kept.item_id}:${link.discarded.plate_id}:${link.discarded.item_id}`}
                className="praca-vinculo"
              >
                <p className="praca-selo">
                  <span aria-hidden="true">≡</span> identidade declarada
                </p>
                <p className="mono">
                  {link.kept.plate_id} · {link.kept.item_id}
                </p>
                <p className="dica">a parcela que fica</p>
                <p className="mono">
                  ≡ {link.discarded.plate_id} · {link.discarded.item_id}
                </p>
                <p className="dica">fundida, não contribui</p>
                <p>
                  {link.declared_by ?? "autor não registrado"} ·{" "}
                  {link.declared_at === null
                    ? "instante não registrado"
                    : formatTimestamp(link.declared_at)}
                </p>
                {link.note === null ? null : <p>Nota: {link.note}</p>}
              </li>
            ))}
          </ul>
        )}
        {children}
      </div>
    </section>
  );
}

/**
 * Jornada de medição sobre a API `/v1` autenticada (ADR-0028).
 *
 * A sessão é da casca, não desta jornada: quem lê o OIDC, consome o authorization code
 * (que é de uso único) e renova o token é `App.tsx`. Aqui ela chega pronta — e sem ela
 * nada é chamado, porque toda rota da medição é autenticada e por tenant.
 *
 * `roundId` é a rodada aberta, declarada na URL pela casca (`?rodada=`); vazio é "jornada
 * de medição, nenhuma rodada aberta", que é a tela de escolher ou abrir rodada.
 */
export function MedicaoApp({
  session,
  roundId = "",
  onOpenRound,
}: {
  session: User | null;
  roundId?: string;
  onOpenRound?: (roundId: string) => void;
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

  // Rodada aberta. A URL é a fonte declarada (`?rodada=`), mas quem navega dentro da
  // jornada é esta tela: o estado local segue a prop e avisa a casca ao mudar.
  const [rodada, setRodada] = useState(roundId);
  useEffect(() => setRodada(roundId), [roundId]);

  // Estado servido pela rodada; nada aqui é derivado de cálculo local.
  const [state, setState] = useState<RoundState | null>(null);
  // Versão da rodada: token de concorrência de TODA a cadeia. Ele vem da última resposta
  // lida, e é ele que a próxima mutação cita em `base_version`.
  const [version, setVersion] = useState<number | null>(null);
  const [takeoff, setTakeoff] = useState<TakeoffResponse | null>(null);
  const [overlay, setOverlay] = useState<OverlayResponse | null>(null);
  const [overlayTentativas, setOverlayTentativas] = useState(0);
  const [plateSrc, setPlateSrc] = useState<string | null>(null);
  /**
   * A resposta da prancha, e não só a URL: o `upload_id` dela é o documento cujas páginas o
   * lote de promoção oferece, e o `page_count` é quantas páginas esse documento tem.
   */
  const [plate, setPlate] = useState<PlateResponse | null>(null);
  // A praça (F-046): as folhas da rodada e o consolidado que o servidor deriva delas. A
  // rodada de uma folha lê isto do mesmo jeito e não mostra nada de praça na tela.
  const [worksite, setWorksite] = useState<WorksiteResponse | null>(null);
  /** `plate_id` da folha em foco; vazio é "a primeira folha da praça". */
  const [folhaFocada, setFolhaFocada] = useState("");
  /** Páginas marcadas para virar folha. Começa VAZIA e nunca é preenchida por padrão. */
  const [paginasSelecionadas, setPaginasSelecionadas] = useState<number[]>([]);
  /** Folhas marcadas para a leitura paga. Começa VAZIA, pelo mesmo motivo. */
  const [folhasSelecionadas, setFolhasSelecionadas] = useState<string[]>([]);
  /**
   * O conjunto de códigos de CADA folha, por `plate_id` (F-046 T4d).
   *
   * A folha aberta já vive em `codes`; este mapa existe para a pergunta que só a praça
   * faz — "o que falta nas OUTRAS folhas?" —, e é uma leitura por folha, feita quando a
   * etapa de códigos é aberta. Folha ausente do mapa é "ainda não lida", nunca zero.
   */
  const [codigosPorFolha, setCodigosPorFolha] = useState<Record<string, CodesResponse>>(
    {},
  );
  /**
   * O pacote de takeoff de CADA folha, por `plate_id`. Serve à escolha das duas leituras
   * do vínculo de identidade: o par `(plate_id, item_id)` é o endereço da praça, e sem os
   * itens das duas folhas não há o que endereçar.
   */
  const [pacotesPorFolha, setPacotesPorFolha] = useState<Record<string, TakeoffItem[]>>(
    {},
  );
  /** O vínculo em digitação; `VINCULO_VAZIO` é o normal — nada nasce escolhido. */
  const [vinculo, setVinculo] = useState<RascunhoDeVinculo>(VINCULO_VAZIO);
  /** A prévia do efeito da fusão, calculada pelo SERVIDOR. `null` é "ainda não pedida". */
  const [previaDoVinculo, setPreviaDoVinculo] =
    useState<IdentityLinkPreviewResponse | null>(null);
  const [prevendo, setPrevendo] = useState(false);
  const [suggestions, setSuggestions] = useState<SuggestionsResponse | null>(null);
  const [codes, setCodes] = useState<CodesResponse | null>(null);
  const [bulletin, setBulletin] = useState<BulletinResponse | null>(null);
  const [dossier, setDossier] = useState<DossierResponse | null>(null);

  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [alertMessage, setAlertMessage] = useState<string | null>(null);
  const [revisionConflict, setRevisionConflict] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [openStep, setOpenStep] = useState<EtapaId | null>(null);

  // Escolha e abertura de rodada.
  const [rounds, setRounds] = useState<RoundSummary[] | null>(null);
  const [roundsCursor, setRoundsCursor] = useState<string | null>(null);
  const [roundForm, setRoundForm] = useState(EMPTY_ROUND_FORM);
  // `null` é "ainda não li", e lista vazia é "não há orçamento assinado". Tratar os dois
  // como o mesmo faria a tela afirmar ausência antes de saber.
  const [origens, setOrigens] = useState<ValuationOrigin[] | null>(null);
  const [origemEscolhida, setOrigemEscolhida] = useState<string | null>(null);
  // Nasce em "do zero", que é o caminho que sempre existiu, e só vira a origem por
  // orçamento quando existe pelo menos um ASSINADO para escolher. O padrão segue o dado, e
  // não o otimismo: sem orçamento assinado, oferecer essa origem como padrão esconderia o
  // único caminho que funciona.
  const [origemDoOrcamento, setOrigemDoOrcamento] = useState(false);
  // Reajuste declarado na abertura (F-039). `null` é "sem reajuste", e é o padrão: o ato
  // existe e não se impõe. Só aparece no caminho do orçamento assinado, porque sem
  // contratado não há preço contratual a reajustar.
  const [reajuste, setReajuste] = useState<PriceAdjustmentDraft | null>(null);
  // RE-RA declarada na abertura (F-040). `null` é "sem RE-RA", e é o padrão: não re-ratificar
  // é o caminho normal. Como o reajuste, só no caminho contratado (orçamento assinado).
  const [reRa, setReRa] = useState<AmendmentDraft | null>(null);
  const [catalogFile, setCatalogFile] = useState<File | null>(null);

  // Prancha (upload e leitura automática).
  const [uploadFile, setUploadFile] = useState<File | null>(null);

  // Aprovação e exportação. `confirmandoAprovacao` é o SEGUNDO ato explícito: ele não é
  // preferência guardada, é o estado de um gesto que ainda não terminou, e por isso morre
  // com o componente. Os três desfechos abaixo têm tela ou bloco próprio em vez de virarem
  // mais um alerta: `403` sem nomear papel, portão do domínio com a lista de violações e
  // auditoria reprovada com "nada foi publicado" por extenso.
  const [confirmandoAprovacao, setConfirmandoAprovacao] = useState(false);
  const [exportando, setExportando] = useState(false);
  const [semAcesso, setSemAcesso] = useState(false);
  const [violacoesDeExportacao, setViolacoesDeExportacao] = useState<
    ExportViolation[] | null
  >(null);
  const [auditoriaReprovada, setAuditoriaReprovada] = useState<string[] | null>(null);

  // Revisão do takeoff.
  const [selectedItemId, setSelectedItemId] = useState("");
  const [decision, setDecision] = useState(EMPTY_DECISION);
  /**
   * O croqui que a pessoa está declarando (F-047 T7b). É rascunho de formulário, e não o
   * elo: o elo vive na rodada, e quem o lê é `state.scene_link`.
   */
  const [croquiDeclarado, setCroquiDeclarado] = useState("");
  /**
   * O relatório do último confronto desta sessão. `null` é "ninguém confrontou aqui", e é
   * por isso que a etapa fica idêntica à de antes da feature enquanto ele for `null` — o
   * relatório é do ATO, não da rodada, e nenhuma rota o republica.
   */
  const [confronto, setConfronto] = useState<SceneConfrontationReport | null>(null);
  /** Rascunho da resolução de divergência. Nada nasce pré-marcado. */
  const [resolucao, setResolucao] = useState<{
    choice: DivergenceChoice | "";
    motivo: string;
  }>({ choice: "", motivo: "" });
  const [zoom, setZoom] = useState(MIN_ZOOM);
  const [imageSize, setImageSize] = useState<{ width: number; height: number } | null>(
    null,
  );
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const panOrigin = useRef<PanOrigin | null>(null);
  const [panning, setPanning] = useState(false);
  // Prancha limpa por padrão: nenhuma marcação sobre a imagem que o projetista enviou.
  // Só o item selecionado ganha o retângulo fino, sem número. "Mostrar marcações"
  // revela retângulo + número de todos, para auditoria. Estado de componente, nunca em
  // storage — reabrir a ferramenta volta ao padrão limpo.
  const [mostrarMarcacoes, setMostrarMarcacoes] = useState(false);

  // Códigos.
  const [selectedPendingId, setSelectedPendingId] = useState("");
  const [codeChoice, setCodeChoice] = useState<CodeChoice | null>(null);
  const [codeNote, setCodeNote] = useState("");
  /**
   * A caixa de desfazer um código confirmado (F-045). `null` é o estado normal: desfazer é
   * ato deliberado, e a caixa só existe depois do clique que a abre.
   */
  const [desfazerCaixa, setDesfazerCaixa] = useState<CaixaDeDesfazer | null>(null);
  const [query, setQuery] = useState("");
  const [searchResult, setSearchResult] = useState<CatalogSearchResponse | null>(null);
  // Busca incremental: ela nunca toca `submitting` (cada tecla congelaria a tela inteira)
  // e nunca escreve no alerta global — erro transitório de digitação vira aviso ao lado
  // do campo, do lado de quem está digitando.
  const [buscando, setBuscando] = useState(false);
  const [buscaAviso, setBuscaAviso] = useState<string | null>(null);
  const buscaAbortRef = useRef<AbortController | null>(null);
  const buscaTimerRef = useRef<number | null>(null);
  // Último código confirmado nesta sessão: a decisão colapsa o cartão do item (ele some
  // da lista de pendentes), e sem isto a descrição completa e os chips escolhidos
  // desapareciam da tela no exato momento em que a decisão foi tomada.
  const [ultimoCodigoConfirmado, setUltimoCodigoConfirmado] = useState<{
    itemLabel: string;
    code: string;
    description: string;
    note: string;
  } | null>(null);
  // Cache em memória, por código: descrição completa dos códigos já confirmados
  // (persistentes entre recarregamentos, ao contrário de `ultimoCodigoConfirmado`).
  // `undefined` (chave ausente) = ainda não buscado; `null` = buscado e não encontrado
  // no catálogo desta rodada; nunca busca de novo um código que já está aqui.
  const [assignmentDescriptions, setAssignmentDescriptions] = useState<
    Record<string, string | null>
  >({});

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

  /**
   * Orçamentos que podem originar uma medição (F-036).
   *
   * Observacional: a falha aqui NÃO derruba a listagem de rodadas. Sem a lista, a tela cai
   * na origem por upload, que é o caminho que sempre existiu — perder a comodidade é melhor
   * que perder a jornada.
   */
  const carregarOrigens = useCallback(async () => {
    const token = tokenDaSessao();
    if (token === null) {
      return;
    }
    try {
      const resposta = await listValuationOrigins(token);
      setOrigens(resposta.items);
      if (resposta.items.some((origem) => origem.signature === "signed")) {
        setOrigemDoOrcamento(true);
      }
    } catch {
      setOrigens([]);
    }
  }, [tokenDaSessao]);

  const carregarRodadas = useCallback(async () => {
    const token = tokenDaSessao();
    if (token === null) {
      return;
    }
    setLoading(true);
    try {
      const page = await listRounds(token);
      setRounds(page.items);
      setRoundsCursor(page.next_cursor);
      setAlertMessage(null);
    } catch (error) {
      setAlertMessage(describeError(error));
    } finally {
      setLoading(false);
    }
  }, [tokenDaSessao]);

  const carregarMaisRodadas = async () => {
    const token = tokenDaSessao();
    if (token === null || roundsCursor === null) {
      return;
    }
    setLoading(true);
    try {
      const page = await listRounds(token, { cursor: roundsCursor });
      setRounds((current) => [...(current ?? []), ...page.items]);
      setRoundsCursor(page.next_cursor);
    } catch (error) {
      setAlertMessage(describeError(error));
    } finally {
      setLoading(false);
    }
  };

  const carregarEstado = useCallback(async () => {
    const token = tokenDaSessao();
    if (token === null || rodada === "") {
      return;
    }
    setLoading(true);
    try {
      const nextState = await getRoundState(token, rodada);
      setState(nextState);
      setVersion(nextState.version);
      setRevisionConflict(false);
      setAlertMessage(null);
      // A praça é lida ANTES do resto, e é a ordem que importa: é ela que diz de qual
      // folha as leituras seguintes falam. A leitura é observacional — uma falha aqui não
      // pode derrubar a revisão da folha que já está na tela —, e sem ela a jornada cai no
      // caminho de sempre, o da primeira folha.
      const praca = await leituraObservacional(() => getWorksite(token, rodada));
      setWorksite(praca);
      const aberta = folhaEmFoco(praca, folhaFocada);
      const folha = folhaDaChamada(praca, folhaFocada);
      // Quem sabe se ESTA folha tem pacote é a praça; sem ela (ou com uma folha só), a
      // resposta continua sendo a da rodada, como sempre foi.
      const temPacote = aberta === null ? nextState.takeoff.present : aberta.takeoff_present;
      if (temPacote) {
        setTakeoff(await getTakeoff(token, rodada, folha));
        setCodes(await getCodes(token, rodada, folha));
        setOverlay(
          await leituraObservacional(() => getTakeoffOverlay(token, rodada, folha)),
        );
        setOverlayTentativas(0);
      } else {
        setTakeoff(null);
        setCodes(null);
        setOverlay(null);
      }
      // A URL da imagem é assinada e de curta duração: ela é relida junto com o estado e
      // vai direto no `src`, sem header nenhum e sem nunca aparecer em log.
      const prancha = nextState.plate.present
        ? await leituraObservacional(() => getPlate(token, rodada, folha))
        : null;
      setPlate(prancha);
      setPlateSrc(prancha?.image_url ?? null);
      // A shortlist só é buscada quando já existe na rodada: a primeira leitura
      // **calcula e grava** o artefato, e isso é ato do orçamentista, não efeito colateral
      // de abrir a tela. `suggestions_present` fala da PRIMEIRA folha, então a folha 2 em
      // diante nunca entra aqui: um `GET` dela calcularia e gravaria a shortlist daquela
      // folha sem gesto nenhum, que é exatamente o que a regra da jornada proíbe. Nas
      // demais folhas o cálculo fica atrás do botão que declara o que vai ser gravado.
      setSuggestions(
        folha === undefined && nextState.codes.suggestions_present
          ? await getSuggestions(token, rodada)
          : null,
      );
      setBulletin(
        nextState.bulletin.present ? await getBulletin(token, rodada) : null,
      );
      setDossier(nextState.dossier.present ? await getDossier(token, rodada) : null);
    } catch (error) {
      setAlertMessage(describeError(error));
    } finally {
      setLoading(false);
    }
  }, [folhaFocada, rodada, tokenDaSessao]);

  // Sem sessão nada é chamado: toda rota da medição é autenticada e por tenant, e uma
  // chamada sem token devolveria 401 na tela de quem ainda nem entrou. `autenticado` é
  // booleano de propósito — a renovação silenciosa troca o objeto da sessão, e depender
  // dele recarregaria a rodada a cada renovação.
  useEffect(() => {
    if (!autenticado) {
      return;
    }
    if (rodada === "") {
      void carregarRodadas();
      void carregarOrigens();
      return;
    }
    void carregarEstado();
  }, [autenticado, rodada, carregarEstado, carregarRodadas, carregarOrigens]);

  const abrirRodada = (proxima: string) => {
    setState(null);
    setVersion(null);
    setTakeoff(null);
    setOverlay(null);
    setCodes(null);
    setSuggestions(null);
    setBulletin(null);
    setDossier(null);
    setPlateSrc(null);
    setPlate(null);
    setWorksite(null);
    setFolhaFocada("");
    setPaginasSelecionadas([]);
    setFolhasSelecionadas([]);
    setCodigosPorFolha({});
    setPacotesPorFolha({});
    setVinculo(VINCULO_VAZIO);
    setPreviaDoVinculo(null);
    setOpenStep(null);
    setSelectedItemId("");
    setSelectedPendingId("");
    setAlertMessage(null);
    setRevisionConflict(false);
    setConfirmandoAprovacao(false);
    setSemAcesso(false);
    setViolacoesDeExportacao(null);
    setAuditoriaReprovada(null);
    setRodada(proxima);
    onOpenRound?.(proxima);
  };

  /**
   * A medição seguinte (F-040): abre a rodada `n+1` a partir de uma rodada anterior aprovada.
   *
   * O período NÃO é digitado — é o da rodada anterior mais um, calculado e enviado (decisão 2
   * do pacote de design). Obra, catálogo e contratado vêm da rodada anterior; o corpo só cita
   * `previous_round_id`. Reajuste e RE-RA da rodada seguinte podem ser declarados depois, na
   * própria rodada nova.
   */
  const abrirMedicaoSeguinte = async (round: RoundSummary) => {
    if (submitting) {
      return;
    }
    const token = tokenDaSessao();
    if (token === null) {
      return;
    }
    setSubmitting(true);
    setAlertMessage(null);
    try {
      const created = await createRound(token, {
        ...EMPTY_ROUND_FORM,
        previousRoundId: round.round_id,
        referenceLabel: `Medição ${round.period_number + 1} — ${round.worksite_name}`,
        periodNumber: String(round.period_number + 1),
      });
      setToast("Medição seguinte aberta a partir da rodada anterior aprovada.");
      abrirRodada(created.round_id);
    } catch (error) {
      setAlertMessage(describeError(error));
    } finally {
      setSubmitting(false);
    }
  };

  /**
   * Abre a rodada nova: o catálogo sobe pelo presign (PUT direto no armazenamento) e a
   * rodada nasce com ele instalado. O catálogo é imutável na rodada — trocar de catálogo é
   * abrir outra —, e por isso ele é escolhido aqui e em nenhum outro lugar da jornada.
   */
  const criarRodada = async () => {
    const token = tokenDaSessao();
    if (token === null) {
      return;
    }
    setSubmitting(true);
    setAlertMessage(null);
    try {
      if (origemDoOrcamento) {
        if (origemEscolhida === null) {
          return;
        }
        // Obra, catálogo e contratado vêm do conteúdo assinado; declará-los aqui é recusado
        // pelo servidor, e é por isso que o corpo não os leva.
        const problema = reajusteIssue(reajuste);
        if (problema !== null) {
          setAlertMessage(problema);
          return;
        }
        const problemaReRa = reRaIssue(reRa);
        if (problemaReRa !== null) {
          setAlertMessage(problemaReRa);
          return;
        }
        const created = await createRound(token, {
          ...roundForm,
          estimateRoundId: origemEscolhida,
          priceAdjustment: reajuste ?? undefined,
          amendment: reRa ?? undefined,
        });
        setRoundForm(EMPTY_ROUND_FORM);
        setOrigemEscolhida(null);
        setReajuste(null);
        setReRa(null);
        setToast(
          reRa !== null
            ? "Rodada aberta com o contratado re-ratificado."
            : reajuste === null
              ? "Rodada aberta com o contratado do orçamento assinado."
              : "Rodada aberta com o contratado reajustado.",
        );
        abrirRodada(created.round_id);
        return;
      }
      if (catalogFile === null) {
        return;
      }
      const keyErro = worksiteKeyError(roundForm.worksiteKey);
      if (keyErro !== null) {
        setAlertMessage(keyErro);
        return;
      }
      const catalogUploadId = await uploadCatalog(token, catalogFile);
      const created = await createRound(token, {
        ...roundForm,
        catalogUploadId,
      });
      setRoundForm(EMPTY_ROUND_FORM);
      setCatalogFile(null);
      setToast("Rodada aberta com o catálogo instalado.");
      abrirRodada(created.round_id);
    } catch (error) {
      setAlertMessage(describeError(error));
    } finally {
      setSubmitting(false);
    }
  };

  /**
   * Envia o PDF da prancha e pede a leitura da legenda. São dois atos da rodada — associar
   * a prancha e enfileirar a chamada paga —, cada um com a sua chave de idempotência e a
   * sua versão-base; o gesto do orçamentista é um só, e o consentimento é o próprio
   * clique, declarado no aviso ao lado do botão.
   */
  const enviarPrancha = async () => {
    const token = tokenDaSessao();
    if (token === null || uploadFile === null || version === null) {
      return;
    }
    setSubmitting(true);
    setAlertMessage(null);
    try {
      const uploadId = await uploadPlateFile(token, uploadFile);
      const plate = await associatePlate(token, rodada, uploadId, version);
      aplicarVersao(plate.version);
      setUploadFile(null);
      try {
        const extraction = await createPlateExtraction(token, rodada, plate.version);
        aplicarVersao(extraction.version);
        setToast("Prancha enviada; a leitura automática da legenda foi enfileirada.");
      } catch (error) {
        // A prancha já está na rodada: a leitura recusada não desfaz o envio, e a etapa
        // Prancha passa a oferecer o disparo de novo em vez de pedir outro upload.
        setAlertMessage(describeError(error));
      }
      await atualizarEstado();
    } catch (error) {
      setAlertMessage(describeError(error));
    } finally {
      setSubmitting(false);
    }
  };

  /**
   * Promove EM LOTE as páginas marcadas a folhas da praça (F-046 T4).
   *
   * Um ato, uma confirmação: a seleção é toda enviada de uma vez, e o servidor apura o teto
   * da praça e a página repetida sobre o lote inteiro antes da primeira folha. Promover
   * **não** dispara leitura nenhuma — a chamada paga é o ato seguinte, com o número de
   * folhas escrito no botão dele.
   */
  const acrescentarFolhas = async () => {
    const token = tokenDaSessao();
    if (
      token === null ||
      version === null ||
      plate === null ||
      paginasSelecionadas.length === 0
    ) {
      return;
    }
    setSubmitting(true);
    setAlertMessage(null);
    try {
      const paginas = [...paginasSelecionadas].sort((left, right) => left - right);
      const resposta = await appendPlates(
        token,
        rodada,
        plate.upload_id,
        paginas,
        version,
      );
      aplicarVersao(resposta.version);
      setPaginasSelecionadas([]);
      setToast(
        `${resposta.appended.length} ${
          resposta.appended.length === 1 ? "folha acrescentada" : "folhas acrescentadas"
        } à praça; a leitura da legenda ainda não foi disparada.`,
      );
      await atualizarEstado();
    } catch (error) {
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
   * Enfileira a leitura das folhas marcadas: uma chamada paga POR FOLHA.
   *
   * O número de folhas do lote é a autorização de quem paga, e ele vai no corpo e volta
   * declarado na resposta — é a última fronteira em que esse número pode ser conferido
   * antes de a primeira chamada acontecer.
   */
  const lerFolhasSelecionadas = async () => {
    const token = tokenDaSessao();
    if (token === null || version === null || folhasSelecionadas.length === 0) {
      return;
    }
    setSubmitting(true);
    setAlertMessage(null);
    try {
      const resposta = await createPlatesExtraction(
        token,
        rodada,
        folhasSelecionadas,
        version,
      );
      aplicarVersao(resposta.version);
      setFolhasSelecionadas([]);
      setToast(
        `Leitura enfileirada para ${resposta.plate_count} ${
          resposta.plate_count === 1 ? "folha" : "folhas"
        } da praça.`,
      );
      await atualizarEstado();
    } catch (error) {
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
   * Outra origem: um PDF diferente vira mais uma folha da MESMA praça (F-046).
   *
   * A praça não é um arquivo — detalhe que veio em PDF separado entra pela mesma porta e
   * vira mais uma folha. Ao contrário do primeiro envio, este ato **não** dispara leitura
   * nenhuma: a folha nasce sem pacote e a chamada paga sai no ato de ler, onde o número de
   * folhas está escrito no botão. A rota singular da extração é da PRIMEIRA folha, e
   * chamá-la aqui releria a folha errada.
   */
  const enviarOutraFolha = async () => {
    const token = tokenDaSessao();
    if (token === null || uploadFile === null || version === null) {
      return;
    }
    setSubmitting(true);
    setAlertMessage(null);
    try {
      const uploadId = await uploadPlateFile(token, uploadFile);
      const folha = await associatePlate(token, rodada, uploadId, version);
      aplicarVersao(folha.version);
      setUploadFile(null);
      setToast(
        "Folha acrescentada à praça; a leitura da legenda ainda não foi disparada.",
      );
      await atualizarEstado();
    } catch (error) {
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

  /** Marca ou desmarca uma página do lote; nada aqui marca por conta própria. */
  const alternarPagina = (pagina: number) => {
    setPaginasSelecionadas((atual) =>
      atual.includes(pagina)
        ? atual.filter((numero) => numero !== pagina)
        : [...atual, pagina],
    );
  };

  /** Marca ou desmarca uma folha do lote de leitura; cada marca é uma chamada paga. */
  const alternarFolha = (plateId: string) => {
    setFolhasSelecionadas((atual) =>
      atual.includes(plateId)
        ? atual.filter((id) => id !== plateId)
        : [...atual, plateId],
    );
  };

  /** Dispara a leitura de uma prancha já associada, sem reenviar o documento. */
  const tentarExtracaoNovamente = async () => {
    const token = tokenDaSessao();
    if (token === null || version === null) {
      return;
    }
    setSubmitting(true);
    setAlertMessage(null);
    try {
      const extraction = await createPlateExtraction(token, rodada, version);
      aplicarVersao(extraction.version);
      setToast("Nova leitura automática enfileirada.");
      await atualizarEstado();
    } catch (error) {
      // O conflito tem banner próprio, com o botão de recarregar e o formulário
      // preservado; repetir a frase no alerta comum só empilharia ruído.
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

  /** Um ciclo do poll: relê o estado e, se a leitura acabou de publicar o takeoff,
   * carrega o pacote e leva a tela direto para a revisão — sem clique nenhum. */
  const pollExtracao = useCallback(async () => {
    const token = tokenDaSessao();
    if (token === null || rodada === "") {
      return;
    }
    try {
      const nextState = await getRoundState(token, rodada);
      setState(nextState);
      setVersion(nextState.version);
      if (
        nextState.extraction.status !== "queued" &&
        nextState.extraction.status !== "running" &&
        nextState.takeoff.present
      ) {
        // A folha que acabou de ser lida muda o estado da praça: ela é relida PRIMEIRO,
        // porque é dela que sai a folha que as leituras seguintes nomeiam.
        const praca = await leituraObservacional(() => getWorksite(token, rodada));
        setWorksite(praca);
        const aberta = folhaEmFoco(praca, folhaFocada);
        const folha = folhaDaChamada(praca, folhaFocada);
        if (aberta === null || aberta.takeoff_present) {
          setTakeoff(await getTakeoff(token, rodada, folha));
          setCodes(await getCodes(token, rodada, folha));
          setOverlay(
            await leituraObservacional(() => getTakeoffOverlay(token, rodada, folha)),
          );
          setOverlayTentativas(0);
        }
        const prancha = await leituraObservacional(() => getPlate(token, rodada, folha));
        setPlate(prancha);
        setPlateSrc(prancha?.image_url ?? null);
        setOpenStep("revisao");
      }
    } catch (error) {
      setAlertMessage(describeError(error));
    }
  }, [folhaFocada, rodada, tokenDaSessao]);

  // Poll do estado a cada ~3s enquanto a leitura automática está na fila ou rodando; para
  // sozinho assim que ela fecha (`done` ou `failed`), porque a condição do efeito deixa de
  // valer no próximo render.
  const extracaoEmVoo =
    state?.extraction.status === "queued" || state?.extraction.status === "running";
  useEffect(() => {
    if (!extracaoEmVoo) {
      return;
    }
    const timer = setInterval(() => void pollExtracao(), EXTRACTION_POLL_MS);
    return () => clearInterval(timer);
  }, [extracaoEmVoo, pollExtracao]);

  const atualizarOverlay = useCallback(async () => {
    const token = tokenDaSessao();
    if (token === null || rodada === "") {
      return;
    }
    try {
      setOverlay(
        await getTakeoffOverlay(token, rodada, folhaDaChamada(worksite, folhaFocada)),
      );
    } catch (error) {
      setAlertMessage(describeError(error));
    }
  }, [folhaFocada, rodada, tokenDaSessao, worksite]);

  // Overlay vencido é consequência normal de uma decisão (ADR-0030): o desenho é
  // reconstruído por comando de fila, e até lá a tela mostra o anterior MARCADO. O poll
  // acompanha o re-render, com teto — sem worker o desenho fica vencido, e isso precisa
  // aparecer como estado, não como tráfego infinito.
  /**
   * A folha em foco é a PRIMEIRA da praça? Só ela tem re-render de overlay em fila
   * (limitação declarada da F-046 T4c: o comando desenha `takeoff_packet_json` e ainda
   * não conhece a praça). Nas demais, o desenho fica vencido para sempre — e esperar por
   * ele seria tráfego que nunca vira resposta.
   */
  const folhaComRerender = (folhaEmFoco(worksite, folhaFocada)?.position ?? 1) === 1;
  const overlayVencido = overlay !== null && overlay.stale && folhaComRerender;
  useEffect(() => {
    if (!overlayVencido || overlayTentativas >= OVERLAY_POLL_MAX) {
      return;
    }
    const timer = setTimeout(() => {
      setOverlayTentativas((current) => current + 1);
      void atualizarOverlay();
    }, OVERLAY_POLL_MS);
    return () => clearTimeout(timer);
  }, [overlayVencido, overlayTentativas, atualizarOverlay]);

  // Zoom pela roda precisa de listener não passivo: sem `preventDefault` a página rola
  // junto e o desenho foge da mão.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (canvas === null) {
      return;
    }
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      setZoom((current) => zoomAfterWheel(current, event.deltaY));
    };
    canvas.addEventListener("wheel", onWheel, { passive: false });
    return () => canvas.removeEventListener("wheel", onWheel);
    // O canvas só existe na etapa de revisão: a etapa visível entra nas dependências
    // para o listener nascer junto com o elemento, e não uma navegação depois.
  }, [takeoff, openStep]);

  // Descrição completa de cada código já confirmado, para a lista persistente de
  // decisões sobreviver ao recarregamento (ao contrário de `ultimoCodigoConfirmado`,
  // que só existe nesta sessão). Busca por código exato no catálogo desta rodada; nunca
  // repete a busca de um código que já está no cache (achado ou não achado).
  useEffect(() => {
    const token = tokenDaSessao();
    if (token === null || rodada === "") {
      return;
    }
    const confirmedCodes = (codes?.assignments?.assignments ?? [])
      .filter(isConfirmedWithCode)
      .map((assignment) => assignment.code);
    const pendentes = Array.from(new Set(confirmedCodes)).filter(
      (code) => !(code in assignmentDescriptions),
    );
    if (pendentes.length === 0) {
      return;
    }
    let cancelado = false;
    void (async () => {
      for (const code of pendentes) {
        let description: string | null;
        try {
          const response = await searchCatalog(
            token,
            rodada,
            codeSearchTerm(code),
            20,
          );
          // Casamento pelo código EXATO: a busca pode devolver vários candidatos com o
          // mesmo prefixo, e mostrar a descrição de um código parecido seria mentir
          // sobre o que este código específico inclui.
          description = response.results.find((result) => result.code === code)?.description ?? null;
        } catch {
          description = null;
        }
        if (cancelado) {
          return;
        }
        setAssignmentDescriptions((current) => ({ ...current, [code]: description }));
      }
    })();
    return () => {
      cancelado = true;
    };
  }, [codes, assignmentDescriptions, rodada, tokenDaSessao]);

  // Busca enquanto se digita, com debounce e limiar (`consultaIncremental`). A resposta
  // que chega depois de outra tecla é descartada — lista de catálogo trocando sozinha por
  // ordem de rede seria pior que não ter busca incremental.
  useEffect(() => {
    const token = tokenDaSessao();
    const consulta = consultaIncremental(query);
    if (consulta === null || token === null || rodada === "") {
      if (buscaTimerRef.current !== null) {
        window.clearTimeout(buscaTimerRef.current);
        buscaTimerRef.current = null;
      }
      buscaAbortRef.current?.abort();
      buscaAbortRef.current = null;
      setBuscando(false);
      setBuscaAviso(null);
      // Caixa esvaziada limpa a lista; caixa só encurtada mantém o último resultado,
      // que ainda é o que o servidor respondeu para o que está escrito antes.
      if (query.trim() === "") {
        setSearchResult(null);
      }
      return;
    }
    const timer = window.setTimeout(() => {
      buscaTimerRef.current = null;
      buscaAbortRef.current?.abort();
      const controller = new AbortController();
      buscaAbortRef.current = controller;
      setBuscando(true);
      void (async () => {
        try {
          const response = await searchCatalog(token, rodada, consulta, 20, {
            signal: controller.signal,
          });
          if (controller.signal.aborted) {
            return;
          }
          setSearchResult(response);
          setBuscaAviso(null);
        } catch (error) {
          if (isAbortError(error)) {
            return;
          }
          setBuscaAviso(describeError(error));
        } finally {
          // Só a consulta ainda corrente desliga o indicador: a que foi abortada por uma
          // tecla mais nova não pode apagar o "Buscando…" da que a substituiu.
          if (buscaAbortRef.current === controller) {
            buscaAbortRef.current = null;
            setBuscando(false);
          }
        }
      })();
    }, BUSCA_DEBOUNCE_MS);
    buscaTimerRef.current = timer;
    return () => window.clearTimeout(timer);
  }, [query, rodada, tokenDaSessao]);

  const jornada = useMemo(() => derivarEtapas(state, worksite), [state, worksite]);
  const etapaVisivel: EtapaId | "rodada" = openStep === null ? "rodada" : openStep;
  const overlayEstado = overlayFreshness(overlay);

  // A praça (F-046). Tudo aqui é derivado do que o servidor mandou; com UMA folha, `praca`
  // é falso e nada disto aparece na tela — a rodada de uma prancha continua a de sempre.
  const folhas = worksite?.plates ?? [];
  const praca = pracaPlural(worksite);
  const folhaAtual = folhaEmFoco(worksite, folhaFocada);
  /** A folha que TODA chamada desta tela nomeia; `undefined` é a primeira folha. */
  const folhaDaVez = folhaDaChamada(worksite, folhaFocada);
  /**
   * A folha em foco é a que o pacote em mãos descreve? O pacote DECLARA de qual folha ele
   * é, e é essa comparação que decide — nunca a posição na praça. Sob o cabeçalho de uma
   * folha, a imagem e os itens de outra seriam uma afirmação falsa com cara de evidência,
   * e a comparação continua valendo para pegar a leitura que ainda está em voo.
   */
  const folhaServida =
    takeoff !== null &&
    folhaAtual !== null &&
    folhaAtual.plate_id === takeoff.packet.plate_id;
  const folhasSemPacote = folhas.filter((folha) => !folha.takeoff_present);
  const paginasDoDocumento = plate?.page_count ?? state?.plate.page_count ?? 0;
  const paginasJaPromovidas = paginasPromovidas(
    worksite,
    plate?.source_sha256 ?? state?.plate.source_sha256 ?? null,
  );

  const items = takeoff?.packet.items ?? [];
  const selectedItem = items.find((item) => item.id === selectedItemId) ?? null;
  /**
   * O elo desta rodada. Rodada lida antes da F-047 responde sem o campo, e a ausência de
   * campo diz o mesmo que a ausência declarada: ninguém ligou esta rodada a croqui nenhum.
   */
  const elo: SceneLinkState = state?.scene_link ?? { present: false };
  const divergenciasAbertas = itensComDivergenciaAberta(items);
  const pendingItems = codes?.pending_items ?? [];
  /** Os códigos já confirmados do item selecionado — o pacote que está sendo montado. */
  const pacoteDoItem = (codes?.assignments?.assignments ?? []).filter(
    (assignment) =>
      assignment.item_id === selectedPendingId &&
      assignment.status === "confirmed",
  );
  const selectedPending =
    pendingItems.find((item) => item.item_id === selectedPendingId) ?? null;

  const atualizarEstado = useCallback(async () => {
    const token = tokenDaSessao();
    if (token === null || rodada === "") {
      return;
    }
    try {
      const nextState = await getRoundState(token, rodada);
      setState(nextState);
      setVersion(nextState.version);
      // A praça anda junto com a rodada: acrescentar folha e enfileirar leitura mudam as
      // folhas sem mudar o pacote de takeoff que a revisão já tem em mãos.
      setWorksite(await leituraObservacional(() => getWorksite(token, rodada)));
    } catch (error) {
      setAlertMessage(describeError(error));
    }
  }, [rodada, tokenDaSessao]);

  /**
   * O que falta codificar em CADA folha — uma leitura por folha, só quando a etapa de
   * códigos está aberta numa praça plural (F-046 T4d).
   *
   * A etapa de código é por prancha, e sem esta varredura a orçamentista veria "nada
   * pendente" na folha aberta sem saber que outra folha trava o boletim da praça. Ela é
   * feita à medida — o teto de folhas por rodada é 12 — e refeita quando a rodada anda
   * (`version`), porque é uma decisão gravada que muda o que falta. `GET
   * .../code-assignments` só LÊ: ele não calcula nem grava artefato nenhum, ao contrário
   * da shortlist.
   */
  useEffect(() => {
    const token = tokenDaSessao();
    if (token === null || rodada === "" || !praca || etapaVisivel !== "codigos") {
      return;
    }
    let cancelado = false;
    void (async () => {
      const lidas: Record<string, CodesResponse> = {};
      for (const folha of worksite?.plates ?? []) {
        if (!folha.takeoff_present) {
          continue;
        }
        const resposta = await leituraObservacional(() =>
          getCodes(token, rodada, folha.plate_id),
        );
        if (resposta !== null) {
          lidas[folha.plate_id] = resposta;
        }
      }
      if (!cancelado) {
        setCodigosPorFolha(lidas);
      }
    })();
    return () => {
      cancelado = true;
    };
  }, [etapaVisivel, praca, rodada, tokenDaSessao, version, worksite]);

  /**
   * Os itens de cada folha, para o vínculo de identidade poder ser endereçado.
   *
   * O endereço da praça é o par `(plate_id, item_id)`, e escolher as duas leituras exige
   * ter os itens das DUAS folhas em mãos — o pacote da folha aberta não basta. A varredura
   * roda só na etapa da praça, pelo mesmo motivo da de cima: é leitura sob demanda, nunca
   * efeito colateral de abrir a jornada.
   */
  useEffect(() => {
    const token = tokenDaSessao();
    if (token === null || rodada === "" || !praca || etapaVisivel !== "praca") {
      return;
    }
    let cancelado = false;
    void (async () => {
      const lidos: Record<string, TakeoffItem[]> = {};
      for (const folha of worksite?.plates ?? []) {
        if (!folha.takeoff_present) {
          continue;
        }
        const resposta = await leituraObservacional(() =>
          getTakeoff(token, rodada, folha.plate_id),
        );
        if (resposta !== null) {
          lidos[folha.plate_id] = resposta.packet.items;
        }
      }
      if (!cancelado) {
        setPacotesPorFolha(lidos);
      }
    })();
    return () => {
      cancelado = true;
    };
  }, [etapaVisivel, praca, rodada, tokenDaSessao, version, worksite]);

  const abrirEtapa = (etapa: Etapa) => {
    if (etapa.status === "blocked") {
      return;
    }
    setOpenStep(etapa.id);
  };

  /**
   * Trocar a folha em foco: a jornada inteira passa a falar DAQUELA prancha.
   *
   * O que muda de verdade é a recarga — `carregarEstado` depende de `folhaFocada`, então
   * imagem, overlay, itens e conjunto de códigos são relidos com a folha nova. O que fica
   * para trás é a seleção: um item escolhido na folha anterior não existe nesta, e deixar
   * a seleção em pé abriria um formulário que promete decidir item de outra prancha.
   */
  const focarFolha = (plateId: string) => {
    if (plateId === folhaAtual?.plate_id) {
      return;
    }
    setFolhaFocada(plateId);
    setSelectedItemId("");
    setSelectedPendingId("");
    setDecision(EMPTY_DECISION);
    setCodeChoice(null);
    setCodeNote("");
    setDesfazerCaixa(null);
    setImageSize(null);
    setUltimoCodigoConfirmado(null);
  };

  const selecionarItem = (item: TakeoffItem) => {
    setSelectedItemId(item.id);
    setDecision(EMPTY_DECISION);
    // O rascunho da resolução é do ITEM que estava aberto: carregá-lo para o próximo faria
    // uma escolha feita sobre um par de números ser registrada sobre outro.
    setResolucao({ choice: "", motivo: "" });
  };

  const startPan = (event: ReactPointerEvent<HTMLDivElement>) => {
    const canvas = canvasRef.current;
    if (canvas === null || event.button !== 0) {
      return;
    }
    panOrigin.current = {
      pointerX: event.clientX,
      pointerY: event.clientY,
      scrollLeft: canvas.scrollLeft,
      scrollTop: canvas.scrollTop,
    };
    setPanning(true);
  };

  const movePan = (event: ReactPointerEvent<HTMLDivElement>) => {
    const canvas = canvasRef.current;
    const origin = panOrigin.current;
    if (canvas === null || origin === null) {
      return;
    }
    const offset = panScrollOffset(origin, event.clientX, event.clientY);
    canvas.scrollLeft = offset.scrollLeft;
    canvas.scrollTop = offset.scrollTop;
  };

  const endPan = () => {
    panOrigin.current = null;
    setPanning(false);
  };

  const quantidadeParaServidor = parseQuantityInput(decision.quantity);
  const quantidadeInvalida =
    decision.quantity.trim().length > 0 && quantidadeParaServidor === null;
  const exigeQuantidade =
    decision.action === "confirm" && selectedItem?.status === "ambiguous";
  const decisaoBloqueada =
    submitting ||
    selectedItem === null ||
    version === null ||
    decision.action === "" ||
    quantidadeInvalida ||
    (exigeQuantidade && quantidadeParaServidor === null);

  const enviarDecisao = async () => {
    const token = tokenDaSessao();
    if (
      token === null ||
      selectedItem === null ||
      takeoff === null ||
      version === null ||
      decision.action === ""
    ) {
      return;
    }
    setSubmitting(true);
    setAlertMessage(null);
    try {
      // Correção de dado só viaja com `confirm`: uma quantidade digitada e depois
      // abandonada ao trocar para "rejeitar" alteraria o item que está sendo descartado.
      const correcoes =
        decision.action === "confirm"
          ? {
              quantity: quantidadeParaServidor ?? undefined,
              unit: decision.unit,
              itemNote: decision.itemNote,
            }
          : {};
      // A rota é só-lote. Esta tela ainda decide um item por vez, então manda um lote de
      // um — o contrato é o mesmo, a UX de decidir a legenda inteira de uma vez existe
      // hoje só no orçamento-base. Dívida declarada, não esquecimento.
      const response = await postTakeoffDecision(token, rodada, {
        baseVersion: version,
        // A folha é do ATO: este lote revisa a legenda DESTA prancha.
        plateId: folhaDaVez,
        decisions: [
          {
            itemId: selectedItem.id,
            action: decision.action,
            note: decision.note,
            ...correcoes,
          },
        ],
      });
      aplicarVersao(response.version);
      setTakeoff(response);
      // O overlay é consequência da decisão, não parte dela: a resposta já declara que o
      // desenho corrente é do pacote anterior, e a tela passa a dizer isso.
      setOverlay((current) =>
        current === null
          ? current
          : { ...current, ...response.overlay, packet_sha256: response.packet_sha256 },
      );
      setOverlayTentativas(0);
      setDecision(EMPTY_DECISION);
      setRevisionConflict(false);
      setToast(
        `${selectedItem.label}: item ${
          decision.action === "confirm" ? "confirmado" : "rejeitado"
        }. Faltam ${response.pending} de ${response.items}.`,
      );
      await atualizarEstado();
      setCodes(await getCodes(token, rodada, folhaDaVez));
    } catch (error) {
      // O conflito tem banner próprio, com o botão de recarregar e o formulário
      // preservado; repetir a frase no alerta comum só empilharia ruído.
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
   * Declara — ou troca — o croqui aprovado que alimenta esta rodada (F-047 T7b).
   *
   * O ato é sobre a RODADA, não sobre o takeoff: ele não confronta nada e não muda número
   * nenhum. Confrontar é o gesto seguinte, e é separado de propósito — declarar o elo
   * errado e descobrir isso depois de o pacote inteiro ter sido reescrito seria pior do que
   * dois cliques.
   */
  const declararElo = async () => {
    const token = tokenDaSessao();
    const job = croquiDeclarado.trim();
    if (token === null || version === null || job.length === 0) {
      return;
    }
    setSubmitting(true);
    setAlertMessage(null);
    try {
      const proximo = await postSceneLink(token, rodada, {
        jobId: job,
        baseVersion: version,
      });
      setState(proximo);
      aplicarVersao(proximo.version);
      setCroquiDeclarado("");
      // O relatório é do confronto ANTERIOR, contra outro pacote: mantê-lo na tela depois
      // da troca do elo faria a pessoa ler o desfecho de um croqui que não é mais o desta
      // rodada.
      setConfronto(null);
      setRevisionConflict(false);
      setToast("Croqui aprovado declarado nesta rodada.");
    } catch (error) {
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
   * Confronta o takeoff com o `quantitativos.csv` do croqui declarado (F-047 T7b).
   *
   * O gesto é explícito porque ele GRAVA: alimenta item sem quantidade e abre divergência
   * onde os dois números discordam. O texto ao lado do botão declara isso antes do clique,
   * como o cálculo da shortlist.
   */
  const confrontarComACena = async () => {
    const token = tokenDaSessao();
    if (token === null || version === null) {
      return;
    }
    setSubmitting(true);
    setAlertMessage(null);
    try {
      const response = await postSceneQuantities(token, rodada, version);
      aplicarVersao(response.version);
      setTakeoff(response);
      setConfronto(response.scene_confrontation);
      // Confronto que não mudou nada não grava revisão nova, e por isso não devolve
      // overlay: sem pacote novo não há desenho a envelhecer, e declará-lo vencido aqui
      // seria uma marca sem fato atrás.
      const idade = response.overlay;
      if (idade !== undefined) {
        setOverlay((current) =>
          current === null
            ? current
            : { ...current, ...idade, packet_sha256: response.packet_sha256 },
        );
        setOverlayTentativas(0);
      }
      setRevisionConflict(false);
      setToast(
        `Confronto concluído: ${response.scene_confrontation.fed} alimentado(s) pela cena, ` +
          `${response.scene_confrontation.divergences_recorded} divergência(s) gravada(s), ` +
          `${response.scene_confrontation.unchanged} sem mudança.`,
      );
      await atualizarEstado();
    } catch (error) {
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
   * Registra a decisão humana que resolve uma divergência (F-047 T7b).
   *
   * Duas escolhas, e só duas: a rota não aceita uma terceira quantidade, e a tela também
   * não a oferece. O número preterido continua gravado — resolver não é sobrescrever.
   */
  const resolverDivergencia = async () => {
    const token = tokenDaSessao();
    if (
      token === null ||
      selectedItem === null ||
      version === null ||
      resolucao.choice === ""
    ) {
      return;
    }
    setSubmitting(true);
    setAlertMessage(null);
    try {
      const response = await postDivergenceResolution(token, rodada, {
        itemId: selectedItem.id,
        choice: resolucao.choice,
        baseVersion: version,
        note: resolucao.motivo,
      });
      aplicarVersao(response.version);
      setTakeoff(response);
      setOverlay((current) =>
        current === null
          ? current
          : { ...current, ...response.overlay, packet_sha256: response.packet_sha256 },
      );
      setOverlayTentativas(0);
      setResolucao({ choice: "", motivo: "" });
      setRevisionConflict(false);
      setToast(
        `${selectedItem.label}: divergência resolvida — ` +
          `${divergenceChoiceLabel(resolucao.choice)}.`,
      );
      await atualizarEstado();
    } catch (error) {
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
   * Primeira leitura da shortlist: ela CALCULA e grava o artefato na rodada, então fica
   * atrás de um gesto que declara isso. Não avança a versão da rodada — a shortlist é
   * artefato derivado, e um `GET` não é ato humano.
   */
  const calcularShortlist = async () => {
    const token = tokenDaSessao();
    if (token === null) {
      return;
    }
    setSubmitting(true);
    setAlertMessage(null);
    try {
      const response = await getSuggestions(token, rodada, folhaDaVez);
      setSuggestions(response);
      // Híbrida ou lexical é o que a resposta declara (`matching`), não o que a tela
      // supõe: o artefato pode ter sido gravado por outra sessão.
      const braco = response.matching === "hybrid" ? "híbrida" : "lexical";
      setToast(
        response.computed
          ? `Shortlist ${braco} calculada e gravada na rodada.`
          : `Shortlist ${braco} carregada da rodada.`,
      );
      await atualizarEstado();
    } catch (error) {
      setAlertMessage(describeError(error));
    } finally {
      setSubmitting(false);
    }
  };

  /**
   * Recompute explícito da shortlist. Sobrescreve o artefato da rodada, então é gesto do
   * orçamentista e nunca efeito de abrir a tela: ele cita `base_version`, avança a rodada
   * e é recusado quando a shortlist carrega refino pago (`SUGGESTIONS_ALREADY_REFINED`),
   * em vez de perder o lineage da chamada paga.
   */
  const recalcularShortlist = async () => {
    const token = tokenDaSessao();
    if (token === null || version === null) {
      return;
    }
    setSubmitting(true);
    setAlertMessage(null);
    try {
      const response = await postSuggestionsRecompute(token, rodada, version);
      aplicarVersao(response.version);
      setSuggestions(response);
      setToast(
        response.matching === "hybrid"
          ? "Shortlist híbrida recalculada e regravada na rodada."
          : "Shortlist lexical recalculada e regravada na rodada.",
      );
      await atualizarEstado();
    } catch (error) {
      // O conflito tem banner próprio, com o botão de recarregar e o formulário
      // preservado; repetir a frase no alerta comum só empilharia ruído.
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

  /** Busca pedida por Enter ou pelo botão; mesmo braço lexical da digitação. */
  const buscarNoCatalogo = async () => {
    const token = tokenDaSessao();
    if (token === null) {
      return;
    }
    // Cancela a busca em voo: chegando depois, ela sobrescreveria a que acabou de ser
    // pedida.
    if (buscaTimerRef.current !== null) {
      window.clearTimeout(buscaTimerRef.current);
      buscaTimerRef.current = null;
    }
    buscaAbortRef.current?.abort();
    buscaAbortRef.current = null;
    setBuscando(false);
    setBuscaAviso(null);
    setSubmitting(true);
    setAlertMessage(null);
    try {
      setSearchResult(await searchCatalog(token, rodada, query));
    } catch (error) {
      setSearchResult(null);
      setAlertMessage(describeError(error));
    } finally {
      setSubmitting(false);
    }
  };

  const divergenciaDeUnidade =
    selectedPending !== null &&
    codeChoice !== null &&
    unidadesDivergem(selectedPending.unit, codeChoice);
  const notaObrigatoria = divergenciaDeUnidade;

  const decidirCodigo = async (action: "confirm" | "reject") => {
    const token = tokenDaSessao();
    if (token === null || selectedPending === null || version === null) {
      return;
    }
    setSubmitting(true);
    setAlertMessage(null);
    try {
      const response = await postCodeDecision(token, rodada, {
        itemId: selectedPending.item_id,
        action,
        baseVersion: version,
        // `item_id` só é único DENTRO do pacote de uma folha (ADR-0057, decisão 5): sem a
        // folha junto, duas prancha que cunharam o mesmo id seriam indistinguíveis.
        plateId: folhaDaVez,
        code: action === "confirm" ? codeChoice?.code : undefined,
        note: codeNote,
      });
      aplicarVersao(response.version);
      // Captura o código e a descrição escolhidos ANTES de limpar `codeChoice`: é o
      // único lugar onde a descrição completa deste código está disponível na tela, já
      // que a lista de itens pendentes não vai mais mostrar este item confirmado.
      if (action === "confirm" && codeChoice !== null) {
        setUltimoCodigoConfirmado({
          itemLabel: selectedPending.label,
          code: codeChoice.code,
          description: codeChoice.description,
          note: codeNote.trim(),
        });
      }
      setCodes(response);
      setCodeChoice(null);
      setCodeNote("");
      // O item SEGUE selecionado depois de confirmar: o elemento pode disparar mais de um
      // serviço, e limpar a seleção obrigaria a reencontrá-lo na lista a cada código. A
      // rejeição encerra o item sozinha, e aí sim a seleção sai.
      if (action === "reject") {
        setSelectedPendingId("");
      }
      setRevisionConflict(false);
      setToast(
        action === "confirm"
          ? `${selectedPending.label}: código ${codeChoice?.code ?? ""} confirmado; feche o pacote quando não houver mais serviços.`
          : `${selectedPending.label}: registrado como candidato a aditivo.`,
      );
      await atualizarEstado();
    } catch (error) {
      // O conflito tem banner próprio, com o botão de recarregar e o formulário
      // preservado; repetir a frase no alerta comum só empilharia ruído.
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
   * Desfaz um par `(item, código)` confirmado (F-045, pacote de design revisão 2).
   *
   * Gêmeo do handler do orçamento-base, menos o efeito de índice: aqui não há precedente a
   * compensar. A tela redesenha a partir do conjunto que o servidor devolveu — o pacote pode
   * ter reaberto, e isso não é a tela que decide.
   */
  const desfazerCodigo = async () => {
    const token = tokenDaSessao();
    const caixa = desfazerDoItem(desfazerCaixa, selectedPendingId);
    if (
      token === null ||
      version === null ||
      caixa === null ||
      !podeDesfazer(caixa)
    ) {
      return;
    }
    const reabriu = pacoteFechado(codes?.assignments ?? null, caixa.itemId);
    const code = caixa.code;
    setSubmitting(true);
    setAlertMessage(null);
    try {
      const response = await postCodeRevocation(token, rodada, {
        ...pedidoDeDesfazer(caixa, version),
        plateId: folhaDaVez,
      });
      aplicarVersao(response.version);
      setCodes(response);
      setDesfazerCaixa(null);
      setRevisionConflict(false);
      setToast(fraseDesfeitoGravado(code, reabriu));
      await atualizarEstado();
    } catch (error) {
      // Recusa preserva a caixa e o motivo digitado: nada foi gravado, e apagar o texto
      // obrigaria a reescrever a justificativa para tentar de novo.
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

  const fecharPacote = async () => {
    const token = tokenDaSessao();
    if (token === null || selectedPending === null || version === null) {
      return;
    }
    setSubmitting(true);
    setAlertMessage(null);
    try {
      const response = await postCodeClosure(token, rodada, {
        itemId: selectedPending.item_id,
        baseVersion: version,
        plateId: folhaDaVez,
        note: codeNote,
      });
      aplicarVersao(response.version);
      setCodes(response);
      setCodeChoice(null);
      setCodeNote("");
      setSelectedPendingId("");
      setRevisionConflict(false);
      setToast(`${selectedPending.label}: pacote de serviços declarado completo.`);
      await atualizarEstado();
    } catch (error) {
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
   * A prévia do efeito da fusão: **não grava nada e não avança a versão da rodada**.
   *
   * Ela existe porque a conta é do SERVIDOR — esta tela não soma —, e é ela que torna a
   * decisão informada: sem ela, o efeito do vínculo no total só apareceria depois de
   * declarado. Recusa aqui não é acidente de caminho: as recusas da prévia são as mesmas
   * da declaração, e ver a recusa antes de gravar é o ponto.
   */
  const preverVinculo = async () => {
    const token = tokenDaSessao();
    if (token === null || recusaDoVinculo(vinculo.kept, vinculo.discarded) !== null) {
      return;
    }
    setPrevendo(true);
    setAlertMessage(null);
    try {
      setPreviaDoVinculo(
        await previewIdentityLink(token, rodada, {
          kept: vinculo.kept,
          discarded: vinculo.discarded,
        }),
      );
    } catch (error) {
      // A prévia recusada apaga a prévia anterior: mostrar o número de um par que o
      // servidor acabou de recusar seria pior que não mostrar número nenhum.
      setPreviaDoVinculo(null);
      setAlertMessage(describeError(error));
    } finally {
      setPrevendo(false);
    }
  };

  /**
   * O ato: duas leituras de folhas diferentes são o MESMO elemento físico (ADR-0057, D4).
   *
   * Só sai daqui com a prévia DAQUELE par à vista e com motivo escrito. A resposta é a
   * praça inteira já remontada com o vínculo novo, e é dela que a tela redesenha — o
   * consolidado é derivado, e recalculá-lo aqui seria uma segunda verdade.
   */
  const declararIdentidade = async () => {
    const token = tokenDaSessao();
    if (
      token === null ||
      version === null ||
      !previaConfere(previaDoVinculo, vinculo) ||
      vinculo.note.trim().length === 0
    ) {
      return;
    }
    setSubmitting(true);
    setAlertMessage(null);
    try {
      const praca = await declareIdentityLink(token, rodada, {
        kept: vinculo.kept,
        discarded: vinculo.discarded,
        baseVersion: version,
        note: vinculo.note,
      });
      aplicarVersao(praca.version);
      setWorksite(praca);
      setVinculo(VINCULO_VAZIO);
      setPreviaDoVinculo(null);
      setRevisionConflict(false);
      setToast(
        "Identidade declarada: as duas leituras passam a contar como um elemento só. " +
          "A etapa Boletim já marca a medição gravada como vencida e oferece montá-la de " +
          "novo, para o total refletir a fusão.",
      );
      await atualizarEstado();
    } catch (error) {
      // Recusa preserva o rascunho e o motivo digitado: nada foi gravado, e apagar o
      // texto obrigaria a reescrever a justificativa para tentar de novo.
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

  const montarBoletim = async () => {
    const token = tokenDaSessao();
    if (token === null || version === null) {
      return;
    }
    setSubmitting(true);
    setAlertMessage(null);
    try {
      const response = await postCalcBuild(token, rodada, version);
      aplicarVersao(response.version);
      setBulletin(response);
      // O toast diz o estado REAL, não uma antecipação: montar a medição de novo leva a
      // aprovação anterior adiante já caduca (o digest assinado é o do conteúdo antigo), e
      // chamar isso de "sem aprovação" apagaria o fato de que alguém assinou.
      setToast(
        response.approval.stale
          ? "Boletim e memória regravados na rodada; a aprovação anterior caducou — aprove a medição atual."
          : "Boletim e memória gravados na rodada, aguardando aprovação nominal.",
      );
      await atualizarEstado();
    } catch (error) {
      // O conflito tem banner próprio, com o botão de recarregar e o formulário
      // preservado; repetir a frase no alerta comum só empilharia ruído.
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

  /** Desfechos da etapa de aprovação que não podem sobreviver ao próximo ato. */
  const limparDesfechosDaAprovacao = () => {
    setSemAcesso(false);
    setViolacoesDeExportacao(null);
    setAuditoriaReprovada(null);
  };

  /**
   * O ato nominal (VAL-05). O corpo é só `base_version`: quem aprova é o subject do JWT e o
   * instante é o relógio do servidor — a tela mostra a identidade da sessão e nunca a envia.
   *
   * Aprovar de novo é o caminho normal da aprovação caduca, não um erro: o histórico da
   * rodada guarda as duas assinaturas, que é o que um registro de aprovação existe para
   * fazer.
   */
  const aprovarMedicao = async () => {
    const token = tokenDaSessao();
    if (token === null || version === null) {
      return;
    }
    setSubmitting(true);
    setAlertMessage(null);
    limparDesfechosDaAprovacao();
    try {
      const response = await postApprove(token, rodada, version);
      aplicarVersao(response.version);
      setBulletin(response);
      setConfirmandoAprovacao(false);
      setRevisionConflict(false);
      setToast(MENSAGEM_MEDICAO_APROVADA);
      await atualizarEstado();
    } catch (error) {
      if (isForbidden(error)) {
        setSemAcesso(true);
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
   * Publica o `.xlsx` do boletim. A tela não decide nada aqui: ela pede, e os dois portões
   * do servidor — o do domínio e o da auditoria de round-trip — decidem se existe arquivo.
   *
   * Cada desfecho tem forma própria porque eles não significam a mesma coisa: violação do
   * portão é lista de motivos abertos (o servidor recusa por todos de uma vez), auditoria
   * reprovada é tela com "nada foi publicado" por extenso, e `409` é o banner da rodada.
   *
   * A releitura depois do sucesso não é zelo: a URL assinada da planilha **só** existe na
   * leitura, e sem ela a tela teria arquivo publicado e nenhum caminho para baixá-lo.
   */
  const exportarBoletim = async () => {
    const token = tokenDaSessao();
    if (token === null || version === null) {
      return;
    }
    setSubmitting(true);
    setExportando(true);
    setAlertMessage(null);
    limparDesfechosDaAprovacao();
    try {
      const response = await postBulletinExport(token, rodada, version);
      aplicarVersao(response.version);
      setBulletin(
        (await leituraObservacional(() => getBulletin(token, rodada))) ?? response,
      );
      setRevisionConflict(false);
      setToast(
        "Boletim publicado: a auditoria reabriu o arquivo e o reconferiu antes de publicar.",
      );
      await atualizarEstado();
    } catch (error) {
      if (isForbidden(error)) {
        setSemAcesso(true);
        return;
      }
      const violacoes = exportBlockedViolations(error);
      if (violacoes.length > 0) {
        setViolacoesDeExportacao(violacoes);
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
      setExportando(false);
      setSubmitting(false);
    }
  };

  /**
   * Gera o dossiê do aditivo. Mesma condição de elegibilidade do botão de montar boletim
   * (`jornada` → etapa `boletim` não bloqueada): o dossiê é o outro artefato de FECHAMENTO
   * da rodada e exige a mesma revisão completa com todo código decidido.
   */
  const gerarDossie = async () => {
    const token = tokenDaSessao();
    if (token === null || version === null) {
      return;
    }
    setSubmitting(true);
    setAlertMessage(null);
    try {
      const response = await postDossierBuild(token, rodada, version);
      aplicarVersao(response.version);
      setDossier(response);
      setToast("Dossiê do aditivo gravado na rodada.");
      await atualizarEstado();
    } catch (error) {
      // O conflito tem banner próprio, com o botão de recarregar e o formulário
      // preservado; repetir a frase no alerta comum só empilharia ruído.
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

  const boletimEtapa = jornada.etapas.find((etapa) => etapa.id === "boletim") ?? null;
  const dossieDisponivel = boletimEtapa !== null && boletimEtapa.status !== "blocked";

  // Identidade da sessão como a tela a MOSTRA no ato nominal. Ela não é campo e não entra
  // no corpo da mutação: quem carimba é o servidor, lendo o subject do token.
  const identidadeDaSessao =
    session === null
      ? ""
      : (session.profile.preferred_username ?? session.profile.sub);
  // O bloco de aprovação vem do documento já lido e, na falta dele, do estado da rodada:
  // as duas leituras são do servidor e derivam a caducidade do mesmo par de digests.
  const aprovacao: ApprovalState | null =
    bulletin?.approval ?? state?.bulletin.approval ?? null;
  // `approved` e `stale` juntos, sempre: na aprovação caduca os dois valem, e ler só o
  // primeiro ofereceria uma exportação que a rota já sabe que vai recusar.
  const aprovacaoValida =
    aprovacao !== null && aprovacao.approved && !aprovacao.stale;
  // O boletim gravado deixou de descrever a praça. A leitura é a do ESTADO da rodada, e não
  // a do documento em mãos, de propósito: `atualizarEstado` roda depois de todo ato e traz
  // o veredito novo, enquanto o documento em mãos é justamente o que venceu.
  const boletimVencido = state !== null && state.bulletin.present && state.bulletin.stale;
  const nomeDoBoletimXlsx =
    state === null
      ? "boletim.xlsx"
      : `boletim-${state.worksite_key}-medicao-${state.period_number}.xlsx`;

  const shortlist =
    selectedPending === null
      ? []
      : (suggestions?.suggestions.suggestions.find(
          (suggestion) => suggestion.item_id === selectedPending.item_id,
        )?.candidates ?? []);
  const semCandidato =
    selectedPending !== null &&
    (suggestions?.suggestions.unmatched_item_ids.includes(selectedPending.item_id) ??
      false);

  const labelDoItem = (itemId: string): string =>
    items.find((item) => item.id === itemId)?.label ?? itemId;

  const rejeitados = (codes?.assignments?.assignments ?? []).filter(
    (assignment) => assignment.status === "rejected",
  );
  const confirmados = (codes?.assignments?.assignments ?? []).filter(
    (assignment) => assignment.status === "confirmed",
  );
  const semCandidatoPendentes = (
    suggestions?.suggestions.unmatched_item_ids ?? []
  ).filter((itemId) => pendingItems.some((item) => item.item_id === itemId));

  // Sem sessão a jornada não chama nada e não inventa rodada: quem tem a tela de entrar é
  // a casca (`App.tsx`), e as rotas da medição são todas autenticadas e por tenant.
  if (!autenticado) {
    return (
      <div className="jornada-medicao">
        <section className="painel" aria-label="Medição de obra">
          <span className="eyebrow">MEDIÇÃO DE OBRA</span>
          <h1>Entre para abrir uma rodada</h1>
          <p>
            A medição é autenticada e por tenant: rodada, prancha e catálogo só são lidos
            com a sessão de quem decide.
          </p>
          <p className="aviso-fixo">{AVISO_MEDICAO}</p>
        </section>
      </div>
    );
  }

  // Nenhuma rodada aberta: a jornada começa escolhendo — ou abrindo — uma.
  if (rodada === "") {
    const keyErro = worksiteKeyError(roundForm.worksiteKey);
    return (
      <div className="jornada-medicao">
        <header className="topbar">
          <div>
            <span className="eyebrow">MEDIÇÃO DE OBRA</span>
            <h1>Rodadas de medição</h1>
            <p className="topbar-meta">
              Cada rodada é uma prancha, um catálogo e um período de medição.
            </p>
          </div>
          <p className="aviso-fixo">{AVISO_MEDICAO}</p>
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
          <section className="painel" aria-label="Rodadas do tenant">
            <div className="painel-cabecalho">
              <h2>Rodadas abertas</h2>
              <button
                type="button"
                className="botao-secundario"
                onClick={() => void carregarRodadas()}
                disabled={loading}
              >
                {loading ? "Carregando…" : "Recarregar lista"}
              </button>
            </div>
            {rounds === null ? (
              <p>A lista de rodadas ainda não foi lida.</p>
            ) : rounds.length === 0 ? (
              <p>
                Nenhuma rodada neste tenant ainda. Abra a primeira no formulário abaixo.
              </p>
            ) : (
              <ul className="rodadas-lista">
                {rounds.map((round) => (
                  <li key={round.round_id} className="rodada-linha">
                    <div>
                      <strong>{round.worksite_name}</strong>{" "}
                      <span className="mono">({round.worksite_key})</span>{" "}
                      {round.approved ? (
                        <span className="selo selo-ok">aprovada</span>
                      ) : null}
                      <p className="topbar-meta">
                        {round.reference_label} · medição {round.period_number} · etapa{" "}
                        {stageLabel(round.stage)} · leitura da legenda{" "}
                        {extractionStatusLabel(round.extraction_status)} · versão{" "}
                        {round.version}
                      </p>
                      <p className="topbar-meta">
                        Atualizada em {formatTimestamp(round.updated_at)}
                      </p>
                    </div>
                    <div className="rodada-acoes">
                      <button
                        type="button"
                        className="botao-primario"
                        onClick={() => abrirRodada(round.round_id)}
                      >
                        Abrir rodada
                      </button>
                      {round.can_open_next ? (
                        <button
                          type="button"
                          className="botao-secundario"
                          disabled={submitting}
                          onClick={() => void abrirMedicaoSeguinte(round)}
                        >
                          Abrir a medição {round.period_number + 1}
                        </button>
                      ) : null}
                    </div>
                  </li>
                ))}
              </ul>
            )}
            {roundsCursor === null ? null : (
              <button
                type="button"
                className="botao-secundario"
                onClick={() => void carregarMaisRodadas()}
                disabled={loading}
              >
                Carregar mais rodadas
              </button>
            )}
          </section>

          <section className="painel" aria-label="Abrir rodada nova">
            <h2>Abrir rodada nova</h2>
            <form
              className="formulario"
              onSubmit={(event) => {
                event.preventDefault();
                void criarRodada();
              }}
            >
              <fieldset className="acoes">
                <legend className="campo-dica">De onde vem o contratado</legend>
                <label>
                  <input
                    type="radio"
                    name="origem-da-rodada"
                    checked={origemDoOrcamento}
                    disabled={
                      origens !== null &&
                      !origens.some((origem) => origem.signature === "signed")
                    }
                    onChange={() => setOrigemDoOrcamento(true)}
                  />
                  De um orçamento assinado
                </label>
                <label>
                  <input
                    type="radio"
                    name="origem-da-rodada"
                    checked={!origemDoOrcamento}
                    onChange={() => setOrigemDoOrcamento(false)}
                  />
                  Do zero, com catálogo por upload
                </label>
              </fieldset>
              {origemDoOrcamento ? (
                <OrigemDoOrcamento
                  origens={origens}
                  escolhida={origemEscolhida}
                  onEscolher={setOrigemEscolhida}
                />
              ) : null}
              {origemDoOrcamento ? null : (
                <>
              <p>
                O catálogo de preços é instalado na criação e é imutável na rodada: trocar
                de catálogo é abrir outra rodada.
              </p>
              <label className="campo">
                Catálogo de preços (JSON)
                <input
                  type="file"
                  accept=".json,application/json"
                  onChange={(event) => setCatalogFile(event.target.files?.[0] ?? null)}
                />
              </label>
              <label className="campo">
                Chave da obra
                <span className="campo-dica">
                  minúsculas, números e hífen (ex.: praca-sintetica-oeste)
                </span>
                <input
                  type="text"
                  value={roundForm.worksiteKey}
                  onChange={(event) =>
                    setRoundForm((current) => ({
                      ...current,
                      worksiteKey: event.target.value,
                    }))
                  }
                  aria-invalid={roundForm.worksiteKey.length > 0 && keyErro !== null}
                  required
                />
              </label>
              {roundForm.worksiteKey.length > 0 && keyErro !== null ? (
                <p className="campo-erro" role="alert">
                  {keyErro}
                </p>
              ) : null}
              <label className="campo">
                Nome da obra
                <span className="campo-dica">{DICA_NOME_DA_OBRA}</span>
                <input
                  type="text"
                  value={roundForm.worksiteName}
                  onChange={(event) =>
                    setRoundForm((current) => ({
                      ...current,
                      worksiteName: event.target.value,
                    }))
                  }
                  required
                />
              </label>
                </>
              )}
              <label className="campo">
                Número da medição
                <input
                  type="number"
                  min={1}
                  value={roundForm.periodNumber}
                  onChange={(event) =>
                    setRoundForm((current) => ({
                      ...current,
                      periodNumber: event.target.value,
                    }))
                  }
                  required
                />
              </label>
              <label className="campo">
                Rótulo da medição
                <span className="campo-dica">
                  como aparece na planilha (ex.: 3ª MEDIÇÃO)
                </span>
                <input
                  type="text"
                  value={roundForm.referenceLabel}
                  onChange={(event) =>
                    setRoundForm((current) => ({
                      ...current,
                      referenceLabel: event.target.value,
                    }))
                  }
                  required
                />
              </label>
              {origemDoOrcamento ? null : (
                <>
              <label className="campo">
                Endereço (opcional)
                <input
                  type="text"
                  value={roundForm.address}
                  onChange={(event) =>
                    setRoundForm((current) => ({
                      ...current,
                      address: event.target.value,
                    }))
                  }
                />
              </label>
              <label className="campo">
                Contrato (opcional)
                <input
                  type="text"
                  value={roundForm.contractLabel}
                  onChange={(event) =>
                    setRoundForm((current) => ({
                      ...current,
                      contractLabel: event.target.value,
                    }))
                  }
                />
              </label>
                </>
              )}
              {origemDoOrcamento ? (
                <fieldset className="reajuste-do-contrato">
                  <legend>Reajuste do contrato</legend>
                  <p className="dica">
                    O reajuste vale deste período em diante. Medição já aprovada não é
                    recalculada — nem um centavo dela muda.
                  </p>
                  <div className="reajuste-escolha">
                    {REAJUSTE_OPCOES.map((opcao) => (
                      <label
                        key={opcao.valor}
                        className={
                          (reajuste?.kind ?? "none") === opcao.valor ? "ativa" : ""
                        }
                      >
                        <input
                          type="radio"
                          name="reajuste-do-contrato"
                          checked={(reajuste?.kind ?? "none") === opcao.valor}
                          onChange={() =>
                            setReajuste(
                              opcao.valor === "none"
                                ? null
                                : {
                                    kind: opcao.valor,
                                    referencePeriod: "",
                                    indexLabel: "",
                                    factor: "",
                                  },
                            )
                          }
                        />
                        <span>
                          {opcao.titulo}
                          <small>{opcao.explicacao}</small>
                        </span>
                      </label>
                    ))}
                  </div>
                  {reajuste === null ? null : (
                    <>
                      <label className="campo">
                        Período de referência
                        <span className="campo-dica">
                          Como a publicação oficial o nomeia — “08/2025 a 07/2026”.
                        </span>
                        <input
                          type="text"
                          value={reajuste.referencePeriod}
                          onChange={(event) =>
                            setReajuste({
                              ...reajuste,
                              referencePeriod: event.target.value,
                            })
                          }
                        />
                      </label>
                      {reajuste.kind === "index_factor" ? (
                        <>
                          <label className="campo">
                            Índice
                            <input
                              type="text"
                              value={reajuste.indexLabel ?? ""}
                              onChange={(event) =>
                                setReajuste({
                                  ...reajuste,
                                  indexLabel: event.target.value,
                                })
                              }
                            />
                          </label>
                          <label className="campo">
                            Fator
                            <span className="campo-dica">{DICA_FATOR}</span>
                            <input
                              type="text"
                              value={reajuste.factor ?? ""}
                              onChange={(event) =>
                                setReajuste({ ...reajuste, factor: event.target.value })
                              }
                            />
                          </label>
                        </>
                      ) : (
                        <p className="dica">
                          A versão nova da tabela é enviada como catálogo; o servidor resolve
                          o preço de cada código contratado e recusa se faltar algum.
                        </p>
                      )}
                      {reajusteIssue(reajuste) === null ? null : (
                        <p className="campo-aviso">{reajusteIssue(reajuste)}</p>
                      )}
                    </>
                  )}
                </fieldset>
              ) : null}
              {origemDoOrcamento ? (
                <>
                  <ReRatificacaoFieldset value={reRa} onChange={setReRa} />
                  {reRaIssue(reRa) === null ? null : (
                    <p className="campo-aviso">{reRaIssue(reRa)}</p>
                  )}
                </>
              ) : null}
              <button
                type="submit"
                className="botao-primario"
                disabled={
                  submitting ||
                  reajusteIssue(reajuste) !== null ||
                  (origemDoOrcamento
                    ? origemEscolhida === null
                    : catalogFile === null)
                }
              >
                {submitting ? "Abrindo…" : "Abrir rodada"}
              </button>
            </form>
          </section>
        </main>
      </div>
    );
  }

  return (
    <div className="jornada-medicao">
      <header className="topbar">
        <div>
          <span className="eyebrow">MEDIÇÃO DE OBRA</span>
          <h1>
            {state === null ? "Rodada não carregada" : state.worksite_name}
          </h1>
          {state === null ? null : (
            <>
              <p className="topbar-meta mono">
                {state.worksite_key} · rodada {shortDigest(state.round_id)}
              </p>
              <p className="topbar-meta">
                {state.reference_label} · medição {state.period_number} · versão{" "}
                {state.version} · papel {state.reviewer_role}
              </p>
            </>
          )}
          {state === null ? (
            <p className="topbar-meta">
              O estado desta rodada ainda não foi lido da API.
            </p>
          ) : null}
        </div>
        {/* Aviso permanente: ele não fecha, não recolhe e não expira. */}
        <p className="aviso-fixo">{AVISO_MEDICAO}</p>
        <div className="topbar-acoes">
          <button
            type="button"
            className="topbar-link topbar-link-botao"
            onClick={() => abrirRodada("")}
          >
            Trocar de rodada
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

      <nav className="etapas" aria-label="Etapas da medição">
        <button
          type="button"
          className={`etapa-tab ${etapaVisivel === "rodada" ? "ativa" : ""}`}
          onClick={() => setOpenStep(null)}
          aria-current={etapaVisivel === "rodada"}
        >
          Rodada
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

      {revisionConflict ? (
        <BannerRodadaMudou onReload={() => void carregarEstado()} />
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
        {etapaVisivel === "rodada" ? (
          <section className="painel" aria-label="Situação da rodada">
            <h2>Situação da rodada</h2>
            <ul className="cartoes">
              {jornada.etapas.map((etapa) => (
                <li key={etapa.id} className={`cartao ${etapa.status}`}>
                  <h3>{etapa.title}</h3>
                  <p className="cartao-status">
                    Etapa {etapaStatusLabel(etapa.status)}
                  </p>
                  <p>{etapa.summary}</p>
                  {etapa.blockedReason === undefined ? null : (
                    <p className="cartao-motivo">Bloqueada porque {etapa.blockedReason}.</p>
                  )}
                  <button
                    type="button"
                    className="botao-secundario"
                    onClick={() => abrirEtapa(etapa)}
                    disabled={etapa.status === "blocked"}
                  >
                    Abrir {etapa.title.toLowerCase()}
                  </button>
                </li>
              ))}
            </ul>

            {state === null ? (
              <p>
                O estado desta rodada ainda não foi lido. Use “Recarregar estado atual”.
              </p>
            ) : (
              <div className="artefatos">
                <h3>Artefatos da rodada</h3>
                <ul>
                  {Object.entries(state.artifacts).map(([name, digest]) => (
                    <li key={name}>
                      <span className="mono">{name}</span>{" "}
                      <span className="digest" title={digest}>
                        sha256 {shortDigest(digest)}
                      </span>
                    </li>
                  ))}
                </ul>
                <p>
                  Catálogo instalado:{" "}
                  {state.catalog.summary.source_label ?? "sem rótulo declarado"}
                  {state.catalog.summary.reference_month === undefined
                    ? ""
                    : ` · referência ${state.catalog.summary.reference_month}`}
                  {state.catalog.summary.entries === undefined
                    ? ""
                    : ` · ${state.catalog.summary.entries} códigos`}{" "}
                  ·{" "}
                  <span className="digest" title={state.catalog.source_sha256}>
                    sha256 {shortDigest(state.catalog.source_sha256)}
                  </span>
                </p>
                <RegimeDeConferencia contracted={state.contracted} />
                <EloComOCroqui
                  link={elo}
                  jobId={croquiDeclarado}
                  onJobIdChange={setCroquiDeclarado}
                  onDeclarar={() => void declararElo()}
                  onConfrontar={() => void confrontarComACena()}
                  submitting={submitting}
                  confrontoDisponivel={takeoff !== null}
                />
                <RelatorioDoConfronto relatorio={confronto} itens={items} />
                <p>
                  Prancha: {state.plate.present ? "enviada" : "ausente"} · leitura da
                  legenda: {extractionStatusLabel(state.extraction.status)}
                  {overlayEstado === null
                    ? ""
                    : ` · overlay das âncoras: ${overlayEstado.label}`}
                  .
                </p>
              </div>
            )}
          </section>
        ) : null}

        {etapaVisivel === "prancha" ? (
          <section
            className="painel"
            aria-label={praca ? "Pranchas da praça" : "Prancha do projetista"}
          >
            <h2>{praca ? "Pranchas da praça" : "Prancha do projetista"}</h2>
            {praca ? (
              <FaixaDeFolhas
                folhas={folhas}
                emFoco={folhaAtual?.plate_id ?? ""}
                onFocar={focarFolha}
              />
            ) : null}
            {state === null ? (
              <p>O estado desta rodada ainda não foi lido.</p>
            ) : state.plate.present ? (
              <>
                <EstadoExtracao
                  extraction={state.extraction}
                  onRetry={() => void tentarExtracaoNovamente()}
                  retrying={submitting}
                  porFolha={praca}
                />
                {plate === null || paginasDoDocumento <= 1 ? null : (
                  <AcrescentarFolhas
                    paginas={paginasDoDocumento}
                    jaPromovidas={paginasJaPromovidas}
                    selecionadas={paginasSelecionadas}
                    aindaCabem={folhasQueAindaCabem(worksite)}
                    onAlternar={alternarPagina}
                    onConfirmar={() => void acrescentarFolhas()}
                    submitting={submitting}
                  />
                )}
                {folhasSemPacote.length === 0 ? null : (
                  <LerFolhasEmLote
                    folhas={folhasSemPacote}
                    selecionadas={folhasSelecionadas}
                    onAlternar={alternarFolha}
                    onConfirmar={() => void lerFolhasSelecionadas()}
                    submitting={submitting}
                  />
                )}
                <form
                  className="formulario outra-origem"
                  onSubmit={(event) => {
                    event.preventDefault();
                    void enviarOutraFolha();
                  }}
                >
                  <h3>Outra origem</h3>
                  <p className="dica">
                    A praça <strong>não</strong> é um arquivo: detalhe que veio em PDF
                    separado entra pela mesma porta e vira mais uma folha da mesma praça.
                    Cada folha nasce como pacote de takeoff próprio, com sua imagem, seu
                    digest e sua evidência; nada é mesclado na ingestão.
                  </p>
                  <label className="campo">
                    Enviar outro PDF para esta praça
                    <input
                      type="file"
                      accept=".pdf,application/pdf"
                      onChange={(event) => setUploadFile(event.target.files?.[0] ?? null)}
                    />
                  </label>
                  <button
                    type="submit"
                    className="botao-secundario"
                    disabled={uploadFile === null || submitting || version === null}
                  >
                    {submitting ? "Enviando…" : "Acrescentar 1 folha à praça"}
                  </button>
                  <p className="aviso-fixo aviso-inline">
                    Acrescentar não lê legenda nenhuma: a leitura é o ato seguinte, com o
                    número de chamadas pagas escrito no botão dele.
                  </p>
                </form>
              </>
            ) : (
              <form
                className="formulario"
                onSubmit={(event) => {
                  event.preventDefault();
                  void enviarPrancha();
                }}
              >
                <p>Nenhuma prancha enviada nesta rodada ainda.</p>
                <label className="campo">
                  Prancha do projetista (PDF)
                  <input
                    type="file"
                    accept=".pdf,application/pdf"
                    onChange={(event) => setUploadFile(event.target.files?.[0] ?? null)}
                  />
                </label>
                <p className="aviso-fixo aviso-inline">
                  Ao enviar, a leitura da legenda é feita automaticamente por IA (chamada
                  paga, autorizada por contrato do seu tenant).
                </p>
                <button
                  type="submit"
                  className="botao-primario"
                  disabled={uploadFile === null || submitting || version === null}
                >
                  {submitting ? "Enviando…" : "Enviar prancha"}
                </button>
              </form>
            )}
          </section>
        ) : null}

        {etapaVisivel === "revisao" && (takeoff !== null || praca) ? (
          <>
            {praca ? (
              <FaixaDeFolhas
                folhas={folhas}
                emFoco={folhaAtual?.plate_id ?? ""}
                onFocar={focarFolha}
              />
            ) : null}
            {takeoff === null || (praca && !folhaServida) ? (
              folhaAtual === null ? null : (
                <FolhaSemPacote folha={folhaAtual} total={folhas.length} />
              )
            ) : (
          <section className="workspace" aria-label="Revisão do takeoff">
            <article className="painel prancha-painel">
              <div className="painel-cabecalho">
                <h2>
                  Prancha e legenda
                  {praca && folhaAtual !== null ? (
                    <>
                      {" — "}
                      <strong>{folhaLabel(folhaAtual.position, folhas.length)}</strong>
                    </>
                  ) : null}
                </h2>
                <div className="cabecalho-controles">
                  <button
                    type="button"
                    className="botao-secundario"
                    onClick={() => setMostrarMarcacoes((current) => !current)}
                    aria-pressed={mostrarMarcacoes}
                  >
                    {mostrarMarcacoes ? "Ocultar marcações" : "Mostrar marcações"}
                  </button>
                  <div className="zoom-controles">
                    <button
                      type="button"
                      className="botao-secundario"
                      onClick={() => setZoom((current) => clampZoom(current - ZOOM_STEP))}
                      aria-label="Afastar o zoom da prancha"
                    >
                      −
                    </button>
                    <span className="zoom-leitura">
                      {zoom.toFixed(2).replace(".", ",")}×
                    </span>
                    <button
                      type="button"
                      className="botao-secundario"
                      onClick={() => setZoom((current) => clampZoom(current + ZOOM_STEP))}
                      aria-label="Aproximar o zoom da prancha"
                    >
                      +
                    </button>
                  </div>
                </div>
              </div>
              <p className="dica">
                Aqui é a prancha que o projetista enviou: por padrão nenhuma marcação
                fica sobre a imagem. Ao selecionar um item na lista, só o retângulo fino
                dele aparece, sem número. &quot;Mostrar marcações&quot; revela o
                retângulo e o número de todos os itens de uma vez, para auditoria — o
                estado por extenso fica sempre na lista ao lado, nunca só na cor. Role
                com a roda do mouse sobre a prancha para aproximar (de {MIN_ZOOM}× a{" "}
                {MAX_ZOOM}×) e arraste para deslocar.
              </p>
              {plateSrc === null ? (
                <p className="banner-erro" role="alert">
                  A imagem da prancha ainda não está publicada nesta rodada. A lista de
                  itens continua utilizável.
                </p>
              ) : null}
              <div
                className={`prancha-canvas ${panning ? "arrastando" : ""}`}
                ref={canvasRef}
                onPointerDown={startPan}
                onPointerMove={movePan}
                onPointerUp={endPan}
                onPointerCancel={endPan}
              >
                <div
                  className="prancha-stage"
                  style={
                    imageSize === null
                      ? undefined
                      : stageStyle(zoom, imageSize.width, imageSize.height)
                  }
                >
                  {plateSrc === null ? null : (
                    <img
                      src={plateSrc}
                      alt="Prancha do projetista com a legenda quantificada"
                      draggable={false}
                      onLoad={(event) => {
                        const { naturalWidth, naturalHeight } = event.currentTarget;
                        setImageSize(
                          (current) =>
                            current ?? { width: naturalWidth, height: naturalHeight },
                        );
                      }}
                    />
                  )}
                  {imageSize === null ? null : (
                    <svg
                      className="bbox-overlay"
                      viewBox={`0 0 ${imageSize.width} ${imageSize.height}`}
                      preserveAspectRatio="none"
                    >
                      {items.map((item, index) => {
                        const numero = index + 1;
                        const selecionado = item.id === selectedItemId;
                        // Item sem localização confirmada (`anchor !== "registered"`)
                        // nunca ganha retângulo nem número — nem selecionado, nem em
                        // "Mostrar marcações": desenhar um retângulo ali seria afirmar
                        // uma posição que o servidor ainda não confirmou.
                        const registrado = itemAnchor(item) === "registered";
                        // Prancha limpa por padrão: aqui é o lugar de somente a imagem
                        // que o projetista enviou. Nada desenhado, exceto o retângulo
                        // fino do item selecionado — sem número, ele sozinho não precisa
                        // de balão para se identificar. "Mostrar marcações" é o único
                        // jeito de ver todo mundo de uma vez, com número, para auditoria.
                        const mostrar = registrado && (mostrarMarcacoes || selecionado);
                        if (!mostrar) {
                          return null;
                        }
                        const rect = bboxRect(item.evidence.bbox);
                        // O número só existe no modo auditoria; mesmo lá, mora fora do
                        // bbox (`pinPlacement`) — dentro dele, o balão cobria letra da
                        // legenda ("PISO EM(1)CONCRETO" foi o defeito real).
                        const pin =
                          !mostrarMarcacoes || imageSize === null
                            ? null
                            : pinPlacement(
                                item.evidence.bbox,
                                PIN_DIAMETER_PX,
                                imageSize.width,
                                imageSize.height,
                              );
                        const onKeyDownSelecionar = (event: ReactKeyboardEvent<SVGGElement>) => {
                          if (event.key === "Enter" || event.key === " ") {
                            event.preventDefault();
                            selecionarItem(item);
                          }
                        };

                        return (
                          <g
                            key={item.id}
                            className={`bbox bbox-${item.status} ${
                              selecionado && mostrarMarcacoes ? "selecionado" : ""
                            }`}
                            role="button"
                            tabIndex={0}
                            aria-label={`Item ${numero}: ${item.label}, ${itemStatusLabel(
                              item.status,
                            )}`}
                            onClick={() => selecionarItem(item)}
                            onKeyDown={onKeyDownSelecionar}
                          >
                            <rect
                              x={rect.x}
                              y={rect.y}
                              width={rect.width}
                              height={rect.height}
                            />
                            {pin === null ? null : (
                              <>
                                <circle className="bbox-pino-circulo" cx={pin.cx} cy={pin.cy} r={pin.r} />
                                <text
                                  className="bbox-pino-texto"
                                  x={pin.cx}
                                  y={pin.cy + pin.r * 0.35}
                                  textAnchor="middle"
                                >
                                  {numero}
                                </text>
                              </>
                            )}
                          </g>
                        );
                      })}
                    </svg>
                  )}
                </div>
              </div>

              {praca && !folhaComRerender && folhaAtual !== null ? (
                <OverlaySemRerender folha={folhaAtual} total={folhas.length} />
              ) : null}
              {overlay === null ? null : (
                <OverlayDoTakeoff
                  overlay={overlay}
                  onRefresh={() => void atualizarOverlay()}
                />
              )}
            </article>

            <article className="painel lista-painel">
              <h2>
                Itens da legenda
                {praca && folhaAtual !== null ? (
                  <>
                    {" — "}
                    <strong>{folhaLabel(folhaAtual.position, folhas.length)}</strong>
                  </>
                ) : null}
              </h2>
              <p className="dica">
                {takeoff.packet.items.length} itens da prancha{" "}
                <span className="mono">{takeoff.packet.plate_id}</span>. Pacote sha256{" "}
                <span className="digest" title={takeoff.packet_sha256}>
                  {shortDigest(takeoff.packet_sha256)}
                </span>
                .
              </p>
              {divergenciasAbertas.length === 0 ? null : (
                <p className="aviso-fixo aviso-inline" role="alert">
                  <span className="selo selo-atencao">⚠ divergência aberta</span>{" "}
                  {divergenciasAbertas.length} item(ns) não fecham enquanto ninguém escolher
                  entre a quantidade da cena e a da legenda. Eles estão marcados na lista.
                </p>
              )}
              <ul className="itens">
                {items.map((item, index) => (
                  <li
                    key={item.id}
                    className={`item ${item.status} ${
                      item.id === selectedItemId ? "selecionado" : ""
                    }`}
                  >
                    <button
                      type="button"
                      className="item-botao"
                      onClick={() => selecionarItem(item)}
                      aria-pressed={item.id === selectedItemId}
                    >
                      <span className="item-numero">{index + 1}</span>
                      <span className="item-corpo">
                        <span className="item-rotulo">{item.label}</span>
                        <span className="item-estado">{itemStatusLabel(item.status)}</span>
                        <span className="item-quantidade">
                          {formatQuantityText(item.quantity ?? null, unitLabel(item.unit))}
                        </span>
                        {/* Origem e bloqueio aparecem na LISTA, não só no painel: quem
                            percorre a legenda inteira precisa ver qual item não fecha sem
                            abrir um por um. Palavra e forma, nunca só cor. */}
                        {item.element_ref ? (
                          <span className="item-origem">
                            <EtiquetaDeElemento elementRef={item.element_ref} />
                            {vemDaCena(item) ? (
                              <span className="selo selo-cena">
                                ◇ {quantitySourceLabel(item.source)}
                              </span>
                            ) : null}
                          </span>
                        ) : null}
                        {divergenciaAberta(item) === null ? null : (
                          <span className="item-bloqueado">
                            <span className="selo selo-atencao">⚠ divergência aberta</span>{" "}
                            item bloqueado até alguém escolher a origem
                          </span>
                        )}
                        <span className="mono item-raw">{item.raw_text}</span>
                        {item.note ? (
                          <span className="item-nota">Anotação: {item.note}</span>
                        ) : null}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </article>

            <article className="painel decisao-painel">
              <h2>Decisão do item</h2>
              {selectedItem === null ? (
                <p>Escolha um item na lista ou clique no retângulo da prancha.</p>
              ) : (
                <>
                  {/* A origem e a divergência vêm ANTES do ato, decidido ou não: elas são o
                      que a pessoa precisa ler para decidir, e o item já decidido continua
                      precisando mostrar de onde o número veio. */}
                  <OrigemDaQuantidade
                    item={selectedItem}
                    sceneRevisionId={elo.present ? elo.scene_revision_id : null}
                  />
                  <DivergenciaDoItem item={selectedItem} />
                  <ResolucaoDaDivergencia
                    item={selectedItem}
                    escolha={resolucao.choice}
                    motivo={resolucao.motivo}
                    submitting={submitting}
                    onEscolha={(choice) =>
                      setResolucao((current) => ({ ...current, choice }))
                    }
                    onMotivo={(motivo) =>
                      setResolucao((current) => ({ ...current, motivo }))
                    }
                    onRegistrar={() => void resolverDivergencia()}
                    onCancelar={() => setResolucao({ choice: "", motivo: "" })}
                  />
                  {divergenciaAberta(selectedItem) !== null ? (
                    // O item não fecha enquanto a divergência existir: o formulário de
                    // decisão não aparece, e a razão fica escrita no lugar dele.
                    <p className="cartao-motivo">
                      A decisão sobre este item fica indisponível enquanto a divergência
                      estiver aberta. Escolha a origem acima; depois dela o item volta ao
                      curso normal da revisão.
                    </p>
                  ) : selectedItem.decision ? (
                <div className="decisao-registrada">
                  <p>
                    <strong>{selectedItem.label}</strong> —{" "}
                    {itemStatusLabel(selectedItem.status)}.
                  </p>
                  <p>
                    {selectedItem.decision.action === "confirm"
                      ? "Confirmado"
                      : "Rejeitado"}{" "}
                    por {selectedItem.decision.reviewer_id} em{" "}
                    {formatTimestamp(selectedItem.decision.decided_at)}.
                  </p>
                  {selectedItem.decision.note ? (
                    <p>Nota: {selectedItem.decision.note}</p>
                  ) : null}
                  <p className="cartao-motivo">
                    Este item já foi decidido; decisão não se sobrescreve.
                  </p>
                </div>
              ) : (
                <form
                  className="formulario"
                  onSubmit={(event) => {
                    event.preventDefault();
                    void enviarDecisao();
                  }}
                >
                  <p>
                    <strong>{selectedItem.label}</strong> —{" "}
                    {itemStatusLabel(selectedItem.status)} ·{" "}
                    {formatQuantityText(
                      selectedItem.quantity ?? null,
                      unitLabel(selectedItem.unit),
                    )}
                  </p>
                  <p className="mono item-raw">{selectedItem.raw_text}</p>

                  <fieldset className="acoes">
                    <legend>Ato do orçamentista</legend>
                    {/* Nada pré-marcado: a decisão nasce do clique, nunca do default. */}
                    <label>
                      <input
                        type="radio"
                        name="acao"
                        value="confirm"
                        checked={decision.action === "confirm"}
                        onChange={() =>
                          setDecision((current) => ({ ...current, action: "confirm" }))
                        }
                      />
                      Confirmar item
                    </label>
                    <label>
                      <input
                        type="radio"
                        name="acao"
                        value="reject"
                        checked={decision.action === "reject"}
                        onChange={() =>
                          setDecision((current) => ({ ...current, action: "reject" }))
                        }
                      />
                      Rejeitar item
                    </label>
                  </fieldset>

                  {decision.action === "confirm" ? (
                    <>
                      {/* Item alimentado pela cena não tem campo de quantidade nem de
                          unidade (ADR-0058, decisões 5 e 7): a origem ocupa o lugar do
                          input, e a razão já está escrita no bloco de origem acima. A
                          anotação do item continua, porque ela corrige o TEXTO da linha da
                          legenda — não o número. */}
                      {vemDaCena(selectedItem) ? null : (
                      <>
                      <label className="campo">
                        Quantidade
                        {selectedItem.status === "ambiguous" ? (
                          <span className="campo-aviso">
                            obrigatória — {AVISO_QUANTIDADE_AMBIGUA}
                          </span>
                        ) : (
                          <span className="campo-dica">
                            em branco mantém a quantidade extraída
                          </span>
                        )}
                        <input
                          type="text"
                          inputMode="decimal"
                          value={decision.quantity}
                          onChange={(event) =>
                            setDecision((current) => ({
                              ...current,
                              quantity: event.target.value,
                            }))
                          }
                          aria-invalid={quantidadeInvalida}
                        />
                        <span className="campo-dica">
                          {DICA_QUANTIDADE}
                          {quantidadeParaServidor === null
                            ? ""
                            : ` Será enviada como ${quantidadeParaServidor}.`}
                        </span>
                      </label>
                      <label className="campo">
                        Unidade
                        <span className="campo-dica">
                          em branco mantém {unitLabel(selectedItem.unit)}
                        </span>
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
                      </>
                      )}
                      <label className="campo">
                        Anotação do item
                        <span className="campo-dica">
                          corrige o texto que acompanha a linha na legenda
                        </span>
                        <input
                          type="text"
                          value={decision.itemNote}
                          onChange={(event) =>
                            setDecision((current) => ({
                              ...current,
                              itemNote: event.target.value,
                            }))
                          }
                        />
                      </label>
                    </>
                  ) : null}

                  <label className="campo">
                    Nota da decisão
                    <span className="campo-dica">
                      documenta o ato: conversão de unidade, origem da quantidade, motivo
                      da rejeição
                    </span>
                    <textarea
                      value={decision.note}
                      rows={3}
                      onChange={(event) =>
                        setDecision((current) => ({
                          ...current,
                          note: event.target.value,
                        }))
                      }
                    />
                  </label>

                  {quantidadeInvalida ? (
                    <p className="campo-erro" role="alert">
                      Quantidade não reconhecida. {DICA_QUANTIDADE}
                    </p>
                  ) : null}
                  {exigeQuantidade && quantidadeParaServidor === null ? (
                    <p className="campo-erro">
                      Item ambíguo: informe a quantidade para confirmar.
                    </p>
                  ) : null}

                  <button
                    type="submit"
                    className="botao-primario"
                    disabled={decisaoBloqueada}
                  >
                    {submitting ? "Registrando…" : "Registrar decisão"}
                  </button>
                  <p className="dica">
                    Identidade e horário são do servidor: a decisão sai carimbada com a
                    identidade da sua sessão.
                  </p>
                </form>
                  )}
                </>
              )}
              {selectedItem === null || itemAnchor(selectedItem) === "registered" ? null : (
                <p className="aviso-fixo aviso-inline">
                  {AVISO_LOCALIZACAO_NAO_CONFIRMADA}
                </p>
              )}
            </article>
          </section>
            )}
          </>
        ) : null}

        {etapaVisivel === "codigos" && praca ? (
          <>
            <FaixaDeFolhas
              folhas={folhas}
              emFoco={folhaAtual?.plate_id ?? ""}
              onFocar={focarFolha}
            />
            <AndamentoDaCodificacao
              folhas={codificacaoDasFolhas(worksite, codigosPorFolha)}
              total={folhas.length}
              emFoco={folhaAtual?.plate_id ?? ""}
              onFocar={focarFolha}
            />
          </>
        ) : null}

        {etapaVisivel === "codigos" && codes !== null ? (
          <section className="workspace duas-colunas" aria-label="Confirmação de código">
            <article className="painel lista-painel">
              <h2>
                Itens confirmados sem código
                {praca && folhaAtual !== null ? (
                  <>
                    {" — "}
                    <strong>{folhaLabel(folhaAtual.position, folhas.length)}</strong>
                  </>
                ) : null}
              </h2>
              {praca && codes.plate_id !== undefined ? (
                <p className="dica">
                  Codificando a prancha <span className="mono">{codes.plate_id}</span>. O
                  conjunto de códigos é <strong>desta folha</strong>; o boletim da praça é
                  a união dos conjuntos de todas elas.
                </p>
              ) : null}
              {suggestions === null ? (
                <div className="shortlist-vazia">
                  <p>
                    A shortlist ainda não foi calculada{" "}
                    {praca ? "nesta folha" : "nesta rodada"}. Calcular grava a shortlist de
                    código como artefato da rodada.
                  </p>
                  <p className="dica">{DESCRICAO_CALCULO_SHORTLIST}</p>
                  <button
                    type="button"
                    className="botao-primario"
                    onClick={() => void calcularShortlist()}
                    disabled={submitting}
                  >
                    Calcular shortlist
                  </button>
                </div>
              ) : (
                <div className="shortlist-vazia">
                  <p className="dica">
                    Recalcular sobrescreve a shortlist gravada com o algoritmo atual do
                    servidor; as decisões de código já registradas não mudam.
                  </p>
                  <p className="dica">{DESCRICAO_CALCULO_SHORTLIST}</p>
                  {suggestions.semantic_notes.map((note) => (
                    <p key={note} className="dica">
                      {note}
                    </p>
                  ))}
                  {folhaComRerender ? (
                    <button
                      type="button"
                      className="botao-secundario"
                      onClick={() => void recalcularShortlist()}
                      disabled={submitting || version === null}
                    >
                      Recalcular shortlist
                    </button>
                  ) : (
                    // O recompute — o braço PAGO — ainda é o da primeira folha: ele não
                    // aceita a folha e regravaria a shortlist DELA. Oferecer o botão aqui
                    // seria oferecer um ato que estraga outra folha, então ele não é
                    // oferecido, e o motivo fica escrito.
                    <p className="aviso-fixo aviso-inline" role="status">
                      O recálculo pago da shortlist ainda é o da primeira folha da praça:
                      ele não sabe de qual folha recalcular e regravaria a dela. Nesta
                      folha vale a shortlist léxica que a leitura calculou — a mesma que a
                      primeira folha tem antes de qualquer recálculo.
                    </p>
                  )}
                </div>
              )}
              {pendingItems.length === 0 ? (
                <p>Todos os itens confirmados já têm decisão de código.</p>
              ) : (
                <ul className="itens">
                  {pendingItems.map((item) => (
                    <li
                      key={item.item_id}
                      className={`item ${
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
                          <span className="mono item-raw">{item.raw_text}</span>
                          {item.note === null ? null : (
                            <span className="item-nota">Anotação: {item.note}</span>
                          )}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}

              <section className="confirmados" aria-label="Itens com código confirmado">
                <h3>Itens com código confirmado</h3>
                {confirmados.length === 0 ? (
                  <p>Nenhum código confirmado até agora.</p>
                ) : (
                  <ul className="confirmados-lista">
                    {confirmados.map((assignment) => {
                      const code = assignment.code ?? null;
                      // `code` só é nulo num assignment rejeitado; este filtro já é
                      // só de confirmados, mas o tipo do domínio permite nulo aqui.
                      const description = code === null ? null : assignmentDescriptions[code];
                      return (
                        <li key={assignment.item_id}>
                          <strong>{labelDoItem(assignment.item_id)}</strong> —{" "}
                          <span className="codigo-code">{code ?? "sem código"}</span>
                          {code === null ? null : description === undefined ? (
                            <p className="dica">Buscando descrição no catálogo…</p>
                          ) : description === null ? (
                            <p className="campo-aviso">
                              descrição não encontrada no catálogo desta rodada
                            </p>
                          ) : (
                            <>
                              <p className="codigo-descricao">{description}</p>
                              <Inclusoes description={description} />
                            </>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                )}
              </section>

              <section className="aditivo" aria-label="Candidatos a aditivo">
                <h3>Sem código no contrato — candidatos a aditivo</h3>
                <p className="dica">{AVISO_ADITIVO}</p>
                {dossier === null ? (
                  <>
                    <p className="dica">{AVISO_DOSSIE_PREVIA}</p>
                    {rejeitados.length === 0 && semCandidatoPendentes.length === 0 ? (
                      <p>Nenhum item nesta condição até agora.</p>
                    ) : (
                      <ul className="aditivo-lista">
                        {rejeitados.map((assignment) => (
                          <li key={assignment.item_id}>
                            <strong>{labelDoItem(assignment.item_id)}</strong> —{" "}
                            {assignmentStatusLabel(assignment.status)}.{" "}
                            {assignment.decision.note ?? "sem nota registrada"}
                          </li>
                        ))}
                        {semCandidatoPendentes.map((itemId) => (
                          <li key={itemId}>
                            <strong>{labelDoItem(itemId)}</strong> — a shortlist não achou
                            candidato; busque no catálogo antes de tratar como aditivo.
                          </li>
                        ))}
                      </ul>
                    )}
                    {dossieDisponivel ? (
                      <button
                        type="button"
                        className="botao-secundario"
                        onClick={() => void gerarDossie()}
                        disabled={submitting || version === null}
                      >
                        {submitting ? "Gerando…" : "Gerar dossiê do aditivo"}
                      </button>
                    ) : (
                      <p className="cartao-motivo">
                        Gerar o dossiê exige a mesma condição do boletim:{" "}
                        {boletimEtapa?.blockedReason ??
                          "revisão do takeoff e decisão de código completas"}
                        .
                      </p>
                    )}
                  </>
                ) : (
                  <>
                    <p className="dica">{AVISO_DOSSIE_GERADO}</p>
                    <p>
                      Dossiê gerado nesta rodada · sha256{" "}
                      <span className="digest" title={dossier.dossier_sha256}>
                        {shortDigest(dossier.dossier_sha256)}
                      </span>
                    </p>
                    {dossier.dossier.items.length === 0 ? (
                      <p>Nenhum item entrou no dossiê nesta rodada.</p>
                    ) : (
                      <ul className="aditivo-lista">
                        {dossier.dossier.items.map((item) => (
                          <li key={item.item_id}>
                            <strong>{item.label}</strong> —{" "}
                            {formatQuantityText(item.quantity, unitLabel(item.unit))}
                            <p className="codigo-descricao">{item.justification}</p>
                          </li>
                        ))}
                      </ul>
                    )}
                    {dossieDisponivel ? (
                      <button
                        type="button"
                        className="botao-secundario"
                        onClick={() => void gerarDossie()}
                        disabled={submitting || version === null}
                      >
                        {submitting ? "Gerando…" : "Regerar dossiê do aditivo"}
                      </button>
                    ) : null}
                  </>
                )}
              </section>
            </article>

            <article className="painel codigos-painel">
              <h2>Código do item</h2>
              {selectedPending === null ? (
                <>
                  <p>Escolha um item pendente na lista ao lado.</p>
                  {ultimoCodigoConfirmado === null ? null : (
                    <div className="decisao-registrada">
                      <p>
                        <strong>{ultimoCodigoConfirmado.itemLabel}</strong> — código{" "}
                        <span className="codigo-code">{ultimoCodigoConfirmado.code}</span>{" "}
                        confirmado nesta sessão.
                      </p>
                      <p className="codigo-descricao">
                        {ultimoCodigoConfirmado.description}
                      </p>
                      <Inclusoes description={ultimoCodigoConfirmado.description} />
                      {ultimoCodigoConfirmado.note === "" ? null : (
                        <p>Nota: {ultimoCodigoConfirmado.note}</p>
                      )}
                      <p className="cartao-motivo">
                        Este é o último código confirmado nesta sessão; a lista de itens
                        pendentes já não o mostra.
                      </p>
                    </div>
                  )}
                </>
              ) : (
                <>
                  <p>
                    <strong>{selectedPending.label}</strong> ·{" "}
                    {formatQuantityText(
                      selectedPending.quantity,
                      unitLabel(selectedPending.unit),
                    )}
                  </p>

                  <h3>Shortlist do servidor</h3>
                  {semCandidato ? (
                    <p className="cartao-motivo">
                      A shortlist não achou candidato para este item. O caminho é a busca
                      no catálogo abaixo. Se a shortlist foi gravada por uma versão antiga
                      do servidor, recalcule-a no painel ao lado.
                    </p>
                  ) : null}
                  {shortlist.length === 0 && !semCandidato ? (
                    <p>
                      Sem shortlist carregada para este item. Calcule a shortlist ou use a
                      busca.
                    </p>
                  ) : (
                    <ul className="codigos">
                      {shortlist.map((candidate: CodeSuggestionSet.CodeCandidate) => (
                        <CartaoCodigo
                          key={candidate.code}
                          code={candidate.code}
                          description={candidate.description}
                          unit={candidate.unit}
                          unitPrice={candidate.unit_price}
                          score={candidate.lexical_score}
                          inContract={candidate.in_contract}
                          unitCompatible={candidate.unit_compatible}
                          selected={codeChoice?.code === candidate.code}
                          onChoose={() =>
                            setCodeChoice({
                              code: candidate.code,
                              description: candidate.description,
                              unit: candidate.unit,
                              unit_price: candidate.unit_price,
                              unit_compatible: candidate.unit_compatible,
                            })
                          }
                        />
                      ))}
                    </ul>
                  )}

                  <h3>Busca no catálogo</h3>
                  <p className="dica">
                    A busca é a lexical do catálogo instalado nesta rodada, enquanto você
                    digita e no botão: nenhuma chamada paga acontece, e o motivo de o braço
                    semântico não participar vem declarado na resposta.
                  </p>
                  <form
                    className="busca"
                    onSubmit={(event) => {
                      event.preventDefault();
                      void buscarNoCatalogo();
                    }}
                  >
                    <label className="campo">
                      Palavras ou código
                      <input
                        type="search"
                        value={query}
                        onChange={(event) => setQuery(event.target.value)}
                        placeholder="ex.: piso intertravado"
                      />
                    </label>
                    <button
                      type="submit"
                      className="botao-secundario"
                      disabled={submitting}
                    >
                      Buscar
                    </button>
                  </form>
                  {buscando ? (
                    <p className="dica" aria-live="polite">
                      Buscando no catálogo…
                    </p>
                  ) : null}
                  {/* Falha da busca incremental fica ao lado do campo: ela é transitória
                      (uma tecla a mais já refaz a consulta) e não merece o banner que a
                      tela reserva para recusa de mutação. */}
                  {buscaAviso === null ? null : (
                    <p className="campo-aviso" role="alert">
                      {buscaAviso}
                    </p>
                  )}
                  {searchResult === null ? null : (
                    <>
                      <p className="dica">{resumoDaBusca(searchResult)}</p>
                      {/* Degradação declarada pelo servidor não some da tela: é ela que
                          explica por que a lista veio só pelo léxico. */}
                      {searchResult.semantic_notes.map((note) => (
                        <p key={note} className="dica">
                          {note}
                        </p>
                      ))}
                      <ul className="codigos">
                        {searchResult.results.map((result) => (
                          <CartaoCodigo
                            key={result.code}
                            code={result.code}
                            description={result.description}
                            unit={result.unit}
                            unitPrice={result.unit_price}
                            score={null}
                            inContract={null}
                            unitCompatible={null}
                            selected={codeChoice?.code === result.code}
                            onChoose={() =>
                              setCodeChoice({
                                code: result.code,
                                description: result.description,
                                unit: result.unit,
                                unit_price: result.unit_price,
                                unit_compatible: null,
                              })
                            }
                          />
                        ))}
                      </ul>
                    </>
                  )}

                  <h3>Confirmação</h3>
                  <p>
                    {codeChoice === null
                      ? "Nenhum código escolhido ainda."
                      : `Escolhido: ${codeChoice.code} · ${formatMoneyText(
                          codeChoice.unit_price,
                        )} / ${unitLabel(codeChoice.unit)}`}
                  </p>
                  {divergenciaDeUnidade && codeChoice !== null ? (
                    <p className="campo-aviso" role="alert">
                      {unitMismatchHint(selectedPending.unit, codeChoice.unit)}
                    </p>
                  ) : null}
                  <label className="campo">
                    Nota da decisão
                    <span className="campo-dica">
                      {notaObrigatoria
                        ? "obrigatória: registre a conversão de unidade"
                        : "obrigatória para rejeitar; opcional para confirmar ou fechar o pacote"}
                    </span>
                    <textarea
                      value={codeNote}
                      rows={3}
                      onChange={(event) => setCodeNote(event.target.value)}
                    />
                  </label>
                  <div className="acoes-linha">
                    <button
                      type="button"
                      className="botao-primario"
                      onClick={() => void decidirCodigo("confirm")}
                      disabled={
                        submitting ||
                        version === null ||
                        codeChoice === null ||
                        (notaObrigatoria && codeNote.trim().length === 0)
                      }
                    >
                      Confirmar código
                    </button>
                    <button
                      type="button"
                      className="botao-secundario"
                      onClick={() => void decidirCodigo("reject")}
                      disabled={
                        submitting ||
                        version === null ||
                        codeNote.trim().length === 0 ||
                        pacoteDoItem.length > 0
                      }
                    >
                      Sem código no contrato (aditivo)
                    </button>
                    <button
                      type="button"
                      className="botao-secundario"
                      onClick={() => void fecharPacote()}
                      disabled={
                        submitting || version === null || pacoteDoItem.length === 0
                      }
                    >
                      Fechar pacote de serviços
                    </button>
                  </div>
                  {pacoteDoItem.length === 0 ? null : (
                    <>
                      {/* A frase do pacote virou LISTA na revisão 2 do pacote de design: os
                          códigos entre parênteses não davam onde pendurar um ato por código,
                          e desfazer é do PAR (item, código). */}
                      <p className="dica">
                        Pacote em aberto, com {pacoteDoItem.length}{" "}
                        {pacoteDoItem.length === 1 ? "serviço" : "serviços"}. O item só conta
                        como resolvido depois do fechamento.
                      </p>
                      <ul className="lista-simples">
                        {pacoteDoItem.map((assignment) =>
                          assignment.code === null ? null : (
                            <li key={assignment.code}>
                              <code>{assignment.code}</code>{" "}
                              <button
                                type="button"
                                className="botao-secundario"
                                onClick={() =>
                                  setDesfazerCaixa(
                                    abrirDesfazer(
                                      selectedPendingId,
                                      assignment.code as string,
                                    ),
                                  )
                                }
                                disabled={submitting}
                              >
                                {DESFAZER_BOTAO}
                              </button>
                            </li>
                          ),
                        )}
                      </ul>
                      <CaixaDeDesfazerCodigo
                        caixa={desfazerDoItem(desfazerCaixa, selectedPendingId)}
                        pacoteFechado={pacoteFechado(
                          codes?.assignments ?? null,
                          selectedPendingId,
                        )}
                        submitting={submitting}
                        onChange={setDesfazerCaixa}
                        onDesfazer={() => void desfazerCodigo()}
                        onCancelar={() => setDesfazerCaixa(null)}
                      />
                    </>
                  )}
                  <ListaDeDesfeitos
                    desfeitos={desfeitosDoItem(
                      codes?.assignments ?? null,
                      selectedPendingId,
                    )}
                  />
                  <p className="dica">
                    Rejeitar exige nota: é ela que vira o texto do pedido de aditivo.
                  </p>
                </>
              )}
            </article>
          </section>
        ) : null}

        {etapaVisivel === "praca" && worksite !== null ? (
          <PainelDaPraca worksite={worksite} bulletin={bulletin}>
            <DeclararIdentidade
              folhas={folhas}
              itensPorFolha={pacotesPorFolha}
              rascunho={vinculo}
              previa={previaDoVinculo}
              onRascunho={(proximo) => {
                // Trocar a leitura apaga a prévia: um total conferido de outro par é pior
                // que total nenhum, e o botão de declarar depende dela.
                setPreviaDoVinculo((atual) =>
                  previaConfere(atual, proximo) ? atual : null,
                );
                setVinculo(proximo);
              }}
              onPrever={() => void preverVinculo()}
              onDeclarar={() => void declararIdentidade()}
              previewing={prevendo}
              submitting={submitting}
            />
          </PainelDaPraca>
        ) : null}

        {etapaVisivel === "boletim" ? (
          <section className="painel" aria-label="Boletim da medição">
            <h2>Boletim de medição</h2>
            <p className="aviso-fixo aviso-inline">{AVISO_MEDICAO}</p>
            {praca ? (
              // Desde a F-046 T4c o boletim é o da PRAÇA INTEIRA: um por folha, com o
              // total saindo da consolidação por código e a leitura fundida contando uma
              // vez. O que continua valendo é a recusa — folha pendente trava o boletim
              // todo —, e é ela que a etapa da praça nomeia por folha.
              <p className="dica">
                Esta praça tem {folhas.length} folhas, e o boletim cobre todas: um boletim
                por folha, cada parcela na folha onde foi lida, e o total da praça saindo
                da consolidação por código. Folha pendente de revisão trava o boletim
                inteiro — meia praça somada parece uma praça inteira.
              </p>
            ) : null}
            {bulletin === null ? (
              <div className="formulario">
                <p>
                  A medição ainda não foi montada nesta rodada. A obra, o período e o
                  rótulo vêm da própria rodada; quantidades, preços e totais vêm do takeoff
                  confirmado e do catálogo instalado.
                </p>
                {state === null ? null : (
                  <p className="dica">
                    {state.worksite_name} ({state.worksite_key}) ·{" "}
                    {state.reference_label} · medição {state.period_number}
                    {state.address === null ? "" : ` · ${state.address}`}
                    {state.contract_label === null ? "" : ` · ${state.contract_label}`}
                  </p>
                )}
                <button
                  type="button"
                  className="botao-primario"
                  onClick={() => void montarBoletim()}
                  disabled={submitting || version === null}
                >
                  {submitting ? "Montando…" : "Montar boletim e memória"}
                </button>
              </div>
            ) : (
              <>
                {boletimVencido ? (
                  <>
                    <BannerBoletimVencido
                      aprovada={aprovacao?.approved ?? false}
                      submitting={submitting}
                      onRemontar={() => void montarBoletim()}
                    />
                    <p className="dica">
                      Os números abaixo são os da montagem anterior e continuam gravados
                      como estão: nada nesta rodada recalcula sozinho, e a medição só muda
                      quando o boletim é montado de novo.
                    </p>
                  </>
                ) : null}
                <p>
                  Medição {bulletin.valuation.period_number} ·{" "}
                  {bulletin.valuation.reference_label} · sha256{" "}
                  <span className="digest" title={bulletin.valuation_sha256}>
                    {shortDigest(bulletin.valuation_sha256)}
                  </span>
                </p>
                {bulletin.valuation.bulletins.map((worksite) => (
                  <div key={worksite.worksite_key} className="obra">
                    <h3>
                      {worksite.worksite_name}{" "}
                      <span className="mono">({worksite.worksite_key})</span>
                    </h3>
                    <p>
                      {worksite.address ?? "endereço não informado"} ·{" "}
                      {worksite.contract_label ?? "contrato não informado"}
                    </p>
                    <table className="tabela">
                      <caption>Boletim de medição da obra</caption>
                      <thead>
                        <tr>
                          <th scope="col">Item</th>
                          <th scope="col">Código</th>
                          <th scope="col">Descrição</th>
                          <th scope="col">Un</th>
                          <th scope="col">Valor unit.</th>
                          <th scope="col">Quant.</th>
                          <th scope="col">Total</th>
                        </tr>
                      </thead>
                      <tbody>
                        {worksite.lines.map((line) => (
                          <tr key={line.item_number}>
                            <td>{line.item_number}</td>
                            <td className="mono">{line.code}</td>
                            <td className="celula-descricao">
                              <p className="boletim-descricao-texto">{line.description}</p>
                              <Inclusoes description={line.description} />
                            </td>
                            <td>{unitLabel(line.unit)}</td>
                            <td className="numero">{formatMoneyText(line.unit_price)}</td>
                            <td className="numero">{formatDecimalText(line.quantity)}</td>
                            <td className="numero">{formatMoneyText(line.total)}</td>
                          </tr>
                        ))}
                      </tbody>
                      <tfoot>
                        <tr>
                          <th scope="row" colSpan={6}>
                            Total da obra
                          </th>
                          <td className="numero">
                            {formatMoneyText(worksite.total_amount)}
                          </td>
                        </tr>
                      </tfoot>
                    </table>

                    <h4>Memória de cálculo</h4>
                    <ul className="memoria">
                      {bulletin.valuation.calc_sheets
                        .filter((sheet) => sheet.worksite_key === worksite.worksite_key)
                        .map((sheet) => (
                          <li key={sheet.item_number}>
                            <p>
                              <strong>Item {sheet.item_number}</strong> — total{" "}
                              {formatDecimalText(sheet.total_quantity)}
                            </p>
                            <ul>
                              {sheet.blocks.map((block, index) => (
                                <li key={`${sheet.item_number}-${index}`}>
                                  {block.label} ({recipeLabel(block.recipe)}):{" "}
                                  {block.operands
                                    .map(
                                      (operand) =>
                                        `${operand.name} ${formatDecimalText(
                                          operand.value,
                                        )}${operand.unit ? ` ${unitLabel(operand.unit)}` : ""}`,
                                    )
                                    .join(" × ")}
                                  {(block.deductions ?? []).length === 0
                                    ? ""
                                    : ` − ${(block.deductions ?? [])
                                        .map(
                                          (deduction) =>
                                            `${deduction.name} ${formatDecimalText(
                                              deduction.value,
                                            )}`,
                                        )
                                        .join(" − ")}`}{" "}
                                  = {formatDecimalText(block.subtotal)}
                                </li>
                              ))}
                            </ul>
                          </li>
                        ))}
                    </ul>
                  </div>
                ))}
                <p className="total-geral">
                  Total da medição: {formatMoneyText(bulletin.total_amount)}
                </p>
                <p className="dica">
                  Todos os números desta tela vêm do JSON do servidor, que os recomputa na
                  leitura; nada é somado ou multiplicado aqui.
                </p>
              </>
            )}
          </section>
        ) : null}

        {etapaVisivel === "aprovacao" ? (
          semAcesso ? (
            <PainelSemAcesso />
          ) : auditoriaReprovada !== null ? (
            <TelaAuditoriaReprovada
              findings={auditoriaReprovada}
              onDismiss={() => setAuditoriaReprovada(null)}
            />
          ) : (
            <section className="painel" aria-label="Aprovação e exportação">
              <h2>Aprovação e exportação</h2>
              <p className="aviso-fixo aviso-inline">{AVISO_MEDICAO}</p>
              {bulletin === null || aprovacao === null ? (
                <p>
                  A medição desta rodada ainda não foi lida. Monte o boletim na etapa
                  “Boletim”: aprovar decide sobre a medição que existe, e não há o que
                  decidir antes dela.
                </p>
              ) : (
                <>
                  <p>
                    Medição {bulletin.valuation.period_number} ·{" "}
                    {bulletin.valuation.reference_label} · conteúdo{" "}
                    <span
                      className="digest"
                      title={aprovacao.current_digest ?? undefined}
                    >
                      sha256 {shortDigest(aprovacao.current_digest)}
                    </span>{" "}
                    · total <strong>{formatMoneyText(bulletin.total_amount)}</strong>
                  </p>
                  <p className="dica">
                    Esta é a medição montada na etapa “Boletim”, sem nenhuma alteração —
                    aprovar não edita medição, decide sobre a que existe. Para conferir
                    linha a linha, volte à etapa “Boletim”. O digest acima é o do CONTEÚDO
                    medido, que é o que a aprovação amarra.
                  </p>
                  <div className="acoes-linha">
                    <button
                      type="button"
                      className="botao-secundario"
                      onClick={() => setOpenStep("boletim")}
                    >
                      Ver o boletim atual
                    </button>
                  </div>

                  {aprovacao.stale ? (
                    <p className="banner-erro" role="alert">
                      {MENSAGEM_APROVACAO_CADUCA}
                    </p>
                  ) : null}

                  <RegistroDaAprovacao
                    approval={aprovacao}
                    papel={state?.reviewer_role ?? "não declarado"}
                  />

                  {violacoesDeExportacao === null ? null : (
                    <section
                      className="violacoes"
                      aria-label="Motivos abertos do portão de exportação"
                    >
                      <h3>O portão de exportação recusou — nada foi publicado</h3>
                      {violacoesDeExportacao.map((violacao) => (
                        <div key={violationDetailLine(violacao.code, violacao.parts)}>
                          <p className="banner-erro" role="alert">
                            {errorMessage(violacao.code)}
                          </p>
                          <p className="digest">
                            {violationDetailLine(violacao.code, violacao.parts)}
                          </p>
                        </div>
                      ))}
                    </section>
                  )}

                  {aprovacaoValida ? null : (
                    <AtoDeAprovacao
                      titulo={`Aprovar a medição ${bulletin.valuation.period_number}${
                        state === null ? "" : ` de ${state.worksite_name}`
                      }`}
                      identidade={identidadeDaSessao}
                      papel={state?.reviewer_role ?? "não declarado"}
                      contentDigest={aprovacao.current_digest}
                      confirmando={confirmandoAprovacao}
                      gravando={submitting}
                      onAprovar={() => setConfirmandoAprovacao(true)}
                      onConfirmar={() => void aprovarMedicao()}
                      onCancelar={() => setConfirmandoAprovacao(false)}
                    />
                  )}

                  {aprovacaoValida ? (
                    <section className="exportacao" aria-label="Exportação do boletim">
                      <h3>Boletim exportado</h3>
                      {bulletin.workbook_present ? (
                        <>
                          <div className="acoes-linha">
                            {bulletin.workbook_url ? (
                              <a
                                className="botao-primario"
                                href={bulletin.workbook_url}
                                download={nomeDoBoletimXlsx}
                              >
                                Baixar boletim (.xlsx)
                              </a>
                            ) : null}
                            <button
                              type="button"
                              className="botao-secundario"
                              onClick={() => void exportarBoletim()}
                              disabled={submitting || version === null}
                            >
                              {exportando ? "Exportando…" : "Gerar de novo"}
                            </button>
                          </div>
                          <p
                            className="digest"
                            title={bulletin.workbook_sha256 ?? undefined}
                          >
                            {nomeDoBoletimXlsx} · sha256{" "}
                            {shortDigest(bulletin.workbook_sha256)}
                          </p>
                          <p className="dica">
                            Aprovado por{" "}
                            <span className="mono">
                              {aprovacao.approved_by ?? "não declarado"}
                            </span>
                            {aprovacao.approved_at === null
                              ? ""
                              : ` em ${formatTimestamp(aprovacao.approved_at)}`}
                            , sobre o conteúdo{" "}
                            <span
                              className="mono"
                              title={aprovacao.approved_digest ?? undefined}
                            >
                              sha256 {shortDigest(aprovacao.approved_digest)}
                            </span>{" "}
                            — o mesmo que está neste arquivo. Gerado pela rota, sem CLI. O
                            link de download expira e não aparece em registro nenhum.
                          </p>
                          {bulletin.workbook_url ? null : (
                            <p className="dica">
                              O link de download não veio nesta leitura; recarregue o estado
                              atual para pedir uma URL assinada nova.
                            </p>
                          )}
                        </>
                      ) : (
                        <>
                          <p>Nenhum arquivo publicado nesta rodada.</p>
                          <div className="acoes-linha">
                            <button
                              type="button"
                              className="botao-primario"
                              onClick={() => void exportarBoletim()}
                              disabled={submitting || version === null}
                            >
                              {exportando
                                ? "Exportando…"
                                : "Gerar e publicar o boletim (.xlsx)"}
                            </button>
                          </div>
                        </>
                      )}
                      {exportando ? <ProgressoExportacao estado="em-voo" /> : null}
                      <p className="dica">{AVISO_EXPORTACAO_FAIL_CLOSED}</p>
                    </section>
                  ) : (
                    <p className="dica">
                      Exportar é o passo depois de aprovar: sem aprovação nominal válida o
                      botão de gerar o boletim não aparece aqui, e a rota recusaria de
                      qualquer forma. A defesa é do servidor; esta tela só a espelha.
                    </p>
                  )}
                </>
              )}
            </section>
          )
        ) : null}
      </main>
    </div>
  );
}
