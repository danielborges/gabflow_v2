# Release 9 — Estratégia do diretório de cidadãos e organizações v2

## Resultado esperado

Transformar o diretório atual em uma ferramenta de atendimento rápido, profissional e
responsiva. O usuário deve localizar uma pessoa, revisar seu contexto, cadastrar ou
corrigir dados e iniciar uma solicitação sem alternar entre modais ou redigitar
informações.

Esta release cobre o diretório e o cadastro assistido. A criação automática a partir de
WhatsApp e e-mail permanece em descoberta arquitetural e será entregue somente como
sugestão sujeita a revisão humana.

## Estado da implementação nesta branch

Incrementos 9.1 a 9.5 concluídos nesta branch:

- migração aditiva e modelos para profissão, nascimento, CPF protegido, título de eleitor,
  VIP, autoria, versão e vínculo cidadão–organização;
- unicidade de CPF por tenant com HMAC, conteúdo cifrado e resposta de conflito que aponta
  para o cadastro existente;
- endpoints de busca segura e verificação preventiva de CPF/homônimo;
- formulário de cidadão integrado à página, sem modal, com agenda alfabética responsiva;
- novos campos, Search-Select de organizações, marcador VIP e metadados de atendimento;
- histórico de solicitações no detalhe, abertura direta da solicitação e criação de nova
  solicitação com cidadão pré-selecionado;
- testes de backend/frontend, lint e build executados.
- captura explícita pela câmera ou seleção de arquivo, com prévia, substituição e remoção;
- foto privada com limite de tamanho/pixels, validação do tipo real, antimalware,
  recorte quadrado, remoção de EXIF, reencodificação WebP e criptografia AES-GCM;
- endereço estruturado pelo Google Places, revalidado no backend, com bairro derivado,
  limites da jurisdição e associação normalizada a território ativo;
- estados visíveis para território resolvido, não encontrado, bairro não identificado e
  endereço fora da jurisdição.
- administração de aliases e geometrias GeoJSON `Polygon`/`MultiPolygon` por território,
  com importação de arquivo, validação e prevenção de nomes ambíguos;
- resolução geoespacial ponto-em-polígono prioritária e fallback por nome/alias, expondo
  o método que determinou o território.
- agenda, solicitações e histórico funcional paginados por cursores opacos assinados;
- histórico funcional sem valores pessoais, com usuário, ação, campos alterados e versão;
- concorrência otimista por `ETag`/`If-Match`, retornando `412` para edição desatualizada;
- linha do tempo unificada, deep link do cidadão, preservação da busca e proteção contra
  saída com alterações não salvas;
- métricas agregáveis do fluxo sem registrar termos de busca ou outros dados pessoais.
- ingestão idempotente de WhatsApp/e-mail, resolvedor determinístico tenant-safe e fila de
  revisão para vincular cidadão existente ou descartar a sugestão;
- contato mascarado, metadados allowlisted, auditoria mínima, ADR e threat model dos canais.

Permanecem para os próximos cortes: base legal padrão configurável, visualização
cartográfica dos polígonos, SLA operacional da fila e criação manual pré-preenchida.

## Diagnóstico da versão atual

| Capacidade | Estado atual | Lacuna para v2 |
| --- | --- | --- |
| Cadastro/edição | formulário em modal | deve integrar a dinâmica da tela |
| Campos | nome, nome social, contatos, endereço, canal, base legal e consentimentos | faltam foto, profissão, nascimento, documentos, VIP, metadados e organizações |
| Consulta | grade de cartões e busca por nome/nome social | falta agenda alfabética, busca ampla, paginação e detalhe contextual |
| Duplicidade | sem CPF e sem detecção de homônimo | CPF deve bloquear; homônimo deve orientar reutilização |
| Território | endereço textual; organização tem território livre | bairro e território devem ser derivados do endereço |
| Solicitações | API de detalhe já retorna histórico | a tela não apresenta nem navega por esse histórico |
| Auditoria | eventos de criação/correção já existem | falta autoria explícita no modelo e visão funcional de alterações |
| Organizações | cadastro separado | falta vínculo de responsabilidade via Search-Select |

