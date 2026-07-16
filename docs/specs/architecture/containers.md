# Arquitetura — Contêineres

## Aplicação Web

- gestão de atendimento;
- dashboards;
- administração;
- revisão de IA;
- produção legislativa.

## API Backend

Responsável por:
- autenticação e autorização;
- regras de negócio;
- APIs;
- auditoria;
- orquestração.

## Worker Assíncrono

Responsável por:
- transcrição;
- OCR;
- classificação;
- geocodificação;
- notificações;
- indexação;
- geração de relatórios.

## Serviço de IA

Camada de abstração para:
- provedores de LLM;
- prompts versionados;
- políticas;
- mascaramento;
- avaliação;
- fallback.

## Serviço RAG

Responsável por:
- ingestão;
- parsing;
- chunking;
- embeddings;
- recuperação híbrida;
- reranking;
- citações;
- controle de acesso.

## Banco Transacional

Sugestão:
- PostgreSQL;
- PostGIS para geodados;
- row-level security quando aplicável.

## Armazenamento de Objetos

- anexos;
- áudios;
- documentos;
- versões;
- relatórios.

## Índice de Busca

- busca textual;
- filtros;
- agregações;
- busca híbrida.

## Barramento de Eventos

- desacoplamento;
- integração;
- processamento assíncrono;
- auditoria operacional.
