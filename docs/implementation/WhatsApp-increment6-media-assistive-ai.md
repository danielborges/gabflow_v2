# WhatsApp Business Platform - Incremento 6

## Objetivo

Receber áudio, imagem e documento sem aumentar a latência do webhook e transformar o conteúdo
em contexto assistivo para a equipe. A IA sugere; a decisão e a classificação continuam humanas.

## Pipeline assíncrono

1. O webhook valida, deduplica, persiste a referência opaca da Meta e responde antes de download,
   verificação ou IA.
2. `WhatsappMediaDownloadRequested` baixa o objeto pelo adaptador de runtime, valida o SHA-256,
   tamanho e MIME, executa antivírus e grava o arquivo com AES-256-GCM.
3. `WhatsappMediaAnalysisRequested` transcreve áudio ou executa OCR em imagem/documento.
4. Texto, confiança, provedor, modelo e versão de prompt ficam pendentes de revisão humana.
5. Quando há solicitação vinculada, o anexo e os artefatos de transcrição/OCR existentes são
   reutilizados e uma triagem assistiva sugere resumo, categoria, bairro e urgência.

Falha no download, antivírus ou provedor de IA possui retry separado e não desfaz mensagem,
conversa ou protocolo. Arquivos sem análise aplicável continuam disponíveis como anexos.

## Segurança e privacidade

- isolamento por tenant em todas as FKs e consultas;
- referência da Meta não é exposta ao navegador;
- conteúdo criptografado em repouso e descriptografado apenas em arquivo temporário;
- download autenticado com URL assinada de curta duração;
- resultado assistivo exige aceitar, corrigir ou rejeitar;
- logs registram IDs e tipos de erro, nunca texto, arquivo ou credencial;
- `retention_until` torna o prazo configurável e auditável.

O adaptador real da Cloud API deve resolver a credencial da integração apenas em runtime no AWS
Secrets Manager. O incremento não lê nem replica segredos; sem o gate externo o trabalho entra em
retry controlado, preservando a referência recebida.

## Interface

A conversa exibe uma área de mídias com estado de verificação/processamento, confiança,
transcrição ou OCR editável, revisão humana, download curto e reprocessamento de falhas. A triagem
principal identifica as fontes de mídia utilizadas, mas mantém o fluxo de aprovação já existente.

## Critérios de saída

- áudio, imagem e documento normalizados e deduplicados;
- ACK independente de download e IA;
- armazenamento criptografado, antivírus e URL curta;
- transcrição/OCR com confiança e rastreabilidade de modelo/prompt;
- revisão humana antes do uso definitivo;
- mídia vinculada a solicitação sem duplicar o subsistema de anexos;
- indisponibilidade da IA não bloqueia protocolo;
- API, interface, migração, OpenAPI, AsyncAPI, BDD e testes alinhados.
