# 2. Requisitos

## Requisitos funcionais

| ID | Requisito | Prioridade |
|---|---|---|
| FR-001 | Conectar uma WABA própria do tenant por Embedded Signup | Must |
| FR-002 | Associar `waba_id` e `phone_number_id` a exatamente um tenant ativo | Must |
| FR-003 | Validar webhook, responder rapidamente e processar de forma assíncrona | Must |
| FR-004 | Deduplicar eventos por identificador da Meta | Must |
| FR-005 | Receber texto, áudio, imagem, documento, contato e localização | Must |
| FR-006 | Exibir aviso de privacidade e registrar evidência de aceite/base | Must |
| FR-007 | Localizar cidadão pelo identificador WhatsApp dentro do tenant | Must |
| FR-008 | Cadastrar cidadão com dados mínimos e confirmação | Must |
| FR-009 | Criar solicitação por WhatsApp Flow ou diálogo guiado de contingência | Must |
| FR-010 | Gerar protocolo público não sequencial e não enumerável | Must |
| FR-011 | Transcrever áudio e indicar confiança/erro | Should |
| FR-012 | Sugerir resumo, categoria, bairro e urgência com justificativa | Must |
| FR-013 | Exigir validação humana para ações de alto impacto ou baixa confiança | Must |
| FR-014 | Consultar andamento após verificação proporcional de identidade | Must |
| FR-015 | Permitir handoff humano e impedir respostas automáticas concorrentes | Must |
| FR-016 | Enviar mensagens livres somente na janela permitida; fora dela usar template aprovado | Must |
| FR-017 | Registrar envio, entrega, leitura e falha | Must |
| FR-018 | Processar PARAR/SAIR/CANCELAR e equivalentes como opt-out | Must |
| FR-019 | Desconectar integração, revogar acesso e interromper processamento | Must |
| FR-020 | Permitir exportação/correção/exclusão ou anonimização conforme política | Must |
| FR-021 | Versionar Flows, templates, prompts e classificadores | Must |
| FR-022 | Disponibilizar painel de saúde e auditoria por tenant | Should |

## Regras de negócio

- BR-001: `phone_number_id` desconhecido vai para quarentena; nunca para tenant padrão.
- BR-002: um número ativo não pode pertencer a dois tenants.
- BR-003: todo acesso a dados operacionais exige contexto de tenant derivado no servidor.
- BR-004: números, tokens e segredos nunca são aceitos do frontend como fonte de autoridade.
- BR-005: o cidadão pode conversar sem fornecer CPF; documento só será solicitado se estritamente necessário.
- BR-006: mensagens ofensivas não eliminam o direito ao atendimento; ameaças reais seguem protocolo humano.
- BR-007: classificação da IA é sugestão e conserva texto original, versão do modelo e confiança.
- BR-008: o bot pausa ao iniciar handoff e só retorna por ação explícita ou timeout configurado.
- BR-009: o conteúdo de um tenant não compõe contexto RAG de outro.
- BR-010: templates devem ser transacionais e aprovados; marketing político fica desabilitado por padrão.
- BR-011: falha da IA não impede protocolo; usa fila/manual e coleta estruturada.
- BR-012: mensagens repetidas não criam solicitações duplicadas sem confirmação.

## Requisitos não funcionais

| ID | Requisito |
|---|---|
| NFR-001 | Disponibilidade mensal do processamento: 99,9% após piloto |
| NFR-002 | ACK do webhook dentro do limite da Meta; meta interna p95 < 500 ms |
| NFR-003 | Início do processamento assíncrono p95 < 5 s em operação normal |
| NFR-004 | Criptografia TLS em trânsito e criptografia gerenciada em repouso |
| NFR-005 | Segredos em cofre; rotação e menor privilégio |
| NFR-006 | RLS ou enforcement equivalente e testes negativos multi-tenant |
| NFR-007 | Logs estruturados com `tenant_id`, `correlation_id` e sem conteúdo bruto |
| NFR-008 | RPO <= 15 min e RTO <= 4 h para dados operacionais |
| NFR-009 | Acessibilidade WCAG 2.2 AA no painel administrativo |
| NFR-010 | Portabilidade: exportação legível e remoção do vínculo da WABA |

## Critérios de confiança da IA

- Confiança alta: preencher sugestão, sem executar transição irreversível.
- Confiança média: pedir confirmação ao cidadão ou assessor.
- Confiança baixa/entrada ambígua: encaminhar à fila humana.
- Urgência envolvendo risco à vida: mostrar orientação de emergência previamente aprovada e notificar humano; não prometer atendimento emergencial.
