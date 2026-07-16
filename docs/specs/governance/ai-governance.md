# Governança de IA

## Catálogo de casos de uso

Cada caso deve registrar:
- finalidade;
- proprietário;
- nível de risco;
- dados utilizados;
- modelo;
- prompt;
- métricas;
- fallback;
- necessidade de revisão;
- política de retenção.

## Níveis de risco

### Baixo
- resumo interno;
- extração de entidades;
- sugestão de tags.

### Médio
- sugestão de resposta;
- classificação de prioridade;
- detecção de duplicidade;
- geração de insights.

### Alto
- minuta legislativa;
- análise jurídica;
- comunicação pública;
- decisão com impacto individual.

## Controles

- prompts versionados;
- avaliação antes de produção;
- canary release;
- monitoramento de drift;
- limite de custo;
- bloqueio de PII desnecessária;
- red teaming;
- feedback humano;
- trilha de auditoria;
- rollback de modelo e prompt.
