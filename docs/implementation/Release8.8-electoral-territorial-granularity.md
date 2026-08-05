# Release 8.8 — Granularidade territorial eleitoral

## Lacuna corrigida

O resultado eleitoral aceitava apenas município e zona. A Release 8.8 adiciona uma
extensão territorial versionada ao dataset publicado, sem alterar nem duplicar o seu
resultado-base, para oferecer bairro, local de votação e seção conforme RF-021.

## Fontes e proveniência

- votação por seção eleitoral do TSE, particionada por ano e UF;
- eleitorado por local de votação do TSE, usado para nome, endereço, bairro e coordenadas;
- hash, URL, parser, arquivos de origem, totais e qualidade preservados por versão;
- reconciliação bloqueante entre a soma nominal por seção e o total do dataset-base.

Local e seção são recortes oficiais. Bairro é agregado a partir do bairro declarado no
cadastro do local de votação e, conforme RN-014, sempre retorna `derived=true`,
`mapping_type=DERIVED` e aviso metodológico. Nenhum polígono de bairro, local ou seção é
inventado.

## Operação

```bash
flask electoral-import-territories --dataset-id <uuid>
```

O comando baixa as duas fontes oficiais correspondentes ao ano e à UF do dataset. Para
homologação ou reprocessamento controlado, `--section-file` e `--location-file` aceitam
arquivos já baixados. A repetição dos mesmos hashes é idempotente e uma versão territorial
mais nova substitui a anterior sem apagar seu histórico.

## Consulta

`GET /api/v1/electoral/candidates/{candidate_id}/results` passa a aceitar:

- `municipality`;
- `electoral_zone`;
- `neighborhood`;
- `polling_place`;
- `section`.

Os níveis efetivamente disponíveis são devolvidos em `available_levels`. Uma eleição sem
extensão territorial continua retornando `422` para os três níveis detalhados, sem sugerir
que existe informação que ainda não foi importada.

## Homologação piloto

A extensão oficial de 2024/MG foi publicada com 3.465.464 resultados nominais em 50.973
seções. Os 24.390.246 votos reconciliaram exatamente com o dataset-base, nenhuma linha
válida foi rejeitada e 100% das seções foram vinculadas a bairro no cadastro de locais.

Após restringir o cálculo aos territórios onde a candidatura consultada possui resultado,
as consultas reais de homologação ficaram em 0,23 s para bairro, 0,15 s para local e
0,05 s para seção, sem contar inicialização do processo de linha de comando.
