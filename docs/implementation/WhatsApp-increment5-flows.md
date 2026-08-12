# WhatsApp Business Platform - Incremento 5

## Objetivo

Adicionar coleta estruturada por WhatsApp Flows sem tornar a jornada dependente da
disponibilidade do recurso da Meta. O incremento entrega tres formularios: cadastro minimo do
cidadao, nova solicitacao e complemento de solicitacao.

## Versionamento e ativacao

Cada tenant possui definicoes isoladas por `flow_key`, versao e ambiente. O ambiente e derivado
no servidor. A definicao guarda o schema canonico, as telas e o SHA-256 desse conteudo. Na
ativacao, o hash e recalculado; uma definicao alterada depois de versionada e recusada.

Somente administradores podem preparar definicoes, criar versoes e associar o `meta_flow_id`
publicado. A ativacao aposenta atomicamente a versao ativa anterior. Respostas em transito
continuam vinculadas a versao exata usada no envio.

## Sessao e recebimento

O disparo cria uma sessao de 30 minutos vinculada ao tenant, conversa, definicao e operador. O
token aleatorio aparece somente no comando `WhatsappFlowLaunchRequested`; a sessao persiste
apenas seu hash SHA-256. Uma nova sessao substitui qualquer sessao pendente anterior.

O webhook oficial `interactive/nfm_reply` e normalizado pelo pipeline confiavel do Incremento 2.
Antes de aplicar dados, o processador valida:

- assinatura do webhook no ponto de entrada;
- hash do token, tenant, conversa, versao e validade da sessao;
- deduplicacao por mensagem da Meta e hash da resposta;
- lista estrita de campos, tipos, limites, enums e confirmacoes;
- pre-requisitos de privacidade e identidade da jornada.

Campos desconhecidos, token invalido, sessao expirada e schema invalido sao rejeitados sem retry
infinito e sem criar solicitacao. A confirmacao de nova solicitacao usa chave idempotente derivada
da sessao e produz protocolo publico nao enumeravel.

## Fallback e interface

Quando nao existe definicao ativa, o disparo muda a conversa para coleta de dados e publica
`WhatsappGuidedCollectionStarted`. O formulario guiado do Incremento 4 permanece disponivel, sem
perda da conversa ou dos dados ja revisados.

Em Administracao, gestores consultam as versoes e administradores preparam, versionam e ativam
Flows. Na Caixa de Entrada, a equipe dispara o Flow adequado, ve a sessao pendente e continua com
o formulario manual quando a Meta estiver indisponivel.

## Persistencia

- `whatsapp_flow_definitions`: schema, hash, versao, ambiente e ciclo de ativacao;
- `whatsapp_flow_sessions`: vinculo contextual e hash do token, sem token em claro;
- `whatsapp_flow_submissions`: nomes dos campos recebidos, hashes de idempotencia, resultado e
  solicitacao; valores com PII sao minimizados na mesma transacao;
- `whatsapp_request_drafts.declared_urgency`: urgencia declarada pelo cidadao, separada de futura
  classificacao assistiva.

Todas as referencias operacionais usam tenant e FKs compostas. A resposta bruta permanece no
evento de webhook sujeito a minimizacao; mensagens da caixa nao recebem uma segunda copia do
payload do Flow.

## Limite operacional

Os formularios atuais sao estaticos e nao exigem endpoint dinamico de data exchange. Se uma
versao futura introduzir telas dinamicas, o endpoint criptografado e a rotacao das chaves da Meta
devem ser implementados antes da publicacao dessa versao.

O envio real pela Cloud API depende do dispatcher consumir `WhatsappFlowLaunchRequested` e
resolver a credencial exclusivamente em runtime pelo cofre aprovado. Enquanto esse gate externo
nao estiver promovido, o outbox conserva a ordem auditavel e o fallback guiado garante a jornada.

## Criterios de saida

- tres Flows canonicos, versionados por tenant e ambiente;
- ativacao controlada e versoes anteriores preservadas;
- token em claro ausente da sessao persistida;
- `nfm_reply` valido aplicado ao dominio principal;
- replay e campos desconhecidos sem duplicacao ou mutacao parcial;
- protocolo criado idempotentemente pelo Flow de solicitacao;
- fallback guiado explicito;
- APIs, interface, migracao, OpenAPI, AsyncAPI, BDD e testes alinhados.
