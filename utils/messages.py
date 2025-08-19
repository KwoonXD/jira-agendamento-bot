# utils/messages.py
from datetime import datetime


def gerar_mensagem(loja, chamados):
    """
    Gera uma mensagem para um grupo de chamados da mesma loja,
    listando cada FSA e, ao final, exibindo uma única vez o bloco de endereço.

    Parâmetros:
        loja (str): Nome/código da loja.
        chamados (list[dict]): Lista de dicts com chaves:
            key, pdv, ativo, problema, endereco, estado, cep, cidade, data_agendada

    Retorna:
        str: Texto formatado.
    """
    blocos = []
    endereco_info = None  # (endereco, estado, cep, cidade)

    for ch in chamados:
        # Cabeçalho de cada FSA
        linhas = [
            f"*{ch.get('key', '--')}*",
            f"Loja: {loja}",
            f"PDV: {ch.get('pdv', '--')}",
            f"*ATIVO: {ch.get('ativo', '--')}*",
            f"Problema: {ch.get('problema', '--')}",
            "***",
        ]
        blocos.append("\n".join(linhas))

        # Armazena endereço (o último sobrescreve; para um mesmo grupo deve ser igual)
        endereco_info = (
            ch.get("endereco", "--"),
            ch.get("estado", "--"),
            ch.get("cep", "--"),
            ch.get("cidade", "--"),
        )

    # Após listar todos, adiciona o bloco de endereço apenas uma vez
    if endereco_info:
        blocos.append(
            "\n".join(
                [
                    f"Endereço: {endereco_info[0]}",
                    f"Estado: {endereco_info[1]}",
                    f"CEP: {endereco_info[2]}",
                    f"Cidade: {endereco_info[3]}",
                ]
            )
        )

    return "\n\n".join(blocos)


def verificar_duplicidade(chamados):
    """
    Retorna um set de tuplas (pdv, ativo) que aparecem mais de uma vez,
    para sinalizar duplicidade dentro do grupo.
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
