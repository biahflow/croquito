import { useCallback, useEffect, useState } from "react";
import type { User } from "oidc-client-ts";

import {
  getEntitlement,
  listTenants,
  setEntitlement,
  type EntitlementDraft,
  type PlatformTenant,
} from "./api";
import {
  AVISO_PLATAFORMA,
  AVISO_REVOGACAO,
  AVISO_TENANT_NOVO,
  DICA_REFERENCIA,
  describeError,
  estadoLabel,
  formatarInstante,
  MENSAGEM_LISTA_VAZIA,
  MENSAGEM_SEM_LEITURA,
  MENSAGEM_SEM_SESSAO,
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

      {sucesso ? (
        <p className="app-toast" role="status">
          {sucesso}
        </p>
      ) : null}
    </>
  );
}
