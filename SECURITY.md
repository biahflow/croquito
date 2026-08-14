# Política de segurança

Status: Accepted  
Responsável: Security / Engineering  
Última revisão: 2026-08-10

## Relato responsável

Relate vulnerabilidades de forma privada ao responsável pelo repositório ou ao
canal interno de segurança. Não publique detalhes exploráveis em uma issue aberta.
Inclua impacto, passos mínimos de reprodução e evidências sem dados reais de
clientes.

## Dados sensíveis

São considerados sensíveis:

- PDFs, imagens e recortes enviados por clientes.
- Textos e medidas extraídos.
- Scene graphs, revisões e exports.
- Respostas brutas de modelos.
- Chaves de API, tokens, URLs assinadas e identificadores de tenant.

Esses dados não podem ser commitados, usados como fixture sem anonimização ou
registrados em logs. A retenção padrão é de sete dias, com exclusão manual
imediata.

## Segredos

- Produção usa AWS Secrets Manager e IAM roles.
- Desenvolvimento local usa arquivo ignorado pelo Git ou credenciais temporárias.
- Segredos nunca aparecem em Markdown, código, testes, screenshots ou erros.
- Suspeita de vazamento exige rotação imediata e incidente registrado.

## Uploads

- Validar tamanho, MIME e assinatura do arquivo.
- Limitar páginas e resolução antes de alocar processamento.
- Processar conteúdo não confiável em container sem privilégios.
- Não executar conteúdo incorporado no PDF.
- Usar chaves S3 geradas pelo servidor, nunca caminhos fornecidos diretamente.

## Referências

- [Threat Model](docs/security/THREAT_MODEL.md)
- [Privacy and LGPD](docs/security/PRIVACY_LGPD.md)
- [Data Retention](docs/security/DATA_RETENTION.md)
- [Incident Response](docs/operations/INCIDENT_RESPONSE.md)

