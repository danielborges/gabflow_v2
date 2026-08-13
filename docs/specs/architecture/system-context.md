# Arquitetura — Contexto

## Atores externos

- Cidadão
- Assessor
- Chefe de Gabinete
- Vereador
- Administrador
- Administrador Global de Conhecimento
- Órgãos municipais
- Câmara Municipal
- Provedores de mensageria
- Provedores de IA
- Serviço de mapas e geocodificação
- Sistemas legislativos e de protocolo heterogêneos, acessados exclusivamente pela porta canônica e por adaptadores tenant-scoped do ADR-013
- APIs públicas e bases normativas homologadas

## Sistemas externos

- WhatsApp Business
- E-mail
- Google/Microsoft Calendar
- Portal da Câmara
- Sistema de Processo Legislativo
- Diário Oficial
- Portal de Transparência
- Armazenamento de objetos
- Provedor OIDC
- Serviço de mapas

## Fronteiras

O GabFlow não substitui:
- serviço de emergência;
- sistema oficial de protocolo legislativo;
- sistema corporativo da Prefeitura;
- decisão jurídica;
- decisão política ou administrativa humana.

## Fronteira de integração legislativa

O GabFlow não assume fornecedor, API ou disponibilidade de integração. O modo `MANUAL`
é o adaptador padrão. Quando um gabinete habilita conector externo, o domínio continua
isolado pelo contrato canônico, por capabilities e por operações assíncronas idempotentes.
Configuração e estado são exclusivos do tenant; segredos permanecem fora do banco
funcional. Consulte o [ADR-013](../adr/ADR-013-generic-legislative-integration.md).
