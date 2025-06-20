from datetime import datetime

def gerar_mensagem(loja, chamados):
    blocos = []
    for ch in chamados:
        # Cabeçalho fixo
        linhas = [
            f"*{ch['key']}*",
            f"*Loja:* {loja}",
            f"*PDV:* {ch.get('pdv','--')}",
            f"*ATIVO:* {ch.get('ativo','--')}",
            f"*Problema:* {ch.get('problema','--')}"
        ]
        # Data Agendada: somente se existir
     

        # Separador e demais campos
        linhas.append("*****")
        linhas.extend([
            f"*Endereço:* {ch.get('endereco','--')}",
            f"*Estado:* {ch.get('estado','--')}",
            f"*CEP:* {ch.get('cep','--')}",
            f"*Cidade:* {ch.get('cidade','--')}"
        ])

        blocos.append("\n".join(linhas))

    return "\n\n".join(blocos)


def verificar_duplicidade(chamados):
    """
    Retorna um set de tuplas (pdv, ativo) que aparecem mais de uma vez,
    para sinalizar duplicidade.
    """
    seen = {}
    duplicates = set()
    for ch in chamados:
        key = (ch.get("pdv"), ch.get("ativo"))
        if key in seen:
            duplicates.add(key)
        else:
            seen[key] = True
    return duplicates
