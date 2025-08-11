# utils/messages.py
from datetime import datetime

# --- Helpers ---------------------------------------------------------------

def _classificar_tipo(ch: dict) -> str:
    """
    "Desktop" se PDV == 300 ou se 'desktop' aparecer no campo ATIVO (case-insensitive).
    Caso contrário, "PDV".
    """
    pdv = str(ch.get("pdv", "")).strip()
    ativo = str(ch.get("ativo", "")).lower()
    if pdv == "300" or "desktop" in ativo:
        return "Desktop"
    return "PDV"


# --- Mensagem para WhatsApp ------------------------------------------------

def gerar_mensagem_whatsapp(
    loja: str,
    chamados: list[dict],
    iso_desktop_url: str | None = None,
    iso_pdv_url: str | None = None,
    rat_url: str | None = None,
) -> str:
    """
    Gera a mensagem no formato que você vem usando:
    - Um bloco por FSA (sem data agendada).
    - Um único bloco de endereço ao final.
    - Depois do endereço, a seção "⚠️ É OBRIGATÓRIO LEVAR" com links:
        • ISO do Desktop (se houver ao menos 1 Desktop)
        • ISO do PDV     (se houver ao menos 1 PDV)
        • RAT            (sempre que informado)
    """

    if not chamados:
        return "—"

    linhas_total: list[str] = []
    endereco_info = None
    tem_desktop = False
    tem_pdv = False

    for ch in chamados:
        tipo = _classificar_tipo(ch)
        if tipo == "Desktop":
            tem_desktop = True
        else:
            tem_pdv = True

        # bloco do chamado (sem data)
        linhas_total.extend([
            f"{ch.get('key','--')}",
            f"Loja {loja}",
            f"PDV:{ch.get('pdv','--')}",
            f"ATIVO:{str(ch.get('ativo','--')).replace(' ', '')}",
            f"Problema:{ch.get('problema','--')}",
            "***"
        ])

        # guardamos o endereço (exibimos 1x ao final)
        endereco_info = (
            ch.get('endereco','--'),
            ch.get('estado','--'),
            ch.get('cep','--'),
            ch.get('cidade','--'),
        )

    # bloco único de endereço
    if endereco_info:
        linhas_total.extend([
            "",
            f"Endereço: {endereco_info[0]}",
            f"Estado: {endereco_info[1]}",
            f"CEP: {endereco_info[2]}",
            f"Cidade: {endereco_info[3]}",
            "",
            "---------",
            "⚠️ *É OBRIGATÓRIO LEVAR:*"
        ])
        if tem_desktop and iso_desktop_url:
            linhas_total.append(f"• 🔧 ISO do Desktop({iso_desktop_url})")
        if tem_pdv and iso_pdv_url:
            linhas_total.append(f"• 🔧 ISO do PDV({iso_pdv_url})")
        if rat_url:
            linhas_total.append(f"• 📄 RAT({rat_url})")

    return "\n".join(linhas_total)


# --- Duplicidade -----------------------------------------------------------

def verificar_duplicidade(chamados: list[dict]) -> set[tuple]:
    """
    Retorna um set de tuplas (pdv, ativo) que aparecem mais de uma vez.
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
