/**
 * Painel "Identidade de elemento" da revisão do croqui (F-047 T7a), conforme os estados
 * 01 a 04 do Design Approval Package aprovado em 2026-08-28.
 *
 * Fronteiras que a tela honra:
 * - a tela NUNCA soma, multiplica ou arredonda quantidade — ela não mostra quantidade
 *   nenhuma, só o que o servidor já gravou na cena (`apps/web/AGENTS.md`);
 * - proposta aparece rotulada como PROPOSTA, com o sinal que a gerou escrito, e nunca
 *   como identidade (ADR-0058, decisão 2);
 * - o `element_ref` é cunhado pelo servidor no ato — o formulário não oferece o teclado
 *   para o nome, porque digitá-lo é recusado com `ELEMENT_REF_NOT_ASSIGNABLE`;
 * - `approximate` não atravessa para a medição, e o motivo está escrito na tela, não num
 *   comentário de código (decisão 4 do ADR-0058, emendada no aceite humano);
 * - cor nunca é o único indicador: precisão é traço E palavra, e "alimenta"/"não
 *   alimenta" é selo E frase.
 */
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  ApiError,
  declareElement,
  listElementProposals,
  rejectElementProposal,
  type ElementProposal,
} from "./api";
import {
  alternarEntidade,
  avisoDeCamadasMisturadas,
  AVISO_DA_PROPOSTA,
  camadasDaSelecao,
  carimboDoAto,
  descricaoDaEntidade,
  elementosDeclarados,
  entidadesSemIdentidade,
  MAXIMO_DO_ROTULO,
  mensagemDoErroDeIdentidade,
  problemaDaDeclaracao,
  problemaDaRecusa,
  problemaDoRotulo,
  sinalDaProposta,
  type ElementoDeclarado,
} from "./elementIdentity";
import { decisionMoment } from "./rectification";
import type { EstadoDoPreview } from "./CroquiApp";
import type { EntidadeDaCena } from "./scenePreview";
import type { SceneRevision } from "@croquito/contracts";

/** Etiqueta do `element_ref`: monoespaçada e com glifo, para não se confundir com selo. */
function EtiquetaDeElemento({ elementRef }: { elementRef: string }) {
  return (
    <span className="etiqueta-elemento">
      <span aria-hidden="true">◇</span> {elementRef}
    </span>
  );
}

/** A precisão dita por traço E por escrito — a cor nunca decide sozinha. */
function PrecisaoEscrita({ elemento }: { elemento: ElementoDeclarado }) {
  return (
    <span className="elemento-precisao">
      {elemento.precisao === null ? null : (
        <span
          className={`amostra-precisao precisao-${elemento.precisao}`}
          aria-hidden="true"
        />
      )}
      {elemento.precisaoNome}
    </span>
  );
}

/**
 * O nome legível, AO LADO do `EL-00N` e nunca no lugar dele (F-047 T2b).
 *
 * Sem rótulo a tela escreve "sem rótulo" por extenso, e não um traço mudo: elemento sem nome
 * é estado normal, e quem lê precisa distinguir "ninguém nomeou" de "o nome não carregou".
 */
function RotuloDoElemento({ rotulo }: { rotulo: string | null }) {
  return rotulo === null ? (
    <span className="elemento-rotulo elemento-rotulo-ausente">sem rótulo</span>
  ) : (
    <span className="elemento-rotulo">{rotulo}</span>
  );
}

function ElementoDeclaradoItem({ elemento }: { elemento: ElementoDeclarado }) {
  return (
    <li className={elemento.alimenta ? "elemento-alimenta" : "elemento-nao-alimenta"}>
      <div className="elemento-linha">
        <EtiquetaDeElemento elementRef={elemento.elementRef} />
        <RotuloDoElemento rotulo={elemento.rotulo} />
        <span className="elemento-composicao">
          {`camada ${elemento.camada} · ${elemento.entityIds.length} ${
            elemento.entityIds.length === 1 ? "entidade" : "entidades"
          }`}
          {elemento.anotacoes > 0
            ? `, ${elemento.anotacoes} de anotação (não é quantidade)`
            : ""}
        </span>
        <PrecisaoEscrita elemento={elemento} />
        <span className={elemento.alimenta ? "selo-alimenta" : "selo-nao-alimenta"}>
          {elemento.alimenta
            ? "→ alimenta a medição"
            : "✕ não alimenta a medição"}
        </span>
      </div>
      {elemento.motivo === null ? null : (
        <p className="elemento-motivo">{elemento.motivo}</p>
      )}
    </li>
  );
}

