from datetime import datetime

ISO_DESKTOP_URL = "https://drive.google.com/file/d/1GQ64blQmysK3rbM0s0Xlot89bDNAbj5L/view?usp=drive_link"
ISO_PDV_URL     = "https://drive.google.com/file/d/1vxfHUDlT3kDdMaN0HroA5Nm9_OxasTaf/view?usp=drive_link"
RAT_URL         = "https://drive.google.com/file/d/1_SG1RofIjoJLgwWYs0ya0fKlmVd74Lhn/view?usp=sharing"

def _fmt_date(raw: str|None) -> str|None:
    if not raw: return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(raw, fmt).strftime("%d/%m/%Y")
        except: pass
    return None

def _is_desktop(pdv, ativo) -> bool:
    pdv = str(pdv or "").strip()
    ativo = str(ativo or "").lower()
    return pdv == "300" or "desktop" in ativo

def _endereco_bloco(ch: dict) -> list[str]:
    iso_link = ISO_DESKTOP_URL if _is_desktop(ch.get("pdv"), ch.get("ativo")) else ISO_PDV_URL
    iso_label = "Desktop" if _is_desktop(ch.get("pdv"), ch.get("ativo")) else "do PDV"
    return [
        f"Endereço: {ch.get('endereco','--')}",
        f"Estado: {ch.get('estado','--')}",
        f"CEP: {ch.get('cep','--')}",
        f"Cidade: {ch.get('cidade','--')}",
        "------",
        "⚠️ *É OBRIGATÓRIO LEVAR:*",
        f"• ISO ({iso_label}) ({iso_link})",
        f"• RAT: ({RAT_URL})",
    ]

def gerar_mensagem(loja: str, chamados: list[dict]) -> str:
    blocos = []
    for ch in chamados:
        blocos.append("\n".join([
            f"*{ch.get('key')}*",
            f"Loja: {loja}",
            f"PDV: {ch.get('pdv')}",
            f"*ATIVO: {ch.get('ativo')}*",
            f"Problema: {ch.get('problema')}",
            "***",
        ]))
    ref = chamados[-1] if chamados else None
    if ref: blocos.append("\n".join(_endereco_bloco(ref)))
    return "\n\n".join(blocos)

def agrupar_por_data(chamados: list[dict]) -> dict[str, list[dict]]:
    out = {}
    for ch in chamados:
        d = _fmt_date(ch.get("data_agendada")) or _fmt_date(ch.get("created")) or "Sem data"
        out.setdefault(d, []).append(ch)
    return out

def agrupar_por_loja(chamados: list[dict]) -> dict[str, list[dict]]:
    out = {}
    for ch in chamados:
        out.setdefault(ch.get("loja","Loja Desconhecida"), []).append(ch)
    return out
