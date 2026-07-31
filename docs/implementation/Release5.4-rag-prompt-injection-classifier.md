# Release 5.4 — canonicalização e classificador de prompt injection

## Resultado

O gateway de segurança combina duas camadas independentes antes de permitir que
conteúdo não confiável gere artefatos RAG:

1. canonicalização defensiva, limitada e auditada por IDs de transformação;
2. classificador dedicado com modelo diferente do gerador de respostas.

A canonicalização cobre NFKC, caracteres invisíveis, HTML, URL encoding,
Base64, hexadecimal, espaçamento entre caracteres, acentos e typos de vocabulário
de segurança. Entrada e conteúdo decodificado possuem limites configuráveis.

## Contrato e falha fechada

O classificador retorna exclusivamente `label`, `score` e `categories`. Campos
adicionais, categorias desconhecidas, JSON inválido, timeout ou indisponibilidade
são rejeitados. Quando o controle é obrigatório, a decisão é
`INDETERMINATE/RETRY`; não existe fallback implícito para `CLEAN`.

O estado persistido não inclui texto de entrada ou explicação livre do modelo.
Mantém apenas provider, modelo, versão, label, score e categorias allowlisted.

## Providers

- `ollama`: provider padrão de produção, com saída estruturada;
- `http`: contrato externo `POST /v1/prompt-injection`;
- `local`: detector reproduzível para testes e contingência explicitamente configurada.

## Validação

O dataset adversarial do incremento 5.1 agora é executado contra o gateway. Ele
cobre ataques diretos, indiretos, multilíngues, codificados, ofuscados, persistentes,
multimodais e distribuídos, além de controles benignos para falsos positivos.
