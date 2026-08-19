#!/usr/bin/env bash
# Cria (ou recria) o usuário de fumaça autenticada da homologação: `smoke.hml`.
#
# Ele existe para UM propósito: o passo "Fumaça autenticada" da esteira atravessar o login
# real e provar a sessão com `GET /v1/projects` (incidente de 2026-08-19 — nenhuma fumaça
# de status pega defeito que só existe depois da credencial). Vive no tenant
# `tenant-smoke-hml`, isolado de qualquer dado real, com e-mail e nome preenchidos (perfil
# incompleto dispara o VERIFY_PROFILE do Keycloak 26 e trava o login — a mesma lição, duas
# vezes) e papel `engineer`.
#
# Execução é ato do operador (lê segredo): o script NUNCA imprime senhas. A senha do
# usuário é gerada aqui, gravada no Secret Manager (croquito-hml-smoke-password) e é dela
# que o secret CROQUITO_HML_SMOKE_PASSWORD do GitHub deve ser espelhado.
#
# Idempotente: usuário existente é atualizado (atributos, papéis e senha nova), não
# duplicado. Rode de novo depois de qualquer recriação de realm.
set -euo pipefail

PROJETO="biahflow-hml"
BASE="https://croquito-hml.biahflow.ai/auth"
REALM="croquito"
USUARIO="smoke.hml"
TENANT="tenant-smoke-hml"
PAPEL="engineer"
SEGREDO_ADMIN="croquito-hml-kc-bootstrap-admin-password"
SEGREDO_SMOKE="croquito-hml-smoke-password"

echo "· token de admin (realm master)"
ADMIN_PW=$(gcloud secrets versions access latest --secret "$SEGREDO_ADMIN" --project "$PROJETO")
TOKEN=$(curl -fsS -X POST "$BASE/realms/master/protocol/openid-connect/token" \
  -d grant_type=password -d client_id=admin-cli -d username=admin \
  --data-urlencode "password=$ADMIN_PW" | python3 -c "import json,sys; print(json.load(sys.stdin)['access_token'])")

echo "· senha nova do usuário de fumaça (gerada, nunca impressa)"
SMOKE_PW=$(python3 -c "import secrets; print(secrets.token_urlsafe(24))")

corpo() {
  python3 - "$1" <<'EOF'
import json
import sys

print(json.dumps({
    "username": "smoke.hml",
    "enabled": True,
    "email": "smoke.hml@example.invalid",
    "firstName": "Fumaca",
    "lastName": "Autenticada",
    "emailVerified": True,
    "attributes": {"tenant_id": [sys.argv[1]]},
}))
EOF
}

EXISTENTE=$(curl -fsS "$BASE/admin/realms/$REALM/users?username=$USUARIO&exact=true" \
  -H "Authorization: Bearer $TOKEN" | python3 -c "import json,sys; u=json.load(sys.stdin); print(u[0]['id'] if u else '')")

if [ -z "$EXISTENTE" ]; then
  echo "· criando $USUARIO"
  corpo "$TENANT" | curl -fsS -o /dev/null -X POST "$BASE/admin/realms/$REALM/users" \
    -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d @-
  EXISTENTE=$(curl -fsS "$BASE/admin/realms/$REALM/users?username=$USUARIO&exact=true" \
    -H "Authorization: Bearer $TOKEN" | python3 -c "import json,sys; print(json.load(sys.stdin)[0]['id'])")
else
  echo "· $USUARIO já existe; atualizando atributos"
  corpo "$TENANT" | curl -fsS -o /dev/null -X PUT "$BASE/admin/realms/$REALM/users/$EXISTENTE" \
    -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d @-
fi

echo "· senha permanente"
printf '{"type":"password","value":"%s","temporary":false}' "$SMOKE_PW" |
  curl -fsS -o /dev/null -X PUT "$BASE/admin/realms/$REALM/users/$EXISTENTE/reset-password" \
    -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d @-

echo "· papel $PAPEL"
PAPEL_JSON=$(curl -fsS "$BASE/admin/realms/$REALM/roles/$PAPEL" -H "Authorization: Bearer $TOKEN")
printf '[%s]' "$PAPEL_JSON" |
  curl -fsS -o /dev/null -X POST "$BASE/admin/realms/$REALM/users/$EXISTENTE/role-mappings/realm" \
    -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d @-

echo "· gravando a senha no Secret Manager ($SEGREDO_SMOKE)"
if ! gcloud secrets describe "$SEGREDO_SMOKE" --project "$PROJETO" >/dev/null 2>&1; then
  gcloud secrets create "$SEGREDO_SMOKE" --project "$PROJETO" --replication-policy automatic
fi
printf '%s' "$SMOKE_PW" | gcloud secrets versions add "$SEGREDO_SMOKE" --project "$PROJETO" --data-file=-

cat <<'FIM'

Pronto. Falta UM passo manual, fora deste script:
  espelhar a senha no GitHub → Settings → Secrets → Actions →
  CROQUITO_HML_SMOKE_PASSWORD  (valor: o segredo croquito-hml-smoke-password do
  Secret Manager — leia pelo console para não imprimir em terminal compartilhado).
FIM