export type EstadoDaIdentidade = {
  /** Estado da leitura da cena — o mesmo do preview: a identidade mora na geometria. */
  estado: EstadoDoPreview;
  scene: SceneRevision.CroquitoSceneRevision | null;
  proposals: ElementProposal[];
  /** Falha ao LER propostas: estado declarado, nunca silêncio. */
  propostasFalharam: boolean;
  selecao: readonly string[];
  motivo: string;
  /** Rascunho do rótulo legível (F-047 T2b). Vazio é válido: o elemento nasce sem nome. */
  rotulo: string;
  /** Proposta que semeou a seleção corrente, para a tela dizer de onde ela veio. */
  propostaSemente: string | null;
  recusandoProposta: string | null;
  motivoDaRecusa: string;
  ocupado: boolean;
  erro: string | null;
  carimbo: string | null;
};

/**
 * Corpo puro do painel: função só do estado e dos atos, sem efeito nem fetch — é o que os
 * testes renderizam. O container abaixo calcula o estado e chama as rotas.
 */
export function ElementIdentityBody({
  view,
  onToggleEntidade,
  onMotivo,
  onRotulo,
  onDeclarar,
  onLimparSelecao,
  onSemearDaProposta,
  onIniciarRecusa,
  onMotivoDaRecusa,
  onCancelarRecusa,
  onConfirmarRecusa,
}: {
  view: EstadoDaIdentidade;
  onToggleEntidade: (entityId: string) => void;
  onMotivo: (motivo: string) => void;
  onRotulo: (rotulo: string) => void;
  onDeclarar: () => void;
  onLimparSelecao: () => void;
  onSemearDaProposta: (proposal: ElementProposal) => void;
  onIniciarRecusa: (proposalId: string) => void;
  onMotivoDaRecusa: (motivo: string) => void;
  onCancelarRecusa: () => void;
  onConfirmarRecusa: () => void;
}) {
  const entities: EntidadeDaCena[] = view.scene?.entities ?? [];
  const elementos = elementosDeclarados(entities, view.scene?.element_labels ?? {});
  const semIdentidade = entidadesSemIdentidade(entities);
  const camadas = camadasDaSelecao(entities, view.selecao);
  const aviso = avisoDeCamadasMisturadas(camadas);
  const impedimentoDoRotulo = problemaDoRotulo(view.rotulo);
  const impedimento = problemaDaDeclaracao(view.selecao, view.motivo);
  // Cada impedimento aparece embaixo do campo que o causou; o botão obedece aos dois.
  const bloqueado = impedimento !== null || impedimentoDoRotulo !== null;
  const impedimentoDaRecusa = problemaDaRecusa(view.motivoDaRecusa);

  if (view.estado === "sem-cena") {
    return (
      <section className="identidade-elemento" aria-label="Identidade de elemento">
        <h3>Identidade de elemento</h3>
        <p className="identidade-vazio">
          <strong>Ainda não há cena resolvida.</strong> A identidade de elemento é
          declarada sobre a geometria: quando o traçado resolver, as entidades aparecem
          aqui para serem agrupadas.
        </p>
      </section>
    );
  }
  if (view.estado === "carregando") {
    return (
      <section className="identidade-elemento" aria-label="Identidade de elemento">
        <h3>Identidade de elemento</h3>
        <p className="identidade-vazio">Lendo a cena e as propostas de agrupamento…</p>
      </section>
    );
  }
  if (view.estado === "falhou" || view.scene === null) {
    return (
      <section className="identidade-elemento" aria-label="Identidade de elemento">
        <h3>Identidade de elemento</h3>
        <p className="identidade-vazio">
          Não foi possível ler a cena para declarar identidade. A aprovação e o portão de
          exportação não dependem deste painel.
        </p>
      </section>
    );
  }

  return (
    <section className="identidade-elemento" aria-label="Identidade de elemento">
      <h3>Identidade de elemento</h3>
      <p className="identidade-intro">
        <code>entity_id</code> é identidade de linha e muda quando a aprovação cria revisão
        nova; camada é vocabulário de CAD; o rótulo é texto livre. A identidade de elemento
        é um terceiro campo, ao lado dos dois — e é o que liga a geometria aprovada à
        medição. Ela nasce de ato humano: o sistema propõe, quem declara é você.
      </p>

      {view.erro === null ? null : (
        <p className="identidade-erro" role="alert">
          {view.erro}
        </p>
      )}
      {view.carimbo === null ? null : (
        <p className="identidade-carimbo">{view.carimbo}</p>
      )}

      <h4>{`Elementos declarados nesta cena (${elementos.length})`}</h4>
      {elementos.length === 0 ? (
        <p className="identidade-vazio">
          Nenhum elemento declarado ainda. Sem identidade declarada, a revisão e a medição
          continuam exatamente como são hoje.
        </p>
      ) : (
        <ul className="lista-elementos">
          {elementos.map((elemento) => (
            <ElementoDeclaradoItem key={elemento.elementRef} elemento={elemento} />
          ))}
        </ul>
      )}

      <h4>{`Agrupamentos propostos pelo sistema (${view.proposals.length})`}</h4>
      {view.propostasFalharam ? (
        <p className="identidade-vazio">
          Não foi possível ler as propostas do sistema. Declarar identidade continua
          possível pela seleção manual abaixo — a proposta torna o ato barato, não o torna
          correto.
        </p>
      ) : view.proposals.length === 0 ? (
        <p className="identidade-vazio">
          Nenhuma proposta em aberto. Proposta é atalho: a declaração pela seleção manual
          abaixo é o caminho completo e não depende dela.
        </p>
      ) : (
        <>
          <p className="identidade-aviso">{AVISO_DA_PROPOSTA}</p>
          <ul className="lista-propostas-elemento">
            {view.proposals.map((proposta) => (
              <li key={proposta.proposal_id}>
                <div className="proposta-elemento-linha">
                  <span className="selo-proposta">
                    <span aria-hidden="true">⚙</span> proposta · {proposta.status}
                  </span>
                  <span className="proposta-elemento-descricao">
                    {`${proposta.entity_ids.length} ${
                      proposta.entity_ids.length === 1 ? "entidade" : "entidades"
                    } na camada ${proposta.layer}`}
                    {proposta.label === null ? "" : ` · rótulo “${proposta.label}”`}
                  </span>
                </div>
                <p className="proposta-elemento-sinal">
                  {`Proposta por ${sinalDaProposta(proposta.signal)}.`}
                </p>
                <div className="proposta-elemento-acoes">
                  <button
                    type="button"
                    className="primary"
                    disabled={view.ocupado}
                    onClick={() => onSemearDaProposta(proposta)}
                  >
                    Declarar elemento a partir da proposta
                  </button>
                  <button
                    type="button"
                    disabled={view.ocupado}
                    onClick={() => onIniciarRecusa(proposta.proposal_id)}
                  >
                    Descartar proposta
                  </button>
                </div>
                {view.recusandoProposta === proposta.proposal_id ? (
                  <div className="proposta-elemento-recusa">
                    <label htmlFor={`recusa-${proposta.proposal_id}`}>
                      Por que esta proposta não descreve um elemento
                    </label>
                    <input
                      id={`recusa-${proposta.proposal_id}`}
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
      <p className="identidade-cunhagem">
        <strong>Identidade do elemento:</strong> cunhada pelo servidor no ato, estável, e
        sobrevive à revisão que a aprovação cria. Você declara <em>quais</em> entidades são
        o elemento, nunca qual é o nome dele.
      </p>
      {view.propostaSemente === null ? null : (
        <p className="identidade-semente">
          {`Seleção semeada pela proposta ${view.propostaSemente}. Confira o grupo antes de assinar: aceitar uma proposta errada declara identidade errada.`}
        </p>
      )}
      {semIdentidade.length === 0 ? (
        <p className="identidade-vazio">
          Todas as entidades desta cena já têm identidade declarada.
        </p>
      ) : (
        <ul className="lista-entidades-sem-identidade">
          {semIdentidade.map((entity) => {
            const entityId = entity.id ?? "";
            return (
              <li key={entityId}>
                <label>
                  <input
                    type="checkbox"
                    checked={view.selecao.includes(entityId)}
                    onChange={() => onToggleEntidade(entityId)}
                  />
                  <code>{entityId}</code>
                  <span className="entidade-sem-identidade-descricao">
                    {descricaoDaEntidade(entity)}
                  </span>
                  <span className="etiqueta-elemento etiqueta-elemento-ausente">
                    — sem identidade
                  </span>
                </label>
              </li>
            );
          })}
        </ul>
      )}

      {aviso === null ? null : <p className="identidade-aviso">{aviso}</p>}

      <label htmlFor="identidade-rotulo">Rótulo (o que a pessoa lê)</label>
      <input
        id="identidade-rotulo"
        type="text"
        value={view.rotulo}
        maxLength={MAXIMO_DO_ROTULO}
        placeholder="Alambrado da quadra"
        onChange={(event) => onRotulo(event.target.value)}
      />
      <p className="identidade-nota">
        O rótulo é o <strong>nome legível</strong> do elemento, e é opcional — sem ele o
        elemento fica "sem rótulo", que é estado válido. Ele não é identidade: o que liga a
        cena à legenda continua sendo só o <code>EL-00N</code>, e dois elementos com o mesmo
        rótulo continuam sendo dois elementos. Renomear depois é ato registrado, com autor e
        instante.
      </p>
      {impedimentoDoRotulo === null ? null : (
        <p className="identidade-impedimento">{impedimentoDoRotulo}</p>
      )}

      <label htmlFor="identidade-motivo">Justificativa do agrupamento</label>
      <input
        id="identidade-motivo"
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
            view.selecao.length === 1 ? "entidade" : "entidades"
          }`}
        </button>
        <button type="button" disabled={view.ocupado} onClick={onLimparSelecao}>
          Limpar seleção
        </button>
      </div>
      <p className="identidade-nota">
        A declaração não se apaga: corrigir uma identidade errada é uma retificação
        registrada, com autor e instante — o mesmo padrão da decisão de leitura na revisão.
      </p>
    </section>
  );
}

/**
 * Container do painel: lê as propostas, envia os atos e devolve a cena nova ao chamador.
 *
 * A cena e o estado de leitura vêm de cima (`CroquiApp` já as busca para o preview): duas
 * leituras da mesma cena divergiriam entre si, e a divergência apareceria como um elemento
 * declarado que o desenho ao lado não conhece.
 */
export function ElementIdentityPanel({
  accessToken,
  jobId,
  scene,
  estado,
  onSceneChanged,
}: {
  accessToken: string;
  jobId: string;
  scene: SceneRevision.CroquitoSceneRevision | null;
  estado: EstadoDoPreview;
  onSceneChanged: (scene: SceneRevision.CroquitoSceneRevision) => void;
}) {
  const [proposals, setProposals] = useState<ElementProposal[]>([]);
  const [propostasFalharam, setPropostasFalharam] = useState(false);
  const [selecao, setSelecao] = useState<string[]>([]);
  const [motivo, setMotivo] = useState("");
  const [rotulo, setRotulo] = useState("");
  const [propostaSemente, setPropostaSemente] = useState<string | null>(null);
  const [recusandoProposta, setRecusandoProposta] = useState<string | null>(null);
  const [motivoDaRecusa, setMotivoDaRecusa] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [carimbo, setCarimbo] = useState<string | null>(null);

  const sceneVersion = scene?.version ?? null;
  const pronto = estado === "pronto" && scene !== null;

  const recarregarPropostas = useCallback(() => {
    if (!pronto || accessToken === "" || jobId === "") {
      return;
    }
    void listElementProposals(accessToken, jobId)
      .then((lista) => {
        setProposals(lista.proposals);
        setPropostasFalharam(false);
      })
      .catch(() => {
        // Ler proposta é conveniência: falhar aqui não impede declarar pela seleção
        // manual, e o painel diz isso com todas as letras em vez de sumir com a seção.
        setProposals([]);
        setPropostasFalharam(true);
      });
  }, [accessToken, jobId, pronto]);

  // Cena nova é lista de propostas nova: as propostas são recalculadas pelo servidor sobre
  // a cena corrente, e mostrar as da versão anterior ofereceria agrupar entidades que
  // acabaram de ganhar identidade.
  useEffect(() => {
    setSelecao([]);
    setRotulo("");
    setPropostaSemente(null);
    setRecusandoProposta(null);
    setMotivoDaRecusa("");
    recarregarPropostas();
  }, [recarregarPropostas, sceneVersion]);

  const reportar = useCallback((error: unknown, fallback: string) => {
    if (error instanceof ApiError) {
      setErro(mensagemDoErroDeIdentidade(error));
      return;
    }
    setErro(fallback);
  }, []);

  const declarar = useCallback(() => {
    if (scene === null || sceneVersion === null) {
      return;
    }
    setOcupado(true);
    setErro(null);
    const nome = rotulo.trim();
    void declareElement(accessToken, jobId, {
      base_version: sceneVersion,
      entity_ids: [...selecao],
      reason: motivo.trim(),
      // Campo em branco NÃO vira `""`: o servidor recusa string vazia, e declarar sem nome
      // é omitir o campo — o elemento nasce sem rótulo, que é cena válida.
      ...(nome === "" ? {} : { label: nome }),
    })
      .then((ato) => {
        setCarimbo(
          carimboDoAto(ato, decisionMoment(ato.acted_at), ato.scene.version),
        );
        setSelecao([]);
        setMotivo("");
        setRotulo("");
        setPropostaSemente(null);
        onSceneChanged(ato.scene);
      })
      .catch((error: unknown) =>
        reportar(error, "Não foi possível declarar a identidade do elemento."),
      )
      .finally(() => setOcupado(false));
  }, [
    accessToken,
    jobId,
    motivo,
    onSceneChanged,
    reportar,
    rotulo,
    scene,
    sceneVersion,
    selecao,
  ]);

  const confirmarRecusa = useCallback(() => {
    const proposalId = recusandoProposta;
    if (proposalId === null) {
      return;
    }
    setOcupado(true);
    setErro(null);
    void rejectElementProposal(accessToken, jobId, proposalId, {
      reason: motivoDaRecusa.trim(),
    })
      .then((recusa) => {
        setCarimbo(
          `Proposta ${recusa.proposal_id} recusada por ${recusa.rejected_by_role} em ` +
            `${decisionMoment(recusa.rejected_at)}. Ela não é mais oferecida.`,
        );
        setRecusandoProposta(null);
        setMotivoDaRecusa("");
        recarregarPropostas();
      })
      .catch((error: unknown) =>
        reportar(error, "Não foi possível registrar a recusa da proposta."),
      )
      .finally(() => setOcupado(false));
  }, [
    accessToken,
    jobId,
    motivoDaRecusa,
    recarregarPropostas,
    recusandoProposta,
    reportar,
  ]);

  const view = useMemo<EstadoDaIdentidade>(
    () => ({
      estado,
      scene,
      proposals,
      propostasFalharam,
      selecao,
      motivo,
      rotulo,
      propostaSemente,
      recusandoProposta,
      motivoDaRecusa,
      ocupado,
      erro,
      carimbo,
    }),
    [
      carimbo,
      erro,
      estado,
      motivo,
      motivoDaRecusa,
      ocupado,
      proposals,
      propostaSemente,
      propostasFalharam,
      recusandoProposta,
      rotulo,
      scene,
      selecao,
    ],
  );

  return (
    <ElementIdentityBody
      view={view}
      onToggleEntidade={(entityId) =>
        setSelecao((atual) => alternarEntidade(atual, entityId))
      }
      onMotivo={setMotivo}
      onRotulo={setRotulo}
      onDeclarar={declarar}
      onLimparSelecao={() => {
        setSelecao([]);
        setRotulo("");
        setPropostaSemente(null);
      }}
      onSemearDaProposta={(proposta) => {
        // Confirmar uma proposta é o MESMO ato da declaração manual: a proposta só semeia
        // a seleção e o rascunho da justificativa. Não existe segundo caminho de escrita.
        setSelecao([...proposta.entity_ids]);
        setPropostaSemente(proposta.proposal_id);
        setMotivo(
          `Agrupamento confirmado a partir da proposta ${proposta.proposal_id} (${sinalDaProposta(
            proposta.signal,
          )}).`,
        );
        setRecusandoProposta(null);
      }}
      onIniciarRecusa={(proposalId) => {
        setRecusandoProposta(proposalId);
        setMotivoDaRecusa("");
      }}
      onMotivoDaRecusa={setMotivoDaRecusa}
      onCancelarRecusa={() => {
        setRecusandoProposta(null);
        setMotivoDaRecusa("");
      }}
      onConfirmarRecusa={confirmarRecusa}
    />
  );
}
