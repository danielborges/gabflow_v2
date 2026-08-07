# Homologação navegada — Gate B da Inteligência Territorial

**Data:** 07/08/2026

**Ambiente:** Gabinete Demonstração, PostgreSQL 17 + PostGIS, aplicação Docker em
`http://localhost:8081`

**Decisão:** **APROVADO**

## Escopo homologado

- comparação entre a janela atual e a janela anterior equivalente;
- mapa de calor, pontos autorizados, hotspots e tabela territorial sincronizada;
- ordenação acessível e seleção por mouse/teclado;
- filtros por período, categoria, canal, território e órgão;
- visões salvas isoladas por usuário;
- painel de causas, qualidade, amostra e exemplos autorizados;
- navegação do território para a grid de Solicitações com o recorte preservado;
- diferenças de autorização entre `ADMIN`, `MANAGER` e `STAFF`;
- telemetria minimizada do funil territorial.

## Massa e evidências

O seed idempotente `seed-territorial-homologation` preparou 765 solicitações em 15
territórios, com 450 registros na janela atual e 315 na anterior. Cada território ficou com
30 registros atuais e 21 anteriores. A massa mantém estados aproximados, verificados, não
resolvidos, ambíguos e externos à jurisdição, além de células liberadas e suprimidas pelo
limiar mínimo de três registros.

| Cenário | Resultado |
| --- | --- |
| comparação geral e por território | aprovado; todas as linhas possuem base equivalente |
| seleção mapa/tabela/painel | aprovado; a seleção de Zona Leste atualizou o painel lateral |
| filtro e visão salva | aprovado; visão `Gate B — Saúde` criada e isolada por usuário |
| drill-down | aprovado; Zona Leste abriu 30 solicitações com período e território preservados |
| perfil admin | pontos, protocolos e exemplos autorizados visíveis |
| perfil manager | pontos e exemplos autorizados visíveis; visões do admin não expostas |
| perfil staff | somente agregados; nenhum protocolo/ponto individual exposto |
| telemetria | eventos de abertura, filtro e investigação persistidos sem conteúdo pessoal |

## Defeitos encontrados e corrigidos

1. A primeira versão da massa correlacionava a janela temporal ao índice do território. Isso
   deixava parte dos territórios sem base anterior mesmo quando a comparação geral existia. O
   seed passou a alternar janelas por rodadas completas de territórios e ganhou teste de
   repetibilidade.
2. O endpoint carregava interações, históricos e encaminhamentos sob demanda para cada
   solicitação, produzindo consultas em cascata. O carregamento passou a ser feito em lote com
   `selectinload`.

## Desempenho

Foram realizadas 20 consultas autenticadas consecutivas ao painel operacional com a massa de
765 solicitações:

- mínimo: 193,5 ms;
- mediana: 359,3 ms;
- P95: 550,2 ms;
- máximo: 733,4 ms.

O P95 ficou abaixo do orçamento de 1,5 segundo definido para o recorte operacional homologado.

## Decisão do gate

O Gate B está aprovado porque usuários autorizados conseguem partir do sinal territorial,
investigar causas e chegar aos casos preservando o contexto, enquanto perfis sem autorização
recebem apenas agregados. A conversão do funil está instrumentada e foi observada no ambiente
de demonstração.

O incremento 5.3 pode iniciar. A seleção e homologação do provedor externo de geocodificação
continuam sendo uma decisão própria do Gate C e não alteram esta aprovação.
