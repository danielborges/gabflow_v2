# Release 7.4 — Persistência privada, geometria oficial e mapa

## Entrega

Esta release conclui o Incremento 3 do módulo Inteligência Eleitoral. O Parlamentar pode revisar
vínculos históricos, favoritar objetos, salvar comparações e explorar resultados municipais em
mapa coroplético. Dados privados permanecem isolados por gabinete e usuário.

## Persistência privada

- `electoral_identity_reviews`: decisão `CONFIRMED` ou `REJECTED` para pares de candidaturas;
- `electoral_favorites`: candidato, território ou comparação com snapshot público minimizado;
- `electoral_saved_comparisons`: nome, eleição, duas a cinco candidaturas, nível e filtros;
- RLS obrigatório por `app.tenant_id` e `app.user_id`, além dos filtros equivalentes na aplicação;
- auditoria para revisão, criação, consulta e exclusão.

O histórico continua usando nome completo normalizado quando ainda não há revisão. Depois da
confirmação, a resposta muda para `human_review` e deixa de apresentar o aviso de homônimo.

## Geometria oficial

A carga `electoral-import-geometry` consome a API de Malhas do IBGE por HTTPS, descompacta a
resposta gzip, valida o GeoJSON, calcula SHA-256 e preserva o recurso bruto. A versão piloto é:

- referência: Malha Municipal Digital 2024/MG;
- qualidade: intermediária;
- sistema de referência: SIRGAS 2000 / EPSG:4326;
- 853 municípios com `MULTIPOLYGON` válido e índice GiST;
- 853 vínculos TSE–IBGE, sendo os aliases históricos/pontuação registrados como revisados.

O crosswalk registra método, status de revisão e observação. Geometria e crosswalk possuem versão
independente do resultado eleitoral, permitindo avisar quando uma eleição usa malha de outro ano.

## Mapa sincronizado

`GET /api/v1/electoral/candidates/{candidate_id}/map` devolve uma `FeatureCollection` com votos,
participação, posição e variação frente à candidatura histórica anterior. Mapa e tabela compartilham
o código territorial selecionado. A interface oferece teclado, fonte, ano e versão da malha.

O nível `electoral_zone` nunca reutiliza ou inventa polígonos municipais: retorna
`geometry_available=false`, lista vazia e aviso para usar tabela/ranking.

## Critérios verificados

- favorito e comparação de um usuário não aparecem para outro gabinete/usuário;
- revisão humana altera o método de identidade somente no escopo privado do revisor;
- sexto candidato continua rejeitado;
- todas as geometrias publicadas estão preenchidas e formam união PostGIS válida;
- os 853 municípios eleitorais de MG possuem crosswalk para o código IBGE;
- zonas sem fonte geométrica oficial permanecem sem desenho.
