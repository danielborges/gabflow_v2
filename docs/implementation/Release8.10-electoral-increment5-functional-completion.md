# Release 8.10 — Acabamento funcional do Incremento 5

## Objetivo

Esta release reabre e encerra as três lacunas práticas que permaneceram após a Release 7.9:
o overlay sem crosswalk operacional, alertas que existiam apenas como feed e a ausência de
gestão visual do perfil versionado do ICT.

## Crosswalk territorial revisado

- o parlamentar associa um território operacional do gabinete a uma ou mais unidades
  eleitorais pertencentes à eleição selecionada;
- o vínculo registra autor, data, método e nota de revisão, pode ser desativado e nunca é
  inferido automaticamente por semelhança de nome;
- ao gerar um snapshot com eleição e candidatura, os votos das unidades vinculadas são
  materializados no próprio payload do território, garantindo reprodutibilidade histórica;
- a camada eleitoral continua separada dos indicadores operacionais: o campo
  `electoral_performance_used` permanece `false` e os votos não alteram pesos, metas, ICT ou
  alertas de atendimento.

## Entrega e histórico de alertas

- frequência imediata é materializada durante a criação do snapshot;
- frequências diária e semanal são avaliadas pelo scheduler do worker;
- entregas `IN_APP` são registradas como concluídas e entregas `EMAIL` usam o outbox e o
  provedor de e-mail já adotado pelo GabFlow;
- a chave composta por preferência, snapshot, evento e canal impede duplicidade;
- cada usuário consulta seu histórico com canal, estado, horário, território e eventual erro.

## Gestão visual do ICT

- o painel do mandato permite revisar pesos, metas e justificativa;
- salvar cria uma nova versão, preservando os snapshots e perfis anteriores;
- a interface explicita que os pesos devem somar 100% e que resultados eleitorais não entram
  na fórmula.

## Contratos e segurança

- novos contratos: `GET/POST /electoral/territory-links`,
  `DELETE /electoral/territory-links/{link_id}` e `GET /electoral/alert-deliveries`;
- tabelas novas usam RLS forçada por tenant; leitura do histórico também é filtrada pelo
  usuário autenticado;
- somente o parlamentar pode criar ou desativar vínculos e versionar o ICT;
- snapshots continuam sujeitos ao limiar de privacidade e à generalização de categorias.

## Homologação mínima

1. Vincular um território operacional a uma zona da eleição selecionada.
2. Gerar snapshot com a candidatura do parlamentar e confirmar o total contextual de votos.
3. Confirmar que o ICT é idêntico antes e depois do vínculo para os mesmos dados operacionais.
4. Ativar alerta imediato no GabFlow, gerar snapshot e conferir uma única entrega no histórico.
5. Criar uma nova versão de pesos e confirmar que snapshots antigos conservam configuração e
   hash originais.
