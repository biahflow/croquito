/**
 * Painel "Identidade de elemento na revisão" (F-051 T6), conforme os estados 03, 04 e 08 do
 * Design Approval Package aprovado em 2026-09-04.
 *
 * É o irmão, uma etapa antes, de `elementIdentityPanel.tsx` — e é o idioma dele, mantido de
 * propósito: aviso fixo antes de qualquer sugestão, selo `⚙ proposta · unresolved` tracejado,
 * recusa com motivo obrigatório, carimbo com PAPEL profissional e instante, e um único
 * caminho de escrita — "declarar a partir da sugestão" só semeia a seleção, nunca grava.
 *
 * Fronteiras que a tela honra:
 * - o `element_ref` é cunhado pelo servidor no ato, e o campo dele é somente-leitura e
 *   VAZIO: adivinhar o próximo número aqui seria inferir identidade (ADR-0058/0063), e o
 *   contador é partilhado com a cena — a tela não tem como saber o número certo;
 * - sugestão não é identidade, e o texto de "zero sugestões" é diferente do de "falha ao
 *   ler as sugestões": ausência e silêncio não são a mesma coisa;
 * - cor nunca é o único indicador: proposta é tracejado E o selo escrito, identidade é o
 *   glifo ◇ E o ref monoespaçado, revogada é a palavra "revogada" E o carimbo de quem
 *   revogou.
 */
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  ApiError,
  declareReviewElement,
  listReviewElementSuggestions,
  rejectReviewElementSuggestion,
  relabelReviewElement,
  revokeReviewElement,
  type ReviewElementDeclaration,
  type ReviewElementIdentityAct,
  type ReviewElementSuggestion,
  type VisionProposal,
} from "./api";
import {
  alternarEntidade,
  MAXIMO_DO_ROTULO,
  mensagemDoErroDeIdentidade,
  problemaDaRecusa,
  problemaDoRotulo,
} from "./elementIdentity";
import {
  carimboDoAtoDaRevisao,
  identidadesAtivas,
  mensagemDoErroDaRevisao,
  problemaDaDeclaracaoDaRevisao,
  problemaDaRevogacao,
  problemaDoRenomear,
  propostasSemIdentidade,
} from "./reviewElementIdentity";
import { decisionMoment } from "./rectification";

/** O aviso fixo que acompanha toda sugestão — o mesmo princípio do painel da cena. */
export const AVISO_DA_SUGESTAO =
  "Sugestão não é identidade: ela nasce não resolvida, não gera candidata nenhuma e não " +
  "vale nada até alguém declarar. O rótulo é leitura de máquina sobre caligrafia — aceitar " +
  "o agrupamento sem olhar a folha declara identidade errada, e é para isso que a recusa " +
  "existe.";

/** Etiqueta do `element_ref`: monoespaçada e com glifo, para não se confundir com selo. */
function EtiquetaDeElemento({ elementRef }: { elementRef: string }) {
  return (
    <span className="etiqueta-elemento">
      <span aria-hidden="true">◇</span> {elementRef}
    </span>
  );
}

/** O nome legível, AO LADO do `EL-00N` e nunca no lugar dele. */
function RotuloDoElemento({ rotulo }: { rotulo: string | null }) {
  return rotulo === null ? (
    <span className="elemento-rotulo elemento-rotulo-ausente">sem rótulo</span>
  ) : (
    <span className="elemento-rotulo">{rotulo}</span>
  );
}

export type RascunhoDeRenomear = {
  elementRef: string;
  rotulo: string;
  motivo: string;
};

export type RascunhoDeRevogar = { elementRef: string; motivo: string };