## Experiência proposta

### Desktop e tablet horizontal

A página usa padrão mestre–detalhe:

1. coluna de agenda com busca fixa, índice alfabético e resultados compactos;
2. painel de detalhe/formulário que ocupa o restante da largura;
3. cabeçalho do detalhe com foto, nome, estrela VIP e ações `Salvar` e
   `Nova solicitação`;
4. seções progressivas: dados principais, contato/endereço, documentos e privacidade,
   organizações, solicitações e histórico de alterações;
5. ações principais permanecem visíveis em barra aderente, sem encobrir foco ou erros.

Selecionar uma pessoa troca o painel de detalhe; `Novo cidadão` limpa esse painel. Se
houver alterações não salvas, a troca exige confirmação. A URL deve representar o estado
selecionado (`/diretorio/cidadaos/:id`) para suportar recarregamento e retorno.

### Mobile

A agenda e o detalhe tornam-se duas etapas da mesma rota, não um modal. O botão voltar
retorna à posição, letra e busca anteriores. Campos usam uma coluna, alvos de toque de no
mínimo 24 por 24 CSS pixels e barra de ações que não oculta o foco.

### Agenda telefônica

- nome de exibição: nome social, quando informado, com nome civil como informação de apoio;
- agrupamento por primeira letra normalizada, com `#` para nomes sem letra inicial;
- índice lateral habilitado somente para grupos retornados;
- busca com debounce por nome, nome social, CPF normalizado, telefone e e-mail;
- CPF nunca aparece completo no item; contato principal e bairro podem diferenciar homônimos;
- navegação por teclado, foco visível, anúncio de quantidade e estados de carregamento;
- paginação por cursor para evitar o limite fixo de 100 registros da versão atual.

### Formulário e campos derivados

| Campo | Regra de entrada | Persistência/exibição |
| --- | --- | --- |
| Foto | opcional; câmera ou arquivo; prévia e remoção | arquivo privado, sem implicar autorização de divulgação |
| Nome | obrigatório, mínimo de 2 caracteres úteis | usado na detecção de homônimos |
| Nome social | opcional | preferido na apresentação ao usuário |
| Telefone/e-mail | opcionais; validar quando preenchidos | normalizados, com indicação do canal preferencial |
| Endereço | opcional; seleção validada ou texto preservado | dispara geocodificação |
| Bairro/território | sem edição direta | derivados, com estado pendente/não encontrado |
| Profissão | opcional | texto controlado inicialmente; catálogo futuro não bloqueia a release |
| Data de nascimento | opcional; não futura | data sem fuso horário |
| CPF | opcional; algoritmo oficial e onze dígitos | HMAC para busca/unicidade e valor cifrado para recuperação autorizada |
| Título de eleitor | opcional; validação estrutural configurável | cifrado e ausente de listas/logs |
| Organizações | Search-Select acessível | vínculo N:N com papel `RESPONSAVEL` |
| Canal preferencial | opcional | só pode apontar para canal disponível ou presencial |
| Base legal | seleção opcional no cadastro rápido | valor explícito ou padrão governado pelo tenant; nunca inferido arbitrariamente |
| Autorizações | independentes e inicialmente desmarcadas | histórico imutável por finalidade |
| VIP | booleano interno | estrela com nome/estado acessível e auditoria |
| Cadastrado em | somente leitura | `created_at` |
| Último contato | somente leitura | última interação/tentativa vinculada |
| Atendido por | somente leitura | ator do último contato ou responsável da solicitação mais recente |

## Regras de duplicidade

### CPF

O front-end pode consultar preventivamente a duplicidade, mas a garantia final é uma
restrição única parcial no banco por `tenant_id` e `cpf_lookup_hash`. O endpoint de criação
ou edição responde `409 CPF_DUPLICADO` com `cidadaoId` e nome de exibição acessíveis ao
mesmo tenant. A interface mantém os dados digitados e oferece abrir o cadastro existente.

CPF deve ser enviado no corpo de requisição, nunca em query string. Busca digitada deve
ser enviada por `POST /cidadaos/busca-segura` quando contiver documento; a busca textual
comum pode continuar em `GET`, sem registrar o termo em logs de acesso.

