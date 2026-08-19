# T3 — BUILD REPORT

```text
BUILD REPORT

Status: BUILD_COMPLETE

Files changed:
  - apps/web/src/route.ts — kind `plataforma`, PLATFORM_PARAM, leitura por presença
    depois de `rodada` (precedência job > rodada > plataforma), `?plataforma=` em
    routeSearch; comentário de cabeçalho atualizado contrastando os três critérios que
    `/login` reprova e a plataforma cumpre. `entryRedirect` intocado.
  - apps/web/src/route.test.ts — round-trip de `?plataforma=`, precedência das três
    jornadas, valor ignorado, forma canônica na lista de round-trips.
  - apps/web/src/App.tsx — `JourneySwitch` exportado (terceiro botão só com o papel,
    ausente e não desabilitado); `GET /v1/me` uma vez por sessão com guarda de ref e
    fail-closed silencioso; papéis zerados quando a sessão cai; branch de render
    `route.kind === "plataforma"` montando `PlatformApp`.
  - apps/web/src/App.test.tsx — seletor com papel, sem papel, sem resposta de papéis e
    `aria-current` da jornada aberta.
  - apps/web/src/plataforma/api.ts (novo) — `fetchMe`, `listTenants`, `getEntitlement`,
    `setEntitlement` sobre `apiJson`; `entitlementBody` puro; `Idempotency-Key` por
    gesto; `PLATFORM_OPERATOR_ROLE`.
  - apps/web/src/plataforma/api.test.ts (novo) — oráculo no que saiu no `fetch`.
  - apps/web/src/plataforma/labels.ts (novo) — frases por código estável, estado por
    extenso em três palavras, `formatarInstante`, mensagem de rede.
  - apps/web/src/plataforma/labels.test.ts (novo).
  - apps/web/src/plataforma/PlatformApp.tsx (novo) — lista de tenants, ação por linha
    com confirmação nomeada, formulário de tenant novo com consulta de estado, erro
    persistente `role="alert"`, sucesso transitório.
  - apps/web/src/plataforma/PlatformApp.test.tsx (novo).

Validation executed:
  - baseline (antes de qualquer edição): `make check` OK; `make test` OK
    (pytest verde; vitest 29 arquivos / 529 testes).
  - final: `make check` OK (ruff, mypy strict, check_docs, drift de contratos,
    `tsc -b` + `vite build`, `terraform fmt -check`).
  - final: `make test` OK — pytest 1476 passed, 10 skipped, 47 warnings em 129,61s;
    vitest 32 arquivos / 566 testes (+37 nesta task), 0 falhas.

Validation skipped:
  - `npm --workspace @croquito/web run smoke:headless` — exige stack Docker local
    (Keycloak, API, web) e está declarado como local, nunca CI, no `apps/web/AGENTS.md`;
    não é portão do projeto nem foi pedido pelo Task Contract.

Unavailable capabilities: none

Assumptions:
  - As respostas da T2 foram lidas em `services/api/src/croquito_api/main.py`
    (`MeResponse` 261-264, `PlatformTenantResponse` 267-284,
    `AiProcessingEntitlementResponse` 253-258, rotas 2261-2414) e tipadas conforme —
    chaves em snake_case, `extra="forbid"`, `agreement_reference` obrigatório só na
    ativação (`422 AGREEMENT_REFERENCE_REQUIRED`).
  - O ambiente de teste do workspace web é `node` (vite.config.ts): não há DOM nem
    testing-library, então comportamento interativo não é alcançável por teste puro.
  - `apps/web/src/styles.css` está fora da lista WRITE do contrato, e é o único ponto
    que importa folhas de jornada — a tela reutiliza classes existentes.

Remaining risks:
  - Nenhum teste exercita o fluxo interativo completo (abrir ação → confirmar →
    releitura): o que está coberto é o transporte (`fetch` mockado) e o render estático
    dos estados. O caminho de ponta a ponta só é alcançável pelo smoke headless, que
    não tem cena de plataforma.
  - A tela reusa `.authenticated-workspace`, `.project-list`, `.upload-form`,
    `.app-alert` e `.app-toast`; ela é funcional e legível, mas não passou por revisão
    visual humana e não tem folha própria.
  - `GET /v1/me` é buscado uma vez por sessão: papel concedido no Keycloak durante a
    sessão só aparece depois de recarregar a página. A remoção do papel, ao contrário,
    aparece na hora — como `403` da própria rota.

Human decisions required:
  - Revisão visual da jornada de plataforma, se o produto quiser folha própria em vez
    das classes reaproveitadas (mudança de CSS toca `apps/web/src/styles.css`, fora do
    escopo desta task).
  - Os gates já declarados na feature (aceite do ADR-0036 e merge = deploy) seguem
    pendentes; nada nesta task os antecipa.
```

