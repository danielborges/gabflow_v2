# RIPD — Inteligência Eleitoral e Territorial

Versão: 1.0
Data: 2026-08-03
Estado: **minuta técnica concluída; aprovação formal pendente**

## 1. Identificação

| Papel | Identificação | Estado |
|---|---|---|
| Controlador | Gabinete ou órgão público contratante do GabFlow | Deve ser nominalmente identificado |
| Operador | Pessoa jurídica responsável pela operação do GabFlow | Deve ser confirmada contratualmente |
| Encarregado | Encarregado indicado pelo controlador | Pendente |
| Responsável técnico | Equipe de engenharia do GabFlow | Revisão técnica concluída |
| Jurídico | Assessoria jurídica do controlador e/ou operador | Parecer pendente |

Cada gabinete controlador deve aprovar sua própria finalidade, hipótese legal e configuração.
Este relatório não transfere ao operador a decisão jurídica que cabe ao controlador.

## 2. Projeto e finalidade

O módulo permite que parlamentar autorizado consulte resultados eleitorais oficiais e
agregados, compare candidaturas, visualize geometrias oficiais e gere relatórios internos
auditáveis. O MVP não executa propaganda, microdirecionamento, inferência de voto individual,
seleção de cidadãos, decisão automatizada sobre serviço público ou integração entre voto e
ficha individual de cidadão.

Finalidades propostas para validação pelo controlador:

1. transparência e análise institucional de resultados eleitorais oficiais;
2. planejamento territorial agregado do mandato;
3. produção de relatórios internos reproduzíveis e auditáveis;
4. prestação de contas e governança do acesso ao módulo.

## 3. Inventário do tratamento

| Categoria | Dados | Fonte | Escopo e retenção |
|---|---|---|---|
| Candidaturas | nome civil, nome de urna, número, partido, cargo e situação | Dados Abertos do TSE | Dataset oficial permanente e versionado |
| Resultados | votos e indicadores agregados por município ou zona | Dados Abertos do TSE | Dataset oficial permanente e versionado |
| Geometria | código e malha territorial | IBGE | Versão oficial permanente |
| Usuários | identificador, gabinete, perfil e capacidades | GabFlow | Enquanto houver vínculo e conforme política do controlador |
| Auditoria | ator, ação, data, finalidade e recurso | GabFlow | Conforme política de auditoria e obrigação aplicável |
| Exportações | recorte agregado, autoria, finalidade, fonte e versão | GabFlow | 30 dias por padrão; metadados de auditoria preservados |

O módulo trata dados publicamente disponíveis de pessoas candidatas, inclusive filiação
partidária, que pode revelar opinião política. A natureza pública da fonte não afasta os
princípios de finalidade, adequação, necessidade, transparência, segurança, prevenção e não
discriminação.

## 4. Operações e fluxo

1. O pipeline obtém arquivos oficiais do TSE, registra origem e hash e valida o esquema.
2. Uma versão imutável somente é publicada após validação e controle de qualidade.
3. O parlamentar consulta dados agregados; cada acesso relevante produz auditoria.
4. Comparações exigem mesma eleição e denominador declarado.
5. O mapa utiliza somente geometria oficial versionada; ausência de geometria não cria
   polígonos artificiais.
6. Exportações são processadas de forma assíncrona, cifradas e disponibilizadas por link
   temporário assinado.
7. Expiração ou revogação bloqueia o download e a limpeza remove o objeto cifrado.

Não há transferência internacional identificada no MVP local. Hospedagem, observabilidade,
backup, e-mail ou outros subprocessadores de produção devem ser inventariados antes da
assinatura.

## 5. Hipótese legal — decisão pendente do controlador

A engenharia não fixa automaticamente a hipótese legal. O controlador deve documentá-la por
finalidade, considerando sua natureza jurídica e competência. Para órgão público, a análise
deve considerar a finalidade pública, o interesse público e a execução de competências ou
atribuições legais. Se houver finalidade privada ou eleitoral, devem ser avaliadas as hipóteses
legais correspondentes, as normas do TSE e as limitações para dados sensíveis.

O portal do TSE autoriza acesso, uso, tratamento e compartilhamento de seus dados abertos para
geração de novas informações e controle social. Essa autorização de uso da fonte não substitui
a definição da hipótese legal nem autoriza finalidade incompatível, perfilamento individual ou
propaganda eleitoral.

## 6. Necessidade e proporcionalidade

Controles presentes no MVP:

- resultados apenas agregados; nenhuma informação de eleitor individual;
- ausência de vínculo entre resultado eleitoral e cidadão, endereço ou solicitação;
- acesso opt-in e restrito ao parlamentar, com delegação explícita e temporária;
- segregação por tenant e por usuário em recursos privados;
- RLS forçada, autenticação, capacidades e auditoria;
- finalidade obrigatória nas exportações;
- criptografia AES-256-GCM, SHA-256, expiração, revogação e limpeza;
- fonte, versão, denominador e metodologia visíveis;
- IA, cenários e camadas do mandato fora do MVP ativo.