### Homônimos

A primeira versão compara nome civil e social após caixa baixa, remoção de espaços
duplicados e equivalência de acentos. O retorno mostra apenas nome de exibição, contato
mascarado, bairro e data de nascimento parcial, quando disponíveis. Homônimo não bloqueia:
o usuário pode reutilizar ou confirmar `Criar mesmo assim`; essa decisão entra na auditoria.

Não haverá mesclagem automática. Uma futura mesclagem precisa tratar solicitações,
consentimentos, organizações, agenda, privacidade e trilha de auditoria de forma transacional.

## Arquitetura de dados

### Migração aditiva

1. adicionar em `citizens` profissão, nascimento, referência de foto, CPF cifrado/HMAC,
   final do CPF, título cifrado, VIP e `created_by_id`;
2. criar `citizen_organization_links` com FKs compostas por tenant;
3. criar `citizen_addresses` com geocódigo, bairro, território e estado de resolução;
4. manter `contacts` e `addresses` JSON durante a compatibilidade, executar backfill e
   leitura dupla controlada antes de remover qualquer campo legado;
5. criar índices de pesquisa por nome normalizado, contato normalizado e letra inicial;
6. aplicar RLS/FORCE RLS e validar isolamento nos testes PostgreSQL.

O HMAC de CPF usa chave derivada/versionada por tenant para igualdade e unicidade; o valor
recuperável usa o padrão de criptografia autenticada já adotado no projeto. Rotação de
chave exige reindexação controlada do HMAC e deve evitar janela sem restrição de unicidade.

### Foto

A foto utiliza o pipeline privado de anexos: MIME real permitido (`image/jpeg`,
`image/png` ou `image/webp`), limite de tamanho, varredura, remoção de metadados EXIF,
redimensionamento e miniatura. O navegador solicita câmera apenas após gesto explícito em
HTTPS, encerra todas as tracks depois da captura/cancelamento e oferece input de arquivo
como fallback. O atributo HTML `capture` é melhoria progressiva, não dependência única.

### Território

Ao selecionar endereço, o front envia `placeId`, texto estruturado e coordenadas quando
disponíveis. O backend é a autoridade: normaliza, geocodifica quando necessário e resolve
território por ponto-em-polígono na configuração do tenant. Falhas ficam como `PENDENTE`,
`NAO_ENCONTRADO` ou `FORA_DA_JURISDICAO` e podem ser reprocessadas de forma idempotente.

## Contratos de API

- `GET /cidadaos`: agenda por texto não sensível, letra, VIP, cursor e limite;
- `POST /cidadaos/busca-segura`: busca por CPF ou contato sem colocar PII na URL;
- `POST /cidadaos/verificar-duplicidade`: candidatos por CPF e nome antes do save;
- `POST /cidadaos` e `PATCH /cidadaos/{id}`: contrato único de criação/edição;
- `GET /cidadaos/{id}`: detalhe, metadados derivados, organizações e resumo;
- `GET /cidadaos/{id}/solicitacoes`: histórico paginado;
- `GET /cidadaos/{id}/historico`: alterações funcionais autorizadas;
- `PUT` e `DELETE /cidadaos/{id}/foto`: substituição/remoção idempotente;
- `GET /organizacoes?q=`: resultados compactos para Search-Select;
- `POST /enderecos/resolver`: prévia de bairro/território; o save sempre revalida.

Os contratos devem usar `ETag` ou versão do registro em atualizações para evitar que dois
atendentes sobrescrevam alterações silenciosamente.

## Ingestão por WhatsApp e e-mail

### Arquitetura proposta para descoberta

```text
Webhook/caixa postal -> adaptador do provedor -> evento canônico idempotente
-> normalizador de identidade -> resolvedor determinístico
-> cidadão existente OU sugestão pendente -> revisão humana -> persistência/auditoria
```

Cada adaptador valida assinatura/origem, usa o identificador da mensagem como chave de
idempotência e publica um envelope semântico comum. O resolvedor compara telefone/e-mail
normalizados somente dentro do tenant. Correspondência única pode pré-selecionar; nenhuma
correspondência cria sugestão; múltiplas correspondências exigem escolha. Conteúdo livre de
mensagem não preenche automaticamente campos de identidade e não deve entrar em logs.

