from datetime import datetime

def _classificar_tipo(ch: dict) -> str:
    pdv = str(ch.get("pdv", "")).strip()
    ativo = str(ch.get("ativo", "")).lower()
    if pdv == "300" or "desktop" in ativo:
        return "Desktop"
    return "PDV"

def gerar_mensagem_whatsapp(
    loja: str,
    chamados: list[dict],
    iso_desktop_url: str | None = None,
    iso_pdv_url: str | None = None,
    rat_url: str | None = None,
) -> str:
    if not chamados:
        return "—"

    linhas_total: list[str] = []
    endereco_info = None
    tem_desktop = False
    tem_pdv = False

    for ch in chamados:
        tipo = _classificar_tipo(ch)
        if tipo == "Desktop": tem_desktop = True
        else: tem_pdv = True

        linhas_total.extend([
            f"{ch.get('key','--')}",
            f"Loja {loja}",
            f"PDV:{ch.get('pdv','--')}",
            f"ATIVO:{str(ch.get('ativo','--')).replace(' ', '')}",
            f"Problema:{ch.get('problema','--')}",
            "***"
        ])

        endereco_info = (
            ch.get('endereco','--'),
            ch.get('estado','--'),
            ch.get('cep','--'),
            ch.get('cidade','--'),
        )

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

def verificar_duplicidade(chamados: list[dict]) -> set[tuple]:
    seen = {}
    duplicates = set()
    for ch in chamados:
        key = (ch.get("pdv"), ch.get("ativo"))
        if key in seen:
            duplicates.add(key)
        else:
            seen[key] = True
    return duplicates
