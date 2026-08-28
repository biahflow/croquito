import { useCallback, useEffect, useState } from "react";
import type { User } from "oidc-client-ts";

import {
  ApiError,
  getEntitlement,
  listJourneys,
  listReferenceCatalogIndexes,
  listReferenceCatalogs,
  listTenants,
  publishReferenceCatalog,
  publishReferenceCatalogIndex,
  setEntitlement,
  setJourneyEntitlement,
  uploadReferenceCatalog,
  uploadReferenceCatalogIndex,
  withdrawReferenceCatalog,
  withdrawReferenceCatalogIndex,
  type EntitlementDraft,
  type Journey,
  type JourneyAvailability,
  type JourneyEntitlement,
  type JourneyState,
  type PlatformJourneys,
  type PlatformTenant,
  type ReferenceCatalog,
  type ReferenceCatalogIndex,
} from "./api";
import {
  AVISO_ACERVO,
  AVISO_DISPONIBILIDADE,
  AVISO_ESTADO_NAO_EDITAVEL,
  AVISO_INDICE_VEM_DO_CLI,
  AVISO_INDICES,
  AVISO_PLATAFORMA,
  AVISO_PUBLICAR,
  AVISO_RETIRADA,
  AVISO_RETIRADA_INDICE,
  AVISO_REVOGACAO,
  AVISO_TENANT_NOVO,
  DICA_ACERVO_SEM_PAPEL,
  DICA_APOS_RECUSA,
  DICA_AUTORIZAR_PILOTO,
  DICA_CAMPOS_DO_ARQUIVO,
  DICA_CAMPOS_DO_INDICE,
  DICA_CATALOGO_DO_INDICE,
  DICA_INDICES_SEM_PAPEL,
  DICA_JORNADAS_CARREGANDO,
  DICA_JORNADAS_SEM_PAPEL,
  DICA_NOME_EXIBICAO,
  DICA_REFERENCIA,
  describeAcervoError,
  describeError,
  describeIndiceError,
  describeJourneyError,
  digestCurto,
  estadoDaAutorizacao,
  estadoDoIndice,
  estadoLabel,
  ESTADO_JORNADA_CLASSE,
  ESTADO_JORNADA_LABEL,
  formatarContagem,
  formatarDataBase,
  formatarDia,
  formatarInstante,
  JORNADA_LABEL,
  MENSAGEM_ACERVO_SEM_PAPEL,
  MENSAGEM_INDICES_SEM_PAPEL,
  MENSAGEM_JORNADAS_CARREGANDO,
  MENSAGEM_JORNADAS_SEM_PAPEL,
  MENSAGEM_LISTA_VAZIA,
  MENSAGEM_SEM_CATALOGO_PARA_INDEXAR,
  MENSAGEM_SEM_LEITURA,
  MENSAGEM_SEM_SESSAO,
  mensagemSemAutorizacao,
  nomeDoCatalogoIndexado,
  NOME_EXIBICAO_MINIMO,
  resumoDoAcervo,
  resumoDoAmbiente,
  resumoDosIndices,
  SELO_FORA_DE_CIRCULACAO,
} from "./labels";

/**
 * Jornada de plataforma: quem opera o produto ativa e revoga a autorização contratual de
 * processamento por IA de cada tenant, pela tela.
 *
 * Ela substitui um ritual — token pescado no DevTools e `curl` no `PUT` — e por isso o que
 * ela mostra precisa ser o que o servidor tem, não uma versão otimista: toda mutação é
 * seguida da releitura da lista, e nenhum estado é adivinhado a partir do que foi enviado.
 *
 * Três decisões de tela, todas do `apps/web/AGENTS.md`:
 *
 * - **Ato explícito.** Ativar e revogar exigem abrir a ação da linha e confirmar; nenhum
 *   botão único grava direto, e nada nasce pré-marcado.
 * - **Erro é persistente, sucesso é transitório.** A recusa fica com `role="alert"` até a
 *   próxima leitura bem-sucedida — inclusive o `403` de quem perdeu o papel no meio da
 *   sessão, que precisa ler o motivo em vez de encarar uma tela vazia.
 * - **Cor nunca é o único indicador.** O estado de cada tenant é palavra escrita
 *   ("ativo", "revogado", "nunca autorizado"), e as datas do ato vêm junto.
 */

/** Quanto tempo o aviso de sucesso fica na tela antes de sumir sozinho. */
const DURACAO_SUCESSO_MS = 8000;

/** Gesto aberto numa linha: `true` é ativar, `false` é revogar. */
type AcaoAberta = { tenantId: string; enabled: boolean };

/**
 * Recusa da API na tela. Sem botão de fechar por decisão: enquanto o motivo valer, ele
 * fica — quem o remove é a próxima leitura que der certo.
 */
export function AlertaPersistente({ mensagem }: { mensagem: string }) {
  return (
    <p className="app-alert" role="alert">
      <span>{mensagem}</span>
    </p>
  );
}

/** Estado de um tenant escrito por extenso, com o contrato e os carimbos do ato. */
export function EstadoDoTenant({ tenant }: { tenant: PlatformTenant }) {
  return (
    <div>
      <strong>{tenant.tenant_id}</strong>
      <span>Autorização de IA: {estadoLabel(tenant)}</span>
      <span>Contrato: {tenant.agreement_reference ?? "—"}</span>
      <span>
        Autorizado em {formatarInstante(tenant.authorized_at)} · revogado em{" "}
        {formatarInstante(tenant.revoked_at)}
      </span>
    </div>
  );
}

/**
 * Uma linha da lista, com a ação da linha e a confirmação dela.
 *
 * `acao` já chega filtrada pelo pai: ela é `null` quando o gesto aberto é de outra linha,
 * de modo que só uma confirmação existe na tela por vez.
 */
