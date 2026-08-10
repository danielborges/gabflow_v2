# Prova de qualidade de geocodificação — Gate C

## Objetivo e decisão

Comparar Geoapify, Google e Geocode Earth em condições reproduzíveis antes de promover um
provedor para produção. O Geoapify é o candidato provisório; o resultado da prova, e não a
preferência inicial, determina a decisão final. Mapbox pode ser incluído por decisão explícita
como comparador opcional, sem bloquear nem alterar o Gate C padrão.

**Amostra padrão:** 700 endereços. O ensaio pode variar entre 500 e 1.000 sem alterar o método.

## Formação da amostra

A dimensão geográfica deve conter aproximadamente:

| Segmento | Quantidade de referência |
| --- | ---: |
| área central | 200 |
| periferia urbana | 200 |
| zona rural | 150 |
| demais áreas representativas da jurisdição | 150 |

Em cada segmento, reservar de 15% a 25% para endereços incompletos. Variar endereço completo,
sem número, sem CEP, bairro informal/oficial, logradouro com abreviação e localidade rural.

Usar preferencialmente endereços de equipamentos públicos, logradouros oficiais e pontos de
referência verificáveis. Se um endereço operacional real for indispensável, remover qualquer
vínculo com cidadão, solicitação, telefone, documento ou identificador interno antes da extração.
A base de benchmark não pode permitir recompor o titular original.

## Verdade de referência

- validar município e jurisdição contra malha oficial versionada no PostGIS;
- validar logradouro, bairro e número usando fonte municipal/IBGE e revisão humana registrada;
- armazenar a fonte, versão da malha, data e revisor da verdade de referência;
- congelar o dataset por checksum antes da primeira execução;
- não alterar a referência depois de conhecer a resposta de um provedor sem registrar uma nova
  versão e justificativa.

## Execução reproduzível

1. Enviar o mesmo endereço normalizado a todos os candidatos, em execução próxima no tempo.
2. Aplicar país `BR` e a mesma jurisdição ou `bounding box`, quando suportado.
3. Desabilitar autocomplete; uma consulta corresponde a uma tentativa de geocodificação.
4. Persistir apenas o contrato canônico permitido e um hash da entrada no relatório comparativo.
5. Registrar versão da API, parâmetros, latência, código HTTP, quota e custo estimado.
6. Repetir uma amostra de 10% para avaliar estabilidade.
7. Submeter divergências e ambiguidades à revisão cega, sem revelar o nome do provedor.

Credenciais ficam em segredo de ambiente e nunca entram no repositório ou no dataset.

### Executor implementado

O backend fornece o comando `flask geocoding-benchmark`, com adaptadores para `geoapify`,
`google`, `mapbox` e `geocode-earth`. O executor:

- ordena os casos por `case_id` e registra o SHA-256 exato do CSV;
- executa provedores sequencialmente, com intervalo e timeout configuráveis;
- usa o `bbox` para orientar as consultas e, quando `--jurisdiction-tenant` é informado,
  classifica `OUTSIDE_JURISDICTION` pelo polígono GeoJSON oficial do gabinete;
- repete 10% da amostra, escolhida deterministicamente, para medir estabilidade;
- não grava a consulta textual nem o payload bruto no relatório;
- grava somente fingerprint da consulta, contrato canônico, avaliação, latência e erro tipado;
- publica resultados gerais e segmentados, distribuição por status, distâncias, custos,
  gates e decisão por provedor em JSON;
- escreve o relatório de maneira atômica.

O relatório registra o SHA-256 da geometria normalizada utilizada, permitindo comprovar que
execuções posteriores avaliaram exatamente a mesma jurisdição. Em ensaios de Gate C,
`--jurisdiction-tenant` é obrigatório; o retângulo isolado não representa adequadamente limites
municipais irregulares.

O conjunto padrão executado quando `--provider` não é informado contém `geoapify`, `google` e
`geocode-earth`. O adaptador `mapbox` permanece selecionável explicitamente.
Na amostra padrão de 700 casos, com repetição de 10%, isso representa 2.310 consultas antes de
eventuais retentativas; incluir Mapbox acrescenta outras 770 consultas.

Variáveis exigidas para o conjunto padrão:

```text
GEOAPIFY_API_KEY
GOOGLE_MAPS_API_KEY
GEOCODE_EARTH_API_KEY
```

`MAPBOX_ACCESS_TOKEN` é exigida somente quando `--provider mapbox` for informado.

Formato CSV obrigatório:

```csv
case_id,segment,incomplete,query,expected_number,expected_street,expected_neighborhood,expected_city,expected_state,expected_postcode,expected_latitude,expected_longitude,expected_inside_jurisdiction
```

