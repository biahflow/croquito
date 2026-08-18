"""Fumaça da borda pública de homologação.

Só HTTP, sem credencial, sem `gcloud`: as quatro rotas passam pelo nginx, que é o único
serviço público, e provam que o proxy same-origin e as duas SPAs estão de pé.

Cada rota é verificada pelo **conteúdo**, não só pelo código de status. A razão está no
incidente de 2026-08-14/18: o serviço da API ficou servindo o container de exemplo do Cloud
Run, que responde `200` em quase todo caminho — uma fumaça que olhasse só o status teria
dito "verde" durante os quatro dias em que a sessão autenticada não subia.

Só usa a biblioteca padrão, de propósito: é o que permite a mesma fumaça rodar no runner do
deploy sem instalar nada e na máquina do operador sem ambiente montado.

Uso:

    make smoke-hml
    make smoke-hml BASE_URL=https://outro-host

Sai com código 1 se qualquer verificação falhar; nada aqui escreve em ambiente nenhum.
"""

from __future__ import annotations

import argparse
import json
import ssl
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE_URL_PADRAO = "https://croquito-hml.biahflow.ai"
REALM = "croquito"
TIMEOUT_S = 15.0


class VerificacaoFalhou(RuntimeError):
    """A rota respondeu, mas não o que a homologação precisa que ela responda."""


@dataclass(frozen=True)
class Resposta:
    status: int
    corpo: str


@dataclass(frozen=True)
class Verificacao:
    """Uma rota da borda e o que precisa ser verdade sobre a resposta dela."""

    rota: str
    o_que_prova: str
    conferir: Callable[[Resposta], None]


@lru_cache(maxsize=1)
def contexto_ssl() -> ssl.SSLContext:
    """Confiança de TLS que funciona nos dois lugares onde esta fumaça roda.

    O Python que não vem do sistema (o do `uv`, o do python.org) não enxerga as âncoras do
    macOS e recusa qualquer HTTPS — o mesmo tropeço que o runbook do aceite já registra como
    `SSL_CERT_FILE`. Quando `certifi` está por perto, ele resolve; no runner Linux do deploy
    o padrão já funciona, e é para lá que o fallback aponta.
    """
    try:
        import certifi
    except ImportError:
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=certifi.where())


def buscar(url: str) -> Resposta:
    """GET simples. Status de erro é resposta, não exceção — o corpo dele também informa."""
    requisicao = Request(url, headers={"User-Agent": "croquito-smoke-hml"})
    try:
        with urlopen(requisicao, timeout=TIMEOUT_S, context=contexto_ssl()) as resposta:
            corpo = resposta.read().decode("utf-8", errors="replace")
            return Resposta(status=resposta.status, corpo=corpo)
    except HTTPError as erro:
        return Resposta(status=erro.code, corpo=erro.read().decode("utf-8", errors="replace"))


def _exigir_status_200(resposta: Resposta) -> None:
    if resposta.status != 200:
        raise VerificacaoFalhou(f"status {resposta.status}")


def _json_ou_falha(resposta: Resposta, de_quem: str) -> dict[str, object]:
    try:
        corpo = json.loads(resposta.corpo)
    except json.JSONDecodeError:
        linhas = resposta.corpo.strip().splitlines()[:1]
        trecho = linhas[0][:80] if linhas else "(vazio)"
        raise VerificacaoFalhou(
            f"corpo não é JSON — quem responde não é {de_quem}: {trecho!r}"
        ) from None
    if not isinstance(corpo, dict):
        raise VerificacaoFalhou(f"corpo JSON não é objeto: {type(corpo).__name__}")
    return corpo


def conferir_health(resposta: Resposta) -> None:
    """A API precisa responder o próprio corpo de health, não uma página qualquer."""
    _exigir_status_200(resposta)
    corpo = _json_ou_falha(resposta, "a API")
    if corpo.get("status") != "ok":
        raise VerificacaoFalhou(f"health sem status ok: {corpo!r}")


