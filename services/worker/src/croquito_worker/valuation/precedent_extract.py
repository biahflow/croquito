"""Extração local do pacote de semeadura do índice de precedentes (F-044 T2, fonte B).

Sem esta ferramenta o índice nasceria vazio: só uma rodada real existe no banco, e o ganho
medido no Human Gate 1 (`docs/features/F-044-precedente-de-codigo/evidence.md`) esperaria
várias praças novas para aparecer. A semeadura entra pelas praças que a orçamentista já fez
— só que elas existem como planilha de orçamento, não como rodada do sistema.

**A planilha do cliente nunca sobe.** Esta é uma ferramenta LOCAL, da mesma família de
`parity`/`bulletin_compare`/`precedent-eval`: ela abre o `.xlsx` na máquina de quem roda e
escreve um pacote em `--output` (ignorado pelo Git, retenção local de 7 dias). O que a
ingestão recebe é esse pacote — rótulo, código e fonte de preço, o MESMO dado que as
revisões já guardam —, e nunca o arquivo.

Nada de leitura é reimplementado aqui. `read_memoria_sheet` abre o `.xlsx`,
`scan_memoria_rows` interpreta o formato e `normalize_label` normaliza — as três são da T1.
O que este módulo acrescenta é só a conversão para `PrecedentSeedPacket` e a contagem
honesta dos blocos que não têm rótulo.

Duas coisas ficam registradas aqui, e só aqui:

- **A fonte de preço é DECLARADA por quem roda** (`--price-source`), com
  `MEMORIA_PRICE_SOURCE` como valor padrão. A aba de memória de cálculo não grava
  `catalog_sha256` nenhum, e a chave do índice é (rótulo normalizado, fonte de preço): sem
  poder declarar a fonte, todo precedente semeado nasceria sob um rótulo de fonte que
  jamais casaria com o `catalog_sha256` de uma rodada real, e a semeadura não serviria para
  nada. Declarar é a única forma honesta de amarrar as duas — inventar um hash seria pior.
- **A chave da praça é DECLARADA por quem roda** (`--worksite`), no mesmo espaço de chave
  das rodadas reais (`WORKSITE_KEY_PATTERN`). O `precedent-eval` deriva a dele do nome do
  arquivo e da aba porque lá a chave só precisa distinguir praças dentro de uma medição;
  aqui ela precisa COLIDIR com a rodada real da mesma praça, que é o que impede a contagem
  de praças de contar a mesma obra duas vezes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Final

from croquito_valuation.precedent import (
    NormalizationStrategy,
    PrecedentSeedObservation,
    PrecedentSeedPacket,
    normalize_label,
)
from croquito_worker.io_utils import atomic_write_text
from croquito_worker.valuation.memoria_reader import read_memoria_sheet
from croquito_worker.valuation.precedent_eval import MEMORIA_PRICE_SOURCE, parse_memoria_spec

SEED_NORMALIZATION_STRATEGY: Final = NormalizationStrategy.FOLDED
"""A estratégia que o índice usa, e que o pacote declara.

`folded` porque foi a medida: `exact` e `folded` deram resultado IDÊNTICO nos três arquivos
reais do Human Gate 1, e não há evidência que justifique normalização mais agressiva neste
corpus (`evidence.md`, unknown 2). A estratégia viaja DENTRO do pacote em vez de ficar
implícita para que uma troca futura seja detectável: a ingestão recusa o pacote cuja
estratégia não seja a do índice, em vez de misturar chaves de duas normalizações.
"""


def build_seed_packet(
    *,
    memoria: str,
    worksite_key: str,
    price_source: str = MEMORIA_PRICE_SOURCE,
) -> PrecedentSeedPacket:
    """Lê `<arquivo.xlsx>:<aba>` e devolve o pacote de semeadura daquela praça.

    Blocos item+código que terminam sem rótulo NÃO entram nas observações — não há chave de
    índice sem rótulo — mas são contados e têm a linha nomeada no pacote. Descartá-los em
    silêncio esconderia de quem semeia o quanto da planilha ficou de fora.

    Dois blocos com o mesmo rótulo e o mesmo código viram UMA observação: a chave do índice
    é `(praça, rótulo, fonte, código)`, e repetir a mesma tupla no pacote só produziria uma
    linha "pulada" na ingestão. A ordem é a da planilha, estável.
    """
    path, sheet_name = parse_memoria_spec(memoria)
    scan = read_memoria_sheet(path, sheet_name)

    seen: set[tuple[str, str]] = set()
    observations: list[PrecedentSeedObservation] = []
    for block in scan.labeled_blocks:
        assert block.label is not None  # garantido por `labeled_blocks`
        normalized = normalize_label(block.label, SEED_NORMALIZATION_STRATEGY)
        key = (normalized, block.code)
        if key in seen:
            continue
        seen.add(key)
        observations.append(
            PrecedentSeedObservation(
                label_original=block.label,
                label_normalized=normalized,
                code=block.code,
                price_source=price_source,
            )
        )

    return PrecedentSeedPacket(
        worksite_key=worksite_key,
        normalization_strategy=SEED_NORMALIZATION_STRATEGY,
        observations=tuple(observations),
        block_count=len(scan.blocks),
        labeled_block_count=len(scan.labeled_blocks),
        unlabeled_block_count=len(scan.unlabeled_blocks),
        unlabeled_block_rows=tuple(block.row for block in scan.unlabeled_blocks),
    )


def run_precedent_extract(
    *,
    memoria: str,
    worksite_key: str,
    output_path: Path,
    price_source: str = MEMORIA_PRICE_SOURCE,
) -> PrecedentSeedPacket:
    """Monta o pacote e o escreve em `output_path`, pronto para `POST /v1/precedents/seed`."""
    packet = build_seed_packet(
        memoria=memoria, worksite_key=worksite_key, price_source=price_source
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        packet.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True
    )
    atomic_write_text(output_path, payload + "\n")
    return packet


def summary_text(packet: PrecedentSeedPacket) -> str:
    """Resumo para stdout. **Não** imprime rótulo: contagens bastam para conferir a leitura,
    e o rótulo de legenda é texto de cliente que já está no pacote, dentro de `--output`."""
    return "\n".join(
        [
            f"praça: {packet.worksite_key}",
            f"normalização: {packet.normalization_strategy.value}",
            f"blocos: {packet.block_count} "
            f"rotulados={packet.labeled_block_count} "
            f"sem_rotulo={packet.unlabeled_block_count} "
            f"linhas_sem_rotulo={list(packet.unlabeled_block_rows)}",
            f"observações: {len(packet.observations)} "
            f"rótulos={len({item.label_normalized for item in packet.observations})}",
        ]
    )
