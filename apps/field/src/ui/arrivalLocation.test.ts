import { describe, expect, it } from "vitest";

import type { GpsFix } from "../domain/types";
import type { Order } from "../orders/types";
import { describeArrivalLocation } from "./arrivalLocation";

function order(overrides: Partial<Order> = {}): Order {
  return {
    id: "order-teste",
    name: "Praça de Teste",
    short_name: "Teste",
    location: "Cidade Teste",
    scope_label: "levantamento completo",
    checklist: [],
    ...overrides,
  };
}

function fix(overrides: Partial<GpsFix> = {}): GpsFix {
  return { lat: -22.8267, lng: -43.0537, accuracy_m: 8, ...overrides };
}

describe("describeArrivalLocation", () => {
  it("mostra nome da ordem e endereço, com distância quando o fix e o ponto de referência existem", () => {
    const result = describeArrivalLocation(
      order({
        name: "Praça de Guaxindiba",
        location: "São Gonçalo",
        address: "Rua Alfredo Backer, s/n",
        address_location: { lat: -22.8267, lng: -43.0537 },
      }),
      // ~0.001 grau de deslocamento em lat ≈ 111 m — usado só para gerar um valor > 0
      // determinístico, sem depender de nenhum device real.
      fix({ lat: -22.826, lng: -43.0537 }),
    );

    expect(result.title).toBe("Local confirmado — Praça de Guaxindiba");
    expect(result.detail).toMatch(/^Rua Alfredo Backer, s\/n · São Gonçalo — a ~\d+ m do endereço da ordem · a localização serve para achar a obra, não para medir$/);
  });

  it("omite a distância quando não há fix de GPS ainda (endereço continua aparecendo)", () => {
    const result = describeArrivalLocation(
      order({
        address: "Rua Alfredo Backer, s/n",
        address_location: { lat: -22.8267, lng: -43.0537 },
      }),
      undefined,
    );

    expect(result.detail).toBe(
      "Rua Alfredo Backer, s/n · Cidade Teste · a localização serve para achar a obra, não para medir",
    );
  });

  it("omite a distância quando a ordem tem endereço mas não tem ponto de referência", () => {
    const result = describeArrivalLocation(order({ address: "Rua do Campo do Toca, s/n" }), fix());

    expect(result.detail).toBe(
      "Rua do Campo do Toca, s/n · Cidade Teste · a localização serve para achar a obra, não para medir",
    );
  });

  it("fixture legada sem endereço não quebra — mostra só o que a ordem tem (location)", () => {
    const result = describeArrivalLocation(order(), fix());

    expect(result.title).toBe("Local confirmado — Praça de Teste");
    expect(result.detail).toBe("Cidade Teste · a localização serve para achar a obra, não para medir");
  });

  it("sem ordem ativa (corrida entre telas) não quebra — texto genérico", () => {
    const result = describeArrivalLocation(null, fix());

    expect(result.title).toBe("Local confirmado");
    expect(result.detail).toBe("A localização serve para achar a obra, não para medir.");
  });

  it("nunca imprime coordenadas cruas no texto", () => {
    const result = describeArrivalLocation(
      order({ address: "Rua Alfredo Backer, s/n", address_location: { lat: -22.8267, lng: -43.0537 } }),
      fix({ lat: -22.826, lng: -43.0537 }),
    );

    expect(result.detail).not.toMatch(/-22\.\d+/);
    expect(result.detail).not.toMatch(/-43\.\d+/);
  });
});
