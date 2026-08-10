# Encerramento formal do Gate D — operação territorial

## Decisão

O **Gate D foi APROVADO e formalmente encerrado em 10/08/2026** no ambiente local de
homologação do Gabinete Demonstração.

O critério do gate foi atendido: uma ação territorial preserva o recorte de origem e possui
responsável, prazo, evidência estruturada e resultado, com permissões por perfil, métricas de
execução, ciclo de vida dos alertas e trilha de auditoria.

Este encerramento não autoriza promoção automática para produção. O Gate C permanece encerrado
como reprovado e, portanto, o Gate E continua bloqueado até uma nova aprovação de geocodificação e
as revisões explícitas de privacidade, metodologia e ganho de produto.

## Critérios de aceite

| Critério | Meta | Resultado | Decisão |
| --- | ---: | ---: | --- |
| Massa de cidadãos | 300 | 307 | aprovado |
| Massa de organizações | 50 | 51 | aprovado |
| Massa de solicitações | 750 | 765 | aprovado |
| Concorrência | 50 usuários virtuais | 50 | aprovado |
| Volume do ensaio | 1.000 requisições | 1.000 | aprovado |
| RNF-002, P95 geral | até 2.000 ms | 452,1 ms | aprovado |
| P95 do painel operacional | até 2.000 ms | 561,3 ms | aprovado |
| Taxa de erro | até 1% | 0% | aprovado |
| Homologação negocial | todos os cenários críticos | 13 de 13 | aprovado |

O perfil de carga simula uma abertura do painel por usuário virtual, seguida de consultas de
ações, métricas e alertas territoriais. O ensaio é autenticado, somente leitura e usa o tenant
`gabinete-demo`.

## Resultado do teste de carga

- 1.000 sucessos em 1.000 requisições, sem erro;
- duração de 3,642 segundos e vazão de 274,56 requisições por segundo;
- P50 de 148,4 ms, P95 de 452,1 ms, P99 de 544,9 ms e máximo de 620,1 ms;
- ações territoriais: 476 requisições, P95 de 392,7 ms;
- métricas de execução: 237 requisições, P95 de 331,0 ms;
- alertas: 237 requisições, P95 de 346,2 ms;
- painel operacional: 50 requisições, P95 de 561,3 ms.

As primeiras rodadas foram preservadas, pois fazem parte da evidência de engenharia:

| Rodada | Configuração/achado | P95 geral | Erros | Decisão |
| --- | --- | ---: | ---: | --- |
| 1 | mistura artificial com 20% de chamadas completas ao painel | 2.361,4 ms | 0 | reprovada |
| 2 | capacidade elevada; painel ainda acima do orçamento experimental de 1,5 s | 1.660,8 ms | 0 | reprovada |
| 3 | capacidade elevada; uma chamada expirou e o painel permaneceu instável | 1.672,5 ms | 1 | reprovada |
| 4 | mistura negocial realista, antes da proteção de rajada | 2.146,9 ms | 0 | reprovada |
| Final | 4 processos, 8 threads e cache segregado de 3 s com single-flight | 452,1 ms | 0 | aprovada |

O gargalo era a recomposição simultânea do painel operacional para a mesma combinação de tenant,
perfil e filtros. A correção adicionou capacidade configurável ao Gunicorn e um cache curto,
segregado por tenant e permissões, com consolidação de requisições concorrentes. Lembretes
dependentes do usuário continuam sendo avaliados fora do cache.

## Homologação negocial

A homologação foi executada com os perfis reais `admin` e `staff` do ambiente de demonstração:

1. a liderança acessou o painel e a lista de trabalhadores;
2. criou uma ação no território Centro, atribuiu responsável e definiu prazo;
3. o trabalhador visualizou a ação no escopo `PROPRIAS`;
4. tentativas do trabalhador de criar ação e alterar prazo retornaram `403`;
5. o trabalhador moveu a ação de `PENDENTE` para `EM_ANDAMENTO`;
6. registrou evidência estruturada com tipo, título, data, descrição e URL;
7. concluiu a ação com resultado obrigatório;
8. a liderança confirmou métricas de conclusão e cobertura de evidências;
9. alertas históricos foram consultados e criação, movimentação e evidência foram encontradas na
   auditoria.

Foram aprovados **13 de 13 cenários**, sem reprovação. A execução criou a ação
`e6d6fe50-d5fa-4310-b326-39258375951f` e a evidência
`aeacbb72-77b7-4ba9-a710-bdddb99b9b36`, mantidas no Gabinete Demonstração como prova auditável.

## Evidências reproduzíveis

- roteiro de carga: `benchmark/territorial-gate-d-load.py`;
- relatório aprovado: `benchmark/territorial-gate-d-load-report.json`;
- rodadas diagnósticas: `benchmark/territorial-gate-d-load-report-round1-failed.json` a
  `benchmark/territorial-gate-d-load-report-round4-failed.json`;
- roteiro negocial: `benchmark/territorial-gate-d-business-homologation.py`;
- relatório negocial: `benchmark/territorial-gate-d-business-homologation-report.json`;
- testes automatizados: `backend/tests/test_territorial_operations.py` e
  `backend/tests/test_p1_completion.py`.

Os relatórios não contêm senha, cookie ou token. O teste de carga não altera dados; apenas o
roteiro negocial cria uma ação/evidência sintética e redefine a credencial do usuário exclusivo de
homologação, operações registradas na auditoria.

## Condições operacionais e reabertura

O resultado comprova o volume-alvo na topologia local homologada, não a capacidade ilimitada de
produção. O Gate D deve ser reavaliado se houver mudança relevante na topologia, consultas do
painel, regras de autorização, volume-alvo ou duração do cache. Para rollback, o cache pode ser
desabilitado com `OPERATIONAL_DASHBOARD_CACHE_SECONDS=0` e a capacidade volta a ser controlada por
`WEB_CONCURRENCY` e `GUNICORN_THREADS`.
