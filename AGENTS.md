# Instruções para agentes

Status: Accepted  
Responsável: Engineering  
Última revisão: 2026-08-18

## Escopo

Estas instruções valem para todo o repositório. Arquivos `AGENTS.md` em
subdiretórios acrescentam regras específicas e não podem enfraquecer estas regras.

## Leitura obrigatória

Antes de alterar qualquer arquivo:

1. Leia [docs/INDEX.md](docs/INDEX.md).
2. Leia [docs/STATUS.md](docs/STATUS.md).
3. Siga o roteiro de leitura da tarefa indicado no índice.
4. Leia ADRs relacionados e o `AGENTS.md` mais próximo do arquivo alvo.
5. Para trabalho planejado, leia também o [Project Context](docs/engineering/PROJECT_CONTEXT.md)
   e os artefatos da feature selecionada.

Não carregue toda a documentação por padrão. Leia somente as fontes canônicas
necessárias, mas leia cada documento selecionado por completo.

## Fontes de verdade e conflitos

- Segurança e privacidade têm precedência sobre conveniência e prazo.
- ADRs aceitos definem decisões arquiteturais.
- PRD e FDD definem intenção e comportamento de produto.
- API Contract, Domain Model e DXF Output Spec definem interfaces.
- NFR define limites mensuráveis.
- Testes e evals verificam os contratos; não os substituem silenciosamente.

Quando código, teste e documentação divergirem, não escolha uma interpretação
ocultamente. Identifique a fonte desatualizada, corrija-a no mesmo trabalho e
registre uma nova decisão quando a mudança exigir ADR.

## Ciclo de trabalho e evidência

O [Project Context](docs/engineering/PROJECT_CONTEXT.md) define onde localizar o
roadmap canônico, o status derivado, os perfis de validação e os artefatos de feature.
Nenhum agente escolhe prioridade de produto ou inicia item de roadmap sem seleção humana.

- Planner trabalha somente a partir de um Feature Contract aceito e produz o formato
  `FEATURE EXECUTION PLAN` da Engineering OS.
- Builder executa somente Task Contract autorizado, registra o baseline aplicável e
  encerra com o `BUILD REPORT` completo da Engineering OS.
- Reviewer atua em modo somente leitura sobre o pacote de evidências
  `BASELINE → CHANGE → FINAL` e encerra como `REVIEW_PASS`, `REVIEW_FINDINGS` ou
  `REVIEW_EVIDENCE_INCOMPLETE`.

Esses contratos acrescentam rastreabilidade; não substituem os gates de segurança,
privacidade, arquitetura e operação deste repositório.

## Limites de autonomia

Pode executar sem confirmação adicional:

- Ler arquivos e inspecionar o estado local.
- Editar arquivos dentro do escopo solicitado.
- Executar testes, linters, type checks e builds não destrutivos.
- Criar fixtures sintéticas sem dados de clientes.

Exige aprovação explícita:

- Deploy ou mutação de recursos AWS.
- Migração destrutiva ou irreversível de banco.
- Chamadas pagas em massa a modelos ou OCR.
- Envio de documentos para serviços externos fora de um teste autorizado.
- Alteração de retenção, residência de dados ou fornecedores.
- Exclusão material de dados ou artefatos de usuário.

Não delegue trabalho a outros agentes salvo quando a tarefa pedir explicitamente
delegação ou paralelismo.

## Regras AI First

- Modelos produzem observações; o `Canonical Scene Graph` é a fonte geométrica.
- Nunca invente, arredonde silenciosamente ou complete uma medida ausente.
- Nunca force ortogonalidade, simetria, arco ou círculo sem evidência registrada.
- Preserve `raw_text`, região de origem, modelo, versão de prompt e associação.
- Use somente schemas estruturados e rejeite saídas fora do contrato.
- Uma divergência entre provedores deve virar `Issue`; nenhum modelo vence em
  silêncio.
- Textract ajuda a localizar e transcrever, mas não determina geometria.
- Confiança do modelo não libera exportação nem substitui regra determinística.
- Mudança de prompt, modelo, roteamento ou normalização exige eval comparativa e
  plano de rollback.
- Não faça fine-tuning sem ADR, licença dos dados e baseline reproduzível.

## Regras de dados e segurança

- Nunca copie PDFs reais de clientes para o repositório.
- Nunca registre imagens, textos integrais, cotas completas, tokens, segredos ou
  URLs assinadas em logs.
- Use IDs lógicos e hashes para referenciar o golden dataset.
- Fixtures versionadas devem ser sintéticas, anonimizadas ou explicitamente
  licenciadas.
- Valide MIME, tamanho e estrutura de PDFs antes de processar.
- Todo objeto de usuário deve ser isolado por tenant/projeto.

## Disciplina de mudança

- Mudança de comportamento: atualize FDD e critérios de aceite.
- Mudança de interface: atualize API Contract e testes de contrato.
- Mudança arquitetural: siga o [processo de ADR](docs/adr/README.md); a aceitação é ato humano.
- Mudança de NFR: atualize NFR, observabilidade e teste correspondente.
- Mudança de IA: atualize Model Routing, Prompt Contracts e Evaluation Strategy.
- Mudança operacional: atualize runbook e rollback.

## Qualidade de implementação

- Prefira funções determinísticas para normalização e geometria.
- Isole SDKs de fornecedores atrás de interfaces internas.
- Faça operações assíncronas idempotentes e observáveis.
- Use tipagem estrita e erros de domínio explícitos.
- Escreva testes proporcionais ao risco, incluindo casos negativos.
- Não introduza dependência sem revisar licença, manutenção e superfície de risco.

## Conclusão de tarefa

Uma mudança só está concluída quando:

- Implementação e documentação concordam.
- Testes relevantes passaram.
- Evals passaram quando IA foi alterada.
- Métricas e falhas novas são observáveis.
- Migração e rollback foram considerados.
- [docs/STATUS.md](docs/STATUS.md) foi atualizado se o marco mudou.

A interface padrão de desenvolvimento é `make setup`, `make check`, `make test` e
`make dev`. Os perfis de validação e seus limites estão no
[Project Context](docs/engineering/PROJECT_CONTEXT.md); detalhes de execução, no
`CLAUDE.md` da raiz e em [Local Development](docs/engineering/LOCAL_DEVELOPMENT.md).