export function LinhaTenant({
  tenant,
  acao,
  referencia,
  enviando,
  onAbrir,
  onCancelar,
  onReferencia,
  onConfirmar,
}: {
  tenant: PlatformTenant;
  acao: { enabled: boolean } | null;
  referencia: string;
  enviando: boolean;
  onAbrir: (enabled: boolean) => void;
  onCancelar: () => void;
  onReferencia: (valor: string) => void;
  onConfirmar: () => void;
}) {
  return (
    <li>
      <EstadoDoTenant tenant={tenant} />
      <div>
        {acao === null ? (
          <button
            className="button project-action"
            type="button"
            onClick={() => onAbrir(!tenant.enabled)}
          >
            {tenant.enabled ? "Revogar autorização" : "Ativar autorização"}
          </button>
        ) : (
          <form
            className="upload-form"
            onSubmit={(event) => {
              event.preventDefault();
              onConfirmar();
            }}
          >
            {acao.enabled ? (
              <label>
                Referência do contrato
                <input
                  value={referencia}
                  onChange={(event) => onReferencia(event.target.value)}
                  placeholder="contrato 05/2024"
                />
                <small className="field-hint">{DICA_REFERENCIA}</small>
              </label>
            ) : (
              <p className="field-hint">{AVISO_REVOGACAO}</p>
            )}
            <button
              className="button button-primary"
              type="submit"
              disabled={enviando}
            >
              {acao.enabled
                ? `Confirmar ativação de ${tenant.tenant_id}`
                : `Confirmar revogação de ${tenant.tenant_id}`}
            </button>
            <button
              className="button project-action"
              type="button"
              onClick={onCancelar}
              disabled={enviando}
            >
              Cancelar
            </button>
          </form>
        )}
      </div>
    </li>
  );
}

/** Frase do estado da lista; nenhuma delas fabrica tenant. */
function resumoDaLista(
  tenants: PlatformTenant[] | null,
  carregando: boolean,
): string {
  if (tenants === null) {
    return carregando ? "Lendo a lista de tenants…" : MENSAGEM_SEM_LEITURA;
  }
  if (tenants.length === 0) {
    return MENSAGEM_LISTA_VAZIA;
  }
  return `${tenants.length} tenant${tenants.length === 1 ? "" : "s"} com pegada no banco.`;
}

