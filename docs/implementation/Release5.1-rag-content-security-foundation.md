# Release 5.1 — Fundação de segurança de conteúdo do RAG

## Escopo entregue

O incremento 5.1 é deliberadamente documental e estabelece o contrato de segurança
que antecede mudanças no runtime:

- threat model de prompt injection direto, indireto, ofuscado, multimodal e
  persistente;
- ativos, atores, superfícies, fronteiras de confiança e invariantes;
- diagnóstico corrigido dos controles existentes e das lacunas reais;
- requisitos RIA-105 a RIA-111, RNF-040 a RNF-044 e RF-137 a RF-140;
- JSON Schema versionado para casos adversariais;
- dataset v1 com partições `REGRESSION` e `HOLDOUT`;
- ataques em português, inglês, espanhol, conteúdo codificado, Unicode, metadados,
  OCR, múltiplos chunks, consultas, feedback e conectores;
- controles benignos destinados a medir falsos positivos;
- gates iniciais de segurança e regras de governança do dataset.

## Artefatos

- `docs/specs/architecture/rag-content-security-threat-model.md`;
- `docs/specs/datasets/prompt-injection-adversarial.schema.json`;
- `docs/specs/datasets/prompt-injection-adversarial-v1.json`;
- cenários em `docs/specs/features/assistente-rag.feature`;
- requisitos e critérios de Done atualizados.

## Decisões

1. O RLS existente protege isolamento de linhas, mas não previne prompt injection.
2. Aprovação para indexação significa autorização para uso como dado, nunca como
   instrução.
3. O dataset adversarial não é fonte factual e jamais integra o índice RAG.
4. Casos suspeitos, maliciosos ou indeterminados não poderão produzir derivados.
5. Falha de scanner ou classificador obrigatório será tratada como falha fechada.
6. Métricas de ataques e de controles benignos serão avaliadas separadamente.

## Gates definidos

- todos os ataques críticos conhecidos contidos;
- recall adversarial mínimo de 98% no holdout;
- falso positivo máximo de 2% nos controles benignos;
- zero derivados para decisão diferente de `CLEAN`;
- zero recuperação de versão em quarentena;
- decisão reproduzível por política e checksum.

Os números são gates iniciais e podem ficar mais rigorosos após a primeira execução
automatizada. Redução exige ADR e aprovação explícita de segurança.

## Próximo incremento

O 5.2 implementou o gateway unificado, o contrato fechado de decisão e o estado de
segurança persistente. O enforcement completo antes de derivados segue no 5.3; o
classificador dedicado, antimalware, revarredura, validação de saída e criptografia
permanecem nos incrementos subsequentes.
