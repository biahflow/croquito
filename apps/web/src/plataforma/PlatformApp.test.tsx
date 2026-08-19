import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { User } from "oidc-client-ts";

import type { PlatformTenant } from "./api";
import {
  AlertaPersistente,
  LinhaTenant,
  PlatformApp,
} from "./PlatformApp";

/**
 * `renderToStaticMarkup` não roda efeitos: o que sai destes renders é exatamente o
 * primeiro estado, antes de qualquer resposta da API. É o que garante que nenhum tenant,
 * contrato ou carimbo seja fabricado pela tela.
 */

const sessao = {
  access_token: "token-de-teste",
  profile: { sub: "operador-de-teste" },
} as unknown as User;

function tenant(overrides: Partial<PlatformTenant> = {}): PlatformTenant {
  return {
    tenant_id: "acme",
    enabled: false,
    agreement_reference: null,
    authorized_at: null,
    revoked_at: null,
    ...overrides,
  };
}

describe("PlatformApp sem sessão", () => {
  it("pede a sessão e não mostra tenant nenhum", () => {
    const html = renderToStaticMarkup(<PlatformApp session={null} />);

    expect(html).toContain("Entre para administrar a autorização contratual");
    expect(html).toContain("exigem o papel de operador");
    expect(html).not.toContain("Ativar autorização");
    expect(html).not.toContain("acme");
  });
});

describe("PlatformApp com sessão, antes da primeira resposta", () => {
  it("declara que a lista ainda não foi lida em vez de inventar tenant", () => {
    const html = renderToStaticMarkup(<PlatformApp session={sessao} />);

    expect(html).toContain("A lista de tenants ainda não foi lida.");
    expect(html).not.toContain("Autorização de IA:");
  });

  /**
   * O tenant que existe só no provedor de identidade não tem pegada no banco e por isso
   * não aparece na lista. Sem o campo de texto livre, ativá-lo seria impossível pela tela
   * — que é o ritual de `curl` que esta jornada veio substituir.
   */
  it("oferece ativar um tenant pelo identificador, com a razão escrita", () => {
    const html = renderToStaticMarkup(<PlatformApp session={sessao} />);

    expect(html).toContain("Identificador do tenant");
    expect(html).toContain("Ativar autorização deste tenant");
    expect(html).toContain("Consultar estado antes de ativar");
    expect(html).toContain("só no provedor de identidade");
    expect(html).toContain("Referência do contrato");
  });

  it("não fabrica sucesso nem erro antes de qualquer ato", () => {
    const html = renderToStaticMarkup(<PlatformApp session={sessao} />);

    expect(html).not.toContain('role="alert"');
    expect(html).not.toContain("app-toast");
  });
});

describe("LinhaTenant", () => {
  const inertes = {
    referencia: "",
    enviando: false,
    onAbrir: () => {},
    onCancelar: () => {},
    onReferencia: () => {},
    onConfirmar: () => {},
  };

  it("escreve o estado por extenso, e não só por cor", () => {
    const html = renderToStaticMarkup(
      <LinhaTenant
        tenant={tenant({
          enabled: true,
          agreement_reference: "contrato 05/2024",
          authorized_at: "2026-03-02T15:30:00Z",
        })}
        acao={null}
        {...inertes}
      />,
    );

    expect(html).toContain("Autorização de IA: ativo");
    expect(html).toContain("contrato 05/2024");
    expect(html).toContain("02/03/2026");
    // Ativo só oferece revogar; a ação disponível é a que falta fazer.
    expect(html).toContain("Revogar autorização");
    expect(html).not.toContain("Ativar autorização<");
  });

  it("distingue o tenant nunca autorizado do revogado", () => {
    const nunca = renderToStaticMarkup(
      <LinhaTenant tenant={tenant()} acao={null} {...inertes} />,
    );
    const revogado = renderToStaticMarkup(
      <LinhaTenant
        tenant={tenant({
          agreement_reference: "contrato 05/2024",
          authorized_at: "2026-03-02T15:30:00Z",
          revoked_at: "2026-03-09T15:30:00Z",
        })}
        acao={null}
        {...inertes}
      />,
    );

    expect(nunca).toContain("Autorização de IA: nunca autorizado");
    expect(nunca).toContain("Contrato: —");
    expect(revogado).toContain("Autorização de IA: revogado");
    expect(revogado).toContain("09/03/2026");
  });

  /**
   * A confirmação é gesto separado: abrir a ação não grava nada, e o botão nomeia o
   * tenant para que o ato não seja confirmado na linha errada.
   */
  it("a ativação pede a referência do contrato e uma confirmação nomeada", () => {
    const html = renderToStaticMarkup(
      <LinhaTenant
        tenant={tenant()}
        acao={{ enabled: true }}
        {...inertes}
      />,
    );

    expect(html).toContain("Referência do contrato");
    expect(html).toContain("Confirmar ativação de acme");
    expect(html).toContain("Cancelar");
    expect(html).toContain("3 a 128");
  });

  it("a revogação diz o que ela faz e o que ela não desfaz", () => {
    const html = renderToStaticMarkup(
      <LinhaTenant
        tenant={tenant({ enabled: true, agreement_reference: "contrato 05/2024" })}
        acao={{ enabled: false }}
        {...inertes}
      />,
    );

    expect(html).toContain("Confirmar revogação de acme");
    expect(html).toContain("bloqueia envios novos");
    expect(html).toContain("permanece");
    // Revogar não pede referência: o contrato que autorizou continua sendo o gravado.
    expect(html).not.toContain("<input");
  });
});

describe("AlertaPersistente", () => {
  it("é anunciado como alerta e não oferece fechar", () => {
    const html = renderToStaticMarkup(
      <AlertaPersistente mensagem="Sua conta não tem o papel de operador." />,
    );

    expect(html).toContain('role="alert"');
    expect(html).toContain("Sua conta não tem o papel de operador.");
    expect(html).not.toContain("app-alert-close");
  });
});
