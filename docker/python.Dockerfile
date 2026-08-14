# syntax=docker/dockerfile:1

# Imagem única dos processos Python: API, worker (push do Pub/Sub), servidor de medição
# e o job de inicialização de banco. Os quatro rodam o MESMO código — o que muda entre
# eles é `command`/`args` no deploy, não o conteúdo do container. Quatro imagens seriam
# quatro versões possíveis do mesmo pacote no ar ao mesmo tempo, e a pergunta "qual
# revisão do worker corresponde a esta revisão da API?" deixaria de ter resposta trivial.
#
# Sem `CMD`: a imagem não escolhe processo. Quem escolhe é o deploy
# (`.github/workflows/deploy-hml.yml`), e subir esta imagem sem comando é erro visível.

# ---------------------------------------------------------------------------
# Estágio de build: resolve o lock e materializa o venv em /app/.venv
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

# uv pinado por versão (nunca `latest`): a esteira precisa produzir a mesma resolução
# amanhã. A versão é a mesma usada no desenvolvimento local.
COPY --from=ghcr.io/astral-sh/uv:0.11.17 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    # O interpretador é o da imagem base; baixar outro criaria uma segunda versão de
    # Python dentro da mesma imagem.
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

# Camada das dependências primeiro, sem o projeto: mudança em `packages/`/`services/`
# não invalida o download e a compilação de opencv, numpy, matplotlib e pymupdf.
# `--frozen` recusa qualquer resolução nova — o `uv.lock` versionado é a verdade, e é
# ele que garante que `google-cloud-pubsub` (transporte de fila em GCP) está instalável.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --no-editable

# `README.md` entra porque `pyproject.toml` o declara como `readme`: sem ele o build do
# pacote falha. `scripts/` não vai para o runtime; fica aqui para o contexto do projeto.
COPY README.md ./
COPY packages/ packages/
COPY services/ services/
COPY scripts/ scripts/

# `--no-editable` instala os quatro pacotes como cópia dentro do venv. Com editable, o
# runtime precisaria carregar `packages/` e `services/` no mesmo caminho absoluto, e um
# `.pth` apontando para diretório inexistente falha só na hora do import.
RUN uv sync --frozen --no-dev --no-editable

# ---------------------------------------------------------------------------
# Runtime: só o venv, usuário sem privilégio
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

# `libglib2.0-0` é cinto de segurança, e a medição está registrada: no
# `opencv-python-headless` 4.14 as bibliotecas nativas vêm embutidas na roda
# (`opencv_python_headless.libs/`), nenhum `.so` do pacote declara `libgthread-2.0` e o
# import passa sem ela — foi verificado nas duas arquiteturas. A dependência de glib
# existiu em versões anteriores do pacote, e mantê-la custa ~10 MB contra o risco de um
# bump de versão voltar a exigi-la num ambiente onde o erro só aparece em produção.
#
# Quem prova o contrário a qualquer momento é o smoke de import no fim deste estágio: se
# faltar biblioteca de sistema (esta ou `libgomp1`), o build falha aqui.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Usuário sem privilégio com HOME próprio e gravável: matplotlib, fontconfig e qualquer
# biblioteca que queira cache escrevem em HOME, e HOME apontando para diretório de root
# vira warning na melhor hipótese e falha na pior.
RUN useradd --create-home --home-dir /home/croquito --uid 10001 --shell /usr/sbin/nologin croquito

COPY --from=builder --chown=croquito:croquito /app/.venv /app/.venv

ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # Cloud Run dá apenas memória como disco gravável; o cache do matplotlib mora nela.
    MPLCONFIGDIR=/tmp/matplotlib

WORKDIR /app
USER croquito

# Smoke de import no build: as quatro bibliotecas com dependência nativa (visão, PDF,
# CAD e geometria). Falhar aqui é barato; falhar no primeiro job real não é.
RUN python -c "import cv2, fitz, ezdxf, shapely; print('imports nativos ok')"
