/**
 * Fixture local de ordens de levantamento — o "servidor" desta fatia (Task Contract T4,
 * Out of Scope: sem rede real). Três ordens sintéticas espelhando a prancha 1 do Design
 * Approval Package; nenhum dado real de cliente (coordenadas, técnico, horários).
 */

import type { ChecklistItem, Order } from "./types";

function item(id: string, label: string): ChecklistItem {
  return { id, label, required: true };
}

const GUAXINDIBA_CHECKLIST: ChecklistItem[] = [
  item("perimetro", "Perímetro da praça"),
  item("calcada", "Calçada perimetral"),
  item("meio-fio", "Meio-fio"),
  item("academia", "Academia ao ar livre"),
  item("bancos", "Bancos"),
  item("iluminacao", "Postes de iluminação"),
  item("drenagem", "Bueiros e drenagem"),
  item("arvores", "Árvores existentes"),
  item("piso", "Piso / grama"),
  item("escada", "Escada de acesso"),
  item("rampa", "Rampa de acessibilidade"),
  item("quadra", "Quadra poliesportiva"),
  item("playground", "Playground infantil"),
  item("foto-acesso", "Foto do acesso principal"),
];

const CAMPO_DO_TOCA_CHECKLIST: ChecklistItem[] = [
  item("academia", "Academia ao ar livre"),
  item("aparelho-1", "Aparelho de ginástica 1"),
  item("aparelho-2", "Aparelho de ginástica 2"),
  item("calcada-norte", "Calçada lado norte"),
  item("calcada-sul", "Calçada lado sul"),
  item("meio-fio", "Meio-fio"),
  item("banco", "Banco de apoio"),
  item("lixeira", "Lixeira"),
  item("foto-acesso", "Foto do acesso principal"),
];

const RAUL_CAMPELO_CHECKLIST: ChecklistItem[] = [
  item("perimetro", "Perímetro da praça"),
  item("calcada", "Calçada perimetral"),
  item("meio-fio", "Meio-fio"),
  item("bancos", "Bancos"),
  item("iluminacao", "Postes de iluminação"),
  item("arvores", "Árvores existentes"),
  item("piso", "Piso / grama"),
  item("playground", "Playground infantil"),
  item("quadra", "Quadra poliesportiva"),
  item("foto-acesso", "Foto do acesso principal"),
];

export const ORDERS: Order[] = [
  {
    id: "order-guaxindiba",
    name: "Praça de Guaxindiba",
    short_name: "Guaxindiba",
    location: "São Gonçalo",
    scope_label: "levantamento completo",
    checklist: GUAXINDIBA_CHECKLIST,
  },
  {
    id: "order-campo-do-toca",
    name: "Praça do Campo do Toca",
    short_name: "Campo do Toca",
    location: "Rio de Janeiro",
    scope_label: "academia + calçadas",
    checklist: CAMPO_DO_TOCA_CHECKLIST,
  },
  {
    id: "order-raul-campelo",
    name: "Praça Raul Campelo",
    short_name: "Raul Campelo",
    location: "Rio de Janeiro",
    scope_label: "levantamento completo",
    checklist: RAUL_CAMPELO_CHECKLIST,
  },
];
