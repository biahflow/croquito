/**
 * Cliente da jornada de plataforma na API `/v1` autenticada (F-012, T2/T3).
 *
 * O transporte é o mesmo das outras jornadas (`apiJson` em `apps/web/src/api.ts`): ele
 * leva o `Authorization` da sessão OIDC, refaz a chamada uma vez quando o token expirou e
 * traduz o envelope aninhado (`{detail: {code, detail, details}}`) num `ApiError`. Este
 * módulo não abre `fetch` nenhum por conta própria, exceto o `PUT` assinado do presign do
 * acervo — que é upload direto no object store e nunca passa pela API.
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

// --------------------------------------------------------------------------------------
// Acervo de catálogos de referência (F-037, ADR-0047)
//
// Tabela pública publicada UMA vez para todos os tenants. O registro não tem tenant e
// nenhuma rota devolve URL assinada do objeto publicado: o cliente escolhe a tabela, o
// servidor é quem a lê. Nada aqui baixa catálogo.

/**
 * Uma publicação do acervo, como `GET /v1/platform/reference-catalogs` a devolve.
 *
 * `object_sha256` é o digest dos BYTES publicados e `source_sha256` o do arquivo de
 * origem, carimbado pelo importador — são fatos distintos e nenhum dos dois é derivado do
 * outro. A chave do objeto NÃO vem na resposta, de propósito: ela é referência interna do
 * store, e o objeto do acervo fica fora de todo caminho que assina URL.
 *
 * `available: false` com `withdrawn_at` preenchido é a publicação fora de circulação, que
 * CONTINUA na lista: retirar não apaga, e uma rodada montada sobre ela ainda a referencia.
 */
export type ReferenceCatalog = {
  reference_catalog_id: string;
  display_name: string;
  origin: string;
  reference_month: string;
  entry_count: number;
  object_sha256: string;
  source_sha256: string;
  available: boolean;
  published_by: string;
  published_at: string;
  withdrawn_at: string | null;
};

type ReferenceCatalogList = {
  catalogs: ReferenceCatalog[];
};

/** O que o presign devolve; o byte vai direto para esta URL, sem passar pela API. */
type PresignedUpload = {
  upload_id: string;
  url: string;
  headers: Record<string, string>;
};

/** O arquivo já no store, com o digest que a tela calculou para chegar até aqui. */
export type ReferenceCatalogUpload = {
  uploadId: string;
  objectSha256: string;
};

/** O gesto de publicar, antes de virar corpo de requisição. */
export type PublishCatalogDraft = {
  uploadId: string;
  displayName: string;
};

const ACERVO_PATH = "/v1/platform/reference-catalogs";

/**
 * Corpo do presign do acervo, puro e testável.
 *
 * `content_type` NÃO entra, e é o ponto do contrato que este construtor existe para
 * fixar: o tipo é `application/json` por definição da rota, e `extra="forbid"` do lado do
 * servidor recusa o campo com `422`. Mandá-lo "por garantia" seria justamente o que
 * derruba a publicação.
 */
export function referenceCatalogPresignBody(upload: {
  filename: string;
  sizeBytes: number;
  sha256: string;
}): Record<string, unknown> {
  return {
    filename: upload.filename,
    size_bytes: upload.sizeBytes,
    sha256: upload.sha256,
  };
}

/**
 * Corpo da publicação, puro e testável. DOIS campos, e é deliberado que não haja mais:
 * origem, data-base, digest da fonte e contagem vêm de dentro do arquivo, e o servidor
 * recusa qualquer um deles no corpo. O nome de exibição viaja sem espaço nas pontas —
 * vazio ou curto demais, a recusa é do servidor, que é a autoridade sobre a regra.
 */
export function publishCatalogBody(
  draft: PublishCatalogDraft,
): Record<string, unknown> {
  return {
    upload_id: draft.uploadId,
    display_name: draft.displayName.trim(),
  };
}

function withdrawPath(referenceCatalogId: string): string {
  return `${ACERVO_PATH}/${encodeURIComponent(referenceCatalogId)}/withdraw`;
}

function toHex(buffer: ArrayBuffer): string {
  return Array.from(new Uint8Array(buffer), (value) =>
    value.toString(16).padStart(2, "0"),
  ).join("");
}

/**
 * O acervo INTEIRO, inclusive o que saiu de circulação.
 *
 * A ordem é a do servidor (`origin`, `reference_month`, `id`) e a tela não a reordena:
 * duas publicações da mesma origem e data-base saem na ordem em que foram publicadas, e
 * embaralhar isso aqui esconderia qual é a mais nova.
 */
export async function listReferenceCatalogs(
  accessToken: string,
): Promise<ReferenceCatalog[]> {
  const resposta = await apiJson<ReferenceCatalogList>(ACERVO_PATH, accessToken);
  return resposta.catalogs;
}

