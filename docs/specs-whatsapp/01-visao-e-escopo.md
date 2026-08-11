# 1. Visão e escopo

## Problema

Gabinetes recebem mensagens não estruturadas, áudios, fotos e localizações por WhatsApp. O atendimento manual dificulta triagem, protocolo, acompanhamento e produção de inteligência territorial. O GabFlow deve transformar a conversa em atendimento rastreável sem retirar do gabinete a propriedade do número, da WABA ou da relação com o cidadão.

## Objetivos

1. Identificar o tenant pelo número que recebeu a mensagem.
2. Cadastrar ou localizar o cidadão com transparência e minimização de dados.
3. Capturar solicitações por conversa e WhatsApp Flows.
4. Interpretar texto e áudio, sugerindo classificação e resumo.
5. Criar protocolo e permitir acompanhamento pelo WhatsApp.
6. Encaminhar para assessor e permitir atendimento humano.
7. Manter isolamento, auditoria, consentimento e exclusão conforme LGPD.

## Atores

- **Cidadão:** inicia conversa, cadastra-se, cria e acompanha solicitações.
- **Assessor:** atende, corrige classificação, responde e altera andamento.
- **Chefe de gabinete:** configura filas, SLAs, modelos e permissões.
- **Administrador do tenant:** conecta a WABA e administra integração.
- **Administrador GabFlow:** monitora integração sem acessar conteúdo por padrão.
- **Meta:** entrega mensagens, status, Flows e templates pela Cloud API.

## Escopo MVP

- Embedded Signup; conexão/desconexão e diagnóstico.
- Recebimento de texto, áudio, imagem, documento e localização.
- Consentimento, cadastro mínimo do cidadão e nova solicitação.
- WhatsApp Flow de cadastro/solicitação.
- Transcrição de áudio, resumo e classificação assistida.
- Protocolo, consulta de andamento e notificações transacionais.
- Handoff humano, caixa de entrada e trilha de auditoria.
- Opt-out, bloqueio, retenção e métricas operacionais.

## Fora do MVP

- Campanhas políticas, disparos em massa e segmentação eleitoral persuasiva.
- Um número central compartilhado por gabinetes.
- Treinamento de modelos públicos com conversas dos cidadãos.
- Decisões automáticas sobre prioridade social ou concessão de benefícios.
- Faturamento consolidado via linha de crédito do GabFlow.

## Jornada principal

1. O cidadão envia uma mensagem ao número institucional do gabinete.
2. O webhook é autenticado, persistido de forma idempotente e roteado pelo `phone_number_id`.
3. O GabFlow informa finalidade e privacidade e registra a base aplicável/consentimento quando necessário.
4. A intenção é detectada: nova solicitação, acompanhamento, falar com assessor, descadastro ou dúvida.
5. Para nova solicitação, um Flow coleta os campos estruturados; anexos permanecem na conversa.
6. A IA gera transcrição, resumo, categoria e sinais de urgência como sugestões.
7. Regras determinísticas validam dados e criam o protocolo.
8. O assessor revisa e atende; o cidadão recebe atualizações permitidas.
