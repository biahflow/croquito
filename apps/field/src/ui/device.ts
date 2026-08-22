const DEVICE_ID_STORAGE_KEY = "croquito-field-device-id";

/**
 * Identidade deste aparelho, estável entre sessões. É a chave de sequência do outbox
 * (`seq` cresce por device), então precisa sobreviver a fechar o app — daí localStorage e
 * não memória.
 */
export function getOrCreateDeviceId(): string {
  const existing = localStorage.getItem(DEVICE_ID_STORAGE_KEY);
  if (existing !== null && existing !== "") {
    return existing;
  }
  const id = crypto.randomUUID();
  localStorage.setItem(DEVICE_ID_STORAGE_KEY, id);
  return id;
}
