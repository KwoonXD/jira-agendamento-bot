# utils/messages.py
from datetime import datetime

def _is_desktop(ch: dict) -> bool:
    """Desktop se PDV == 300 ou se 'desktop' aparecer em ATIVO (case-insensitive)."""
    pdv = str(ch.get("pdv", "")).strip()
    ativo = str(ch.get("ativo", "")).lower()
    return pdv == "300" or "desktop" in ativo

def gerar_mensagem(
    loja: str,
    chamados: list[dict],
    iso_desktop_url: str | None = None,
    iso_pdv_url: str | None = None,
    rat_url: str | None = None,  # mantido no args caso precise futuramente
    *,
    whatsapp_style: bool = True
) -> str:
    """
    Gera texto por LOJA no formato de WhatsApp (igual ao print enviado):
      - 1 bloco por FSA (sem data), com *** separando cada um
      - Ao final: Endereço + linha de traço + bloco 'É OBRIGATÓRIO LEVAR'
      - ISO do PDV sempre que houver PDV; ISO do Desktop só se houver Desktop
    """
    linhas: list[str] = []
    tem_pdv, tem_desktop = False, False

    for ch in chamados:
        if _is_desktop(ch):
            tem_desktop = True
        else:
            tem_pdv = True

        linhas.extend([
            f"{ch.get('key','--')}",
            f"Loja: {loja}",
            f"PDV: {ch.get('pdv','--')}",
            f"ATIVO: {ch.get('ativo','--')}",
            f"Problema:{' ' + ch.get('problema','--')}",
            "***",
            "",
        ])

    # bloco de endereço uma única vez
    if chamados:
        last = chamados[-1]
        endereco = last.get('endereco', '--')
        estado   = last.get('estado', '--')
        cep      = last.get('cep', '--')
        cidade   = last.get('cidade', '--')

        linhas.extend([
            f"Endereço: {endereco}",
            f"Estado: {estado}",
            f"CEP: {cep}",
            f"Cidade: {cidade}",
            "",
            "--------",
            "",
            "⚠️ *É OBRIGATÓRIO LEVAR:*",
        ])

        # ISO(s) – só mostra os que fazem sentido para a loja
        if tem_pdv and iso_pdv_url:
            linhas.append(f"• 🖇️ ISO do PDV({iso_pdv_url})")
        if tem_desktop and iso_desktop_url:
            linhas.append(f"• 🖇️ ISO do Desktop({iso_desktop_url})")

    # remove possíveis linhas em branco finais duplicadas
    while linhas and not linhas[-1]:
        linhas.pop()

    return "\n".join(linhas)

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
