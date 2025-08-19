# Links padrão (pode trocar depois)
ISO_DESKTOP_URL = "https://drive.google.com/file/d/1GQ64blQmysK3rbM0s0Xlot89bDNAbj5L/view?usp=drive_link"
ISO_PDV_URL     = "https://drive.google.com/file/d/1vxfHUDlT3kDdMaN0HroA5Nm9_OxasTaf/view?usp=drive_link"
RAT_URL         = "https://drive.google.com/file/d/1_SG1RofIjoJLgwWYs0ya0fKlmVd74Lhn/view?usp=sharing"

def _fmt_endereco(ch: dict) -> list[str]:
    return [
        f"Endereço: {ch.get('endereco','--')}",
        f"Estado: {ch.get('estado','--')}",
        f"CEP: {ch.get('cep','--')}",
        f"Cidade: {ch.get('cidade','--')}",
    ]

def gerar_mensagem(
    loja: str,
    chamados: list[dict],
    iso_desktop: str = ISO_DESKTOP_URL,
    iso_pdv: str = ISO_PDV_URL,
    rat_url: str = RAT_URL,
    detect_desktop=None,
) -> str:
    """
    Mensagem para o técnico (sem Status/Tipo).
    - Por FSA: key, Loja, PDV, ATIVO, Problema.
    - Endereço: uma vez no final.
    - "É obrigatório levar": ISO Desktop e/ou ISO PDV conforme detecção.
    - RAT no final.
    """
    blocos = []
    precisa_desktop = False
    precisa_pdv = False

    for ch in chamados:
        if callable(detect_desktop):
            if detect_desktop(ch):
                precisa_desktop = True
            else:
                precisa_pdv = True

        linhas = [
            f"*{ch.get('key','--')}*",
            f"Loja: {loja}",
            f"PDV: {ch.get('pdv','--')}",
            f"*ATIVO: {ch.get('ativo','--')}*",
            f"Problema: {ch.get('problema','--')}",
            "***"
        ]
        blocos.append("\n".join(linhas))

    # Endereço (pega do último chamado que tiver dados)
    ref = None
    for c in reversed(chamados):
        if any(c.get(k) for k in ("endereco", "estado", "cep", "cidade")):
            ref = c
            break
    if ref:
        blocos.append("\n".join(_fmt_endereco(ref)))

    obrig = []
    if precisa_desktop:
        obrig.append(f"- [ISO Desktop]({iso_desktop})")
    if precisa_pdv:
        obrig.append(f"- [ISO PDV]({iso_pdv})")
    if obrig:
        blocos.append("**É obrigatório levar:**\n" + "\n".join(obrig))

    blocos.append(f"**RAT:** {rat_url}")
    return "\n\n".join(blocos)

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
