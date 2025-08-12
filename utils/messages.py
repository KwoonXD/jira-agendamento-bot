# utils/messages.py
from datetime import datetime

def _fmt_data_agendada(raw):
    if not raw:
        return "--"
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(raw, fmt).strftime("%d/%m/%Y %H:%M")
        except Exception:
            pass
    return str(raw)

def _is_desktop_item(ch):
    # Regras: PDV 300 => Desktop, OU ativo contém "desktop"
    pdv = str(ch.get("pdv", "")).strip()
    ativo = str(ch.get("ativo", "")).lower()
    return pdv == "300" or "desktop" in ativo

def gerar_mensagem_whatsapp(loja, chamados, iso_desktop_url, iso_pdv_url, rat_url):
    """
    Mensagem formatada por loja para WhatsApp.
    - NÃO exibe Status nem 'Tipo de atendimento'
    - NÃO exibe Data agendada nos itens
    - Exibe endereço (uma vez) e, abaixo, o bloco 'É OBRIGATÓRIO LEVAR'
      com ISO (por tipo) e RAT.
    """
    blocos = []
    endereco_info = None
    precisa_iso_pdv = False
    precisa_iso_desktop = False

    for ch in chamados:
        # Flags ISO por item
        if _is_desktop_item(ch):
            precisa_iso_desktop = True
        else:
            precisa_iso_pdv = True

        linhas = [
            f"*{ch.get('key','--')}*",
            f"Loja: {loja}",
            f"PDV: {ch.get('pdv','--')}",
            f"*ATIVO: {ch.get('ativo','--')}*",
            f"Problema: {ch.get('problema','--')}",
            "***"
        ]
        blocos.append("\n".join(linhas))

        endereco_info = (
            ch.get('endereco','--'),
            ch.get('estado','--'),
            ch.get('cep','--'),
            ch.get('cidade','--')
        )

    # Endereço uma vez
    if endereco_info:
        blocos.append(
            "\n".join([
                f"Endereço: {endereco_info[0]}",
                f"Estado: {endereco_info[1]}",
                f"CEP: {endereco_info[2]}",
                f"Cidade: {endereco_info[3]}",
                "------",
                "⚠️ *É OBRIGATÓRIO LEVAR:*",
                *( [f"• ISO do Desktop: {iso_desktop_url}"] if precisa_iso_desktop else [] ),
                *( [f"• ISO do PDV: {iso_pdv_url}"] if precisa_iso_pdv else [] ),
                f"• RAT: {rat_url}",
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
