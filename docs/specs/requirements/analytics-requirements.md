# Requisitos de Analytics e Insights

- **RA-001** Volume de solicitações por período.
- **RA-002** Distribuição por categoria e subcategoria.
- **RA-003** Distribuição territorial.
- **RA-004** Canais mais utilizados.
- **RA-005** Tempo até primeira resposta.
- **RA-006** Tempo até encaminhamento.
- **RA-007** Tempo até encerramento.
- **RA-008** Taxa de resolução.
- **RA-009** Taxa de reabertura.
- **RA-010** Taxa de solicitações sem retorno.
- **RA-011** Órgãos mais acionados.
- **RA-012** Tempo de resposta por órgão.
- **RA-013** Demandas reincidentes por local.
- **RA-014** Tendência de crescimento ou redução.
- **RA-015** Detecção de anomalias.
- **RA-016** Solicitações agrupadas por evento urbano.
- **RA-017** Demandas que originaram proposições.
- **RA-018** Proposições originadas de múltiplas demandas.
- **RA-019** Bairros com baixa presença do gabinete.
- **RA-020** Cobertura de visitas por território.
- **RA-021** Temas com maior taxa de solução.
- **RA-022** Qualidade cadastral.
- **RA-023** Carga de trabalho por equipe.
- **RA-024** Previsão de volume, com faixa de incerteza.
- **RA-025** Relatório de prestação de contas.

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
