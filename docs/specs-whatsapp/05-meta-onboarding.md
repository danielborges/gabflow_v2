# 5. Meta, onboarding e lifecycle

## Preparação do GabFlow

1. Criar Business Portfolio verificado do GabFlow e aplicativo Meta exclusivo.
2. Adicionar produto WhatsApp e configurar Cloud API.
3. Solicitar acesso avançado às permissões necessárias, especialmente mensageria e gerenciamento.
4. Concluir registro como Tech Provider e App Review com screencast e usuário de teste.
5. Configurar Embedded Signup, domínios, redirect URIs, webhook e verify token.
6. Publicar política de privacidade, termos, exclusão de dados e contato do encarregado.
7. Separar aplicativos/credenciais de desenvolvimento, homologação e produção.

Os nomes exatos de permissões, versões da Graph API, requisitos de revisão, preços e políticas devem ser conferidos na documentação oficial no momento da implantação.

## Embedded Signup do tenant

1. Administrador autenticado inicia `POST /tenants/{tenantId}/whatsapp/onboarding-sessions`.
2. Backend valida papel, ausência de integração conflitante e gera estado anti-CSRF de uso único.
3. Frontend abre o Embedded Signup.
4. Gabinete autentica-se na Meta, seleciona/cria portfolio, WABA e número e concede acesso.
5. Callback envia `code` e `state` ao backend; o código nunca é persistido no browser.
6. Backend troca código por credencial apropriada, registra número na Cloud API e assina a WABA nos webhooks.
7. Backend consulta metadados oficiais, verifica unicidade e salva referência do segredo no cofre.
8. Teste de saúde confirma webhook e envio controlado.
9. Integração passa a `ACTIVE`; auditoria registra administrador e objetos vinculados.

## Validações de ativação

- Estado/nonce válido e não reutilizado.
- Usuário é administrador do tenant.
- WABA e número retornados pela Meta, não pelo formulário local.
- Número não está ativo em outro tenant.
- Nome de exibição e status do número são aceitáveis.
- Método de cobrança do cliente está configurado quando exigido.
- Webhook está assinado e teste ponta a ponta foi concluído.

## Reconexão e troca de número

- Reconexão preserva histórico, mas cria nova versão da integração.
- Troca de número exige janela de manutenção e confirmação reforçada.
- O mapeamento antigo fica inativo antes de o novo se tornar ativo.
- Eventos atrasados do número antigo continuam correlacionáveis, sem iniciar novas conversas.

## Desconexão/offboarding

1. Confirmar ação com autenticação reforçada.
2. Suspender envios e novos processamentos.
3. Revogar/invalidar credenciais e assinatura quando aplicável.
4. Marcar integração `DISCONNECTED` e preservar trilha mínima.
5. Permitir exportação antes da política de retenção/exclusão.
6. Nunca reatribuir histórico ao novo proprietário de um número reciclado.

## WhatsApp Flows

- Flow `citizen_registration`: nome, forma de tratamento, cidade/bairro e aceite/ciência.
- Flow `new_service_request`: categoria, assunto, descrição, local, urgência declarada e confirmação.
- Flow `request_complement`: campos faltantes solicitados pelo assessor.
- Cada publicação possui versão, hash e ambiente.
- Endpoint de dados valida assinatura/autenticidade, tenant, versão, estado da conversa e esquema.
- Se Flow estiver indisponível, usar perguntas sequenciais com retomada segura.
