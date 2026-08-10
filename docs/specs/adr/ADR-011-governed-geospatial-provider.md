# ADR-011 — Stack cartográfica e geocodificação governada

## Status

**Gate C reprovado em 10/08/2026.** Nenhum provedor foi promovido para produção.
MapLibre GL JS, PostgreSQL/PostGIS e o adaptador intercambiável permanecem aceitos; Geoapify
continua provisório somente para desenvolvimento e homologação controlada. Mapbox permanece
opcional e fora do conjunto obrigatório.

## Contexto

A Inteligência Territorial precisa persistir coordenadas para análise histórica, resolver
territórios em malhas oficiais, operar sob LGPD e trocar de fornecedor sem reescrever o domínio.
Precisão declarada pelo fornecedor ou desempenho em aplicações de consumo não substituem uma
avaliação com endereços representativos da área de atuação dos gabinetes.

## Decisão

Adotar provisoriamente a seguinte composição:

- **Geoapify** como primeiro candidato para geocodificação e tiles;
- **MapLibre GL JS** como renderizador cartográfico no frontend;
- **PostgreSQL/PostGIS** como fonte de verdade para coordenadas, jurisdição, territórios,
  proveniência, confiança e histórico;
- malhas oficiais do IBGE e, quando disponíveis, dos municípios, versionadas no PostGIS;
- adaptador de geocodificação independente de fornecedor.

A promoção do Geoapify para produção depende da prova definida em
[`Territorial-geocoding-quality-proof.md`](../../implementation/Territorial-geocoding-quality-proof.md).
Google e Geocode Earth formam, com o Geoapify, o conjunto padrão de candidatos comparáveis.
Mapbox não integra o Gate C obrigatório porque o fluxo aprovado não depende de seus mapas ou
tiles e sua geocodificação permanente acrescenta uma condição comercial específica. O adaptador
Mapbox permanece disponível como comparador opcional, sem se tornar dependência do domínio.

A rodada de 700 casos executada em 10/08/2026 reprovou os três candidatos obrigatórios por metas
eliminatórias de qualidade. A decisão completa está em
[`Territorial-geocoding-gate-c-closure.md`](../../implementation/Territorial-geocoding-gate-c-closure.md).
Uma promoção futura exige nova rodada versionada; esta ADR não autoriza uso de provedor externo
em produção enquanto o Gate C permanecer reprovado.

## Contrato do adaptador

O domínio não recebe o payload bruto do fornecedor. Todo adaptador deve converter a resposta
para um contrato canônico contendo, no mínimo:

- identificador e versão do provedor;
- coordenadas em WGS 84;
- endereço normalizado por componente;
- tipo e granularidade do resultado;
- confiança original e confiança normalizada;
- estado `VERIFIED`, `APPROXIMATE`, `AMBIGUOUS`, `UNRESOLVED` ou
  `OUTSIDE_JURISDICTION`;
- instante, latência e identificador idempotente da consulta;
- atribuições e prazo de retenção aplicáveis.

Chaves, payloads brutos e regras específicas ficam no adaptador. Retentativas, timeout, circuit
breaker, quota e fallback são configuráveis por provedor. Nenhuma troca de fornecedor pode
alterar silenciosamente uma coordenada já verificada por pessoa.

## Condições de produção

- benchmark com 500 a 1.000 endereços representativos e sem vínculo com cidadãos;
- acerto municipal mínimo de 95%;
- metas de logradouro, número, bairro e jurisdição atendidas por segmento;
- retenção, suboperadores, LGPD, SLA, residência de dados e atribuições aprovados;
- plano comercial e limites de custo configurados;
- fila humana para ambiguidades, divergências e pontos externos;
- telemetria sem endereço, coordenada individual ou conteúdo pessoal;
- fallback nunca promove automaticamente um resultado conflitante para `VERIFIED`.

## Consequências

- desenvolvimento e homologação podem usar a franquia gratuita do Geoapify com dados públicos,
  sintéticos ou efetivamente anonimizados;
- produção exige plano e termos compatíveis com retenção e finalidade analítica;
- a base cartográfica pode mudar sem substituir MapLibre ou o contrato territorial;
- atribuições das fontes devem acompanhar mapa, exportações e metadados persistidos;
- existe custo adicional de integração, benchmark e operação do adaptador, compensado pela
  redução de lock-in e pelo controle da qualidade.

## Alternativas consideradas

- **Google Maps:** forte candidato de precisão, mas com restrições de retenção e combinação com
  mapas de terceiros incompatíveis com o uso como fonte histórica padrão sem contrato específico.
- **Mapbox Permanent Geocoding:** permite persistência, porém requer modalidade permanente e
  avaliação dos termos para uso analítico; foi mantido como comparador opcional, fora do conjunto
  padrão do Gate C.
- **Geocode Earth:** termos favoráveis à persistência e bom candidato a fallback, sujeito ao
  benchmark de cobertura local.
- **Nominatim público:** inadequado para carga recorrente de produção; uma instalação própria
  permanece alternativa futura caso escala e operação justifiquem.