Antes de implementar conectores, registrar ADR com provedores, retenção, opt-out, replay,
dead-letter, limites, observabilidade e responsabilidades de controlador/operador. O MVP
de canal deve ser feature-flagged por tenant e começar apenas com fila de sugestões.

## Auditoria, privacidade e segurança

- registrar criação, campos alterados, consentimentos, documentos, foto, VIP, vínculos e
  decisão sobre homônimo; o usuário de criação é imutável;
- separar histórico funcional visível de log técnico; mascarar PII e nunca registrar
  binário, CPF/título completos, endereço ou mensagem bruta;
- autorizar listagem, detalhe, foto, solicitações e histórico pelo mesmo tenant e perfil;
- manter autorizações de contato e divulgação independentes e inicialmente falsas;
- validar o catálogo e a base legal padrão com o encarregado; o software não deve inferir
  uma base legal apenas pelo tipo de usuário ou canal, e deve bloquear a persistência se
  não conseguir resolver uma hipótese válida;
- preservar direitos de acesso, correção, revogação e eliminação conforme os fluxos de
  privacidade já existentes.

## Acessibilidade e qualidade de UX

Meta: WCAG 2.2 nível AA. Search-Select segue o padrão WAI-ARIA de combobox/listbox, com
setas, Enter, Escape, `aria-expanded`, `aria-controls`, opção ativa e anúncio de resultados.
Ícone, cor ou posição nunca são o único meio de comunicar VIP, consentimento, erro ou
seleção. Erros ficam próximos aos campos e o resumo leva foco ao primeiro erro.

Metas de piloto, a validar com usuários reais de gabinete:

- mediana de até 45 segundos para cadastro mínimo em dispositivo móvel;
- até 3 ações principais para localizar cidadão e iniciar solicitação;
- busca percebida em até 300 ms no percentil 95, excluindo latência de rede externa;
- zero perda silenciosa de edição por navegação ou conflito concorrente;
- testes com teclado, leitor de tela, zoom de 200%, câmera negada e conexão degradada.

## Plano de entrega

### 9.1 — Fundação e contratos

- migrações aditivas, criptografia/HMAC, índices e RLS;
- contratos OpenAPI, modelos de domínio e compatibilidade com JSON legado;
- testes de CPF único, isolamento, auditoria e concorrência.

### 9.2 — Diretório e formulário

- **Entregue:** layout mestre–detalhe responsivo e rotas profundas;
- **Entregue:** agenda alfabética paginada, barra A–Z com disponibilidade global por tenant,
  filtro por nome social/civil e busca segura;
- **Entregue:** cartões enriquecidos com contatos, localidade, profissão, preferência de canal
  e VIP, sem exibir documentos pessoais;
- formulário unificado, VIP, campos somente leitura e proteção de edição não salva;
- validação automatizada de acessibilidade e testes de interação.

### 9.3 — Foto, endereço e organizações

- câmera/upload com fallback e processamento seguro;
- resolução de bairro/território e reprocessamento;
- Search-Select de organizações e vínculo N:N.

### 9.4 — Solicitações e auditoria funcional

- lista paginada, deep link para solicitação e nova solicitação pré-vinculada;
- histórico de alterações autorizado e métricas de uso do fluxo.

### 9.5 — Canais assistidos

- **Entregue:** ADR-010 e threat model dos conectores Meta/Resend;
- **Entregue:** `ChannelMessage` como envelope canônico, idempotência por origem, resolvedor determinístico e fila tenant-safe;
- **Entregue:** revisão explícita para vincular cadastro existente ou descartar sugestão, sem criação ou mesclagem automática;
- **Entregue:** mascaramento de contato, allowlist de metadados e auditoria sem conteúdo livre.

### 9.6 — Operação e conclusão do cadastro assistido

- **Entregue:** configuração tenant-scoped de base legal padrão, SLA e retenção;
- **Entregue:** atribuição de responsável, filtros operacionais, contadores, vencimento,
  métricas de conclusão e reabertura justificada;
