# Release 8.2.1 — acabamento funcional de cenários

## Resultado

A release transforma as APIs da 8.2 em jornadas completas de produto, sem alterar a
semântica imutável dos cenários ou atribuir confiança estatística às faixas.

## Jornadas entregues

- tela documental para a URL `/inteligencia-eleitoral/cenarios/compartilhado/{token}`;
- visualização somente leitura de premissas, dataset, metodologia, totais, faixas e
  detalhamento territorial;
- criação de links com validade configurável entre 1 e 30 dias e cópia imediata da URL;
- gestão de links emitidos com status, expiração, acessos e revogação;
- cópia com edição prévia de deltas, incertezas e justificativas;
- comparação com totais, diferenças, intervalos e tabela territorial lado a lado;
- sensibilidade com amplitudes configuráveis, grades ímpares de 3×3 a 11×11 e tabela de
  amostras;
- mensagens explícitas de que faixas e comparações não são previsões.

## Segurança

- a tela compartilhada continua exigindo autenticação, mandato ativo, feature flag,
  capacidade `consultar_dados_publicos` e o mesmo tenant;
- a gestão exige `criar_cenario` e respeita autoria para usuários delegados;
- tokens antigos não aparecem na listagem e não podem ser reconstruídos do hash;
- expiração e revogação retornam HTTP 410;
- nenhuma jornada oferece atualização de um cenário persistido.

## Homologação

- testes backend cobrem gestão, expiração, revogação e comparação incompatível;
- testes frontend cobrem editor de cópia, validade do link, parâmetros de sensibilidade,
  comparação territorial e ausência de ações de escrita na tela compartilhada;
- OpenAPI e cenários Gherkin foram atualizados.
