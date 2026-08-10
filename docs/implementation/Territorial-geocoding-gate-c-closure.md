# Encerramento formal — Gate C de geocodificação

**Data:** 10/08/2026

**Escopo:** incremento 5.3 — Cartografia e qualidade governadas

**Decisão:** **REPROVADO — NENHUM PROVEDOR PROMOVIDO PARA PRODUÇÃO**

## Base da decisão

O benchmark externo executou 700 casos de Juiz de Fora/MG, distribuídos entre área central
(200), periferia urbana (200), zona rural (150) e demais áreas (150), com repetição
determinística de 10%. Geoapify, Google e Geocode Earth receberam a mesma amostra e foram
avaliados pela geometria oficial configurada para a jurisdição.

| Evidência | Valor |
| --- | --- |
| checksum SHA-256 do dataset | `7f8d1428f00ecd9f7ff051b65ae122cd428a825d91fe8f8d51b4038bf4f65a13` |
| checksum SHA-256 da geometria | `f36388ebf80e7f2a78b7943c4ddf38e40b7b0aa983a2a3a7c4be44a9899f9af1` |
| checksum SHA-256 do relatório restrito | `602ba01c03110bd90cdc26033c3802084bcf0191bf6d6422c8f3f47b388116ab` |
| versão do executor | `geocoding-benchmark-v1` |
| erros de chamada | zero nos três provedores |

O dataset e o relatório detalhado permanecem fora do versionamento por conterem consultas,
coordenadas e componentes normalizados. O manifesto auditável está em
[`benchmark/territorial-geocoding-manifest-v1.json`](../../benchmark/territorial-geocoding-manifest-v1.json).

## Resultados eliminatórios

| Provedor | Metas não atendidas | Evidência principal |
| --- | --- | --- |
| Geoapify | logradouro geral e bairro | logradouro 83,43% para meta de 85%; bairro 12,43% para meta de 85% |
| Google | jurisdição, logradouro geral, bairro e resolução completa | jurisdição 98,71% para meta de 99%; logradouro 74,14%; bairro 64,14%; resolução 82,68% |
| Geocode Earth | município, logradouro geral/urbano, número urbano e bairro | município 85,43% para meta de 95%; logradouro 40,43%; logradouro urbano 34,06%; número urbano 33%; bairro 30,86% |

Os três provedores preservaram zero ponto externo promovido automaticamente a `VERIFIED` e
atingiram a meta de estabilidade. Esses resultados positivos não compensam metas eliminatórias
não atendidas. Como nenhum candidato passou todos os gates técnicos, a pontuação ponderada não
é aplicável e não existe vencedor elegível.

## Pendências de governança observadas

- a revisão humana cega da amostra e das divergências permanece pendente;
- o relatório não recebeu custos contratuais por mil consultas;
- DPA, suboperadores, transferência internacional, retenção, SLA, suporte e atribuições não
  possuem aprovação formal anexada;
- a importação versionada da malha oficial no PostGIS está registrada como pendente no manifesto.

Essas pendências reforçam a reprovação, mas não são necessárias para eliminar os candidatos:
as falhas de qualidade, isoladamente, já impedem a promoção.

## Efeito operacional

- nenhum provedor externo está autorizado para geocodificação de produção;
- Geoapify permanece permitido somente em desenvolvimento e homologação controlada com dados
  públicos, sintéticos ou efetivamente anonimizados;
- o fluxo controlado por solicitação pode ser ativado por feature flag nesses ambientes, com
  cota por gabinete e revisão humana obrigatória, conforme
  [`Territorial-geocoding-homologation-flow.md`](Territorial-geocoding-homologation-flow.md);
- MapLibre GL JS, PostgreSQL/PostGIS, o contrato canônico e o adaptador intercambiável permanecem
  válidos e independentes da escolha futura do provedor;
- resultados ambíguos, externos ou divergentes continuam sem promoção automática a `VERIFIED`.
- o Gate E permanece bloqueado; o incremento 5.4 só pode avançar em partes que não dependam de
  geocodificação externa de produção.

## Condições para um novo Gate C

Uma nova avaliação deve usar versão nova e congelada do dataset e do manifesto, registrar
revisão humana cega, investigar aliases/bairros e diferenças rurais, repetir os três candidatos
obrigatórios e anexar custos e aprovações jurídica/comercial. O gate somente poderá ser reaberto
quando ao menos um provedor atender **todas** as metas eliminatórias; a nova rodada não altera
nem sobrescreve esta decisão.

## Validações da implementação

- `ruff check app/geocoding/benchmark.py tests/test_geocoding_benchmark.py`: aprovado;
- `pytest tests/test_geocoding_benchmark.py -q`: **10 testes aprovados**;
- checksum do CSV recalculado localmente e coincidente com manifesto e relatório;
- relatórios e CSV protegidos por `.gitignore`; somente o manifesto permanece elegível para
  versionamento;
- novos relatórios passam a emitir `qualityDecision`, com gates reprovados por provedor e
  `productionAuthorization: false`, pois aprovação técnica nunca substitui governança formal.
