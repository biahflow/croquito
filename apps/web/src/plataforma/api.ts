/**
 * Cliente da jornada de plataforma na API `/v1` autenticada (F-012, T2/T3).
 *
 * O transporte é o mesmo das outras jornadas (`apiJson` em `apps/web/src/api.ts`): ele
 * leva o `Authorization` da sessão OIDC, refaz a chamada uma vez quando o token expirou e
 * traduz o envelope aninhado (`{detail: {code, detail, details}}`) num `ApiError`. Este
 * módulo não abre `fetch` nenhum por conta própria.
 *
 * Três invariantes moram aqui:
 *
 * - **Quem autoriza é o servidor.** A SPA nunca decodifica token nem deduz papel: ela
 *   PERGUNTA (`GET /v1/me`) para saber o que oferecer, e cada rota de plataforma volta a
 *   exigir `platform_operator` no backend. Esconder o botão é ergonomia; a autorização
 *   continua sendo o `403` que estas funções deixam subir.
 * - **A referência do contrato é o objeto do ato.** Ativar sem `agreement_reference` é
 *   recusado pelo servidor (`422 AGREEMENT_REFERENCE_REQUIRED`), e é assim que fica: o
 *   client não inventa referência nem bloqueia o pedido por conta própria.
 * - **Mutação manda `Idempotency-Key` por gesto.** A chave nasce no gesto e é reusada na
 *   retentativa interna do `apiJson` (o 401 que renova o token e repete a chamada) —
 *   replay, nunca segunda escrita. É o mesmo padrão das mutações do croqui e da medição.
 */

import { apiJson, ApiError } from "../api";

export { ApiError };

/** Papel exigido pelo backend em toda rota de plataforma (`main.py`). */
export const PLATFORM_OPERATOR_ROLE = "platform_operator";

/**
 * Resposta de `GET /v1/me`. Exige só autenticação e não devolve claims brutos nem o
 * token: é a mesma superfície (`subject`, `tenant_id`, `roles`) que o backend usa para
 * decidir autorização.
 */
/**
 * As jornadas que o produto liga e desliga por ambiente e por tenant (F-034). A Plataforma
 * não entra: ela é governada por papel e é onde a disponibilidade é administrada.
 */
export type Journey = "croqui" | "medicao" | "orcamento";

export type Me = {
  subject: string;
  tenant_id: string;
  roles: string[];
  /**
   * Jornadas que este principal pode abrir, **já resolvidas pelo servidor** — ambiente,
   * tenant e papel. A tela renderiza esta lista; ela não recalcula papel nem decide
   * disponibilidade. Lista vazia é resposta legítima.
   */
  journeys: Journey[];
};

/**
 * Estado legível do entitlement de um tenant, como `GET /v1/platform/tenants` devolve.
 *
 * Os três campos opcionais são nulos no tenant que NUNCA teve entitlement criado — que é
 * um resultado válido (200), não um 404. Por isso o estado tem três palavras, não duas:
 * "nunca autorizado" não é a mesma coisa que "revogado".
 */
export type PlatformTenant = {
  tenant_id: string;
  enabled: boolean;
  agreement_reference: string | null;
  authorized_at: string | null;
  revoked_at: string | null;
};

type PlatformTenantList = {
  tenants: PlatformTenant[];
};

/**
 * Resposta do `PUT`. Diferente de `PlatformTenant`: aqui o entitlement existe por
 * construção, então `agreement_reference` e `authorized_at` chegam preenchidos.
 */
export type AiProcessingEntitlement = {
  tenant_id: string;
  enabled: boolean;
  agreement_reference: string;
  authorized_at: string;
  revoked_at: string | null;
};

/** O gesto de ativar ou desativar um tenant, antes de virar corpo de requisição. */
export type EntitlementDraft = {
  tenantId: string;
  enabled: boolean;
  agreementReference?: string;
};

/**
 * Corpo do `PUT`, puro e testável. `extra="forbid"` do lado do servidor recusa campo que
 * não esteja no contrato, então nada além de `enabled` e `agreement_reference` viaja.
 *
 * Na revogação a referência NÃO é enviada: o contrato que autorizou continua sendo o que
 * está gravado, e reescrevê-lo com o que estava na tela apagaria o registro do ato
 * original. Na ativação ela vai como o operador escreveu, sem espaço nas pontas — vazia,
 * ela nem entra no corpo, e a recusa vem do servidor com o código estável.
 */
export function entitlementBody(draft: EntitlementDraft): Record<string, unknown> {
  const reference = draft.agreementReference?.trim() ?? "";
  if (!draft.enabled || reference === "") {
    return { enabled: draft.enabled };
  }
  return { enabled: draft.enabled, agreement_reference: reference };
}

function entitlementPath(tenantId: string): string {
  return `/v1/platform/tenants/${encodeURIComponent(
    tenantId,
  )}/ai-processing-entitlement`;
}

