# Keycloak do ambiente hospedado (`croquito-auth-hml`), servido em subpath `/auth`
# atrás do nginx do host público — same-origin com as duas SPAs e com a API.
#
# Duas fases porque `kc.sh build` fixa as opções de BUILD (banco, path relativo,
# health) numa imagem otimizada: o `start --optimized` do runtime não repete o build
# a cada frio, que é a diferença entre subir em segundos e subir em minutos num
# serviço que escala a partir do zero.
#
# O que NÃO está aqui, de propósito: hostname, credencial do banco e senha do admin
# de bootstrap. Isso é opção de runtime e mora no deploy
# (`.github/workflows/deploy-hml.yml`), lida de Secret Manager — segredo em camada de
# imagem fica legível para quem puxa a imagem, mesmo que o Dockerfile não o imprima.
FROM quay.io/keycloak/keycloak:26.2 AS builder

ENV KC_DB=postgres \
    KC_HEALTH_ENABLED=true \
    KC_HTTP_RELATIVE_PATH=/auth

RUN /opt/keycloak/bin/kc.sh build

FROM quay.io/keycloak/keycloak:26.2

COPY --from=builder /opt/keycloak/ /opt/keycloak/

# O realm é importado na subida e **não tem usuários**: nenhuma senha de fixture entra
# num ambiente hospedado. Usuário real nasce pelo console de administração, com o
# procedimento em `docs/operations/HML_KEYCLOAK.md`.
#
# `--import-realm` é idempotente na prática: a estratégia do importador de diretório é
# `IGNORE_EXISTING`, então subir uma revisão nova não sobrescreve usuário criado à mão.
#
# O arquivo TROCA DE NOME no caminho: o importador de diretório do Keycloak exige que o
# nome do arquivo seja `<realm>-realm.json` e recusa **subir o servidor** quando não é
# (`File name / realm name mismatch`, medido na 26.2). No repositório o nome precisa
# distinguir este realm do local (`croquito-realm.json`), então a distinção fica fora da
# imagem e o nome exigido entra aqui.
COPY croquito-hml-realm.json /opt/keycloak/data/import/croquito-realm.json

ENTRYPOINT ["/opt/keycloak/bin/kc.sh", "start", "--optimized", "--import-realm"]