export type EstadoDaIdentidadeDaRevisao = {
  /** As identidades da revisão corrente, revogadas incluídas — a lista é o histórico. */
  declaracoes: readonly ReviewElementDeclaration[];
  /** Falha ao LER as declarações: estado declarado, nunca silêncio. */
  declaracoesFalharam: boolean;
  sugestoes: readonly ReviewElementSuggestion[];
  /** Falha ao LER as sugestões — texto diferente de "nenhuma sugestão". */
  sugestoesFalharam: boolean;
  /** Snapshot de propostas da revisão; sem ele não há sobre o que declarar. */
  propostas: readonly VisionProposal[];
  selecao: readonly string[];
  motivo: string;
  /** Rascunho do rótulo legível. Vazio é válido: o elemento pode nascer sem nome. */
  rotulo: string;
  /** Sugestão que semeou a seleção corrente, para a tela dizer de onde ela veio. */
  sugestaoSemente: string | null;
  recusandoSugestao: string | null;
  motivoDaRecusa: string;
  renomeando: RascunhoDeRenomear | null;
  revogando: RascunhoDeRevogar | null;
  ocupado: boolean;
  erro: string | null;
  carimbo: string | null;
};

/**
 * Corpo puro do painel: função só do estado e dos atos, sem efeito nem fetch — é o que os
 * testes renderizam. O container abaixo lê as sugestões e chama as rotas.
 */