/** Quem é o principal autenticado — a pergunta que decide se a jornada é oferecida. */
export function fetchMe(accessToken: string): Promise<Me> {
  return apiJson<Me>("/v1/me", accessToken);
}

/**
 * Tenants com pegada no banco (entitlements ∪ projects ∪ uploads). Um tenant que existe
 * só no Keycloak, sem nenhum upload, NÃO aparece aqui — é por isso que a tela mantém o
 * campo de texto livre para ativar um tenant pelo identificador.
 */
export async function listTenants(
  accessToken: string,
): Promise<PlatformTenant[]> {
  const resposta = await apiJson<PlatformTenantList>(
    "/v1/platform/tenants",
    accessToken,
  );
  return resposta.tenants;
}

/** Estado de um tenant específico; 200 mesmo quando nunca foi ativado. */
export function getEntitlement(
  accessToken: string,
  tenantId: string,
): Promise<PlatformTenant> {
  return apiJson<PlatformTenant>(entitlementPath(tenantId), accessToken);
}

/** Ativa ou revoga a autorização contratual de IA de um tenant. */
export function setEntitlement(
  accessToken: string,
  draft: EntitlementDraft,
): Promise<AiProcessingEntitlement> {
  return apiJson<AiProcessingEntitlement>(
    entitlementPath(draft.tenantId),
    accessToken,
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": crypto.randomUUID(),
      },
      body: JSON.stringify(entitlementBody(draft)),
    },
  );
}

/**
 * Estado declarado de uma jornada NESTE ambiente (F-034, fatia 2).
 *
 * A tela mostra e não edita: mudar o estado é alterar configuração e publicar, e por isso
 * não existe rota que o escreva — o pacote de design aprovado diz isso por escrito na
 * própria tela, para ninguém procurar um interruptor que não existe.
 */
export type JourneyState = "enabled" | "pilot" | "disabled";

export type JourneyAvailability = {
  journey: Journey;
  state: JourneyState;
};

/**
 * Uma autorização de (tenant, jornada). Diferente de `PlatformTenant`: aqui a linha só
 * existe porque houve um ato, então contrato, autor e data chegam preenchidos.
 *
 * `enabled: false` com `revoked_at` preenchido é a autorização revogada, que CONTINUA na
 * lista — sumir com ela apagaria a trilha de que um dia houve autorização.
 */
export type JourneyEntitlement = {
  tenant_id: string;
  journey: Journey;
  enabled: boolean;
  agreement_reference: string;
  authorized_by: string;
  authorized_at: string;
  revoked_at: string | null;
};

/** O que `GET /v1/platform/journeys` devolve: o ambiente e os atos, numa leitura só. */
export type PlatformJourneys = {
  journeys: JourneyAvailability[];
  entitlements: JourneyEntitlement[];
};

/** O gesto de autorizar ou revogar um cliente numa jornada, antes de virar requisição. */
export type JourneyEntitlementDraft = {
  tenantId: string;
  journey: Journey;
  enabled: boolean;
  agreementReference?: string;
};

/**
 * Corpo do `PUT`. Mesma regra do entitlement de IA: na revogação a referência NÃO viaja,
 * porque o contrato que autorizou continua sendo o que está gravado, e reescrevê-lo com o
 * que estava na tela apagaria o registro do ato original.
 */
export function journeyEntitlementBody(
  draft: JourneyEntitlementDraft,
): Record<string, unknown> {
  const reference = draft.agreementReference?.trim() ?? "";
  if (!draft.enabled || reference === "") {
    return { enabled: draft.enabled };
  }
  return { enabled: draft.enabled, agreement_reference: reference };
}

function journeyEntitlementPath(tenantId: string, journey: Journey): string {
  return `/v1/platform/tenants/${encodeURIComponent(
    tenantId,
  )}/journey-entitlements/${journey}`;
}

/** Estado das jornadas neste ambiente e toda autorização já concedida. */
export function listJourneys(accessToken: string): Promise<PlatformJourneys> {
  return apiJson<PlatformJourneys>("/v1/platform/journeys", accessToken);
}

/**
 * Autoriza ou revoga um cliente numa jornada.
 *
 * Autorizar jornada que não está em piloto é recusado pelo SERVIDOR
 * (`409 JOURNEY_NOT_IN_PILOT`), e é assim que fica: a tela oferece todas as jornadas e
 * deixa a recusa subir com a frase por extenso, em vez de reimplementar a regra aqui.
 */
export function setJourneyEntitlement(
  accessToken: string,
  draft: JourneyEntitlementDraft,
): Promise<JourneyEntitlement> {
  return apiJson<JourneyEntitlement>(
    journeyEntitlementPath(draft.tenantId, draft.journey),
    accessToken,
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": crypto.randomUUID(),
      },
      body: JSON.stringify(journeyEntitlementBody(draft)),
    },
  );
}