## 7. Riscos e mitigação

Escala: probabilidade e impacto de 1 a 5. Risco inerente e residual são classificados pelo
produto `P x I`: baixo 1–4, médio 5–9, alto 10–16 e crítico 17–25.

| Risco | Inerente | Medidas existentes | Residual |
|---|---:|---|---:|
| Inferência ou microdirecionamento de eleitor | 4x5 = 20 | Sem dado individual, sem drill-down, agregação e escopo funcional explícito | 2x5 = 10 |
| Condicionar serviço público ao desempenho eleitoral | 3x5 = 15 | Regra proibitiva, ausência de automação decisória e separação de domínios | 2x5 = 10 |
| Acesso indevido ou vazamento de exportação | 4x4 = 16 | JWT, capacidade, token curto, AES-GCM, retenção, revogação e auditoria | 2x4 = 8 |
| Reutilização incompatível para propaganda | 3x5 = 15 | Finalidade registrada, marca d'água, acesso restrito e auditoria | 2x5 = 10 |
| Associação histórica incorreta de identidade | 3x4 = 12 | Vínculos revisáveis, fonte, alertas e versionamento | 2x4 = 8 |
| Geometria ou comparação enganosa | 3x4 = 12 | Malha oficial, ausência explícita, denominador e avisos de comparabilidade | 1x4 = 4 |
| Retenção excessiva | 3x3 = 9 | Exportações por 30 dias e limpeza agendada | 1x3 = 3 |
| Papel controlador/operador ou subprocessadores indefinidos | 4x4 = 16 | Bloqueio de produção e exigência contratual | 2x4 = 8 após formalização |
| Resposta insuficiente a incidente | 3x5 = 15 | Logs, hash e revogação; runbook nominal ainda pendente | 2x5 = 10 |

Riscos residuais altos impedem expansão para cidadãos, IA ou propaganda. Para o MVP agregado,
a aceitação desses riscos depende de decisão documentada do controlador e do encarregado.

## 8. Direitos, transparência e segurança

Antes da produção, o aviso de privacidade deve informar controlador, operador, encarregado,
finalidades, categorias de dados, fontes, compartilhamentos, retenção, medidas de segurança e
canais para exercício de direitos. O procedimento deve permitir localizar e corrigir vínculos
de identidade e responder a solicitações aplicáveis sem alterar o resultado oficial do TSE.

O plano de incidentes deve definir detecção, contenção, preservação de evidências, avaliação de
risco ou dano relevante, comunicação ao controlador, à ANPD e aos titulares quando aplicável,
além dos prazos e responsáveis vigentes.

## 9. Pareceres e aprovação

| Aprovação | Responsável | Decisão/data | Condições |
|---|---|---|---|
| Engenharia e segurança | Equipe GabFlow | Aprovado tecnicamente em 2026-08-03 | Manter controles e testes do gate |
| Controlador | A indicar | Pendente | Definir finalidade, hipótese legal e risco residual aceito |
| Encarregado | A indicar | Pendente | Validar transparência, direitos, incidentes e revisão contínua |
| Jurídico | A indicar | Pendente | Validar LGPD, normas eleitorais, contrato e subprocessadores |

Sem as três aprovações pendentes, o módulo não está autorizado para produção ampla.

## 10. Revisão contínua

Revisar este RIPD ao menos anualmente e antes de qualquer mudança que inclua dados de cidadãos,
camadas do mandato, categorias sensíveis, IA, cenários, propaganda, novo subprocessador,
transferência internacional, nova granularidade ou alteração normativa.

## 11. Referências oficiais consultadas

- Lei nº 13.709/2018 — LGPD, texto compilado:
  https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709compilado.htm
- ANPD — Relatório de Impacto à Proteção de Dados Pessoais:
  https://www.gov.br/anpd/pt-br/canais_atendimento/agente-de-tratamento/relatorio-de-impacto-a-protecao-de-dados-pessoais-ripd
- ANPD — Guia orientativo para tratamento pelo Poder Público:
  https://www.gov.br/anpd/pt-br/centrais-de-conteudo/materiais-educativos-e-publicacoes/guia_orientativo_tratamento_de_dados_pessoais_pelo_poder_publico
- TSE/ANPD — Guia de aplicação da LGPD no contexto eleitoral:
  https://www.tse.jus.br/o-tse/catalogo-de-publicacoes/lista-do-catalogo-de-publicacoes/publicacoes/g/guia-orientativo-aplicacao-da-lei-geral-de-protecao-de-dados-pessoais-lgpd
- TSE — Portal de Dados Abertos:
  https://dadosabertos.tse.jus.br/pt_BR/
- TSE — Resolução nº 23.610/2019, texto compilado:
  https://www.tse.jus.br/legislacao/compilada/res/2019/resolucao-no-23-610-de-18-de-dezembro-de-2019
