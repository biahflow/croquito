# ADR-0011: Identidade OIDC portável com Keycloak inicial

Status: Accepted  
Responsável: Architecture / Security  
Data: 2026-08-10  
Supersedes: componente de identidade do ADR-0002

## Contexto

O produto precisa de convite, login, papéis e auditoria de aprovação técnica, mas
não deve acoplar a regra de domínio a Cognito ou a outro provedor de nuvem.

## Decisão

Usar OpenID Connect com Authorization Code + PKCE no browser e validação JWT por
`issuer`, JWKS e `audience` na API. Keycloak é o provedor inicial: roda em Docker
local e pode ser hospedado fora ou dentro da AWS. A API deriva `tenant_id`, `sub`
e papéis do token; o cliente não fornece esses valores.

Papéis iniciais: `engineer` aprova tecnicamente; `cad_operator` revisa sem
aprovar; `tenant_admin` administra membros; `platform_operator` administra
entitlements contratuais fora do tenant. O vínculo profissional é atribuído pelo
administrador do tenant neste MVP.

## Consequências

- Trocar Keycloak por Cognito, Auth0 ou outro IdP OIDC não altera o domínio.
- Operação do Keycloak passa a ser responsabilidade explícita de staging/produção.
- JWT de teste existe apenas quando habilitado na configuração de teste; não é
  uma rota de autenticação de produção.
