# ADR-003 — RAG com citações obrigatórias

## Status
Aceito

## Decisão
Toda resposta baseada em base institucional deve utilizar recuperação de fontes e citações verificáveis.

## Consequências
- maior confiança;
- auditabilidade;
- necessidade de versionar documentos;
- necessidade de avaliação de groundedness;
- respostas podem declarar insuficiência de evidência.

## Metadados obrigatórios

Cada citação deve preservar:

- escopo `GLOBAL` ou `PRIVADO`;
- coleção e documento;
- versão e checksum;
- página, seção ou entidade de origem quando aplicável;
- jurisdição e vigência;
- pontuação e método de recuperação.

Fontes globais e privadas devem ser visualmente distinguíveis. Revogação ou
substituição não apaga a versão usada em respostas históricas.
