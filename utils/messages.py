# utils/messages.py

from datetime import datetime

def gerar_mensagem(loja, chamados):
    """
    Gera uma mensagem para um grupo de chamados da mesma loja.
    Exibe detalhes de cada FSA, o endereço da loja uma única vez,
    e inclui links obrigatórios no final dependendo das regras de ativo/pdv.
    """
    blocos = []
    endereco_info = None
    incluir_iso_desktop = False
    incluir_iso_pdv = False

    for ch in chamados:
        ativo = ch.get('ativo', '--')
        pdv_raw = ch.get('pdv', '--')

        # Lógica para inclusão de links
        if isinstance(pdv_raw, int):
            pdv = pdv_raw
        else:
            try:
                pdv = int(str(pdv_raw).strip())
            except:
                pdv = None

        if 'desktop' in str(ativo).lower() or (pdv == 300):
            incluir_iso_desktop = True
        if pdv and pdv > 300:
            incluir_iso_pdv = True

        # Bloco do chamado
        linhas = [
            f"*{ch['key']}*",
            f"Loja: {loja}",
            f"PDV: {pdv_raw}",
            f"*ATIVO: {ativo}*",
            f"Problema: {ch.get('problema', '--')}",
            "***"
        ]
        blocos.append("\n".join(linhas))

        endereco_info = (
            ch.get('endereco', '--'),
            ch.get('estado', '--'),
            ch.get('cep', '--'),
            ch.get('cidade', '--')
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

    # 🔽 Instruções obrigatórias
    instrucoes = ["---", "⚠️ **É OBRIGATÓRIO LEVAR:**"]
    if incluir_iso_desktop:
        instrucoes.append("- 📀 [ISO do Desktop](https://drive.google.com/file/d/1GQ64blQmysK3rbM0s0Xlot89bDNAbj5L/view?usp=drive_link)")
    if incluir_iso_pdv:
        instrucoes.append("- 📀 [ISO do PDV](https://drive.google.com/file/d/1vxfHUDlT3kDdMaN0HroA5Nm9_OxasTaf/view?usp=drive_link)")
    instrucoes.append("- 📝 [RAT Atualizada](https://drive.google.com/file/d/1_SG1RofIjoJLgwWYs0ya0fKlmVd74Lhn/view?usp=sharing)")

    blocos.append("\n".join(instrucoes))

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