export function PlatformApp({ session }: { session: User | null }) {
  const [tenants, setTenants] = useState<PlatformTenant[] | null>(null);
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [acao, setAcao] = useState<AcaoAberta | null>(null);
  const [referencia, setReferencia] = useState("");
  const [novoTenant, setNovoTenant] = useState("");
  const [novaReferencia, setNovaReferencia] = useState("");
  const [consulta, setConsulta] = useState<PlatformTenant | null>(null);

  const accessToken = session?.access_token ?? null;

  const carregar = useCallback(async () => {
    if (accessToken === null) {
      return;
    }
    setCarregando(true);
    try {
      setTenants(await listTenants(accessToken));
      setErro(null);
    } catch (error) {
      // O `403` de quem perdeu o papel no meio da sessão cai aqui. A lista anterior
      // continua na tela com o motivo escrito em cima; sumir com tudo seria trocar uma
      // explicação por uma tela branca.
      setErro(describeError(error));
    } finally {
      setCarregando(false);
    }
  }, [accessToken]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  // Sucesso é transitório; erro não. Quem confirma um ato precisa ver que ele passou, e
  // depois disso a tela volta a ser só o estado atual.
  useEffect(() => {
    if (sucesso === null) {
      return;
    }
    const timer = setTimeout(() => setSucesso(null), DURACAO_SUCESSO_MS);
    return () => clearTimeout(timer);
  }, [sucesso]);

  const aplicar = useCallback(
    async (draft: EntitlementDraft, aoConcluir: () => void) => {
      if (accessToken === null) {
        return;
      }
      setEnviando(true);
      setErro(null);
      try {
        const resposta = await setEntitlement(accessToken, draft);
        aoConcluir();
        setSucesso(
          resposta.enabled
            ? `Autorização ativa para ${resposta.tenant_id}, contrato ${resposta.agreement_reference}.`
            : `Autorização revogada para ${resposta.tenant_id}.`,
        );
        // O que a tela mostra depois do ato é o que o servidor devolve na releitura.
        await carregar();
      } catch (error) {
        setErro(describeError(error));
      } finally {
        setEnviando(false);
      }
    },
    [accessToken, carregar],
  );

  const consultarTenant = useCallback(async () => {
    if (accessToken === null || novoTenant.trim() === "") {
      return;
    }
    setErro(null);
    try {
      setConsulta(await getEntitlement(accessToken, novoTenant.trim()));
    } catch (error) {
      setConsulta(null);
      setErro(describeError(error));
    }
  }, [accessToken, novoTenant]);

  if (session === null) {
    return (
      <section className="authenticated-workspace">
        <div>
          <span className="eyebrow">PLATAFORMA</span>
          <h2>Autorização contratual de IA</h2>
          <p>{MENSAGEM_SEM_SESSAO}</p>
        </div>
      </section>
    );
  }

  return (
    <>
      {erro ? <AlertaPersistente mensagem={erro} /> : null}

      <section className="authenticated-workspace">
        <div>
          <span className="eyebrow">PLATAFORMA</span>
          <h2>Autorização contratual de IA</h2>
          <p>{AVISO_PLATAFORMA}</p>
          <p className="field-hint">{resumoDaLista(tenants, carregando)}</p>
          <button
            className="button project-action"
            type="button"
            onClick={() => void carregar()}
            disabled={carregando}
          >
            Recarregar lista
          </button>
        </div>

        {/* Tenant sem pegada no banco não está na lista, e ativá-lo é justamente o caso
            do cliente novo: o identificador é digitado como ele aparece no token. */}
        <div>
          <span className="eyebrow">ATIVAR TENANT NOVO</span>
          <p className="field-hint">{AVISO_TENANT_NOVO}</p>
          <form
            className="upload-form"
            onSubmit={(event) => {
              event.preventDefault();
              void aplicar(
                {
                  tenantId: novoTenant.trim(),
                  enabled: true,
                  agreementReference: novaReferencia,
                },
                () => {
                  setNovoTenant("");
                  setNovaReferencia("");
                  setConsulta(null);
                },
              );
            }}
          >
            <label>
              Identificador do tenant
              <input
                value={novoTenant}
                onChange={(event) => setNovoTenant(event.target.value)}
                placeholder="acme"
              />
            </label>
            <label>
              Referência do contrato
              <input
                value={novaReferencia}
                onChange={(event) => setNovaReferencia(event.target.value)}
                placeholder="contrato 05/2024"
              />
              <small className="field-hint">{DICA_REFERENCIA}</small>
            </label>
            <button
              className="button button-primary"
              type="submit"
              disabled={enviando || novoTenant.trim() === ""}
            >
              Ativar autorização deste tenant
            </button>
            <button
              className="button project-action"
              type="button"
              onClick={() => void consultarTenant()}
              disabled={novoTenant.trim() === ""}
            >
              Consultar estado antes de ativar
            </button>
          </form>
          {consulta ? <EstadoDoTenant tenant={consulta} /> : null}
        </div>

        {/* Sem tenant lido não há lista vazia decorativa: o estado da leitura está
            escrito na coluna ao lado, e uma lista sem linha nenhuma só ocuparia espaço. */}
        {tenants !== null && tenants.length > 0 ? (
          <ul className="project-list">
            {tenants.map((tenant) => (
              <LinhaTenant
                key={tenant.tenant_id}
                tenant={tenant}
                acao={
                  acao !== null && acao.tenantId === tenant.tenant_id
                    ? { enabled: acao.enabled }
                    : null
                }
                referencia={referencia}
                enviando={enviando}
                onAbrir={(enabled) => {
                  setAcao({ tenantId: tenant.tenant_id, enabled });
                  // O campo nasce VAZIO mesmo quando já houve contrato: reativar um
                  // tenant revogado com a referência antiga já preenchida registraria
                  // um ato novo sob um contrato que ninguém conferiu.
                  setReferencia("");
                }}
                onCancelar={() => {
                  setAcao(null);
                  setReferencia("");
                }}
                onReferencia={setReferencia}
                onConfirmar={() => {
                  if (acao === null) {
                    return;
                  }
                  void aplicar(
                    {
                      tenantId: acao.tenantId,
                      enabled: acao.enabled,
                      agreementReference: referencia,
                    },
                    () => {
                      setAcao(null);
                      setReferencia("");
                    },
                  );
                }}
              />
            ))}
          </ul>
        ) : null}
      </section>

      {/* A seção nova mora ABAIXO da autorização de IA (Design Approval Package da F-034
          fatia 2, decisão 1): as duas respondem à mesma pergunta — o que este cliente pode
          usar — e são administradas pelo mesmo papel. */}
      <DisponibilidadeDeJornada session={session} />

      {/* Terceira seção EMPILHADA, não uma aba (Design Approval Package da F-037, revisão
          1, divergência 1): a tela 7 desenha `Tenants | Jornadas | Acervo de tabelas` como
          fita de abas, e esta jornada não tem mecanismo de aba nenhum — cada assunto é uma
          `<section>` própria. O conteúdo aprovado entra inteiro; o que fica de fora é a
          fita, que o mock inventou. */}
      <AcervoDeCatalogos session={session} />

      {/* Quarta seção empilhada, logo abaixo do acervo (Design Approval das duas
          superfícies, aprovado em 2026-08-28): o índice é irmão do catálogo e só existe
          sobre uma tabela já publicada, então ele vem DEPOIS dela e não antes. */}
      <IndicesDeEmbeddings session={session} />

      {sucesso ? (
        <p className="app-toast" role="status">
          {sucesso}
        </p>
      ) : null}
    </>
  );
}

/**
 * Disponibilidade de jornada por tenant (F-034, fatia 2).
 *
 * Corresponde à revisão 1 do Design Approval Package, aprovada por ato humano em
 * 2026-08-22: mesma seção da autorização de IA, logo abaixo dela, com os estados normal,
 * vazio, carregando, recusa e sem papel. O bloco de histórico do pacote está desenhado
 * como RESERVADO e é a F-017; ele não é construído aqui.
 *
 * Três decisões do pacote viram código:
 *
 * - **O estado do ambiente é mostrado e não é editável.** Não existe rota que o escreva, e
 *   a tela diz isso por escrito para ninguém procurar um interruptor que não existe.
 * - **A tela age só onde tem efeito, mas quem recusa é o servidor.** O seletor oferece as
 *   três jornadas; autorizar numa que não está em piloto sobe como `409` e vira a frase
 *   por extenso. Reimplementar a regra aqui faria a tela decidir autorização.
 * - **Revogado continua na lista**, com a data da revogação — sumir apagaria a trilha.
 */

/** Pastilha do estado do ambiente. A palavra ao lado é o que carrega o significado. */
export function PastilhaDeEstado({ state }: { state: JourneyState }) {
  return (
    <span className={ESTADO_JORNADA_CLASSE[state]}>
      {ESTADO_JORNADA_LABEL[state]}
    </span>
  );
}

/** Estado declarado de cada jornada neste ambiente; leitura, nunca edição. */
export function EstadoDasJornadas({
  journeys,
}: {
  journeys: JourneyAvailability[];
}) {
  return (
    <div className="journey-states">
      {journeys.map((entry) => (
        <div key={entry.journey}>
          <span>{JORNADA_LABEL[entry.journey]}</span>
          <PastilhaDeEstado state={entry.state} />
        </div>
      ))}
    </div>
  );
}

/**
 * Uma autorização na lista, com o contrato e os carimbos do ato.
 *
 * A linha revogada oferece "Autorizar de novo", que apenas PREENCHE o formulário ao lado:
 * autorizar de novo é ato novo e precisa de uma referência de contrato que alguém conferiu
 * — reenviar a antiga gravaria um ato sob um contrato que ninguém leu.
 */
export function LinhaAutorizacao({
  entitlement,
  enviando,
  onRevogar,
  onReautorizar,
}: {
  entitlement: JourneyEntitlement;
  enviando: boolean;
  onRevogar: () => void;
  onReautorizar: () => void;
}) {
  return (
    <li>
      <div>
        <strong>{entitlement.tenant_id}</strong>
        <span>{estadoDaAutorizacao(entitlement)}</span>
        <span>Contrato: {entitlement.agreement_reference}</span>
        <span>
          Autorizado por {entitlement.authorized_by} em{" "}
          {formatarInstante(entitlement.authorized_at)} · revogado em{" "}
          {formatarInstante(entitlement.revoked_at)}
        </span>
      </div>
      <button
        className="button project-action"
        type="button"
        disabled={enviando}
        onClick={() => (entitlement.enabled ? onRevogar() : onReautorizar())}
      >
        {entitlement.enabled ? "Revogar" : "Autorizar de novo"}
      </button>
    </li>
  );
}

/**
 * A coluna da esquerda: o que a seção é e o estado de cada jornada neste ambiente.
 *
 * `journeys === null` é a leitura ainda em curso — e aí não há estado a descrever, então a
 * coluna diz só o que está acontecendo, em vez de explicar uma lista que não está na tela.
 */
export function ColunaDoAmbiente({
  journeys,
}: {
  journeys: JourneyAvailability[] | null;
}) {
  return (
    <div>
      <span className="eyebrow">DISPONIBILIDADE DE JORNADA</span>
      <h2>Quais jornadas existem para cada cliente</h2>
      {journeys === null ? (
        <span className="field-hint">{MENSAGEM_JORNADAS_CARREGANDO}</span>
      ) : (
        <>
          <p>
            {AVISO_DISPONIBILIDADE.antes}
            <strong>{AVISO_DISPONIBILIDADE.enfase}</strong>
            {AVISO_DISPONIBILIDADE.depois}
          </p>
          <span className="field-hint">{resumoDoAmbiente(journeys)}</span>
          <EstadoDasJornadas journeys={journeys} />
          {/* Por escrito, para ninguém procurar um interruptor que não existe. */}
          <p className="field-hint">{AVISO_ESTADO_NAO_EDITAVEL}</p>
        </>
      )}
    </div>
  );
}

/**
 * A coluna da direita: autorizar um cliente numa jornada.
 *
 * O seletor oferece as TRÊS jornadas, não só as em piloto: quem recusa a que não tem
 * efeito é o servidor, com a frase por extenso. Filtrar aqui esconderia a regra em vez de
 * explicá-la, e faria a tela decidir autorização.
 */
export function FormularioDeAutorizacao({
  journeys,
  dica,
  tenantId,
  jornada,
  referencia,
  enviando,
  onTenantId,
  onJornada,
  onReferencia,
  onAutorizar,
}: {
  journeys: JourneyAvailability[] | null;
  dica: string;
  tenantId: string;
  jornada: Journey | null;
  referencia: string;
  enviando: boolean;
  onTenantId: (valor: string) => void;
  onJornada: (valor: Journey) => void;
  onReferencia: (valor: string) => void;
  onAutorizar: () => void;
}) {
  const lido = journeys !== null;
  return (
    <div>
      <span className="eyebrow">AUTORIZAR CLIENTE NO PILOTO</span>
      <p className="field-hint">{dica}</p>
      <form
        className="upload-form journey-form"
        onSubmit={(event) => {
          event.preventDefault();
          onAutorizar();
        }}
      >
        <label>
          Identificador do tenant
          <input
            value={tenantId}
            onChange={(event) => onTenantId(event.target.value)}
            placeholder="tenant-exemplo"
            disabled={!lido}
          />
        </label>
        <label>
          Jornada
          <select
            value={jornada ?? ""}
            onChange={(event) => onJornada(event.target.value as Journey)}
            disabled={!lido}
          >
            {journeys === null ? (
              <option value="">—</option>
            ) : (
              journeys.map((entry) => (
                <option key={entry.journey} value={entry.journey}>
                  {JORNADA_LABEL[entry.journey]}
                </option>
              ))
            )}
          </select>
        </label>
        <label>
          Referência do contrato
          <input
            value={referencia}
            onChange={(event) => onReferencia(event.target.value)}
            placeholder="contrato 05/2024"
            disabled={!lido}
          />
        </label>
        {/* `button-primary` é o que pinta o verde na folha real; no pacote aprovado o
            mesmo verde vem de `.button`, porque a rendição carrega um recorte da folha.
            A captura aprovada mostra o botão preenchido, e é ele que sai aqui. */}
        <button
          className="button button-primary"
          type="submit"
          disabled={!lido || enviando || tenantId.trim() === ""}
        >
          Autorizar
        </button>
      </form>
    </div>
  );
}

/** Primeira jornada em piloto, ou a primeira da lista quando nenhuma está em piloto. */
function jornadaInicial(journeys: JourneyAvailability[]): Journey | null {
  const piloto = journeys.find((entry) => entry.state === "pilot");
  return piloto?.journey ?? journeys[0]?.journey ?? null;
}

export function DisponibilidadeDeJornada({ session }: { session: User | null }) {
  const [dados, setDados] = useState<PlatformJourneys | null>(null);
  const [semPapel, setSemPapel] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [tenantId, setTenantId] = useState("");
  const [jornada, setJornada] = useState<Journey | null>(null);
  const [referencia, setReferencia] = useState("");

  const accessToken = session?.access_token ?? null;

  const carregar = useCallback(async () => {
    if (accessToken === null) {
      return;
    }
    try {
      const resposta = await listJourneys(accessToken);
      setDados(resposta);
      setSemPapel(false);
      setErro(null);
      // A jornada escolhida só é reposicionada quando ainda não há escolha: sobrescrever
      // depois de cada ato jogaria fora a seleção de quem está no meio do trabalho.
      setJornada((atual) => atual ?? jornadaInicial(resposta.journeys));
    } catch (error) {
      // `403` aqui não é falha: é a conta sem o papel de plataforma, e o pacote aprovado
      // desenha um estado próprio para ela — motivo por extenso, e não tela em branco.
      if (error instanceof ApiError && error.status === 403) {
        setSemPapel(true);
        setErro(null);
        return;
      }
      setErro(describeJourneyError(error));
    }
  }, [accessToken]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  const autorizar = useCallback(async () => {
    if (accessToken === null || jornada === null) {
      return;
    }
    setEnviando(true);
    try {
      await setJourneyEntitlement(accessToken, {
        tenantId: tenantId.trim(),
        journey: jornada,
        enabled: true,
        agreementReference: referencia,
      });
      setErro(null);
      setTenantId("");
      setReferencia("");
      // O que a tela mostra depois do ato é o que o servidor devolve na releitura.
      await carregar();
    } catch (error) {
      setErro(describeJourneyError(error));
    } finally {
      setEnviando(false);
    }
  }, [accessToken, carregar, jornada, referencia, tenantId]);

  const revogar = useCallback(
    async (entitlement: JourneyEntitlement) => {
      if (accessToken === null) {
        return;
      }
      setEnviando(true);
      try {
        await setJourneyEntitlement(accessToken, {
          tenantId: entitlement.tenant_id,
          journey: entitlement.journey,
          enabled: false,
        });
        setErro(null);
        await carregar();
      } catch (error) {
        setErro(describeJourneyError(error));
      } finally {
        setEnviando(false);
      }
    },
    [accessToken, carregar],
  );

  if (session === null) {
    return null;
  }

  if (semPapel) {
    return (
      <section className="authenticated-workspace">
        <div>
          <span className="eyebrow">DISPONIBILIDADE DE JORNADA</span>
          <h2>Quais jornadas existem para cada cliente</h2>
          <p>{MENSAGEM_JORNADAS_SEM_PAPEL}</p>
          <span className="field-hint">{DICA_JORNADAS_SEM_PAPEL}</span>
        </div>
      </section>
    );
  }

  const entitlements = dados?.entitlements ?? [];
  // A recusa manda na dica: depois dela, o que importa é que nada foi gravado. Sem recusa,
  // a dica descreve o que a leitura encontrou.
  const dicaDoFormulario = erro
    ? DICA_APOS_RECUSA
    : dados === null
      ? DICA_JORNADAS_CARREGANDO
      : entitlements.length === 0
        ? mensagemSemAutorizacao(dados.journeys)
        : DICA_AUTORIZAR_PILOTO;

  return (
    <>
      {erro ? <AlertaPersistente mensagem={erro} /> : null}

      <section className="authenticated-workspace">
        <ColunaDoAmbiente journeys={dados?.journeys ?? null} />

        <FormularioDeAutorizacao
          journeys={dados?.journeys ?? null}
          dica={dicaDoFormulario}
          tenantId={tenantId}
          jornada={jornada}
          referencia={referencia}
          enviando={enviando}
          onTenantId={setTenantId}
          onJornada={setJornada}
          onReferencia={setReferencia}
          onAutorizar={() => void autorizar()}
        />

        {entitlements.length > 0 ? (
          <ul className="project-list journey-entitlements">
            {entitlements.map((entitlement) => (
              <LinhaAutorizacao
                key={`${entitlement.tenant_id}:${entitlement.journey}`}
                entitlement={entitlement}
                enviando={enviando}
                onRevogar={() => void revogar(entitlement)}
                onReautorizar={() => {
                  // Autorizar de novo é ato novo: o formulário é preenchido com o par, e a
                  // referência do contrato nasce VAZIA para alguém escrevê-la de fato.
                  setTenantId(entitlement.tenant_id);
                  setJornada(entitlement.journey);
                  setReferencia("");
                }}
              />
            ))}
          </ul>
        ) : null}
      </section>
    </>
  );
}

/**
 * Acervo de catálogos de referência (F-037, ADR-0047).
 *
 * Corresponde às telas 7 e 8 da revisão 1 do Design Approval Package, aprovada por ato
 * humano em 2026-08-22, com uma divergência declarada ANTES da implementação: o mock
 * desenha abas e esta jornada não tem abas — o acervo é uma seção empilhada, como a
 * disponibilidade de jornada acima dela.
 *
 * Três decisões do pacote viram código:
 *
 * - **Publicar é ato de plataforma e é imutável.** Não há "substituir": data-base nova é
 *   entrada nova, e republicar o mesmo conteúdo é recusado pelo SERVIDOR com código
 *   estável, que a tela traduz. Nenhuma regra de imutabilidade é reimplementada aqui.
 * - **Retirar de circulação mostra a consequência.** A linha retirada CONTINUA na lista,
 *   com a palavra escrita e a data — apagá-la esconderia o que aconteceu, e as rodadas que
 *   já a referenciam continuam funcionando.
 * - **Rótulo não se digita onde o arquivo já diz.** Só o nome de exibição é escrito;
 *   origem, data-base e contagem são lidas de dentro do `catalog.json` pelo servidor. A
 *   tela nunca abre o arquivo — ela calcula o digest para subir, e nada mais.
 *
 * O bloco RESERVADO do pacote (tela 9, a plataforma buscar data-base nova sozinha) não é
 * construído aqui: está fora de escopo pela decisão 10 do ADR-0047.
 */

/** Uma publicação na lista, com a marca escrita de quem saiu de circulação. */
export function LinhaCatalogo({
  catalogo,
  enviando,
  onRetirar,
}: {
  catalogo: ReferenceCatalog;
  enviando: boolean;
  onRetirar: () => void;
}) {
  const foraDeCirculacao = !catalogo.available;
  return (
    <li>
      <div>
        <strong>{catalogo.display_name}</strong>
        {foraDeCirculacao ? (
          // A linha retirada diz o que houve e quando. A contagem de rodadas que ainda a
          // referenciam está desenhada no pacote aprovado e NÃO entra: nenhuma rota
          // devolve esse número hoje, e escrevê-lo a partir de um palpite seria pior do
          // que omiti-lo (divergência registrada na entrega desta task).
          <span>
            origem {catalogo.origin} · ref.{" "}
            {formatarDataBase(catalogo.reference_month)} · retirada de circulação em{" "}
            {formatarDia(catalogo.withdrawn_at)}
          </span>
        ) : (
          <span>
            origem {catalogo.origin} · ref.{" "}
            {formatarDataBase(catalogo.reference_month)} ·{" "}
            {formatarContagem(catalogo.entry_count)} itens ·{" "}
            {/* Digest truncado na tela, valor inteiro no `title`: é o padrão do produto
                para conferência visual de conteúdo. */}
            <code title={catalogo.object_sha256}>
              sha256 {digestCurto(catalogo.object_sha256)}
            </code>{" "}
            · publicada por {catalogo.published_by} em{" "}
            {formatarDia(catalogo.published_at)}
          </span>
        )}
      </div>
      {foraDeCirculacao ? (
        // Cor nunca é o único indicador: a pastilha carrega a PALAVRA, e a linha já diz
        // por extenso que a tabela foi retirada e quando.
        <span className="neutral">{SELO_FORA_DE_CIRCULACAO}</span>
      ) : (
        <button
          className="button project-action"
          type="button"
          disabled={enviando}
          onClick={onRetirar}
        >
          Retirar de circulação
        </button>
      )}
    </li>
  );
}

/**
 * A coluna da direita: publicar uma tabela.
 *
 * O arquivo é o `catalog.json` já normalizado pelo CLI; o servidor não importa `.xlsx`
 * nem `.DBF` (ADR-0047 decisão 9), e a frase acima do campo diz isso. O botão só destrava
 * com arquivo escolhido e nome de exibição do tamanho que o CONTRATO exige — não é regra
 * própria da tela, é o mesmo `min_length` do servidor, repetido para o nome curto demais
 * morrer antes da rede.
 */
export function FormularioDePublicacao({
  arquivoEscolhido,
  nomeExibicao,
  enviando,
  campoArquivoKey,
  onArquivo,
  onNomeExibicao,
  onPublicar,
}: {
  arquivoEscolhido: boolean;
  nomeExibicao: string;
  enviando: boolean;
  campoArquivoKey: number;
  onArquivo: (arquivo: File | null) => void;
  onNomeExibicao: (valor: string) => void;
  onPublicar: () => void;
}) {
  const nomeCurto = nomeExibicao.trim().length < NOME_EXIBICAO_MINIMO;
  return (
    <div>
      <span className="eyebrow">PUBLICAR TABELA</span>
      <p className="field-hint">
        {AVISO_PUBLICAR.antes}
        <code>{AVISO_PUBLICAR.comandos[0]}</code>,{" "}
        <code>{AVISO_PUBLICAR.comandos[1]}</code>,{" "}
        <code>{AVISO_PUBLICAR.comandos[2]}</code>
        {AVISO_PUBLICAR.meio}
        <code>{AVISO_PUBLICAR.arquivo}</code>
        {AVISO_PUBLICAR.depois}
      </p>
      <form
        className="upload-form"
        onSubmit={(event) => {
          event.preventDefault();
          onPublicar();
        }}
      >
        <label>
          Catálogo normalizado (JSON)
          {/* O campo de arquivo é não controlado por natureza; a `key` muda depois de uma
              publicação e é o que o esvazia sem tocar no DOM por fora do React. */}
          <input
            key={campoArquivoKey}
            type="file"
            accept="application/json,.json"
            disabled={enviando}
            onChange={(event) => onArquivo(event.target.files?.[0] ?? null)}
          />
        </label>
        <label>
          Nome de exibição
          <input
            value={nomeExibicao}
            onChange={(event) => onNomeExibicao(event.target.value)}
            placeholder="SINAPI RJ desonerado"
            disabled={enviando}
          />
          <small className="field-hint">{DICA_NOME_EXIBICAO}</small>
        </label>
        <button
          className="button button-primary"
          type="submit"
          disabled={enviando || !arquivoEscolhido || nomeCurto}
        >
          Publicar
        </button>
      </form>
      <span className="field-hint">{DICA_CAMPOS_DO_ARQUIVO}</span>
    </div>
  );
}

export function AcervoDeCatalogos({ session }: { session: User | null }) {
  const [catalogos, setCatalogos] = useState<ReferenceCatalog[] | null>(null);
  const [carregando, setCarregando] = useState(false);
  const [semPapel, setSemPapel] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [nomeExibicao, setNomeExibicao] = useState("");
  const [campoArquivoKey, setCampoArquivoKey] = useState(0);

  const accessToken = session?.access_token ?? null;

  const carregar = useCallback(async () => {
    if (accessToken === null) {
      return;
    }
    setCarregando(true);
    try {
      setCatalogos(await listReferenceCatalogs(accessToken));
      setSemPapel(false);
      setErro(null);
    } catch (error) {
      // `403` aqui não é falha: é a conta sem o papel de plataforma, e ela lê o motivo em
      // vez de encarar uma seção em branco. Quem autoriza continua sendo o servidor.
      if (error instanceof ApiError && error.status === 403) {
        setSemPapel(true);
        setErro(null);
        return;
      }
      setErro(describeAcervoError(error));
    } finally {
      setCarregando(false);
    }
  }, [accessToken]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  // Sem toast de sucesso, ao contrário da seção de autorização: `.app-toast` é
  // `position: fixed` no mesmo canto (`styles.css`), e duas seções empilhadas com toast
  // próprio sobreporiam as faixas no mesmo pixel quando dois atos acontecessem na mesma
  // janela. Aqui a confirmação é a releitura da lista — a linha nova aparece publicada, a
  // retirada aparece fora de circulação —, que é o mesmo desenho de
  // `DisponibilidadeDeJornada`.
  const publicar = useCallback(async () => {
    if (accessToken === null || arquivo === null) {
      return;
    }
    setEnviando(true);
    // O digest é o do arquivo que ESTA tela subiu, e é ele que a recusa de republicar
    // cita. Nasce nulo porque a falha pode acontecer antes de o arquivo ser lido, e aí
    // não há conteúdo a nomear.
    let objectSha256: string | null = null;
    try {
      const upload = await uploadReferenceCatalog(accessToken, arquivo);
      objectSha256 = upload.objectSha256;
      const publicado = await publishReferenceCatalog(accessToken, {
        uploadId: upload.uploadId,
        displayName: nomeExibicao,
      });
      setErro(null);
      setArquivo(null);
      setNomeExibicao("");
      setCampoArquivoKey((valor) => valor + 1);
      // O que a tela mostra depois do ato é o que o servidor devolve na releitura: a
      // linha nova aparecendo na lista É a confirmação de que a publicação aconteceu.
      await carregar();
    } catch (error) {
      setErro(describeAcervoError(error, objectSha256));
    } finally {
      setEnviando(false);
    }
  }, [accessToken, arquivo, carregar, nomeExibicao]);

  const retirar = useCallback(
    async (catalogo: ReferenceCatalog) => {
      if (accessToken === null) {
        return;
      }
      setEnviando(true);
      try {
        await withdrawReferenceCatalog(
          accessToken,
          catalogo.reference_catalog_id,
        );
        setErro(null);
        // A linha reaparecendo marcada como fora de circulação é a confirmação do ato.
        await carregar();
      } catch (error) {
        setErro(describeAcervoError(error));
      } finally {
        setEnviando(false);
      }
    },
    [accessToken, carregar],
  );

  if (session === null) {
    return null;
  }

  if (semPapel) {
    return (
      <section className="authenticated-workspace">
        <div>
          <span className="eyebrow">ACERVO DE TABELAS DE REFERÊNCIA</span>
          <h2>Tabelas publicadas</h2>
          <p>{MENSAGEM_ACERVO_SEM_PAPEL}</p>
          <span className="field-hint">{DICA_ACERVO_SEM_PAPEL}</span>
        </div>
      </section>
    );
  }

  return (
    <>
      {erro ? <AlertaPersistente mensagem={erro} /> : null}

      <section className="authenticated-workspace">
        <div>
          <span className="eyebrow">ACERVO DE TABELAS DE REFERÊNCIA</span>
          <h2>Tabelas publicadas</h2>
          <p>{AVISO_ACERVO}</p>
          <span className="field-hint">{resumoDoAcervo(catalogos, carregando)}</span>
          <button
            className="button project-action"
            type="button"
            onClick={() => void carregar()}
            disabled={carregando}
          >
            Recarregar acervo
          </button>
        </div>

        <FormularioDePublicacao
          arquivoEscolhido={arquivo !== null}
          nomeExibicao={nomeExibicao}
          enviando={enviando}
          campoArquivoKey={campoArquivoKey}
          onArquivo={setArquivo}
          onNomeExibicao={setNomeExibicao}
          onPublicar={() => void publicar()}
        />

        {/* `journey-entitlements` é a regra de linha de LARGURA INTEIRA que a F-034
            escreveu — `.project-list` sozinha é uma faixa de chips, apertada para uma
            linha que carrega origem, data-base, contagem, digest e autor. O nome ficou
            preso à jornada porque renomeá-lo toca `src/styles.css`, fora da fronteira
            desta task. */}
        {catalogos !== null && catalogos.length > 0 ? (
          <>
            <ul className="project-list journey-entitlements">
              {catalogos.map((catalogo) => (
                <LinhaCatalogo
                  key={catalogo.reference_catalog_id}
                  catalogo={catalogo}
                  enviando={enviando}
                  onRetirar={() => void retirar(catalogo)}
                />
              ))}
            </ul>
            {/* A consequência de retirar, por escrito, logo abaixo da lista onde o ato
                acontece. Sem lista não há ato a explicar: o estado do acervo vazio já
                está escrito na coluna ao lado. */}
            <p className="field-hint">{AVISO_RETIRADA}</p>
          </>
        ) : null}
      </section>
    </>
  );
}

/**
 * Índices de embeddings publicados (F-041, ADR-0054).
 *
 * Espelho próximo do acervo, porque a pergunta é a mesma — onde mora um artefato público,
 * sem dono, endereçado por digest —, com três diferenças que são decisões escritas:
 *
 * - **O índice é construído pelo CLI, nunca aqui** (D4). O `catalog-embeddings.json` sai do
 *   comando pago `index-catalog`; esta tela sobe o arquivo e o servidor o lê e confere.
 *   Não há botão de construir, e a frase acima do campo diz isso por escrito.
 * - **A tela nunca baixa o índice.** Nenhuma rota o assina e `object_key` não vem na
 *   resposta: o que se lê aqui é a identidade da publicação (sobre qual tabela, com qual
 *   receita, provider, modelo e dimensões), nunca um único vetor.
 * - **Retirar não apaga, e a razão é mais forte que a do acervo**: a shortlist já gravada
 *   cita o digest do índice que a produziu. A linha continua na lista, o objeto continua
 *   no armazenamento, e a fonte volta a entrar só pelo braço léxico — estado normal (D6).
 *
 * O acervo é lido aqui de novo, e não recebido do componente vizinho, pela mesma autonomia
 * das outras seções: cada uma carrega o que mostra e tem o próprio botão de recarregar. O
 * custo é um `GET` a mais; a alternativa seria acoplar duas seções que hoje não se
 * conhecem, para economizar uma leitura de lista.
 */

/** Uma publicação de índice na lista, com o estado escrito por extenso. */
export function LinhaIndice({
  indice,
  catalogos,
  enviando,
  onRetirar,
}: {
  indice: ReferenceCatalogIndex;
  catalogos: ReferenceCatalog[] | null;
  enviando: boolean;
  onRetirar: () => void;
}) {
  const foraDeCirculacao = !indice.available;
  return (
    <li>
      <div>
        <strong>{nomeDoCatalogoIndexado(indice, catalogos)}</strong>
        {/* Cor nunca é o único indicador: o estado é a PRIMEIRA coisa escrita na linha,
            antes de qualquer marca visual. */}
        <span>
          {estadoDoIndice(indice)} · receita {indice.text_recipe} · {indice.provider}{" "}
          {indice.model_id} · {indice.dims} dimensões ·{" "}
          {formatarContagem(indice.code_count)} códigos
        </span>
        <span>
          {/* Digest truncado na tela, valor inteiro no `title`: padrão do produto para
              conferência visual de conteúdo. */}
          <code title={indice.object_sha256}>
            sha256 {digestCurto(indice.object_sha256)}
          </code>{" "}
          · publicado por {indice.published_by} em {formatarDia(indice.published_at)}
          {foraDeCirculacao
            ? ` · retirado de circulação em ${formatarDia(indice.withdrawn_at)}`
            : ""}
        </span>
      </div>
      {foraDeCirculacao ? (
        <span className="neutral">{SELO_FORA_DE_CIRCULACAO}</span>
      ) : (
        <button
          className="button project-action"
          type="button"
          disabled={enviando}
          onClick={onRetirar}
        >
          Retirar de circulação
        </button>
      )}
    </li>
  );
}

/**
 * A coluna da direita: publicar um índice.
 *
 * Dois campos, e nenhum deles descreve o índice: o arquivo e a tabela sobre a qual ele foi
 * construído. Receita, provider, modelo, dimensões e contagem vêm de dentro do documento —
 * digitá-los ao lado do conteúdo seria deixar o rótulo discordar dele.
 *
 * O seletor oferece TODAS as tabelas do acervo, inclusive as fora de circulação: o índice é
 * resolvido pelo digest da fonte (ADR-0054 D3), então ele continua servindo qualquer
 * catálogo com os mesmos bytes de origem. A palavra ao lado do nome diz qual é qual.
 */
export function FormularioDePublicacaoDeIndice({
  catalogos,
  catalogoId,
  arquivoEscolhido,
  enviando,
  campoArquivoKey,
  onArquivo,
  onCatalogo,
  onPublicar,
}: {
  catalogos: ReferenceCatalog[] | null;
  catalogoId: string;
  arquivoEscolhido: boolean;
  enviando: boolean;
  campoArquivoKey: number;
  onArquivo: (arquivo: File | null) => void;
  onCatalogo: (valor: string) => void;
  onPublicar: () => void;
}) {
  const semCatalogo = catalogos !== null && catalogos.length === 0;
  return (
    <div>
      <span className="eyebrow">PUBLICAR ÍNDICE</span>
      {/* Por escrito, para ninguém procurar aqui um botão de construir índice. */}
      <p className="field-hint">
        {AVISO_INDICE_VEM_DO_CLI.antes}
        <code>{AVISO_INDICE_VEM_DO_CLI.comando}</code>
        {AVISO_INDICE_VEM_DO_CLI.meio}
        <code>{AVISO_INDICE_VEM_DO_CLI.arquivo}</code>
        {AVISO_INDICE_VEM_DO_CLI.depois}
      </p>
      {semCatalogo ? (
        <p className="field-hint">{MENSAGEM_SEM_CATALOGO_PARA_INDEXAR}</p>
      ) : null}
      <form
        className="upload-form"
        onSubmit={(event) => {
          event.preventDefault();
          onPublicar();
        }}
      >
        <label>
          Índice de embeddings (JSON)
          {/* Campo de arquivo é não controlado por natureza; a `key` muda depois de uma
              publicação e é o que o esvazia sem tocar no DOM por fora do React. */}
          <input
            key={campoArquivoKey}
            type="file"
            accept="application/json,.json"
            disabled={enviando}
            onChange={(event) => onArquivo(event.target.files?.[0] ?? null)}
          />
        </label>
        <label>
          Tabela indexada
          <select
            value={catalogoId}
            onChange={(event) => onCatalogo(event.target.value)}
            disabled={enviando || catalogos === null || semCatalogo}
          >
            {catalogos === null || semCatalogo ? (
              <option value="">—</option>
            ) : (
              catalogos.map((catalogo) => (
                <option
                  key={catalogo.reference_catalog_id}
                  value={catalogo.reference_catalog_id}
                >
                  {catalogo.display_name} ·{" "}
                  {formatarDataBase(catalogo.reference_month)}
                  {catalogo.available ? "" : " (fora de circulação)"}
                </option>
              ))
            )}
          </select>
          <small className="field-hint">{DICA_CATALOGO_DO_INDICE}</small>
        </label>
        <button
          className="button button-primary"
          type="submit"
          disabled={enviando || !arquivoEscolhido || catalogoId === ""}
        >
          Publicar índice
        </button>
      </form>
      <span className="field-hint">{DICA_CAMPOS_DO_INDICE}</span>
    </div>
  );
}

export function IndicesDeEmbeddings({ session }: { session: User | null }) {
  const [indices, setIndices] = useState<ReferenceCatalogIndex[] | null>(null);
  const [catalogos, setCatalogos] = useState<ReferenceCatalog[] | null>(null);
  const [carregando, setCarregando] = useState(false);
  const [semPapel, setSemPapel] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [catalogoId, setCatalogoId] = useState("");
  const [campoArquivoKey, setCampoArquivoKey] = useState(0);

  const accessToken = session?.access_token ?? null;

  const carregar = useCallback(async () => {
    if (accessToken === null) {
      return;
    }
    setCarregando(true);
    try {
      // As duas leituras juntas porque a linha do índice nomeia a TABELA que ele indexa, e
      // o formulário escolhe entre elas: uma lista sem a outra mostraria índice sem nome.
      const [publicados, acervo] = await Promise.all([
        listReferenceCatalogIndexes(accessToken),
        listReferenceCatalogs(accessToken),
      ]);
      setIndices(publicados);
      setCatalogos(acervo);
      // A tabela escolhida só é reposicionada quando ainda não há escolha: sobrescrever
      // depois de cada ato jogaria fora a seleção de quem está no meio do trabalho.
      setCatalogoId(
        (atual) => atual || (acervo[0]?.reference_catalog_id ?? ""),
      );
      setSemPapel(false);
      setErro(null);
    } catch (error) {
      // `403` aqui não é falha: é a conta sem o papel de plataforma, e ela lê o motivo em
      // vez de encarar uma seção em branco. Quem autoriza continua sendo o servidor.
      if (error instanceof ApiError && error.status === 403) {
        setSemPapel(true);
        setErro(null);
        return;
      }
      setErro(describeIndiceError(error));
    } finally {
      setCarregando(false);
    }
  }, [accessToken]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  // Sem toast de sucesso, pelo mesmo motivo do acervo: `.app-toast` é `position: fixed` no
  // mesmo canto, e seções empilhadas com toast próprio sobreporiam as faixas no mesmo
  // pixel. A confirmação é a releitura — a linha nova aparece publicada.
  const publicar = useCallback(async () => {
    if (accessToken === null || arquivo === null || catalogoId === "") {
      return;
    }
    setEnviando(true);
    try {
      const upload = await uploadReferenceCatalogIndex(accessToken, arquivo);
      await publishReferenceCatalogIndex(accessToken, {
        uploadId: upload.uploadId,
        referenceCatalogId: catalogoId,
      });
      setErro(null);
      setArquivo(null);
      setCampoArquivoKey((valor) => valor + 1);
      await carregar();
    } catch (error) {
      setErro(describeIndiceError(error));
    } finally {
      setEnviando(false);
    }
  }, [accessToken, arquivo, carregar, catalogoId]);

  const retirar = useCallback(
    async (indice: ReferenceCatalogIndex) => {
      if (accessToken === null) {
        return;
      }
      setEnviando(true);
      try {
        await withdrawReferenceCatalogIndex(
          accessToken,
          indice.reference_catalog_index_id,
        );
        setErro(null);
        // A linha reaparecendo marcada como fora de circulação é a confirmação do ato.
        await carregar();
      } catch (error) {
        setErro(describeIndiceError(error));
      } finally {
        setEnviando(false);
      }
    },
    [accessToken, carregar],
  );

  if (session === null) {
    return null;
  }

  if (semPapel) {
    return (
      <section className="authenticated-workspace">
        <div>
          <span className="eyebrow">ÍNDICES DE EMBEDDINGS</span>
          <h2>Índices publicados</h2>
          <p>{MENSAGEM_INDICES_SEM_PAPEL}</p>
          <span className="field-hint">{DICA_INDICES_SEM_PAPEL}</span>
        </div>
      </section>
    );
  }

  return (
    <>
      {erro ? <AlertaPersistente mensagem={erro} /> : null}

      <section className="authenticated-workspace">
        <div>
          <span className="eyebrow">ÍNDICES DE EMBEDDINGS</span>
          <h2>Índices publicados</h2>
          <p>{AVISO_INDICES}</p>
          <span className="field-hint">
            {resumoDosIndices(indices, carregando)}
          </span>
          <button
            className="button project-action"
            type="button"
            onClick={() => void carregar()}
            disabled={carregando}
          >
            Recarregar índices
          </button>
        </div>

        <FormularioDePublicacaoDeIndice
          catalogos={catalogos}
          catalogoId={catalogoId}
          arquivoEscolhido={arquivo !== null}
          enviando={enviando}
          campoArquivoKey={campoArquivoKey}
          onArquivo={setArquivo}
          onCatalogo={setCatalogoId}
          onPublicar={() => void publicar()}
        />

        {indices !== null && indices.length > 0 ? (
          <>
            <ul className="project-list journey-entitlements">
              {indices.map((indice) => (
                <LinhaIndice
                  key={indice.reference_catalog_index_id}
                  indice={indice}
                  catalogos={catalogos}
                  enviando={enviando}
                  onRetirar={() => void retirar(indice)}
                />
              ))}
            </ul>
            {/* A consequência de retirar, por escrito, logo abaixo da lista onde o ato
                acontece. Sem lista não há ato a explicar. */}
            <p className="field-hint">{AVISO_RETIRADA_INDICE}</p>
          </>
        ) : null}
      </section>
    </>
  );
}
