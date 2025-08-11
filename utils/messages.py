# utils/messages.py
from datetime import datetime

def _classificar_tipo(ch):
    """Desktop se PDV == 300 ou se 'desktop' aparecer em ATIVO (case-insensitive)."""
    pdv = str(ch.get("pdv", "")).strip()
    ativo = str(ch.get("ativo", "")).lower()
    if pdv == "300" or "desktop" in ativo:
        return "Desktop"
    return "PDV"

def gerar_mensagem(loja, chamados, iso_desktop_url=None, iso_pdv_url=None, rat_url=None):
    """
    Mensagem por loja, listando FSAs e exibindo endereço uma única vez.
    - Não exibe 'Data agendada'
    - RAT: aparece em cada FSA
    - ISO: aparece uma única vez, abaixo do endereço; mostra Desktop/PDV conforme houver chamados do tipo.
    """
    blocos = []
    endereco_info = None
    tem_desktop = False
    tem_pdv = False

    for ch in chamados:
        tipo = _classificar_tipo(ch)
        if tipo == "Desktop":
            tem_desktop = True
        else:
            tem_pdv = True

        linhas = [
            f"*{ch.get('key','--')}*",
            f"Loja: {loja}",
            f"Status: {ch.get('status','--')}",
            f"PDV: {ch.get('pdv','--')}",
            f"*ATIVO: {ch.get('ativo','--')}*",
            f"Tipo de atendimento: {tipo}",
            f"Problema: {ch.get('problema','--')}",
        ]

        # RAT sempre por chamado
        if rat_url:
            linhas.append(f"RAT: {rat_url}")

        linhas.append("***")
        blocos.append("\n".join(linhas))

        # guarda endereço (uma vez só ao final)
        endereco_info = (
            ch.get('endereco','--'),
            ch.get('estado','--'),
            ch.get('cep','--'),
            ch.get('cidade','--')
        )

    # bloco único de endereço + ISO(s) logo abaixo
    if endereco_info:
        endereco_bloco = [
            f"Endereço: {endereco_info[0]}",
            f"Estado: {endereco_info[1]}",
            f"CEP: {endereco_info[2]}",
            f"Cidade: {endereco_info[3]}",
        ]
        # ISO(s) após o endereço, somente os necessários
        if tem_desktop and iso_desktop_url:
            endereco_bloco.append(f"ISO (Desktop): {iso_desktop_url}")
        if tem_pdv and iso_pdv_url:
            endereco_bloco.append(f"ISO (PDV): {iso_pdv_url}")

        blocos.append("\n".join(endereco_bloco))

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
