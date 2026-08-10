# Fluxo Geoapify para desenvolvimento e homologação

## Objetivo

Permitir que usuários autorizados consultem e visualizem resultados reais do Geoapify sem
transformar a integração em autorização de produção. O fluxo opera por solicitação, registra
proveniência e exige revisão humana para o estado `VERIFIED`.

## Ativação

Configure somente no ambiente de desenvolvimento ou homologação:

```text
APP_ENV=homologation
GEOAPIFY_API_KEY=<segredo do ambiente>
GEOCODING_HOMOLOGATION_ENABLED=true
GEOCODING_HOMOLOGATION_DAILY_LIMIT=100
GEOCODING_HOMOLOGATION_TIMEOUT_SECONDS=12
VITE_TERRITORIAL_MAP_ENABLED=true
VITE_GEOAPIFY_MAP_API_KEY=<chave-publica-restrita-por-dominio>
```

A flag nasce desligada. Mesmo com flag e credencial, `APP_ENV=production` bloqueia o endpoint.
Alterações de configuração exigem reinicialização do serviço de API.
As variáveis `VITE_*` são incorporadas durante o build do frontend; por isso, exigem uma nova
imagem do serviço web. O mapa interativo também valida `VITE_APP_ENV` e só inicia em
`development`, `homologation`, `staging` ou `test`.

Use projetos ou credenciais distintas para os dois consumos:

- `GEOAPIFY_API_KEY` é segredo exclusivo do backend e atende à geocodificação;
- `VITE_GEOAPIFY_MAP_API_KEY` é necessariamente visível no navegador, atende somente aos tiles
  do mapa e deve ser limitada no painel Geoapify aos domínios de desenvolvimento/homologação.

## Uso na aplicação

1. Abra uma solicitação que tenha endereço.
2. Na seção **Localização com Geoapify**, confirme que o dado pertence à homologação e está
   autorizado para consulta externa.
3. Use **Consultar Geoapify**. A resposta aparece com coordenadas, confiança, estado, atribuição
   e link de mapa.
4. Confira o endereço no mapa e na fonte oficial da jurisdição.
5. Registre justificativa e escolha **Aprovar localização** ou **Rejeitar**.

Na aba **Visão geral > Inteligência territorial**, a mesma homologação apresenta o mapa base
Geoapify com navegação, limites oficiais da jurisdição, mapa de calor e pontos autorizados. Um
clique em uma célula ou ponto que possua território seleciona o mesmo recorte na tabela. Com a
flag desligada, chave ausente, ambiente de produção ou falha de inicialização, a interface usa a
representação cartográfica local de contingência.

Somente `ADMIN` e `MANAGER` consultam e revisam. Outros perfis com acesso à solicitação podem
visualizar o estado e a indicação de revisão pendente, mas não acionam o provedor.

## Controles

- limite de dez chamadas por minuto no endpoint;
- cota diária por gabinete, contabilizada em auditoria;
- endereço e coordenadas não são copiados para o evento de auditoria de consumo;
- a consulta exige confirmação explícita de dado de teste autorizado;
- geometria oficial prevalece sobre o retângulo de busca ao classificar ponto externo;
- resposta automática `VERIFIED` do provedor é rebaixada para `APPROXIMATE`;
- localização já verificada por uma pessoa não pode ser sobrescrita por nova consulta;
- ponto externo ou sem coordenadas não pode ser aprovado;
- aprovação e rejeição registram usuário, instante, decisão e justificativa;
- rejeição remove a coordenada ativa e o ponto deixa de alimentar o mapa territorial;
- chave de geocodificação permanece somente no segredo do backend;
- chave pública de tiles é segregada, restrita por domínio e não autoriza geocodificação;
- o frontend bloqueia o mapa Geoapify quando `VITE_APP_ENV=production`.

## Relação com o Gate C

Este fluxo não altera a reprovação do Gate C e não autoriza geocodificação externa em produção.
Ele existe para homologar a experiência, revisar divergências e formar evidências para uma nova
rodada versionada do gate. Geoapify continua sendo candidato, não fornecedor aprovado.