- **Entregue:** preparação do formulário com nome e contato sugeridos pelo envelope, exigindo
  confirmação humana independente de nome, contato e base legal;
- **Entregue:** validação normal de CPF e homônimos antes da criação e vínculo atômico entre
  cidadão, revisão e mensagem somente depois do salvamento definitivo;
- **Entregue:** proveniência por identificadores opacos no histórico e na auditoria, sem copiar
  conteúdo livre ou contato para logs;
- **Entregue:** minimização manual e auditada de envelopes concluídos após o prazo configurado,
  preservando os identificadores e a decisão da revisão;
- **Invariante preservada:** mensagens nunca criam, mesclam ou sobrescrevem cidadãos sem a
  revisão e a confirmação explícitas de um usuário autenticado.

### 9.7 — Gestão cartográfica territorial

- **Entregue:** mapa administrativo com a malha oficial da jurisdição e sobreposição dos
  territórios ativos e inativos;
- **Entregue:** seleção sincronizada entre mapa e tabela, identificação visual do território
  e exibição dos aliases usados pela resolução automática;
- **Entregue:** desenho de `Polygon` e de múltiplas partes `MultiPolygon`, fechamento
  automático do anel e importação GeoJSON como alternativa;
- **Entregue:** edição por arraste, teclado ou coordenadas, remoção de vértice e de parte do
  território, preservando o contrato GeoJSON longitude/latitude;
- **Entregue:** painel de métricas com partes e vértices, layout responsivo e fallback avançado
  para edição textual do GeoJSON;
- **Entregue:** persistência pelos endpoints administrativos já auditados, com validação de
  tipo, limites, fechamento dos anéis, colisões de nomes e aliases e isolamento por tenant.

Cada incremento deve poder ser ativado por feature flag e possuir rollback sem perda dos
dados já gravados. A remoção dos campos JSON legados só ocorre após backfill verificado,
período de leitura dupla e aprovação operacional.

## Estratégia de testes

- unidade: normalização/validação, HMAC, homônimos, projeções de metadados e estados;
- integração PostgreSQL: unicidade concorrente, FKs compostas, RLS, auditoria e paginação;
- contrato: OpenAPI para 201/409/412/422 e mascaramento de respostas;
- componentes: teclado, foco, erros, edição, câmera negada e retorno à agenda;
- ponta a ponta: cadastrar, detectar duplicidade, vincular organização, abrir solicitação,
  editar e consultar histórico em desktop e viewport móvel;
- segurança: autorização horizontal, upload malicioso, EXIF, PII em URL/log e replay de webhook;
- migração: backfill idempotente, comparação legado/novo e rollback de aplicação.

## Decisões a validar antes da implementação

1. confirmar catálogo e governança das bases legais com privacidade/jurídico;
2. confirmar se título de eleitor terá somente número ou também zona e seção;
3. confirmar papéis possíveis além de `RESPONSAVEL` no vínculo com organização;
4. definir limites, recorte e política de retenção da foto;
5. escolher provedores e modelo operacional de WhatsApp/e-mail no ADR da etapa 9.5;
6. validar as metas de tempo e a arquitetura mestre–detalhe em teste de usabilidade com
   assessores antes de estabilizar o design.

## Referências de implementação

- W3C, WCAG 2.2: https://www.w3.org/TR/WCAG22/
- W3C WAI-ARIA APG, Combobox: https://www.w3.org/WAI/ARIA/apg/patterns/combobox/
- MDN, `MediaDevices.getUserMedia()`: https://developer.mozilla.org/docs/Web/API/MediaDevices/getUserMedia
- MDN, atributo HTML `capture`: https://developer.mozilla.org/docs/Web/HTML/Reference/Attributes/capture
- ANPD, Direitos dos titulares: https://www.gov.br/anpd/pt-br/assuntos/titular-de-dados-1/direito-dos-titulares
- ANPD, FAQ sobre hipóteses legais: https://www.gov.br/anpd/pt-br/acesso-a-informacao/perguntas-frequentes/perguntas-frequentes