## Desvios conscientes do contrato

1. **`JourneySwitch` extraído e exportado de `App.tsx`.** O contrato pede o teste "botão
   presente com papel, ausente sem papel" em `App.test.tsx`. O ambiente do vitest é `node`
   e `renderToStaticMarkup(<App />)` nunca alcança a casca: `session` nasce `null` e
   `renderToStaticMarkup` não roda efeitos, então o render estático é sempre a porta de
   entrada. Extrair o seletor é o que torna a regra verificável, e segue o precedente de
   `MedicaoApp.tsx`, que exporta `OverlayDoTakeoff` e `BannerRodadaMudou` pelo mesmo
   motivo. O comportamento em produção é idêntico.
2. **Nenhuma folha de estilo nova.** `apps/web/src/styles.css` é o único arquivo que
   importa folhas de jornada e está fora da lista WRITE; o Design System registra que o
   projeto não tem escala tipográfica, de espaçamento nem de raio e proíbe inventá-las
   numa feature. A tela usa só classes existentes.
3. **`formatarInstante` duplicado de `medicao/format.ts`.** Importar entre jornadas
   acoplaria plataforma e medição (hoje elas só compartilham o transporte em `../api`).
   A cópia tem dez linhas e está declarada em comentário no arquivo.
4. **`getEntitlement` ganhou uso real.** O contrato pede a função; sem uso ela seria
   código morto, então ela alimenta o botão "Consultar estado antes de ativar" do
   formulário de tenant novo — que é justamente o caso do tenant sem pegada no banco.
5. **A jornada é montada pela ROTA, não pelo papel.** Quem força `?plataforma=` sem
   `platform_operator` vê a tela e lê o `403` traduzido, como o Goal pede ("forçando a
   query, recebe erro legível"). Barrar no client trocaria a frase por tela vazia e não
   acrescentaria segurança — a autorização é do backend.
6. **Ativar com referência vazia não é bloqueado no client.** O botão continua
   habilitado e a recusa vem do servidor (`AGREEMENT_REFERENCE_REQUIRED`), que é a
   autoridade sobre a regra — e é o que mantém a frase do `labels.ts` viva em vez de
   inalcançável.
7. **O campo de referência nasce vazio ao reativar tenant revogado.** Pré-preencher com
   o contrato anterior registraria um ato novo sob um contrato que ninguém conferiu.

## Oportunidades vistas e NÃO implementadas (fora de escopo)

- Cena de plataforma no smoke headless (`apps/web/e2e/smoke-headless.mjs`): é o único
  teste que atravessa comportamento real de browser e hoje não cobre esta jornada.
- Folha própria (`apps/web/src/plataforma/styles.css`) com a linha de `@import` em
  `apps/web/src/styles.css`, se a tela ganhar revisão visual.
- `apps/web/AGENTS.md` não tem seção da jornada de plataforma (as regras da jornada de
  medição estão lá); documentação é a T4.
- Trilha de auditoria e custo por tenant na tela — já declarados na F-017.
