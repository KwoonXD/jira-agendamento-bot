from datetime import datetime

def gerar_mensagem(loja, chamados):
    blocos = []
    for ch in chamados:
        linhas = [
            f"*{ch['key']}*",
            f"*Loja:* {loja}",
            f"*PDV:* {ch.get('pdv','--')}",
            f"*ATIVO:* {ch.get('ativo','--')}",
            f"*Problema:* {ch.get('problema','--')}"
        ]

        # --- Data Agendada (se houver) ---
        raw = ch.get("data_agendada")
        if raw:
            try:
                dt = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S.%f%z")
                linhas.append(f"*Data Agendada:* {dt.strftime('%d/%m/%Y %H:%M')}")
            except Exception:
                # em caso de formato inesperado, mostra o raw
                linhas.append(f"*Data Agendada:* {raw}")

        # separador
        linhas.append("*****")

        # demais campos
        linhas.extend([
            f"*Endereço:* {ch.get('endereco','--')}",
            f"*Estado:* {ch.get('estado','--')}",
            f"*CEP:* {ch.get('cep','--')}",
            f"*Cidade:* {ch.get('cidade','--')}"
        ])

        blocos.append("\n".join(linhas))

    # separa cada bloco de chamado por linha em branco dupla
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