def conferir_descoberta_oidc(issuer_base: str) -> Callable[[Resposta], None]:
    """O discovery precisa anunciar o issuer da borda pública — issuer errado quebra o login.

    O issuer é o que o Keycloak anuncia (`KC_HOSTNAME`), e não o host por onde a requisição
    entrou: testar pela URL `run.app` do serviço é legítimo e o issuer continua sendo o
    público. Por isso ele é parâmetro próprio, e não derivado da URL consultada.
    """

    def conferir(resposta: Resposta) -> None:
        _exigir_status_200(resposta)
        corpo = _json_ou_falha(resposta, "o Keycloak")
        esperado = f"{issuer_base}/auth/realms/{REALM}"
        if corpo.get("issuer") != esperado:
            raise VerificacaoFalhou(f"issuer {corpo.get('issuer')!r}, esperado {esperado!r}")

    return conferir


def conferir_spa(nome: str) -> Callable[[Resposta], None]:
    """A SPA precisa devolver o próprio index, e não o 404 do catch-all do nginx."""

    def conferir(resposta: Resposta) -> None:
        _exigir_status_200(resposta)
        if f"/{nome}/assets/" not in resposta.corpo:
            raise VerificacaoFalhou(f"a resposta não referencia /{nome}/assets/")

    return conferir


def montar_verificacoes(issuer_base: str) -> list[Verificacao]:
    return [
        Verificacao(
            rota="/revisao/",
            o_que_prova="SPA da revisão publicada pelo nginx",
            conferir=conferir_spa("revisao"),
        ),
        Verificacao(
            rota="/medicao/",
            o_que_prova="SPA da medição publicada pelo nginx",
            conferir=conferir_spa("medicao"),
        ),
        Verificacao(
            rota="/api/healthz",
            o_que_prova="API viva atrás do proxy same-origin",
            conferir=conferir_health,
        ),
        Verificacao(
            rota=f"/auth/realms/{REALM}/.well-known/openid-configuration",
            o_que_prova="sessão autenticada: Keycloak de pé com o issuer da borda pública",
            conferir=conferir_descoberta_oidc(issuer_base),
        ),
    ]


def executar(
    base_url: str,
    issuer_base: str,
    tentativas: int,
    espera_s: float,
) -> list[tuple[Verificacao, str]]:
    """Roda todas as verificações e devolve as que falharam, com o motivo.

    Não para na primeira falha de propósito: quando o ambiente cai, saber que *duas* coisas
    caíram — e quais — vale mais do que descobrir uma por rodada.
    """
    falhas: list[tuple[Verificacao, str]] = []

    for verificacao in montar_verificacoes(issuer_base):
        motivo = ""
        for tentativa in range(1, tentativas + 1):
            try:
                verificacao.conferir(buscar(f"{base_url}{verificacao.rota}"))
            except (VerificacaoFalhou, URLError, TimeoutError) as erro:
                motivo = str(erro) or type(erro).__name__
                if tentativa < tentativas:
                    print(f"  tentativa {tentativa} em {verificacao.rota}: {motivo}")
                    time.sleep(espera_s)
                continue
            motivo = ""
            break

        if motivo:
            falhas.append((verificacao, motivo))
            print(f"FALHA  {verificacao.rota} — {motivo}")
        else:
            print(f"ok     {verificacao.rota} — {verificacao.o_que_prova}")

    return falhas


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=BASE_URL_PADRAO, help="Borda pública a verificar.")
    parser.add_argument(
        "--issuer-base",
        default=None,
        help=(
            "Base do issuer que o Keycloak deve anunciar. Só difere de --base-url quando se "
            "consulta o serviço pela URL run.app: o issuer segue sendo o público."
        ),
    )
    parser.add_argument(
        "--tentativas",
        type=int,
        default=5,
        help="Tentativas por rota. O Keycloak escala a zero e nasce em dezenas de segundos.",
    )
    parser.add_argument("--espera", type=float, default=10.0, help="Segundos entre tentativas.")
    args = parser.parse_args()

    base_url = str(args.base_url).rstrip("/")
    issuer_base = str(args.issuer_base or BASE_URL_PADRAO).rstrip("/")
    print(f"Fumaça da borda: {base_url} (issuer esperado sob {issuer_base})")

    falhas = executar(base_url, issuer_base, int(args.tentativas), float(args.espera))

    if falhas:
        print(f"\n{len(falhas)} verificação(ões) falharam:")
        for verificacao, motivo in falhas:
            print(f"  {verificacao.rota}: {motivo} (prova ausente: {verificacao.o_que_prova})")
        return 1

    print("\nBorda de homologação íntegra.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
