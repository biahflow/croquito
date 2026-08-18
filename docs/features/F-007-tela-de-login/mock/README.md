# Mock aprovado da F-007 — porta de entrada

Status: Aprovado (visual)  
Responsável: Product / Engineering  
Última revisão: 2026-08-18

Este diretório guarda o artefato que sustenta o gate humano **"aprovação do visual da tela"**
do [Feature Contract da F-007](../feature.md). Ele existe porque um gate que cita um artefato
que ninguém consegue abrir é um gate que será rediscutido: o Builder precisa ver o que foi
aprovado, e não a descrição de alguém sobre o que foi aprovado.

## Conteúdo

| Arquivo | O que é |
| --- | --- |
| [`login.html`](login.html) | O mock, autocontido. Abra no navegador. Revisão 2 — a que foi aprovada. |
| [`01-login-desktop.png`](01-login-desktop.png) | A tela `/login` em desktop |
| [`02-login-celular.png`](02-login-celular.png) | `/login` em 390px, com o estado de ambiente indisponível |
| [`03-keycloak-tema-croquito.png`](03-keycloak-tema-croquito.png) | As três páginas do Keycloak no tema `croquito` |

As imagens acompanham o HTML de propósito: elas fixam o que foi aprovado independentemente de
fonte instalada, versão de navegador ou renderização — o HTML mostra a intenção, as imagens
mostram o resultado conferido na data.

## O que foi aprovado, e o que não foi

**Aprovado por decisão humana de 2026-08-18: o visual.** Composição, hierarquia, o peso do CTA,
o croqui vetorial, o card do Keycloak e o comportamento responsivo.

**Não aprovado: o texto.** Nenhuma linha de copy passou por gate — título, promessa, rótulo do
CTA, a frase sobre conta por convite, a mensagem de ambiente indisponível e os e-mails. A única
frase que não é proposta é "Do croqui ao orçamento.", que vem da descrição do produto. O
Feature Contract mantém isso como `Unknown` e como gate próprio.

## Como ler este mock ao implementar

- **Não é implementação.** É HTML estático, sem comportamento, sem acessibilidade auditada e
  sem estado. Nada aqui deve ser copiado para `apps/web` como código.
- **Os tokens são cópia de `apps/web/src/styles.css`**, feita em 2026-08-18, e as regras de uso
  estão no [Design System](../../../engineering/DESIGN_SYSTEM.md). A folha é a fonte de verdade;
  se divergirem, a folha vence e este arquivo está velho.
- **Tamanho, espaçamento e raio deste mock são valores novos**, não citações: o Design System
  registra que o projeto ainda não tem escala para nenhum dos três.
- **Os logos são os de `apps/web/src/assets/` e `apps/web/public/favicon.svg`**, embutidos para
  o arquivo abrir sozinho.
- **O que está em âmbar depende da [F-008](../../F-008-ciclo-de-vida-de-conta/feature.md)** —
  recuperação de senha, convite e Google. A F-007 entrega o tema e reserva o espaço do botão;
  o botão do Google **só é renderizado quando existe identity provider configurado no realm**
  (critério 9 do contrato).
- **"Prefeitura de Niterói", no card de convite, é exemplo** — não é dado nem decisão. Exibir o
  nome do tenant no convite ainda está em aberto.

## Decisões de desenho que o mock carrega

- Nenhuma peça da casca das jornadas aparece sem sessão — sem topbar, sem pílula de schema, sem
  alternância de jornada ([ADR-0032](../../../adr/0032-porta-de-entrada-e-estado-sem-sessao.md),
  D3).
- O "Entrar" é o objeto de maior peso da página, em preenchimento `--accent` sobre
  `--accent-ink`, como a folha de estilo determina. Hoje ele é um `button-quiet` na topbar.
- "Esqueci minha senha" fica na página do Keycloak, não em `/login`: é onde vive o campo de
  senha. Oferecer recuperação antes de a pessoa dizer quem é seria mandá-la a um fluxo sem
  sujeito.
- O tema veste seis templates e os e-mails, não só o `login.ftl` (ADR-0032, D7).
- "Ambiente indisponível" é uma tela, não um parágrafo solto: separa "você não entrou" de "o
  ambiente caiu" — a confusão que custou quatro dias silenciosos na
  [F-006](../../F-006-hml-conserto/feature.md).
