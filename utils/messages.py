# utils/messages.py
from datetime import datetime

def gerar_mensagem(loja, chamados):
    """
    Gera mensagem textual por loja.
    Endereço aparece apenas uma vez ao final.
    """
    blocos = []
    endereco_info = None

    for ch in chamados:
        linhas = [
            f"*{ch.get('key','--')}*",
            f"Loja: {loja}",
            f"PDV: {ch.get('pdv','--')}",
            f"*ATIVO: {ch.get('ativo','--')}*",
            f"Problema: {ch.get('problema','--')}",
            "***",
        ]
        blocos.append("\n".join(linhas))

        endereco_info = (
            ch.get('endereco','--'),
            ch.get('estado','--'),
            ch.get('cep','--'),
            ch.get('cidade','--'),
        )

    if endereco_info:
        blocos.append(
            "\n".join([
                f"Endereço: {endereco_info[0]}",
                f"Estado: {endereco_info[1]}",
                f"CEP: {endereco_info[2]}",
                f"Cidade: {endereco_info[3]}",
            ])
        )

    return "\n\n".join(blocos)

def verificar_duplicidade(chamados):
    """
    Retorna pares (pdv, ativo) duplicados.
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
