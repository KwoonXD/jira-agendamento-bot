# utils/messages.py
from datetime import datetime

def _fmt_data_agendada(raw):
    if not raw:
        return "--"
    # tenta alguns formatos comuns do Jira
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(raw, fmt).strftime("%d/%m/%Y %H:%M")
        except Exception:
            pass
    return str(raw)

def gerar_mensagem(loja, chamados):
    """
    Gera mensagem por loja, listando FSAs e exibindo endereço uma única vez.
    Agora inclui Status e Data agendada.
    """
    blocos = []
    endereco_info = None

    for ch in chamados:
        linhas = [
            f"*{ch.get('key','--')}*",
            f"Loja: {loja}",
            f"Status: {ch.get('status','--')}",
            f"PDV: {ch.get('pdv','--')}",
            f"*ATIVO: {ch.get('ativo','--')}*",
            f"Problema: {ch.get('problema','--')}",
            f"Data agendada: {_fmt_data_agendada(ch.get('data_agendada'))}",
            "***"
        ]
        blocos.append("\n".join(linhas))

        endereco_info = (
            ch.get('endereco','--'),
            ch.get('estado','--'),
            ch.get('cep','--'),
            ch.get('cidade','--')
        )

    if endereco_info:
        blocos.append(
            "\n".join([
                f"Endereço: {endereco_info[0]}",
                f"Estado: {endereco_info[1]}",
                f"CEP: {endereco_info[2]}",
                f"Cidade: {endereco_info[3]}"
            ])
        )

    return "\n\n".join(blocos)

def verificar_duplicidade(chamados):
    seen = {}
    duplicates = set()
    for ch in chamados:
        key = (ch.get("pdv"), ch.get("ativo"))
        if key in seen:
            duplicates.add(key)
        else:
            seen[key] = True
    return duplicates
