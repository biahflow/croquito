"""Extração local do pacote de semeadura do índice de precedentes (F-044 T2, fonte B).

Três invariantes, e são as que a semeadura depende para não estragar o índice:

- **bloco sem rótulo é contado, nunca descartado em silêncio** — sem rótulo não há chave de
  índice, mas quem semeia precisa saber quanto da planilha ficou de fora;
- **a normalização é a da T1**, gravada no pacote junto das observações, para que a ingestão
  possa recusar um pacote de outra estratégia em vez de misturar duas chaves;
- **a fonte de preço é declarada**, e a chave do índice é (rótulo, fonte): sem poder
  declará-la, todo precedente semeado nasceria sob uma fonte que jamais casaria com o
  `catalog_sha256` de uma rodada real.

Nenhuma planilha real entra aqui: as fixtures são sintéticas, escritas pelo próprio teste,
como manda o `AGENTS.md`. A ferramenta é local e offline; nada aqui paga nada.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from openpyxl import Workbook

from croquito_valuation.errors import ValuationValidationError
from croquito_valuation.precedent import NormalizationStrategy, PrecedentSeedPacket
from croquito_worker.valuation.cli import main
from croquito_worker.valuation.precedent_eval import MEMORIA_PRICE_SOURCE
from croquito_worker.valuation.precedent_extract import build_seed_packet, run_precedent_extract

_CATALOG_SHA = "a" * 64


def _write_memoria_workbook(path: Path, sheet_name: str, rows: list[list[object]]) -> None:
    workbook = Workbook()
    worksheet = workbook.active
    assert worksheet is not None
    worksheet.title = sheet_name
    for row in rows:
        worksheet.append(row)
    workbook.save(path)


def _praca_sintetica(path: Path) -> None:
    """Praça sintética com o pacote N:N, um rótulo repetido e um bloco sem rótulo.

    `PISO EM CONCRETO` dispara dois códigos, que é a forma do documento real (F-038): um
    elemento medido uma vez alimenta vários serviços. O bloco final sem rótulo existe no dado
    real e é justamente o que a ferramenta precisa contar em vez de esconder.
    """
    _write_memoria_workbook(
        path,
        "MEMÓRIA DE CÁLCULO",
        [
            [None, "01.10", "BP09100050(B)", "descrição do código"],
            [None, None, None, "PISO EM CONCRETO"],
            [None, "01.11", "ET39050109(/)", "descrição do código"],
            [None, None, None, "Piso em Concretô"],
            [None, "01.12", "PJ14150203(A)", "descrição do código"],
            [None, None, None, "ALAMBRADO"],
            [None, "01.13", "SC19050600(/)", "descrição do código"],
        ],
    )


def test_a_extracao_produz_o_pacote_e_conta_os_blocos_sem_rotulo(tmp_path: Path) -> None:
    """Quatro blocos, três rotulados, um sem rótulo — e a linha dele nomeada.

    O bloco sem rótulo NÃO vira observação (não há chave de índice sem rótulo) e mesmo assim
    aparece no pacote pela linha da planilha: é como quem semeia descobre que a leitura
    deixou algo de fora, em vez de acreditar que o pacote é completo.
    """
    memoria = tmp_path / "praca-passada.xlsx"
    _praca_sintetica(memoria)

    packet = build_seed_packet(
        memoria=f"{memoria}:MEMÓRIA DE CÁLCULO", worksite_key="praca-passada-sul"
    )

    assert packet.worksite_key == "praca-passada-sul"
    assert packet.block_count == 4
    assert packet.labeled_block_count == 3
    assert packet.unlabeled_block_count == 1
    assert packet.unlabeled_block_rows == (7,)
    assert len(packet.observations) == 3


def test_a_normalizacao_do_pacote_e_a_da_t1_e_viaja_declarada(tmp_path: Path) -> None:
    """`folded` junta "PISO EM CONCRETO" e "Piso em Concretô" na MESMA chave.

    É o que faz o pacote N:N do rótulo se formar: os dois blocos escrevem o rótulo com caixa
    e acento diferentes e disparam códigos diferentes, e o índice precisa vê-los como um só
    elemento. A estratégia viaja escrita no pacote para que a ingestão possa recusá-lo se um
    dia ela mudar, em vez de misturar chaves de duas normalizações.

    O que `folded` **não** faz, e este teste não finge que faz: colapsar espaço interno
    repetido. Essa é a normalização da T1, reusada como está — a medição do Human Gate 1
    mostrou que ela basta neste corpus, e inventar uma normalização nova aqui contrariaria a
    conclusão que a medição sustenta.
    """
    memoria = tmp_path / "praca-passada.xlsx"
    _praca_sintetica(memoria)

    packet = build_seed_packet(
        memoria=f"{memoria}:MEMÓRIA DE CÁLCULO", worksite_key="praca-passada-sul"
    )

    assert packet.normalization_strategy is NormalizationStrategy.FOLDED
    by_label: dict[str, list[str]] = {}
    for observation in packet.observations:
        by_label.setdefault(observation.label_normalized, []).append(observation.code)
    piso = [codes for label, codes in by_label.items() if "piso" in label]
    assert piso == [["BP09100050(B)", "ET39050109(/)"]]


def test_a_fonte_de_preco_e_declarada_por_quem_semeia(tmp_path: Path) -> None:
    """Sem `--price-source`, o rótulo legível do contrato; com ele, o digest do catálogo.

    A chave do índice é (rótulo, fonte de preço). O padrão é honesto — a aba de memória não
    grava `catalog_sha256` nenhum e inventar um hash seria pior —, mas ele nunca casaria com
    uma rodada real. Poder declarar a fonte é o que torna a semeadura útil para a praça
    seguinte, em vez de um índice paralelo que ninguém alcança.
    """
    memoria = tmp_path / "praca-passada.xlsx"
    _praca_sintetica(memoria)
    spec = f"{memoria}:MEMÓRIA DE CÁLCULO"

    padrao = build_seed_packet(memoria=spec, worksite_key="praca-passada-sul")
    declarada = build_seed_packet(
        memoria=spec, worksite_key="praca-passada-sul", price_source=_CATALOG_SHA
    )

    assert {item.price_source for item in padrao.observations} == {MEMORIA_PRICE_SOURCE}
    assert {item.price_source for item in declarada.observations} == {_CATALOG_SHA}


def test_a_chave_da_praca_precisa_ser_do_mesmo_espaco_das_rodadas_reais(tmp_path: Path) -> None:
    """Chave fora do padrão recusa: é por ela que a ingestão detecta colisão com rodada real.

    Uma praça semeada sob uma chave de outro formato jamais colidiria com a rodada da mesma
    obra, e a contagem de praças — o argumento de autoridade da tela — passaria a contar a
    mesma obra duas vezes.
    """
    memoria = tmp_path / "praca-passada.xlsx"
    _praca_sintetica(memoria)

    with pytest.raises(ValueError):
        build_seed_packet(memoria=f"{memoria}:MEMÓRIA DE CÁLCULO", worksite_key="Praça Passada Sul")


def test_aba_inexistente_recusa_fechado_e_nomeado(tmp_path: Path) -> None:
    memoria = tmp_path / "praca-passada.xlsx"
    _praca_sintetica(memoria)

    with pytest.raises(ValuationValidationError) as excinfo:
        build_seed_packet(memoria=f"{memoria}:ABA QUE NÃO EXISTE", worksite_key="praca-a")

    assert excinfo.value.code == "PRECEDENT_MEMORIA_SHEET_NOT_FOUND"


def test_run_precedent_extract_escreve_um_pacote_relegivel(tmp_path: Path) -> None:
    """O arquivo escrito volta a validar contra o contrato — é ele que a rota vai receber."""
    memoria = tmp_path / "praca-passada.xlsx"
    _praca_sintetica(memoria)
    output = tmp_path / "saida" / "pacote.json"

    packet = run_precedent_extract(
        memoria=f"{memoria}:MEMÓRIA DE CÁLCULO",
        worksite_key="praca-passada-sul",
        output_path=output,
        price_source=_CATALOG_SHA,
    )

    relido = PrecedentSeedPacket.model_validate(json.loads(output.read_text(encoding="utf-8")))
    assert relido == packet


def test_cli_precedent_extract_nao_imprime_rotulo_de_legenda(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """O resumo do terminal traz contagens, e não rótulo.

    O rótulo é texto de cliente. Ele vive no pacote, dentro de `--output` (ignorado pelo Git,
    retenção local de 7 dias) — não precisa passear pelo terminal nem por log nenhum.
    """
    memoria = tmp_path / "praca-passada.xlsx"
    _praca_sintetica(memoria)
    output = tmp_path / "pacote.json"

    exit_code = main(
        [
            "precedent-extract",
            "--memoria",
            f"{memoria}:MEMÓRIA DE CÁLCULO",
            "--worksite",
            "praca-passada-sul",
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "blocos: 4 rotulados=3 sem_rotulo=1 linhas_sem_rotulo=[7]" in captured.out
    assert "PISO EM CONCRETO" not in captured.out
    assert output.is_file()


def test_cli_precedent_extract_recusa_fechado_com_codigo_estavel(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "pacote.json"

    exit_code = main(
        [
            "precedent-extract",
            "--memoria",
            "sem-separador",
            "--worksite",
            "praca-passada-sul",
            "--output",
            str(output),
        ]
    )

    assert exit_code == 2
    assert json.loads(capsys.readouterr().out)["refused"] == "PRECEDENT_MEMORIA_SPEC_INVALID"
    assert not output.exists()
