"""Gate de contrato da API (F-005): snapshot de OpenAPI e paridade com o API Contract.

Duas divergências são detectadas por este gate:

1. O documento OpenAPI gerado pela aplicação diverge do snapshot versionado
   (`tests/api/openapi.snapshot.json`) — mudança de superfície não revisada/regenerada.
2. A superfície `/v1` real diverge do que `docs/architecture/API_CONTRACT.md` documenta —
   rota exposta e não documentada, rota documentada e não exposta, ou rota ainda marcada
   "Estado: decidido, não implementado." que já foi exposta.

Não há precedente de teste que leia arquivos de `docs/` a partir de `tests/`. A raiz do
repositório é derivada de `__file__` (nunca do diretório de trabalho do processo), porque
`pytest` pode ser invocado de qualquer lugar e `testpaths = ["tests"]` não garante CWD na
raiz.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from croquito_api.openapi_export import snapshot_text

# tests/api/test_openapi_contract.py -> tests/api -> tests -> raiz do repositório.
REPO_ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_PATH = REPO_ROOT / "tests" / "api" / "openapi.snapshot.json"
API_CONTRACT_PATH = REPO_ROOT / "docs" / "architecture" / "API_CONTRACT.md"

_ROUTE_METHODS = "GET|POST|PUT|DELETE|PATCH"
_INLINE_ROUTE_PATTERN = re.compile(rf"`({_ROUTE_METHODS}) (/[^`]+)`")
# Os campos de operação do Path Item Object da spec OpenAPI 3.1, e só eles. Deliberadamente
# mais largo que `_ROUTE_METHODS` (que é a regex de leitura do Markdown do API Contract): aqui
# um método a menos faria uma operação real sumir do gate em silêncio, que é pior que uma
# entrada a mais numa lista fechada pela spec.
_HTTP_METHODS = frozenset({"get", "put", "post", "delete", "options", "head", "patch", "trace"})
_FENCED_CODE_BLOCK_PATTERN = re.compile(r"```.*?```", re.DOTALL)
_SECTION_HEADING_PATTERN = re.compile(r"(?m)^## .*$")
_PENDING_MARKER = "**Estado: decidido, não implementado.**"


def documented_routes(markdown: str) -> dict[str, str]:
    """Extrai rota -> estado (`VIGENTE`/`PENDENTE`) do API Contract.

    Não ancora em heading de rota: o documento mistura `### \\`POST /v1/jobs\\``
    (a maioria), bullet (`- \\`GET /v1/meta\\`: ...`) e menção inline em prosa
    (ex.: `API_CONTRACT.md:258,266`). Ancorar em heading perderia esses dois últimos
    formatos. Em vez disso, captura qualquer span de código inline (crase simples) que
    case "MÉTODO /caminho".
    """
    without_fenced_blocks = _FENCED_CODE_BLOCK_PATTERN.sub("", markdown)
    mentions: dict[str, list[str]] = {}
    for section in _SECTION_HEADING_PATTERN.split(without_fenced_blocks):
        state = "PENDENTE" if _PENDING_MARKER in section else "VIGENTE"
        for method, path in _INLINE_ROUTE_PATTERN.findall(section):
            if not path.startswith("/v1"):
                continue
            mentions.setdefault(f"{method} {path}", []).append(state)
    # Uma rota é PENDENTE só quando TODAS as suas menções estão em seção pendente. A mesma
    # rota pode aparecer em seções de estado diferente — caso real até a publicação da
    # medição em T12: `POST /v1/uploads/presign` é documentada em "Uploads" (vigente) e era
    # citada de novo dentro de "Medição de obra" (então pendente), porque a prancha da
    # medição sobe por ela. Decidir pela primeira menção teria dado o resultado certo só
    # porque "Uploads" vem antes no arquivo: reordenar as seções acusaria uma rota exposta
    # como pendente, erro inventado numa rota correta. Gate que falha sem motivo é gate que
    # alguém desliga. Ver `test_rota_citada_em_secao_pendente_e_em_secao_vigente_continua_vigente`.
    return {
        route: "PENDENTE" if all(state == "PENDENTE" for state in states) else "VIGENTE"
        for route, states in mentions.items()
    }


def _operations(document: dict[str, object]) -> dict[str, object]:
    """Devolve `"MÉTODO /caminho"` -> objeto de operação, sem filtrar por prefixo.

    Só campos de operação entram. Um Path Item Object também pode carregar `parameters`,
    `summary`, `description`, `servers` e `$ref`, que são metadados do caminho e não operações;
    tratá-los como método produziria mensagem de falha do tipo `PARAMETERS /v1/x: definição
    divergente`, que engana quem lê a falha sem abrir este arquivo.
    """
    paths = document["paths"]
    if not isinstance(paths, dict):
        raise TypeError("document['paths'] deveria ser um objeto OpenAPI de rotas.")
    operations: dict[str, object] = {}
    for path, methods in paths.items():
        if not isinstance(path, str) or not isinstance(methods, dict):
            continue
        for method, operation in methods.items():
            if isinstance(method, str) and method.lower() in _HTTP_METHODS:
                operations[f"{method.upper()} {path}"] = operation
    return operations


def exposed_routes(document: dict[str, object]) -> set[str]:
    """Lê `document["paths"]` e devolve `"MÉTODO /caminho"` em maiúsculo, filtrado a `/v1`."""
    return {route for route in _operations(document) if route.split(" ", 1)[1].startswith("/v1")}


def snapshot_errors(gerado: str, versionado: str) -> list[str]:
    """Compara documento gerado e snapshot versionado nomeando método e caminho do que mudou.

    O critério de aceite de F-005 recusa mensagem que só diga "snapshot divergente": quem vê a
    falha precisa saber o que mudou sem abrir o teste nem fazer diff de 157 KB de JSON à mão.
    Por isso a comparação é por operação, e não texto contra texto.
    """
    if gerado == versionado:
        return []

    operacoes_geradas = _operations(json.loads(gerado))
    operacoes_versionadas = _operations(json.loads(versionado))
    erros: list[str] = []

    for route in operacoes_geradas.keys() - operacoes_versionadas.keys():
        erros.append(f"{route}: exposta pela aplicação e ausente do snapshot versionado.")
    for route in operacoes_versionadas.keys() - operacoes_geradas.keys():
        erros.append(f"{route}: presente no snapshot versionado e não exposta pela aplicação.")
    for route in operacoes_geradas.keys() & operacoes_versionadas.keys():
        if operacoes_geradas[route] != operacoes_versionadas[route]:
            erros.append(
                f"{route}: definição divergente entre a aplicação e o snapshot versionado."
            )

    if not erros:
        # Divergência que nenhuma operação explica: versão da API, `components`, `info`, ou um
        # campo de nível de caminho dentro de `paths` (`parameters`, `summary`). Não há método e
        # caminho para nomear, então nomeia a chave de topo que mudou — inclusive quando essa
        # chave é `paths`, o que é verdadeiro e não se contradiz.
        documento_gerado = json.loads(gerado)
        documento_versionado = json.loads(versionado)
        chaves = sorted(
            chave
            for chave in documento_gerado.keys() | documento_versionado.keys()
            if documento_gerado.get(chave) != documento_versionado.get(chave)
        )
        erros.append(
            "documento OpenAPI divergente sem diferença de operação, na(s) chave(s): "
            + ", ".join(chaves)
        )

    return sorted(erros)


def parity_errors(exposed: set[str], documented: dict[str, str]) -> list[str]:
    """Três regras de paridade; cada mensagem nomeia método e caminho, nunca só 'diverge'."""
    errors: list[str] = []

    for route in exposed:
        if route not in documented:
            errors.append(
                f"{route}: exposta pela aplicação e ausente do contrato — documente-a em "
                "docs/architecture/API_CONTRACT.md."
            )

    for route, state in documented.items():
        if state == "VIGENTE" and route not in exposed:
            errors.append(
                f"{route}: documentada como vigente em docs/architecture/API_CONTRACT.md, "
                "mas a aplicação não a expõe."
            )
        elif state == "PENDENTE" and route in exposed:
            # Esta regra é o que obriga F-003 a atualizar o API Contract no mesmo diff em
            # que implementar a migração da medição: assim que uma rota `/v1/valuation-*`
            # passar a ser exposta pela aplicação, a seção "Medição de obra" deixa de poder
            # carregar o aviso "Estado: decidido, não implementado." — o teste reprova até
            # o aviso ser removido, não só até o código existir.
            errors.append(
                f"{route}: exposta pela aplicação mas ainda marcada PENDENTE em "
                "docs/architecture/API_CONTRACT.md — remova o aviso "
                '"Estado: decidido, não implementado." da seção correspondente.'
            )

    return sorted(errors)


def _route_of(error_message: str) -> str:
    return error_message.split(": ", 1)[0]


# Achados de baseline: as 5 divergências entre a aplicação e o API Contract que já existiam
# quando este gate foi criado (F-005, 2026-08-17). Congeladas por decisão humana explícita —
# ver docs/features/F-005-openapi-contract-test/evidence.md — corrigi-las (em código ou em
# documentação) é trabalho próprio, com decisão humana sobre qual lado está errado em cada
# caso. Esta lista SÓ PODE ENCOLHER: uma chave que deixou de corresponder a uma divergência
# real é dívida silenciosa e reprova test_excecao_de_baseline_que_deixou_de_existir_reprova;
# adicionar uma chave nova para silenciar uma falha nova nunca é uso válido desta constante.
BASELINE: dict[str, str] = {
    "GET /v1/projects": (
        "exposta em services/api/src/croquito_api/main.py:3232, nunca documentada."
    ),
    "POST /v1/jobs/{job_id}/review/dimensions": (
        "exposta em services/api/src/croquito_api/main.py:2965, nunca documentada."
    ),
    "POST /v1/jobs/{job_id}/review/notes": (
        "exposta em services/api/src/croquito_api/main.py:3105, nunca documentada."
    ),
    "DELETE /v1/jobs/{job_id}": (
        "documentada em docs/architecture/API_CONTRACT.md:89, inexistente na aplicação."
    ),
    "POST /v1/jobs/{job_id}/regions/{region_id}/reanalyze": (
        "documentada em docs/architecture/API_CONTRACT.md:498, inexistente na aplicação."
    ),
}


def test_o_snapshot_versionado_descreve_a_superficie_atual() -> None:
    erros = snapshot_errors(snapshot_text(), SNAPSHOT_PATH.read_text(encoding="utf-8"))

    assert erros == [], (
        "O documento OpenAPI gerado agora diverge do snapshot versionado em "
        f"{SNAPSHOT_PATH.relative_to(REPO_ROOT)}. Se a mudança na superfície /v1 for "
        "intencional, regenere com `make openapi-snapshot` e revise o diff produzido antes "
        "de commitar.\n" + "\n".join(erros)
    )


def test_documento_alterado_reprova_contra_o_snapshot() -> None:
    """Direção oposta do teste anterior, sobre a mesma função — não sobre o `assert` do Python.

    Usa texto sintético: não toca `tests/api/openapi.snapshot.json`. Cobre as três formas de
    divergência (rota nova, rota sumida, definição mudada) e exige que cada mensagem nomeie
    método e caminho.
    """
    versionado = json.dumps(
        {
            "openapi": "3.1.0",
            "paths": {
                "/v1/sumida": {"get": {"summary": "some no gerado"}},
                "/v1/estavel": {"get": {"summary": "igual nos dois"}},
                "/v1/mudada": {"post": {"summary": "antes"}},
            },
        }
    )
    gerado = json.dumps(
        {
            "openapi": "3.1.0",
            "paths": {
                "/v1/nova": {"get": {"summary": "só no gerado"}},
                "/v1/estavel": {"get": {"summary": "igual nos dois"}},
                "/v1/mudada": {"post": {"summary": "depois"}},
            },
        }
    )

    erros = snapshot_errors(gerado, versionado)

    assert erros == [
        "GET /v1/nova: exposta pela aplicação e ausente do snapshot versionado.",
        "GET /v1/sumida: presente no snapshot versionado e não exposta pela aplicação.",
        "POST /v1/mudada: definição divergente entre a aplicação e o snapshot versionado.",
    ]
    assert "GET /v1/estavel" not in " ".join(erros)
    # A outra direção, em forma pura: documentos idênticos não produzem erro.
    assert snapshot_errors(versionado, versionado) == []


def test_divergencia_fora_de_paths_nomeia_a_chave_que_mudou() -> None:
    """Mudar a versão da API não muda rota nenhuma; a falha ainda precisa dizer o que mudou."""
    versionado = json.dumps({"openapi": "3.1.0", "info": {"version": "0.2.0"}, "paths": {}})
    gerado = json.dumps({"openapi": "3.1.0", "info": {"version": "0.3.0"}, "paths": {}})

    assert snapshot_errors(gerado, versionado) == [
        "documento OpenAPI divergente sem diferença de operação, na(s) chave(s): info"
    ]


def test_campo_de_nivel_de_caminho_nao_e_lido_como_metodo() -> None:
    """`parameters`/`summary` são metadados do caminho, não operações.

    Sem o filtro por `_HTTP_METHODS`, este documento renderia mensagens como
    `PARAMETERS /v1/exemplo: definição divergente`, que manda o leitor procurar um método HTTP
    que não existe.
    """
    versionado = json.dumps(
        {
            "openapi": "3.1.0",
            "paths": {
                "/v1/exemplo": {
                    "summary": "antes",
                    "parameters": [{"name": "tenant", "in": "header"}],
                    "get": {"summary": "igual nos dois"},
                }
            },
        }
    )
    gerado = json.dumps(
        {
            "openapi": "3.1.0",
            "paths": {
                "/v1/exemplo": {
                    "summary": "depois",
                    "parameters": [],
                    "get": {"summary": "igual nos dois"},
                }
            },
        }
    )

    erros = snapshot_errors(gerado, versionado)

    # A operação é idêntica nos dois lados, então nada é imputado a `GET /v1/exemplo`; a
    # divergência real (fora de qualquer operação) continua sendo acusada, nomeando `paths`.
    assert erros == [
        "documento OpenAPI divergente sem diferença de operação, na(s) chave(s): paths"
    ]
    assert "PARAMETERS" not in " ".join(erros)
    assert "SUMMARY" not in " ".join(erros)


def test_toda_rota_exposta_esta_no_contrato() -> None:
    documento = json.loads(snapshot_text())
    exposed = exposed_routes(documento)
    documented = documented_routes(API_CONTRACT_PATH.read_text(encoding="utf-8"))

    erros = parity_errors(exposed, documented)
    erros_fora_do_baseline = [erro for erro in erros if _route_of(erro) not in BASELINE]

    assert erros_fora_do_baseline == [], (
        "Divergência(s) nova(s) entre a aplicação e "
        f"{API_CONTRACT_PATH.relative_to(REPO_ROOT)}:\n" + "\n".join(erros_fora_do_baseline)
    )


def test_rota_exposta_fora_do_contrato_reprova() -> None:
    exposed = {"GET /v1/exemplo"}
    documented: dict[str, str] = {}

    erros = parity_errors(exposed, documented)

    assert erros == [
        "GET /v1/exemplo: exposta pela aplicação e ausente do contrato — documente-a em "
        "docs/architecture/API_CONTRACT.md."
    ]


def test_rota_vigente_no_contrato_e_ausente_da_app_reprova() -> None:
    exposed: set[str] = set()
    documented = {"DELETE /v1/exemplo": "VIGENTE"}

    erros = parity_errors(exposed, documented)

    assert erros == [
        "DELETE /v1/exemplo: documentada como vigente em docs/architecture/API_CONTRACT.md, "
        "mas a aplicação não a expõe."
    ]


def test_secao_pendente_com_rota_ja_exposta_exige_remover_o_aviso() -> None:
    exposed = {"POST /v1/valuation-rounds"}
    documented = {"POST /v1/valuation-rounds": "PENDENTE"}

    erros = parity_errors(exposed, documented)

    assert erros == [
        "POST /v1/valuation-rounds: exposta pela aplicação mas ainda marcada PENDENTE em "
        "docs/architecture/API_CONTRACT.md — remova o aviso "
        '"Estado: decidido, não implementado." da seção correspondente.'
    ]


def test_rota_citada_em_secao_pendente_e_em_secao_vigente_continua_vigente() -> None:
    """Estado não pode depender da ordem das seções no arquivo.

    Teste do PARSER (`documented_routes`), não da medição: usa markdown sintético, não o
    documento real. Exemplo histórico (a seção "Medição de obra" já foi pendente, antes de
    T12): `POST /v1/uploads/presign` é documentada em "Uploads" e citada de novo dentro de
    uma seção pendente, porque a prancha da medição sobe por ela. Tratá-la como pendente por
    causa dessa segunda menção faria o gate acusar erro inventado numa rota correta.
    """
    markdown = (
        "## Medição de obra\n\n"
        f"> {_PENDING_MARKER} Nada aqui existe ainda.\n\n"
        "### `POST /v1/valuation-rounds`\n\n"
        "A prancha sobe por `POST /v1/uploads/presign`.\n\n"
        "## Uploads\n\n"
        "### `POST /v1/uploads/presign`\n"
    )

    documented = documented_routes(markdown)

    assert documented["POST /v1/uploads/presign"] == "VIGENTE"
    assert documented["POST /v1/valuation-rounds"] == "PENDENTE"
    # Com a rota exposta e vigente, e a pendente não exposta, nada diverge: nenhuma das três
    # regras dispara. Era exatamente aqui que a resolução por ordem inventaria uma falha.
    assert parity_errors({"POST /v1/uploads/presign"}, documented) == []


def test_excecao_de_baseline_que_deixou_de_existir_reprova() -> None:
    """Toda chave de `BASELINE` precisa corresponder a uma divergência real hoje.

    Uma exceção que deixou de ocorrer (porque a rota foi documentada, removida, ou a
    divergência foi corrigida por outro trabalho) é dívida silenciosa: continuaria mascarando
    qualquer NOVA divergência que reusasse a mesma chave.
    """
    documento = json.loads(snapshot_text())
    exposed = exposed_routes(documento)
    documented = documented_routes(API_CONTRACT_PATH.read_text(encoding="utf-8"))

    erros = parity_errors(exposed, documented)
    rotas_com_divergencia_real = {_route_of(erro) for erro in erros}

    obsoletas = sorted(chave for chave in BASELINE if chave not in rotas_com_divergencia_real)

    assert obsoletas == [], (
        "Exceção(ões) de BASELINE que deixaram de ser divergência real — remova de "
        "tests/api/test_openapi_contract.py: " + ", ".join(obsoletas)
    )


# As rotas de medição publicadas: as 18 do ADR-0028 (F-003, T12), mais a aprovação nominal e a
# exportação auditada do boletim (F-028), mais as quatro da praça de várias pranchas (F-046: a
# leitura da praça, a declaração de identidade, a promoção de folhas em lote e a extração em
# lote). Listadas explicitamente para que uma rota esquecida no futuro — em qualquer um dos dois
# lados — apareça como falha nomeada, e não como conjunto que encolheu em silêncio.
ROTAS_DE_MEDICAO: frozenset[str] = frozenset(
    {
        "POST /v1/valuation-rounds",
        "GET /v1/valuation-rounds",
        "GET /v1/valuation-rounds/{round_id}",
        "POST /v1/valuation-rounds/{round_id}/plate",
        "POST /v1/valuation-rounds/{round_id}/plates",
        "GET /v1/valuation-rounds/{round_id}/plate",
        "POST /v1/valuation-rounds/{round_id}/plate/extractions",
        "POST /v1/valuation-rounds/{round_id}/plates/extractions",
        "GET /v1/valuation-rounds/{round_id}/takeoff",
        "GET /v1/valuation-rounds/{round_id}/takeoff/overlay",
        "POST /v1/valuation-rounds/{round_id}/takeoff/decisions",
        "GET /v1/valuation-rounds/{round_id}/code-suggestions",
        "POST /v1/valuation-rounds/{round_id}/code-suggestions/recompute",
        "GET /v1/valuation-rounds/{round_id}/catalog/search",
        "GET /v1/valuation-rounds/{round_id}/code-assignments",
        "POST /v1/valuation-rounds/{round_id}/code-assignments/decisions",
        "POST /v1/valuation-rounds/{round_id}/code-assignments/closures",
        "POST /v1/valuation-rounds/{round_id}/code-assignments/revocations",
        "GET /v1/valuation-rounds/{round_id}/worksite",
        "POST /v1/valuation-rounds/{round_id}/worksite/identity-links",
        "POST /v1/valuation-rounds/{round_id}/worksite/identity-links/preview",
        "POST /v1/valuation-rounds/{round_id}/calc",
        "GET /v1/valuation-rounds/{round_id}/bulletin",
        "POST /v1/valuation-rounds/{round_id}/approve",
        "POST /v1/valuation-rounds/{round_id}/bulletin/export",
        "POST /v1/valuation-rounds/{round_id}/amendment-dossier",
        "GET /v1/valuation-rounds/{round_id}/amendment-dossier",
    }
)


def test_as_rotas_da_medicao_estao_todas_vigentes_e_expostas() -> None:
    """Ancora o estado de hoje: as rotas da medição estão todas publicadas.

    Inverte o que este teste afirmava antes da publicação (nenhuma rota exposta, todas
    PENDENTE no contrato): agora exige o oposto dos dois lados, nomeando cada uma das
    rotas, para que uma rota que suma de qualquer lado no futuro reprove nomeada — e não
    como contagem que encolheu em silêncio.

    Começou com as 18 rotas do ADR-0028 (F-003, T12); a F-028 acrescentou a aprovação
    nominal e a exportação auditada do boletim; a F-046, a leitura da praça, a declaração de
    identidade entre folhas, a promoção de folhas em lote e a extração em lote. A lista é
    FECHADA nos dois sentidos de propósito: publicar rota de medição sem passar por aqui
    reprova, que é como expor uma rota nova continua sendo ato deliberado e não efeito
    colateral.
    """
    documented = documented_routes(API_CONTRACT_PATH.read_text(encoding="utf-8"))
    rotas_de_medicao_no_contrato = {
        rota: estado
        for rota, estado in documented.items()
        if rota.split(" ", 1)[1].startswith("/v1/valuation-rounds")
    }

    documento = json.loads(snapshot_text())
    exposed = exposed_routes(documento)
    expostas_de_medicao = {
        rota for rota in exposed if rota.split(" ", 1)[1].startswith("/v1/valuation-rounds")
    }

    faltando_no_contrato = sorted(ROTAS_DE_MEDICAO - rotas_de_medicao_no_contrato.keys())
    assert faltando_no_contrato == [], (
        f"Rota(s) de medição ausentes do API Contract: {faltando_no_contrato}"
    )

    nao_vigentes = sorted(
        rota for rota in ROTAS_DE_MEDICAO if rotas_de_medicao_no_contrato.get(rota) != "VIGENTE"
    )
    assert nao_vigentes == [], (
        f"Rota(s) de medição não marcadas VIGENTE no API Contract: {nao_vigentes}"
    )

    faltando_exposicao = sorted(ROTAS_DE_MEDICAO - expostas_de_medicao)
    assert faltando_exposicao == [], (
        f"Rota(s) de medição documentadas mas não expostas pela aplicação: {faltando_exposicao}"
    )

    expostas_a_mais = sorted(expostas_de_medicao - ROTAS_DE_MEDICAO)
    assert expostas_a_mais == [], (
        "Rota(s) de medição expostas pela aplicação e ausentes desta lista fechada — "
        f"atualize ROTAS_DE_MEDICAO: {expostas_a_mais}"
    )
