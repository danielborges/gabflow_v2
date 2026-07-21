# Requisitos de Analytics e Insights

- **RA-001** Volume de solicitações por período. **Implementado na Release 5.**
- **RA-002** Distribuição por categoria e subcategoria. **Implementado na Release 5 para categoria; subcategoria permanece como evolução de taxonomia.**
- **RA-003** Distribuição territorial. **Implementado na Release 5.**
- **RA-004** Canais mais utilizados. **Implementado na Release 5.**
- **RA-005** Tempo até primeira resposta. **Implementado na Release 5.**
- **RA-006** Tempo até encaminhamento. **Implementado na Release 5.**
- **RA-007** Tempo até encerramento. **Implementado na Release 5.**
- **RA-008** Taxa de resolução. **Implementado na Release 5 como métrica operacional de resoluções registradas.**
- **RA-009** Taxa de reabertura. **Implementado na Release 5 como contagem operacional de reaberturas.**
- **RA-010** Taxa de solicitações sem retorno. **Implementado parcialmente na Release 5 por retornos pendentes/vencidos e fila prioritária.**
- **RA-011** Órgãos mais acionados. **Implementado na Release 5.**
- **RA-012** Tempo de resposta por órgão. **Implementado parcialmente na Release 5 por encaminhamentos e respostas auditáveis; agregação dedicada por órgão fica pendente.**
- **RA-013** Demandas reincidentes por local. **Implementado na Release 5.**
- **RA-014** Tendência de crescimento ou redução. **Implementado na Release 5 por séries temporais e comparação de janelas.**
- **RA-015** Detecção de anomalias. **Implementado na Release 5 por regra determinística de crescimento anormal.**
- **RA-016** Solicitações agrupadas por evento urbano.
- **RA-017** Demandas que originaram proposições.
- **RA-018** Proposições originadas de múltiplas demandas.
- **RA-019** Bairros com baixa presença do gabinete.
- **RA-020** Cobertura de visitas por território.
- **RA-021** Temas com maior taxa de solução.
- **RA-022** Qualidade cadastral.
- **RA-023** Carga de trabalho por equipe.
- **RA-024** Previsão de volume, com faixa de incerteza.
- **RA-025** Relatório de prestação de contas. **Implementado na Release 5 como relatório mensal do mandato.**

## Dimensões mínimas

- tempo;
- tenant;
- equipe;
- responsável;
- canal;
- categoria;
- subcategoria;
- status;
- prioridade;
- bairro;
- região;
- órgão;
- tipo de cidadão ou organização;
- origem;
- resultado.

## Restrições

- Não exibir segmentações com poucos indivíduos quando houver risco de identificação.
- Não criar score de propensão eleitoral.
- Não inferir apoio político individual.
- Resultados preditivos devem ser usados para planejamento, não para excluir atendimento.
