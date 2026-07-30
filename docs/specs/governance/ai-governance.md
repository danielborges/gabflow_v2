# Governança de IA

## Catálogo de casos de uso

Cada caso deve registrar:
- finalidade;
- proprietário;
- nível de risco;
- dados utilizados;
- modelo;
- prompt;
- métricas;
- fallback;
- necessidade de revisão;
- política de retenção.

## Níveis de risco

### Baixo
- resumo interno;
- extração de entidades;
- sugestão de tags.

### Médio
- sugestão de resposta;
- classificação de prioridade;
- detecção de duplicidade;
- geração de insights.

### Alto
- minuta legislativa;
- análise jurídica;
- comunicação pública;
- decisão com impacto individual.

## Controles

- prompts versionados;
- avaliação antes de produção;
- canary release;
- monitoramento de drift;
- limite de custo;
- bloqueio de PII desnecessária;
- red teaming;
- feedback humano;
- trilha de auditoria;
- rollback de modelo e prompt.

## Governança das fontes operacionais

Cada projetor de conhecimento deve possuir proprietário, módulo, tipos de entidade,
ações suportadas, allowlist de campos, critérios de aprovação, finalidade, base
legal, ACL, retenção, política de quarentena e política de purge.

A habilitação de um novo projetor exige:

- revisão de privacidade e ameaça de prompt injection;
- exemplos positivos, inelegíveis e maliciosos;
- testes de criação, atualização, exclusão, anonimização e expiração;
- avaliação de retrieval por tenant antes e depois da ampliação;
- plano de rollback que despublique as fontes derivadas sem afetar a origem.

Saídas produzidas por IA somente podem se tornar fonte operacional após estado de
aprovação humana compatível com o caso de uso.

## Governança do feedback e reaprendizado

Feedback não é aprovação automática de conteúdo nem autorização para treinamento.
O proprietário do caso de uso define taxonomia, papéis moderadores, quantidade
mínima de sinais, janela, decaimento, limites de influência e tolerâncias de
regressão.

Sinais estruturados de baixo risco podem seguir aprovação automática por regra
versionada. Texto livre, resposta corrigida, fonte indicada como ausente e mudança
de alto impacto exigem revisão humana. A ativação relevante deve respeitar
segregação entre autoria do sinal e aprovação do artefato.

Antes de ativar um artefato:

- sinais revogados, superados, rejeitados ou em quarentena são excluídos;
- candidato e baseline usam o mesmo dataset, versão de configuração e filtros;
- isolamento, ACL, vigência, jurisdição, recusa e prompt injection são testados;
- métricas antes/depois e justificativa ficam auditáveis;
- há versão anterior pronta para rollback;
- canário e alertas são definidos quando o impacto for relevante.

Uma correção humana somente vira exemplar quando fundamentada por fontes válidas e
aprovada. Exemplares são separados do contexto probatório e nunca podem ser
apresentados como citação.

A promoção para o dataset é uma ação explícita de gestor. O caso curado copia
somente a pergunta original, identificadores/versionamentos julgados, rota, filtros
e expectativa de recusa; comentário e resposta corrigida não são copiados. Uma
revisão origina no máximo um caso, e perda de aprovação ou elegibilidade desativa o
caso antes de nova execução.