export function ReviewElementIdentityBody({
  view,
  nomeDaProposta,
  onAlternarProposta,
  onMotivo,
  onRotulo,
  onDeclarar,
  onLimparSelecao,
  onSemearDaSugestao,
  onIniciarRecusa,
  onMotivoDaRecusa,
  onCancelarRecusa,
  onConfirmarRecusa,
  onIniciarRenomear,
  onRenomear,
  onCancelarRenomear,
  onConfirmarRenomear,
  onIniciarRevogacao,
  onRevogacao,
  onCancelarRevogacao,
  onConfirmarRevogacao,
}: {
  view: EstadoDaIdentidadeDaRevisao;
  nomeDaProposta: (proposalId: string) => string;
  onAlternarProposta: (proposalId: string) => void;
  onMotivo: (motivo: string) => void;
  onRotulo: (rotulo: string) => void;
  onDeclarar: () => void;
  onLimparSelecao: () => void;
  onSemearDaSugestao: (sugestao: ReviewElementSuggestion) => void;
  onIniciarRecusa: (suggestionId: string) => void;
  onMotivoDaRecusa: (motivo: string) => void;
  onCancelarRecusa: () => void;
  onConfirmarRecusa: () => void;
  onIniciarRenomear: (declaracao: ReviewElementDeclaration) => void;
  onRenomear: (rascunho: RascunhoDeRenomear) => void;
  onCancelarRenomear: () => void;
  onConfirmarRenomear: () => void;
  onIniciarRevogacao: (declaracao: ReviewElementDeclaration) => void;
  onRevogacao: (rascunho: RascunhoDeRevogar) => void;
  onCancelarRevogacao: () => void;
  onConfirmarRevogacao: () => void;
}) {
  const ativas = identidadesAtivas(view.declaracoes);
  const disponiveis = propostasSemIdentidade(view.propostas, view.declaracoes);
  const impedimentoDoRotulo = problemaDoRotulo(view.rotulo);
  const impedimento = problemaDaDeclaracaoDaRevisao(view.selecao, view.motivo);
  const bloqueado = impedimento !== null || impedimentoDoRotulo !== null;
  const impedimentoDaRecusa = problemaDaRecusa(view.motivoDaRecusa);
  const impedimentoDoRenomear =
    view.renomeando === null
      ? null
      : problemaDoRenomear(view.renomeando.rotulo, view.renomeando.motivo);
  const impedimentoDaRevogacao =
    view.revogando === null ? null : problemaDaRevogacao(view.revogando.motivo);

  return (
    <section
      className="identidade-elemento identidade-revisao"
      aria-label="Identidade de elemento na revisão"
    >
      <h3>Identidade de elemento na revisão</h3>
      <p className="identidade-intro">
        Quando o técnico escreve a medida longe do elemento e a liga por uma letra no balão,
        a proximidade em pixels não alcança o referente. Declarar aqui que um conjunto de
        propostas <em>é</em> o elemento “B” faz a cota com esse hint ganhar candidata pela
        identidade, ao lado das de proximidade. A identidade nasce de ato humano: o sistema
        sugere, quem declara é você.
      </p>

      {view.erro === null ? null : (
        <p className="identidade-erro" role="alert">
          {view.erro}
        </p>
      )}
      {view.carimbo === null ? null : (
        <p className="identidade-carimbo">{view.carimbo}</p>
      )}

      <h4>{`Elementos declarados nesta revisão (${ativas.length})`}</h4>
      {view.declaracoesFalharam ? (
        <p className="identidade-vazio">
          Não foi possível ler as identidades declaradas desta revisão. As candidatas por
          identidade que a revisão já gravou continuam no seletor de associação; o que falta
          aqui é a lista, não o efeito delas.
        </p>
      ) : view.declaracoes.length === 0 ? (
        <p className="identidade-vazio">
          Nenhum elemento declarado ainda. Sem identidade declarada, a revisão continua
          exatamente como é hoje — nenhuma candidata nova, nenhum grupo novo no seletor.
        </p>
      ) : (
        <ul className="lista-elementos">
          {view.declaracoes.map((declaracao) => {
            const revogada = declaracao.status === "revoked";
            return (
              <li
                key={declaracao.element_ref}
                className={revogada ? "elemento-revogado" : undefined}
              >
                <div className="elemento-linha">
                  <EtiquetaDeElemento elementRef={declaracao.element_ref} />
                  <RotuloDoElemento rotulo={declaracao.label} />
                  <span className="elemento-composicao">
                    {`${declaracao.proposal_ids.length} ${
                      declaracao.proposal_ids.length === 1 ? "proposta" : "propostas"
                    }`}
                  </span>
                  {revogada ? (
                    <span className="selo-revogado">✕ identidade revogada</span>
                  ) : null}
                </div>
                <p className="elemento-motivo">
                  {`Declarada por ${declaracao.declared_by_role} em ${decisionMoment(
                    declaracao.declared_at,
                  )}.`}
                  {revogada && declaracao.revoked_at !== null
                    ? ` Revogada por ${declaracao.revoked_by_role ?? "papel não registrado"} em ${decisionMoment(
                        declaracao.revoked_at,
                      )} — fica no histórico, e o ${declaracao.element_ref} não volta ao estoque.`
                    : ""}
                </p>
                {revogada ? null : (
                  <div className="proposta-elemento-acoes">
                    <button
                      type="button"
                      disabled={view.ocupado}
                      onClick={() => onIniciarRenomear(declaracao)}
                    >
                      Renomear rótulo
                    </button>
                    <button
                      type="button"
                      disabled={view.ocupado}
                      onClick={() => onIniciarRevogacao(declaracao)}
                    >
                      Revogar identidade
                    </button>
                  </div>
                )}
                {view.renomeando?.elementRef === declaracao.element_ref ? (
                  <div className="proposta-elemento-recusa">
                    <label htmlFor={`renomear-rotulo-${declaracao.element_ref}`}>
                      Rótulo novo
                    </label>
                    <input
                      id={`renomear-rotulo-${declaracao.element_ref}`}
                      type="text"
                      value={view.renomeando.rotulo}
                      maxLength={MAXIMO_DO_ROTULO}
                      onChange={(event) =>
                        onRenomear({
                          elementRef: declaracao.element_ref,
                          rotulo: event.target.value,
                          motivo: view.renomeando?.motivo ?? "",
                        })
                      }
                    />
                    <label htmlFor={`renomear-motivo-${declaracao.element_ref}`}>
                      Por que o nome muda
                    </label>
                    <input
                      id={`renomear-motivo-${declaracao.element_ref}`}
                      type="text"
                      value={view.renomeando.motivo}
                      onChange={(event) =>
                        onRenomear({
                          elementRef: declaracao.element_ref,
                          rotulo: view.renomeando?.rotulo ?? "",
                          motivo: event.target.value,
                        })
                      }
                    />
                    {impedimentoDoRenomear === null ? null : (
                      <p className="identidade-impedimento">{impedimentoDoRenomear}</p>
                    )}
                    <p className="identidade-nota">
                      Renomear move o casamento junto: o elemento renomeado deixa de ser
                      candidato das leituras com o hint antigo.
                    </p>
                    <div className="proposta-elemento-acoes">
                      <button
                        type="button"
                        disabled={view.ocupado || impedimentoDoRenomear !== null}
                        onClick={onConfirmarRenomear}
                      >
                        Registrar o novo rótulo
                      </button>
                      <button type="button" onClick={onCancelarRenomear}>
                        Cancelar
                      </button>
                    </div>
                  </div>
                ) : null}
                {view.revogando?.elementRef === declaracao.element_ref ? (
                  <div className="proposta-elemento-recusa">
                    <label htmlFor={`revogar-motivo-${declaracao.element_ref}`}>
                      Por que esta identidade deixa de valer
                    </label>
                    <input
                      id={`revogar-motivo-${declaracao.element_ref}`}
                      type="text"
                      value={view.revogando.motivo}
                      onChange={(event) =>
                        onRevogacao({
                          elementRef: declaracao.element_ref,
                          motivo: event.target.value,
                        })
                      }
                    />
                    {impedimentoDaRevogacao === null ? null : (
                      <p className="identidade-impedimento">{impedimentoDaRevogacao}</p>
                    )}
                    <p className="identidade-nota">
                      Revogar não desfaz associação já confirmada por esta identidade:
                      corrigir uma associação é a retificação de decisão que a revisão já
                      tem.
                    </p>
                    <div className="proposta-elemento-acoes">
                      <button
                        type="button"
                        disabled={view.ocupado || impedimentoDaRevogacao !== null}
                        onClick={onConfirmarRevogacao}
                      >
                        Registrar a revogação
                      </button>
                      <button type="button" onClick={onCancelarRevogacao}>
                        Cancelar
                      </button>
                    </div>
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}

      <h4>{`Sugestões a partir do rótulo do modelo (${view.sugestoes.length})`}</h4>
      {view.sugestoesFalharam ? (
        <p className="identidade-vazio">
          Não foi possível ler as sugestões do sistema. Declarar identidade continua possível
          pela seleção manual abaixo — a sugestão torna o ato barato, não o torna correto.
        </p>
      ) : view.sugestoes.length === 0 ? (
        <p className="identidade-vazio">
          Nenhuma sugestão em aberto: ou o modelo não rotulou proposta nenhuma, ou as
          rotuladas já foram declaradas ou recusadas. Sugestão é atalho — a declaração pela
          seleção manual abaixo é o caminho completo e não depende dela.
        </p>
      ) : (
        <>
          <p className="identidade-aviso">{AVISO_DA_SUGESTAO}</p>
          <ul className="lista-propostas-elemento">
            {view.sugestoes.map((sugestao) => (
              <li key={sugestao.suggestion_id}>
                <div className="proposta-elemento-linha">
                  <span className="selo-proposta">
                    <span aria-hidden="true">⚙</span> proposta · {sugestao.status}
                  </span>
                  <span className="proposta-elemento-descricao">
                    {`rótulo do modelo “${sugestao.label}” · ${
                      sugestao.proposal_ids.length
                    } ${sugestao.proposal_ids.length === 1 ? "proposta" : "propostas"}`}
                  </span>
                </div>
                <p className="proposta-elemento-sinal">
                  {sugestao.proposal_ids
                    .map((proposalId) => nomeDaProposta(proposalId))
                    .join(" · ")}
                </p>
                <div className="proposta-elemento-acoes">
                  <button
                    type="button"
                    className="primary"
                    disabled={view.ocupado}
                    onClick={() => onSemearDaSugestao(sugestao)}
                  >
                    Declarar elemento a partir da proposta
                  </button>
                  <button
                    type="button"
                    disabled={view.ocupado}
                    onClick={() => onIniciarRecusa(sugestao.suggestion_id)}
                  >
                    Descartar proposta
                  </button>
                </div>
                {view.recusandoSugestao === sugestao.suggestion_id ? (
                  <div className="proposta-elemento-recusa">
                    <label htmlFor={`recusa-sugestao-${sugestao.suggestion_id}`}>
                      Por que esta sugestão não descreve um elemento
                    </label>
                    <input
                      id={`recusa-sugestao-${sugestao.suggestion_id}`}
                      type="text"
                      value={view.motivoDaRecusa}
                      onChange={(event) => onMotivoDaRecusa(event.target.value)}
                    />
                    {impedimentoDaRecusa === null ? null : (
                      <p className="identidade-impedimento">{impedimentoDaRecusa}</p>
                    )}
                    <div className="proposta-elemento-acoes">
                      <button
                        type="button"
                        disabled={view.ocupado || impedimentoDaRecusa !== null}
                        onClick={onConfirmarRecusa}
                      >
                        Registrar a recusa
                      </button>
                      <button type="button" onClick={onCancelarRecusa}>
                        Cancelar
                      </button>
                    </div>
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        </>
      )}

      <h4>Declarar elemento</h4>
      <label htmlFor="identidade-revisao-ref">Identidade do elemento</label>
      {/* Somente-leitura e VAZIO: o ref é cunhado pelo servidor no ato, e o contador é
          partilhado com a cena — escrever aqui um número adivinhado seria mostrar como
          fato o que a tela não tem como saber. */}
      <input
        id="identidade-revisao-ref"
        type="text"
        value=""
        readOnly
        placeholder="cunhada no ato pelo servidor"
      />
      <p className="identidade-cunhagem">
        <strong>Identidade do elemento:</strong> cunhada no ato — nunca digitada, nunca
        inferida, nunca reaproveitada. Você declara <em>quais</em> propostas são o elemento,
        nunca qual é o nome dele.
      </p>
      {view.sugestaoSemente === null ? null : (
        <p className="identidade-semente">
          {`Seleção semeada pela sugestão ${view.sugestaoSemente}. Confira o grupo antes de assinar: aceitar uma sugestão errada declara identidade errada.`}
        </p>
      )}
      {view.propostas.length === 0 ? (
        <p className="identidade-vazio">
          Esta revisão ainda não tem propostas de geometria. A identidade da revisão é
          declarada sobre proposta; sem nenhuma, o caminho continua sendo a anotação da
          folha.
        </p>
      ) : disponiveis.length === 0 ? (
        <p className="identidade-vazio">
          Todas as propostas desta revisão já pertencem a uma identidade ativa.
        </p>
      ) : (
        <ul className="lista-entidades-sem-identidade">
          {disponiveis.map((proposta) => (
            <li key={proposta.id}>
              <label>
                <input
                  type="checkbox"
                  checked={view.selecao.includes(proposta.id)}
                  onChange={() => onAlternarProposta(proposta.id)}
                />
                <span>{nomeDaProposta(proposta.id)}</span>
                <span className="entidade-sem-identidade-descricao">
                  {/* O rótulo do modelo é declarado como do MODELO: ele é sinal para
                      escolher o grupo, e nunca a identidade que só o ato humano cria. */}
                  {proposta.label
                    ? `rótulo do modelo “${proposta.label}”`
                    : "sem rótulo do modelo"}
                </span>
                <span className="etiqueta-elemento etiqueta-elemento-ausente">
                  — sem identidade
                </span>
              </label>
            </li>
          ))}
        </ul>
      )}

      <label htmlFor="identidade-revisao-rotulo">Rótulo (o que a pessoa lê)</label>
      <input
        id="identidade-revisao-rotulo"
        type="text"
        value={view.rotulo}
        maxLength={MAXIMO_DO_ROTULO}
        placeholder="B — fecho da área de lazer"
        onChange={(event) => onRotulo(event.target.value)}
      />
      <p className="identidade-nota">
        O rótulo é o <strong>nome legível</strong> do elemento, e é por ele que o hint da
        cota-balão procura o referente: “B” alcança “B”, “grade B” e “B — fecho da área de
        lazer”, e nada mais. Ele é opcional — sem rótulo o elemento existe, mas nenhuma
        cota-balão o alcança. Entre as identidades ativas do job, o rótulo é único.
      </p>
      {impedimentoDoRotulo === null ? null : (
        <p className="identidade-impedimento">{impedimentoDoRotulo}</p>
      )}

      <label htmlFor="identidade-revisao-motivo">Justificativa do agrupamento</label>
      <input
        id="identidade-revisao-motivo"
        type="text"
        value={view.motivo}
        onChange={(event) => onMotivo(event.target.value)}
      />
      {impedimento === null ? null : (
        <p className="identidade-impedimento">{impedimento}</p>
      )}
      <div className="proposta-elemento-acoes">
        <button
          type="button"
          className="primary"
          disabled={view.ocupado || bloqueado}
          onClick={onDeclarar}
        >
          {`Declarar elemento com ${view.selecao.length} ${
            view.selecao.length === 1 ? "proposta" : "propostas"
          }`}
        </button>
        <button type="button" disabled={view.ocupado} onClick={onLimparSelecao}>
          Limpar seleção
        </button>
      </div>
      <p className="identidade-nota">
        A declaração não se apaga: revogar é ato registrado, com papel e instante, e a
        identidade revogada continua no histórico — o mesmo padrão da decisão de leitura.
      </p>
    </section>
  );
}

/**
 * Container do painel: lê as sugestões, envia os atos e avisa o chamador que a revisão
 * mudou.
 *
 * As declarações vêm de cima (`CroquiApp` já as lê para rotular o grupo do seletor de
 * associação): duas leituras da mesma lista divergiriam entre si, e a divergência
 * apareceria como um grupo do seletor citando um elemento que este painel não conhece.
 */
export function ReviewElementIdentityPanel({
  accessToken,
  jobId,
  baseVersion,
  declaracoes,
  declaracoesFalharam,
  propostas,
  nomeDaProposta,
  onActed,
  onConflict,
}: {
  accessToken: string;
  jobId: string;
  /** `base_version` de todo ato: a versão da revisão que ESTA tela leu. */
  baseVersion: number;
  declaracoes: readonly ReviewElementDeclaration[];
  declaracoesFalharam: boolean;
  propostas: readonly VisionProposal[];
  nomeDaProposta: (proposalId: string) => string;
  onActed: () => void;
  onConflict: () => void;
}) {
  const [sugestoes, setSugestoes] = useState<ReviewElementSuggestion[]>([]);
  const [sugestoesFalharam, setSugestoesFalharam] = useState(false);
  const [selecao, setSelecao] = useState<string[]>([]);
  const [motivo, setMotivo] = useState("");
  const [rotulo, setRotulo] = useState("");
  const [sugestaoSemente, setSugestaoSemente] = useState<string | null>(null);
  const [recusandoSugestao, setRecusandoSugestao] = useState<string | null>(null);
  const [motivoDaRecusa, setMotivoDaRecusa] = useState("");
  const [renomeando, setRenomeando] = useState<RascunhoDeRenomear | null>(null);
  const [revogando, setRevogando] = useState<RascunhoDeRevogar | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [carimbo, setCarimbo] = useState<string | null>(null);

  const recarregarSugestoes = useCallback(() => {
    if (accessToken === "" || jobId === "") {
      return;
    }
    void listReviewElementSuggestions(accessToken, jobId)
      .then((lista) => {
        setSugestoes(lista.suggestions);
        setSugestoesFalharam(false);
      })
      .catch(() => {
        // Ler sugestão é conveniência: falhar aqui não impede declarar pela seleção
        // manual, e o painel diz isso com todas as letras em vez de sumir com a seção.
        setSugestoes([]);
        setSugestoesFalharam(true);
      });
  }, [accessToken, jobId]);

  // Revisão nova é lista de sugestões nova: o produtor roda sobre o snapshot corrente, e
  // oferecer as da versão anterior proporia agrupar propostas que acabaram de ganhar
  // identidade. Os rascunhos em curso também caem — eles citavam a revisão que passou, e o
  // erro também: uma recusa por conflito de versão deixa de valer assim que a tela lê a
  // versão nova. O carimbo do último ato FICA — ele é o registro do que a pessoa acabou de
  // fazer, e some junto com a tela, não com a versão.
  useEffect(() => {
    setErro(null);
    setSelecao([]);
    setRotulo("");
    setSugestaoSemente(null);
    setRecusandoSugestao(null);
    setMotivoDaRecusa("");
    setRenomeando(null);
    setRevogando(null);
    recarregarSugestoes();
  }, [recarregarSugestoes, baseVersion]);

  const reportar = useCallback(
    (error: unknown, fallback: string) => {
      if (error instanceof ApiError) {
        if (error.code === "REVISION_CONFLICT") {
          onConflict();
        }
        setErro(mensagemDoErroDaRevisao(error) ?? mensagemDoErroDeIdentidade(error));
        return;
      }
      setErro(fallback);
    },
    [onConflict],
  );

  const registrarAto = useCallback(
    (ato: ReviewElementIdentityAct) => {
      setCarimbo(carimboDoAtoDaRevisao(ato, decisionMoment(ato.acted_at)));
      setSelecao([]);
      setMotivo("");
      setRotulo("");
      setSugestaoSemente(null);
      setRenomeando(null);
      setRevogando(null);
      onActed();
    },
    [onActed],
  );

  const declarar = useCallback(() => {
    setOcupado(true);
    setErro(null);
    const nome = rotulo.trim();
    void declareReviewElement(accessToken, jobId, {
      base_version: baseVersion,
      proposal_ids: [...selecao],
      reason: motivo.trim(),
      // Campo em branco NÃO vira `""`: o servidor recusa string vazia, e declarar sem nome
      // é omitir o campo — o elemento nasce sem rótulo, que é revisão válida.
      ...(nome === "" ? {} : { label: nome }),
    })
      .then(registrarAto)
      .catch((error: unknown) =>
        reportar(error, "Não foi possível declarar a identidade do elemento."),
      )
      .finally(() => setOcupado(false));
  }, [accessToken, baseVersion, jobId, motivo, registrarAto, reportar, rotulo, selecao]);

  const confirmarRenomear = useCallback(() => {
    if (renomeando === null) {
      return;
    }
    setOcupado(true);
    setErro(null);
    void relabelReviewElement(accessToken, jobId, {
      base_version: baseVersion,
      element_ref: renomeando.elementRef,
      label: renomeando.rotulo.trim(),
      reason: renomeando.motivo.trim(),
    })
      .then(registrarAto)
      .catch((error: unknown) =>
        reportar(error, "Não foi possível renomear a identidade do elemento."),
      )
      .finally(() => setOcupado(false));
  }, [accessToken, baseVersion, jobId, registrarAto, renomeando, reportar]);

  const confirmarRevogacao = useCallback(() => {
    if (revogando === null) {
      return;
    }
    setOcupado(true);
    setErro(null);
    void revokeReviewElement(accessToken, jobId, {
      base_version: baseVersion,
      element_ref: revogando.elementRef,
      reason: revogando.motivo.trim(),
    })
      .then(registrarAto)
      .catch((error: unknown) =>
        reportar(error, "Não foi possível revogar a identidade do elemento."),
      )
      .finally(() => setOcupado(false));
  }, [accessToken, baseVersion, jobId, registrarAto, reportar, revogando]);

  const confirmarRecusa = useCallback(() => {
    const suggestionId = recusandoSugestao;
    if (suggestionId === null) {
      return;
    }
    setOcupado(true);
    setErro(null);
    void rejectReviewElementSuggestion(accessToken, jobId, suggestionId, {
      reason: motivoDaRecusa.trim(),
    })
      .then((recusa) => {
        setCarimbo(
          `Sugestão ${recusa.suggestion_id} recusada por ${recusa.rejected_by_role} em ` +
            `${decisionMoment(recusa.rejected_at)}. Ela não é mais oferecida.`,
        );
        setRecusandoSugestao(null);
        setMotivoDaRecusa("");
        recarregarSugestoes();
      })
      .catch((error: unknown) =>
        reportar(error, "Não foi possível registrar a recusa da sugestão."),
      )
      .finally(() => setOcupado(false));
  }, [
    accessToken,
    jobId,
    motivoDaRecusa,
    recarregarSugestoes,
    recusandoSugestao,
    reportar,
  ]);

  const view = useMemo<EstadoDaIdentidadeDaRevisao>(
    () => ({
      declaracoes,
      declaracoesFalharam,
      sugestoes,
      sugestoesFalharam,
      propostas,
      selecao,
      motivo,
      rotulo,
      sugestaoSemente,
      recusandoSugestao,
      motivoDaRecusa,
      renomeando,
      revogando,
      ocupado,
      erro,
      carimbo,
    }),
    [
      carimbo,
      declaracoes,
      declaracoesFalharam,
      erro,
      motivo,
      motivoDaRecusa,
      ocupado,
      propostas,
      recusandoSugestao,
      renomeando,
      revogando,
      rotulo,
      selecao,
      sugestaoSemente,
      sugestoes,
      sugestoesFalharam,
    ],
  );

  return (
    <ReviewElementIdentityBody
      view={view}
      nomeDaProposta={nomeDaProposta}
      onAlternarProposta={(proposalId) =>
        setSelecao((atual) => alternarEntidade(atual, proposalId))
      }
      onMotivo={setMotivo}
      onRotulo={setRotulo}
      onDeclarar={declarar}
      onLimparSelecao={() => {
        setSelecao([]);
        setRotulo("");
        setSugestaoSemente(null);
      }}
      onSemearDaSugestao={(sugestao) => {
        // Confirmar uma sugestão é o MESMO ato da declaração manual: ela só semeia a
        // seleção, o rótulo e o rascunho da justificativa. Não há segundo caminho de
        // escrita.
        setSelecao([...sugestao.proposal_ids]);
        setSugestaoSemente(sugestao.suggestion_id);
        setRotulo(sugestao.label);
        setMotivo(
          `Agrupamento confirmado a partir da sugestão ${sugestao.suggestion_id} (rótulo do modelo “${sugestao.label}”).`,
        );
        setRecusandoSugestao(null);
      }}
      onIniciarRecusa={(suggestionId) => {
        setRecusandoSugestao(suggestionId);
        setMotivoDaRecusa("");
      }}
      onMotivoDaRecusa={setMotivoDaRecusa}
      onCancelarRecusa={() => {
        setRecusandoSugestao(null);
        setMotivoDaRecusa("");
      }}
      onConfirmarRecusa={confirmarRecusa}
      onIniciarRenomear={(declaracao) => {
        setRevogando(null);
        setRenomeando({
          elementRef: declaracao.element_ref,
          rotulo: declaracao.label ?? "",
          motivo: "",
        });
      }}
      onRenomear={setRenomeando}
      onCancelarRenomear={() => setRenomeando(null)}
      onConfirmarRenomear={confirmarRenomear}
      onIniciarRevogacao={(declaracao) => {
        setRenomeando(null);
        setRevogando({ elementRef: declaracao.element_ref, motivo: "" });
      }}
      onRevogacao={setRevogando}
      onCancelarRevogacao={() => setRevogando(null)}
      onConfirmarRevogacao={confirmarRevogacao}
    />
  );
}
