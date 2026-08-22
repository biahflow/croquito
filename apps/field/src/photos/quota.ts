/**
 * Aviso de pouco espaço local (Task Contract T6, Out of Scope: "apenas aviso escrito se
 * `navigator.storage.estimate` acusar <50 MB livres — um banner, nada além"). Não há
 * gestão de quota nesta fatia: só a leitura e o cálculo do limiar.
 */
export const LOW_STORAGE_THRESHOLD_BYTES = 50 * 1024 * 1024;

/**
 * `true` quando o espaço livre estimado do aparelho está abaixo do limiar. Sem a API
 * disponível (navegador antigo, ambiente sem suporte) ou sem uma estimativa utilizável,
 * devolve `false` — o app nunca vira um bloqueio por causa de uma estimativa ausente, só
 * avisa quando ela existe e é baixa.
 */
export async function isStorageLow(): Promise<boolean> {
  if (typeof navigator === "undefined" || navigator.storage?.estimate === undefined) {
    return false;
  }
  try {
    const { quota, usage } = await navigator.storage.estimate();
    if (quota === undefined || usage === undefined) {
      return false;
    }
    return quota - usage < LOW_STORAGE_THRESHOLD_BYTES;
  } catch {
    return false;
  }
}
