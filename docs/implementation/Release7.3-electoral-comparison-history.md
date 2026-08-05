# Release 7.3 — Início da comparação e do histórico eleitoral

## Entrega

Esta primeira fatia do Incremento 3 publica o recorte oficial 2020/MG/Vereador e habilita duas
eleições municipais comparáveis no piloto. O Parlamentar pode consultar o histórico de uma pessoa
e montar um comparativo territorial de duas a cinco candidaturas da mesma eleição.

## Carga-piloto 2020

- fonte: TSE, votação nominal por município e zona;
- versão publicada: `36690a44-884b-4ff7-9694-954dec002cc8`;
- 111.849 linhas, 10.335.608 votos, zero linhas inválidas e qualidade 1,0;
- Maurício Henrique Pinto de Oliveira Delgado: 25010/DEM, 4.106 votos em Juiz de Fora;
- denominador nominal municipal: 242.206 votos; participação 1,695251%; posição 6.

## Contratos

- `GET /api/v1/electoral/candidates/{candidate_id}/history`: reúne candidaturas publicadas pelo
  nome completo normalizado, mostra votos/participação/posição e avisa mudanças de partido, cargo
  e a necessidade de revisar limites territoriais.
- `POST /api/v1/electoral/comparisons`: aceita de duas a cinco candidaturas, rejeita duplicatas e
  exige mesma eleição, cargo, versão publicada e denominador territorial.

O vínculo histórico automático é identificado como não revisado para que homônimos não sejam
tratados como identidade confirmada. A revisão persistente de identidade faz parte da próxima
fatia do incremento.

## Interface

A pesquisa ganhou uma cesta de comparação limitada a cinco candidaturas. O comparativo alterna
entre votos, participação e posição e mantém o denominador visível. O detalhe individual exibe o
histórico e todos os avisos de comparabilidade.

## Próxima fatia

Persistir vínculos de identidade revisados, favoritos e comparações privadas por usuário. Em
seguida, carregar geometria oficial versionada e implementar mapa coroplético sincronizado com a
tabela, sem inventar polígonos para zonas que não tenham geometria oficial.