Os segmentos aceitos são `central`, `periferia`, `rural` e `demais`. Campos de referência
desconhecidos podem ficar vazios e são excluídos do denominador da respectiva métrica. Município
e classificação de jurisdição são obrigatórios. Aliases oficiais podem ser informados nos
campos textuais de referência separados por `|`.

Exemplo de execução no ambiente Docker, montando um diretório local não versionado:

```powershell
docker compose run --rm `
  -v "${PWD}/benchmark:/benchmark" `
  migrate flask geocoding-benchmark `
  --dataset /benchmark/dataset.csv `
  --output /benchmark/report.json `
  --cost-per-thousand geoapify=1.00 `
  --cost-per-thousand google=5.00 `
  --cost-per-thousand geocode-earth=1.00 `
  --bbox=-43.60,-22.00,-43.10,-21.50 `
  --jurisdiction-tenant gabinete-demo
```

Os custos do exemplo são ilustrativos e devem ser substituídos pelos valores contratuais vigentes.

Sem `--provider`, o comando compara os três candidatos obrigatórios. Para escolher um subconjunto,
repetir `--provider` com os nomes desejados. Para incluir o comparador opcional, acrescentar
`--provider mapbox` e configurar sua credencial e custo contratual. A opção
`--allow-small-sample` existe exclusivamente para smoke tests; sem ela, o comando rejeita menos
de 500 ou mais de 1.000 casos. O relatório deve ser tratado como artefato restrito mesmo sem o
texto original, pois contém coordenadas e componentes normalizados retornados pelos provedores.

## Métricas e metas mínimas

| Dimensão | Métrica | Meta para aprovação |
| --- | --- | ---: |
| município | correspondência exata normalizada | **≥ 95% geral** |
| jurisdição | classificação dentro/fora correta | **≥ 99%** e zero ponto externo promovido a `VERIFIED` |
| logradouro | correspondência exata ou alias oficial | **≥ 90% em endereço urbano completo; ≥ 85% geral** |
| número | ponto no lote/edificação ou interpolação correta identificada | **≥ 75% em endereço urbano completo** |
| bairro | bairro oficial ou alias governado correto | **≥ 85% onde houver referência** |
| resolução | resposta utilizável sem revisão | **≥ 85% em endereço completo** |
| estabilidade | mesma granularidade e distância aceitável na repetição | **≥ 98%** |

Relatar também distância em metros para pontos com referência, mediana, P90 e P95 de latência,
taxa de `AMBIGUOUS`/`UNRESOLVED`, falsos positivos e custo por mil endereços. Resultados rurais e
incompletos não podem ser ocultados pela média geral.

## Pontuação e eliminação

Entre candidatos que cumprirem todas as metas obrigatórias, aplicar:

| Critério | Peso |
| --- | ---: |
| qualidade por segmento | 45% |
| retenção, privacidade, atribuição e ausência de lock-in proibitivo | 25% |
| disponibilidade, SLA, latência e suporte | 15% |
| custo total estimado | 10% |
| simplicidade do adaptador e operação | 5% |

É eliminatório: impedir a persistência necessária, proibir o uso cartográfico pretendido, não
oferecer base jurídica/suboperadores verificáveis, ficar abaixo de 95% no município ou aceitar
automaticamente ponto externo como verificado.

## Evidências jurídicas e operacionais

Antes de produção, anexar à decisão:

- termos de retenção e exclusão dos resultados e logs de consulta;
- lista e localização dos suboperadores;
- DPA e avaliação LGPD de controlador/operador e transferência internacional;
- SLA, suporte, rate limits, política de indisponibilidade e encerramento;
- regras de atribuição no mapa, exportações e relatórios;
- estimativa mensal por cenário e limites de orçamento;
- procedimento de exportação, migração e desligamento do fornecedor.

## Saída do Gate C

O relatório final deve conter dataset/checksum, versão do executor, matriz de resultados,
divergências revisadas, custos, parecer jurídico e decisão `APROVADO`, `APROVADO COM RESSALVAS`
ou `REPROVADO`. Até essa decisão, o Geoapify permanece aprovado somente para desenvolvimento e
homologação controlada.

## Resultado da rodada de 10/08/2026

O Gate C foi encerrado como **REPROVADO**, sem promoção de provedor para produção. A amostra
congelada de 700 casos foi executada contra Geoapify, Google e Geocode Earth; nenhum candidato
atendeu simultaneamente todas as metas eliminatórias. O relatório detalhado permanece como
artefato restrito e a decisão sanitizada, os checksums e as condições para nova rodada estão em
[`Territorial-geocoding-gate-c-closure.md`](Territorial-geocoding-gate-c-closure.md).
