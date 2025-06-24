from datetime import datetime

def gerar_mensagem(loja, chamados):
    blocos = []
    seen_enderecos = set()  # para não repetir o mesmo endereço

    for ch in chamados:
        linhas = [
            f"*{ch['key']}*",
            f"*Loja:* {loja}",
            f"*PDV:* {ch.get('pdv','--')}",
            f"*ATIVO:* {ch.get('ativo','--')}",
            f"*Problema:* {ch.get('problema','--')}"
        ]

        # Data Agendada (se existir)
        raw = ch.get("data_agendada")
        if raw:
            try:
                dt = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S.%f%z")
                linhas.append(f"*Data Agendada:* {dt.strftime('%d/%m/%Y %H:%M')}")
            except Exception:
                linhas.append(f"*Data Agendada:* {raw}")

        linhas.append("*****")

        # monta uma tupla única que representa o endereço completo
        endereco_key = (
            ch.get('endereco','--'),
            ch.get('estado','--'),
            ch.get('cep','--'),
            ch.get('cidade','--')
        )

        # só exibe o bloco de endereço se ainda não exibimos para essa tupla
        if endereco_key not in seen_enderecos:
            seen_enderecos.add(endereco_key)
            linhas.extend([
                f"*Endereço:* {endereco_key[0]}",
                f"*Estado:* {endereco_key[1]}",
                f"*CEP:* {endereco_key[2]}",
                f"*Cidade:* {endereco_key[3]}"
            ])

        blocos.append("\n".join(linhas))

    # separa cada chamado por dupla nova linha
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
