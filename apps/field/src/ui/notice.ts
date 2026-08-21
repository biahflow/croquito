export type NoticeTone = "info" | "ok" | "warn" | "error";

/** Aviso escrito de uma tela — instrução do modo em curso ou erro estruturado devolvido
 * por um comando do domínio (código estável + mensagem em português). Cor nunca carrega
 * o significado sozinha: o texto sempre diz o estado. */
export interface Notice {
  tone: NoticeTone;
  text: string;
}
