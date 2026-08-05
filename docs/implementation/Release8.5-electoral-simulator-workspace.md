# Release 8.5 — Simulador eleitoral funcional

Data de implementação: 2026-08-04.

## Lacuna encerrada

O domínio já possuía cálculo e persistência de cenários, mas a interface dependia de uma
candidatura previamente aberta em outra área e permitia informar somente uma premissa por
criação. Para o Parlamentar, isso não constituía um simulador autônomo.

## Escopo entregue

- seleção de eleição-base, nível territorial e candidatura dentro do simulador;
- busca de candidatura sem abandonar a área de cenários;
- carregamento dos territórios disponíveis para a base escolhida;
- editor de múltiplas premissas territoriais, sem repetição de território;
- deltas de participação e denominador, incertezas e justificativa por premissa;
- endpoint `POST /electoral/scenarios/preview`, sem persistência;
- prévia com base oficial, total simulado, diferença, faixa e detalhamento territorial;
- salvamento opcional somente após a exploração da prévia;
- reutilização do mesmo motor e metodologia na prévia e no cenário persistido;
- auditoria minimizada de cada prévia, sem alterar resultados oficiais;
- navegação identificada explicitamente como `Simulador eleitoral`.

## Garantias

A prévia retorna `simulation: true` e `persisted: false`. O cálculo não grava cenário nem
modifica o catálogo oficial. Toda saída mantém dataset, hash, metodologia, premissas e aviso
de que não se trata de pesquisa registrada ou previsão.

## Homologação

- 21 testes do catálogo eleitoral aprovados, com prévia e criação verificadas contra o
  mesmo resultado territorial;
- teste comprova que a prévia não cria registro em `electoral_scenarios` e recusa premissa
  sem justificativa;
- suíte global de backend não PostgreSQL aprovada integralmente;
- 68 testes de frontend aprovados, incluindo busca interna, escolha da base, múltiplos
  territórios, prévia e salvamento;
- Ruff, ESLint, OpenAPI YAML e build de produção aprovados;
- nenhuma migration foi necessária porque a prévia é efêmera e auditada.
