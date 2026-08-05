# Release 8.2 — cenários comparáveis e compartilháveis

## Escopo entregue

- cópia imutável ligada ao cenário de origem e recalculada sobre o mesmo snapshot;
- link somente leitura, autenticado no tenant, com token armazenado apenas como SHA-256,
  expiração de 1 a 30 dias, contador de acesso e revogação;
- comparação persistida de 2 a 5 cenários estritamente compatíveis;
- sensibilidade multivariada em grade de 3 a 11 passos ímpares;
- intervalos determinísticos por território e no total, derivados das incertezas explícitas;
- interface para criar faixas, selecionar, comparar, copiar, compartilhar e analisar;
- auditoria de todas as operações e RLS forçada nas duas novas tabelas.

## Semântica de segurança analítica

As faixas são intervalos de premissas, não intervalos de confiança. O contrato retorna
`confidence_level: null`, identifica `DETERMINISTIC_ASSUMPTION_RANGE` ou
`DETERMINISTIC_SENSITIVITY_RANGE` e mantém o aviso de simulação. Nenhuma operação escreve
em `electoral_results`.

O compartilhamento não torna o cenário público: a URL continua sujeita ao login, mandato
ativo, feature flag e tenant do usuário. Não existe endpoint de atualização do cenário
compartilhado.

## Persistência e contratos

- migration `s2c0a7e4f6b8`;
- tabelas `electoral_scenario_shares` e `electoral_scenario_analyses`;
- metodologia `territorial-assumption-range-v2`;
- endpoints de cópia, compartilhamento/revogação, comparação, sensibilidade e consulta de
  análise documentados no OpenAPI.

## Homologação

- teste backend cobre cópia, hash do token, leitura, revogação, comparação, sensibilidade,
  intervalos e invariância dos votos oficiais;
- teste frontend cobre a jornada completa das ações da Release 8.2;
- migrations PostgreSQL verificam criação, rollback/reapply e inclusão nas auditorias RLS.