/**
 * Sobe o `catalog.json` pelo presign da PLATAFORMA e devolve o identificador e o digest.
 *
 * A rota é `/v1/platform/reference-catalogs/presign`, e não `/v1/uploads/presign`: o
 * presign do croqui está sob o portão de disponibilidade de jornada, então num ambiente
 * com o croqui desligado o operador receberia `403 JOURNEY_UNAVAILABLE` e o acervo
 * ficaria sem como ser alimentado (F-037, T6).
 *
 * O digest sai junto porque a tela precisa dele depois: é ele que nomeia o conteúdo na
 * recusa de republicar, e recalculá-lo lá seria ler o arquivo duas vezes.
 */
export async function uploadReferenceCatalog(
  accessToken: string,
  file: File,
): Promise<ReferenceCatalogUpload> {
  return uploadPeloPresignDaPlataforma(
    accessToken,
    file,
    `${ACERVO_PATH}/presign`,
    referenceCatalogPresignBody,
  );
}

/**
 * O envio direto de um artefato de plataforma: presign da própria rota, `PUT` no store.
 *
 * Compartilhado entre o acervo e o índice de embeddings porque é o MESMO ato — os dois
 * sobem um `.json` pelo presign de plataforma, com o digest calculado aqui, e nenhum dos
 * dois pode depender de `/v1/uploads/presign`. O que muda entre eles é a rota do presign
 * e o construtor do corpo; o resto seria duas cópias livres para divergir num cabeçalho.
 */
async function uploadPeloPresignDaPlataforma(
  accessToken: string,
  file: File,
  presignPath: string,
  presignBody: (upload: {
    filename: string;
    sizeBytes: number;
    sha256: string;
  }) => Record<string, unknown>,
): Promise<ReferenceCatalogUpload> {
  const digest = toHex(
    await crypto.subtle.digest("SHA-256", await file.arrayBuffer()),
  );
  const presigned = await apiJson<PresignedUpload>(presignPath, accessToken, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": crypto.randomUUID(),
    },
    body: JSON.stringify(
      presignBody({
        filename: file.name,
        sizeBytes: file.size,
        sha256: digest,
      }),
    ),
  });
  const upload = await fetch(presigned.url, {
    method: "PUT",
    headers: presigned.headers,
    body: file,
  });
  if (!upload.ok) {
    // Código próprio: a falha aqui é do `PUT` direto no armazenamento, e chamá-la de
    // `INVALID_UPLOAD` mandaria conferir o arquivo quando o defeito é o envio.
    throw new ApiError(
      "O envio direto do arquivo não foi concluído. Tente novamente.",
      upload.status,
      "UPLOAD_TRANSFER_FAILED",
      "o PUT assinado do arquivo não foi concluído",
      {},
    );
  }
  return { uploadId: presigned.upload_id, objectSha256: digest };
}

/** Publica no acervo o catálogo já subido; vale para todos os tenants. */
export function publishReferenceCatalog(
  accessToken: string,
  draft: PublishCatalogDraft,
): Promise<ReferenceCatalog> {
  return apiJson<ReferenceCatalog>(ACERVO_PATH, accessToken, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": crypto.randomUUID(),
    },
    body: JSON.stringify(publishCatalogBody(draft)),
  });
}

/**
 * Tira o catálogo de circulação. **Sem corpo**: o ato é inteiramente identificado pela
 * rota, e mandar um JSON vazio só ofereceria um campo que o contrato não tem. Repetir
 * sobre um catálogo já retirado devolve o registro como está, sem recarimbar a data.
 */
export function withdrawReferenceCatalog(
  accessToken: string,
  referenceCatalogId: string,
): Promise<ReferenceCatalog> {
  return apiJson<ReferenceCatalog>(withdrawPath(referenceCatalogId), accessToken, {
    method: "POST",
    headers: { "Idempotency-Key": crypto.randomUUID() },
  });
}

// --------------------------------------------------------------------------------------
// Índice de embeddings publicado (F-041, ADR-0054)
//
// Irmão do acervo, e pelo mesmo desenho: artefato público, sem tenant, endereçado por
// digest. Duas diferenças moram aqui e nenhuma delas é detalhe:
//
// - **A tela nunca baixa o índice.** Nenhuma rota o assina, `object_key` não vem na
//   resposta e o servidor é quem o lê. Por isso não existe função de download neste
//   módulo — e a ausência é a decisão, não um esquecimento.
// - **A tela nunca constrói o índice.** Ele sai do comando pago `index-catalog` do CLI
//   (ADR-0054 D4); daqui só sobe o `catalog-embeddings.json` que já existe.

/**
 * Uma publicação de índice, como `GET /v1/platform/reference-catalog-indexes` a devolve.
 *
 * Tudo que descreve o índice vem de DENTRO do documento publicado (`text_recipe`,
 * `provider`, `model_id`, `dims`, `code_count`, `catalog_source_sha256`): nada é digitado
 * na publicação, e por isso nada aqui pode discordar do conteúdo que o servidor lê.
 *
 * `available: false` com `withdrawn_at` preenchido é o índice fora de circulação, que
 * CONTINUA na lista: retirar não apaga, e a shortlist já gravada cita o digest do índice
 * que a produziu.
 */
