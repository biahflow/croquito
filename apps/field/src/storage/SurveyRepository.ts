import type { Survey } from "../domain/types";
import type { SurveyOperation } from "../outbox/types";

/**
 * Um arquivo de mídia local (T6) — hoje só foto. O blob vive aqui, atrás da interface;
 * nunca em `localStorage`, nunca em base64 no estado de React (`apps/field/AGENTS.md`,
 * regra de dados e segurança do repositório: nunca logar conteúdo/URL de foto). `id` é
 * o valor referenciado por `PhotoAnchor.local_media_ref` e por
 * `ArrivalContext.access_media_ref` — o domínio (`src/domain`) só guarda essa referência
 * em texto, nunca o `MediaRecord` inteiro (ele não é serializável em JSON puro por causa
 * do `Blob`, e o domínio precisa continuar serializável).
 */
export interface MediaRecord {
  id: string;
  /** SHA-256 em hex minúsculo do conteúdo original do arquivo, calculado antes de
   * qualquer processamento (não há compressão nesta fatia). */
  sha256: string;
  mime_type: string;
  byte_size: number;
  blob: Blob;
  created_at: string;
}

/**
 * Interface de persistência local. Isola o domínio de Dexie/IndexedDB (ADR-0043, D2): a
 * troca por SQLite/Capacitor deve ser possível sem reescrever `src/domain` nem `src/ui`.
 */
export interface SurveyRepository {
  getSurvey(surveyId: string): Promise<Survey | undefined>;
  saveSurvey(survey: Survey): Promise<void>;
  appendOperation(operation: SurveyOperation): Promise<void>;
  /**
   * Grava o survey e a operação que o produziu numa transação ÚNICA (T9, dívida aberta na
   * revisão de T3): sem isto, um app fechado entre as duas escritas deixaria o survey novo
   * sem a operação correspondente no outbox — o estado local avançaria e o servidor nunca
   * receberia a ação. É o caminho que `applyCommand` usa; `saveSurvey`/`appendOperation`
   * seguem existindo para os casos que gravam UM dos dois (criação do survey ao baixar uma
   * ordem, marcação de status pelo motor de sincronização).
   */
  saveSurveyWithOperation(survey: Survey, operation: SurveyOperation): Promise<void>;
  /** Operações ainda não reconhecidas nem preteridas (`status !== "acked"` e
   * `!== "superseded"`) do survey, em ordem de `seq` — é o que o contador "N pendentes" da
   * barra conta e o que o próximo lote oferece ao servidor. */
  getPendingOperations(surveyId: string): Promise<SurveyOperation[]>;
  /** TODAS as operações do survey (inclusive `acked`), em ordem de `seq`. É a fonte para
   * calcular o próximo `seq`: pendências não servem, porque um ack encolheria a lista e a
   * sequência regrediria, reutilizando valores já emitidos. */
  listOperations(surveyId: string): Promise<SurveyOperation[]>;
  /** Marca a operação como reconhecida. Idempotente: reconhecer de novo uma operação já
   * reconhecida não é erro nem apaga histórico. */
  acknowledge(operationId: string): Promise<void>;
  /**
   * Regrava operações já existentes (T9): mudança de `status` (`local` → `pending`,
   * `→ superseded`) e reancoragem de `seq` na resolução de conflito. Substitui a linha
   * inteira pelo objeto informado — quem chama parte da linha lida, nunca de um objeto
   * montado do zero — e NUNCA remove nada: não existe `deleteOperation` neste repositório,
   * pela mesma razão que não existe `deleteMedia`.
   */
  saveOperations(operations: readonly SurveyOperation[]): Promise<void>;
  /** Grava um arquivo de mídia (T6). Sem `deleteMedia` de propósito — dado local nunca é
   * apagado (mesma regra do outbox, `apps/field/AGENTS.md`). */
  saveMedia(record: MediaRecord): Promise<void>;
  getMedia(mediaId: string): Promise<MediaRecord | undefined>;
}
