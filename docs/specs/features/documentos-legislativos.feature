# language: pt
Funcionalidade: Geração assistida de documentos legislativos

  Cenário: Criar indicação a partir de uma solicitação
    Dado que a solicitação contém fatos, local e órgão competente
    Quando o assessor solicitar uma minuta de indicação
    Então o sistema deve gerar um rascunho
    E deve relacionar a minuta à solicitação
    E deve apontar fontes utilizadas
    E deve exigir revisão humana antes da aprovação

  Cenário: Ausência de fundamentação
    Dado que não há fonte normativa suficiente
    Quando a IA gerar uma minuta
    Então o sistema deve marcar a fundamentação como pendente
    E não deve inventar dispositivo legal