export type ReferenceCatalogIndex = {
  reference_catalog_index_id: string;
  reference_catalog_id: string;
  catalog_source_sha256: string;
  text_recipe: string;
  provider: string;
  model_id: string;
  dims: number;
  code_count: number;
  object_sha256: string;
  available: boolean;
  published_by: string;
  published_at: string;
  withdrawn_at: string | null;
};

type ReferenceCatalogIndexList = {
  indexes: ReferenceCatalogIndex[];
};

/** O gesto de publicar um índice, antes de virar corpo de requisição. */
export type PublishIndexDraft = {
  uploadId: string;
  referenceCatalogId: string;
};

const INDICES_PATH = "/v1/platform/reference-catalog-indexes";

/**
 * Corpo do presign do índice, puro e testável.
 *
 * Mesma forma do presign do acervo e pela mesma razão: `content_type` NÃO entra — o tipo é
 * `application/json` por definição da rota, e `extra="forbid"` do lado do servidor recusa o
 * campo com `422`. Construtor próprio, e não o do acervo reaproveitado, porque são dois
 * contratos do servidor: se um deles ganhar um campo, o outro não deve ganhá-lo junto.
 */
export function referenceCatalogIndexPresignBody(upload: {
  filename: string;
  sizeBytes: number;
  sha256: string;
}): Record<string, unknown> {
  return {
    filename: upload.filename,
    size_bytes: upload.sizeBytes,
    sha256: upload.sha256,
  };
}

/**
 * Corpo da publicação do índice. DOIS campos, e é deliberado que não haja mais: receita de
 * texto, provider, modelo, dimensões, contagem de códigos e o digest do catálogo indexado
 * são lidos de dentro do documento, e o servidor recusa qualquer um deles no corpo.
 *
 * `reference_catalog_id` existe para ser CONFERIDO, não para localizar: a busca do índice
 * é por digest da fonte (ADR-0054 D3), e este campo é o que faz o servidor recusar com
 * `REFERENCE_CATALOG_INDEX_CATALOG_MISMATCH` um índice construído sobre outro catálogo.
 */
export function publishIndexBody(
  draft: PublishIndexDraft,
): Record<string, unknown> {
  return {
    upload_id: draft.uploadId,
    reference_catalog_id: draft.referenceCatalogId,
  };
}

function withdrawIndexPath(referenceCatalogIndexId: string): string {
  return `${INDICES_PATH}/${encodeURIComponent(referenceCatalogIndexId)}/withdraw`;
}

/**
 * Todos os índices, inclusive os que saíram de circulação.
 *
 * A ordem é a do servidor (`catalog_source_sha256`, `text_recipe`, `id`) e a tela não a
 * reordena: dois índices do mesmo catálogo e da mesma receita saem na ordem em que foram
 * publicados, que é a ordem em que a resolução os prefere.
 */
export async function listReferenceCatalogIndexes(
  accessToken: string,
): Promise<ReferenceCatalogIndex[]> {
  const resposta = await apiJson<ReferenceCatalogIndexList>(
    INDICES_PATH,
    accessToken,
  );
  return resposta.indexes;
}

/**
 * Sobe o `catalog-embeddings.json` pelo presign PRÓPRIO da rota do índice.
 *
 * A rota é `/v1/platform/reference-catalog-indexes/presign`, e não `/v1/uploads/presign`,
 * pelo mesmo motivo do acervo: o presign do croqui está sob o portão de disponibilidade de
 * jornada, e num ambiente com o croqui desligado o operador ficaria sem como publicar.
 */
export async function uploadReferenceCatalogIndex(
  accessToken: string,
  file: File,
): Promise<ReferenceCatalogUpload> {
  return uploadPeloPresignDaPlataforma(
    accessToken,
    file,
    `${INDICES_PATH}/presign`,
    referenceCatalogIndexPresignBody,
  );
}

/** Publica o índice já subido; ele passa a valer para todos os tenants. */
export function publishReferenceCatalogIndex(
  accessToken: string,
  draft: PublishIndexDraft,
): Promise<ReferenceCatalogIndex> {
  return apiJson<ReferenceCatalogIndex>(INDICES_PATH, accessToken, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": crypto.randomUUID(),
    },
    body: JSON.stringify(publishIndexBody(draft)),
  });
}

/**
 * Tira o índice de circulação. **Sem corpo**: o ato é inteiramente identificado pela rota.
 * Repetir sobre um índice já retirado devolve o registro como está, sem recarimbar a data.
 */
export function withdrawReferenceCatalogIndex(
  accessToken: string,
  referenceCatalogIndexId: string,
): Promise<ReferenceCatalogIndex> {
  return apiJson<ReferenceCatalogIndex>(
    withdrawIndexPath(referenceCatalogIndexId),
    accessToken,
    {
      method: "POST",
      headers: { "Idempotency-Key": crypto.randomUUID() },
    },
  );
}
