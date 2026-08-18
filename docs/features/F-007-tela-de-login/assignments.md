# Atribuições de harness — F-007

Registros no formato de `HARNESS ASSIGNMENT` de
[`execution.md`](../../engineering-os/workflows/execution.md), fora do plano congelado.
Decisão humana de 2026-08-18, transcrita: **estas atribuições valem para a F-007**; o
usuário optou por não ratificar uma regra-padrão permanente — a próxima feature decide de
novo. Reatribuição depois de execução iniciada é `PLAN_DEVIATION`.

Espec de handoff e revisão linha a linha de todo diff permanecem no modelo principal da
sessão Claude Code, independentemente do executor.

Emenda de 2026-08-18 (decisão humana, transcrita): o disparo das tasks do Codex passa a
ser automático via `codex exec`, operado pela sessão Claude Code; e a escada de modelo
vale também no Codex — `gpt-5.6-luna` para as tasks simples (T1, T6) e `gpt-5.6-sol`
para a sensível (T5). A qualidade de cada entrega do Luna é avaliada na revisão linha a
linha e registrada, como na calibração sonnet/opus.

```text
HARNESS ASSIGNMENT
task_id: T1
harness: Codex (gpt-5.6-luna)
assigned_by: Daniel Campos (2026-08-18)
rationale: S, config declarativa com oráculo direto (curl); segundo exercício real de
           paridade após o PARITY-001.
```

```text
HARNESS ASSIGNMENT
task_id: T2
harness: Claude Code (implementador-opus; spec e revisão no modelo principal)
assigned_by: Daniel Campos (2026-08-18)
rationale: risco nº 1 da feature (loop de login), lógica de sessão — degrau alto da escada
           e revisão linha a linha obrigatória.
```

```text
HARNESS ASSIGNMENT
task_id: T3
harness: Claude Code (implementador-opus; spec e revisão no modelo principal)
assigned_by: Daniel Campos (2026-08-18)
rationale: M com nuance de design system (regras de token) e fidelidade a mock aprovado.
```

```text
HARNESS ASSIGNMENT
task_id: T4
harness: Claude Code (implementador-opus; spec e revisão no modelo principal)
assigned_by: Daniel Campos (2026-08-18)
rationale: L, com unknown resolvido por verificação (formato do tema 26.2) e artefato de
           imagem — muitos pontos de toque.
```

```text
HARNESS ASSIGNMENT
task_id: T5
harness: Codex (gpt-5.6-sol)
assigned_by: Daniel Campos (2026-08-18)
rationale: S e delimitada, com contrato explicitamente anti-afrouxamento; o oráculo é a
           execução real dos dois smokes.
```

```text
HARNESS ASSIGNMENT
task_id: T6
harness: Codex (gpt-5.6-luna)
assigned_by: Daniel Campos (2026-08-18)
rationale: XS documental com portão determinístico (check_docs).
```
