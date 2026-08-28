/* Arquivo gerado. Edite os modelos Pydantic e execute `make contracts`. */

export type CatalogSha256 = string | null;
export type Code = string | null;
export type Action = "confirm" | "reject";
export type DecidedAt = string;
export type DecisionId = string;
export type Note = string | null;
export type ReviewerId = string;
export type ReviewerRole = "orcamentista";
export type ItemId = string;
export type Status = "confirmed" | "rejected";
export type UnitCompatible = boolean;
export type Assignments = CodeAssignment[];
export type CatalogSha2561 = string;
export type ItemId1 = string;
export type Closures = ItemPackageClosure[];
export type ContractSha256 = string | null;
export type ImageSha256 = string;
export type PageNumber = number;
export type PlateId = string;
export type Code1 = string;
export type ItemId2 = string;
export type Note1 = string;
export type ReviewerId1 = string;
export type ReviewerRole1 = "orcamentista";
export type RevocationId = string;
export type RevokedAt = string;
export type Revocations = CodeAssignmentRevocation[];
/**
 * @minItems 2
 */
export type SafetyNotes = [string, string, ...string[]];
export type SchemaVersion = "1.0.0" | "2.0.0";

/**
 * Conjunto imutável de confirmações/rejeições de código de uma prancha.
 *
 * O `schema_version` declara o REGIME, e não só a forma dos campos:
 *
 * - `1.0.0` — um código por item, sem fechamento. É o que está gravado em toda rodada
 *   anterior ao ADR-0053, e relê com o comportamento exato de antes.
 * - `2.0.0` — a identidade é o par `(item_id, code)`, e o pacote de um elemento só está
 *   completo quando um `ItemPackageClosure` diz que está.
 *
 * Pacote aberto é estado NORMAL e persistido, não erro: o segundo dos seis códigos chega
 * num lote seguinte, e entre um e outro a rodada precisa poder ser gravada e relida. Quem
 * recusa pacote aberto é o portão que monta o boletim, onde a metade vira número errado.
 */
export interface CroquitoCodeAssignmentSet {
  assignments: Assignments;
  catalog_sha256: CatalogSha2561;
  closures?: Closures;
  contract_sha256?: ContractSha256;
  image_sha256: ImageSha256;
  page_number: PageNumber;
  plate_id: PlateId;
  revocations?: Revocations;
  safety_notes: SafetyNotes;
  schema_version?: SchemaVersion;
}
/**
 * Resultado imutável da confirmação/rejeição de código de um item.
 *
 * `catalog_sha256` carrega adiante a fonte citada na confirmação (vazio quando a rodada
 * tem um catálogo só, como em toda a medição licitada). É por ele que o orçamento-base
 * sabe, linha a linha, de qual tabela o preço veio — `build_worksite_estimate` exige a
 * citação e recusa a que não estiver na cascata.
 */
export interface CodeAssignment {
  catalog_sha256?: CatalogSha256;
  code?: Code;
  decision: ReviewerDecision;
  item_id: ItemId;
  status: Status;
  unit_compatible: UnitCompatible;
}
/**
 * Decisão humana rastreável do orçamentista.
 *
 * Duplicação local deliberada do `HumanDecision` do contexto de cena: o ADR-0016 mantém
 * os dois contextos separados, e uma decisão sobre medição não é uma decisão sobre
 * geometria. O que se repete é a forma, não o significado.
 */
export interface ReviewerDecision {
  action: Action;
  decided_at: DecidedAt;
  decision_id: DecisionId;
  note?: Note;
  reviewer_id: ReviewerId;
  reviewer_role: ReviewerRole;
}
/**
 * Ato humano que declara o pacote de serviços de um elemento COMPLETO.
 *
 * Existe porque, com a cardinalidade N:N, a presença de um assignment deixou de responder
 * "este item acabou?". Um elemento com um de seis códigos pareceria pronto e produziria
 * boletim parcial em silêncio; o fechamento é o que separa "resolvido" de "pela metade".
 * Nunca é inferido da contagem de códigos — ninguém, além da orçamentista, sabe quantos
 * serviços um elemento dispara.
 */
export interface ItemPackageClosure {
  decision: ReviewerDecision;
  item_id: ItemId1;
}
/**
 * O registro do que foi desfeito, no conjunto CORRENTE.
 *
 * A prova de que o par existiu está na revisão anterior, que continua gravada — mas quem lê
 * o conjunto corrente precisa distinguir "nunca foi decidido" de "foi decidido e desfeito"
 * sem ter de comparar revisões. É essa distinção que uma auditoria procura, e é por isso
 * que o registro fica aqui em vez de só no histórico (ADR-0061 D2).
 *
 * Um par revogado pode ser confirmado outra vez (D5). Quando isso acontece, ele aparece nos
 * dois lugares — em `assignments`, corrente, e aqui, como o que já foi desfeito uma vez —, e
 * é a leitura que decide o que mostrar. Apagar o registro na reconfirmação perderia o ato.
 */
export interface CodeAssignmentRevocation {
  code: Code1;
  item_id: ItemId2;
  note: Note1;
  reviewer_id: ReviewerId1;
  reviewer_role: ReviewerRole1;
  revocation_id: RevocationId;
  revoked_at: RevokedAt;
}
