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

## Governança das fontes operacionais

Cada projetor de conhecimento deve possuir proprietário, módulo, tipos de entidade,
ações suportadas, allowlist de campos, critérios de aprovação, finalidade, base
legal, ACL, retenção, política de quarentena e política de purge.

A habilitação de um novo projetor exige:

- revisão de privacidade e ameaça de prompt injection;
- exemplos positivos, inelegíveis e maliciosos;
- testes de criação, atualização, exclusão, anonimização e expiração;
- avaliação de retrieval por tenant antes e depois da ampliação;
- plano de rollback que despublique as fontes derivadas sem afetar a origem.

Saídas produzidas por IA somente podem se tornar fonte operacional após estado de
aprovação humana compatível com o caso de uso.
