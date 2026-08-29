import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { BannerBoletimVencido } from "./MedicaoApp";
import { BOLETIM_VENCIDO, REMONTAR_CADUCA_A_APROVACAO } from "./etapas";
import { DICA_NOME_DA_OBRA, WORKSITE_SHEET_NAME_BUDGET } from "./requests";

/**
 * O boletim gravado que deixou de descrever a praça (F-046 T5c).
 *
 * A derivação da etapa está em `etapas.test.ts`; o que se prova aqui é o que é da TELA: o
 * estado dito por extenso, o ato oferecido no mesmo lugar em que o estado é declarado e o
 * aviso de que remontar leva a aprovação em vigor adiante já caduca.
 */

describe("o banner do boletim vencido", () => {
  it("diz o estado por extenso e oferece o ato que o resolve", () => {
    const html = renderToStaticMarkup(
      <BannerBoletimVencido
        aprovada={false}
        submitting={false}
        onRemontar={() => undefined}
      />,
    );

    expect(html).toContain(BOLETIM_VENCIDO);
    // O ato que o toast do vínculo já mandava fazer, agora oferecido onde o estado é dito.
    expect(html).toContain("Montar o boletim de novo");
    // Persistente e anunciado: estado que exige ato humano não expira sozinho.
    expect(html).toContain('role="alert"');
    // Sem aprovação em vigor não há o que caducar, e a frase não aparece.
    expect(html).not.toContain(REMONTAR_CADUCA_A_APROVACAO);
  });

  it("com aprovação em vigor, diz o que ela perde ANTES do clique", () => {
    const html = renderToStaticMarkup(
      <BannerBoletimVencido aprovada submitting={false} onRemontar={() => undefined} />,
    );

    expect(html).toContain(REMONTAR_CADUCA_A_APROVACAO);
    // Preservar não é apagar: a frase promete que a assinatura continua registrada.
    expect(html).toContain("não apaga a aprovação");
  });

  it("durante a gravação, o botão não aceita um segundo clique", () => {
    const html = renderToStaticMarkup(
      <BannerBoletimVencido
        aprovada={false}
        submitting
        onRemontar={() => undefined}
      />,
    );

    expect(html).toContain("Montando…");
    expect(html).toContain("disabled=");
  });
});

describe("o teto do nome da obra na abertura da rodada", () => {
  it("é dito ANTES de o nome ser aceito, com o número que o servidor cobra", () => {
    expect(WORKSITE_SHEET_NAME_BUDGET).toBe(23);
    expect(DICA_NOME_DA_OBRA).toContain("23 caracteres");
    expect(DICA_NOME_DA_OBRA).toContain("BM e MEMÓRIA");
    // A tela DIZ o teto; quem recusa é o servidor, porque o nome maior ainda pode caber
    // pelos degraus declarados e uma contagem no navegador recusaria o que o domínio aceita.
    expect(DICA_NOME_DA_OBRA).toContain("recusada");
  });
});
