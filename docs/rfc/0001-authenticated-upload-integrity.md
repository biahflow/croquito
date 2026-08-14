# RFC-0001: Upload autenticado com verificação de integridade

Status: Accepted  
Autor: Engineering  
Data: 2026-08-10

## Resumo

O browser envia PDFs diretamente ao storage privado por URL assinada. Antes de
criar o job, a API confirma tamanho, MIME e SHA-256 do objeto remoto; o worker
abre o PDF em diretório temporário e aplica limites estruturais.

## Objetivos e não objetivos

Objetivos: upload OIDC tenant-scoped, retomada de job, integridade verificável e
falha fechada para PDF malformado. Não objetivos: OCR, IA paga, extração de
geometria ou alteração da retenção de sete dias.

## Proposta

`POST /uploads/presign` exige checksum assinado. O browser calcula SHA-256,
executa PUT direto e então cria o job. A API faz `HeadObject` antes de persistir
o job e pode reenfileirar com a mesma chave de idempotência após falha transitória.
O worker revalida assinatura, digest e estrutura, aceitando no máximo 50 páginas
e 100 MP por página a 200 DPI.

## Segurança, compatibilidade e rollback

Não há bytes de documento no processo da API, logs ou Git. CORS do bucket aceita
somente a origem web configurada e os headers do PUT. As respostas recebem apenas
campos aditivos e a alteração de banco é expand-only; rollback de aplicação
mantém as colunas novas sem uso.

## Aceite

PDF sintético válido percorre presign, PUT, job e worker; tamanho, MIME, checksum,
assinatura, páginas e pixels inválidos não produzem cena. Testes cobrem tenant,
idempotência, recarga do job e CORS local.
