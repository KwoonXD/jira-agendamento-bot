# utils/messages.py

ISO_DESKTOP_URL = "https://drive.google.com/file/d/1GQ64blQmysK3rbM0s0Xlot89bDNAbj5L/view?usp=drive_link"
ISO_PDV_URL     = "https://drive.google.com/file/d/1vxfHUDlT3kDdMaN0HroA5Nm9_OxasTaf/view?usp=drive_link"
RAT_URL         = "https://drive.google.com/file/d/1_SG1RofIjoJLgwWYys0ya0fKImVd74Lhn/view?usp=sharing"


def _fmt_endereco(ch: dict) -> list[str]:
    return [
        f"Endereço: {ch.get('endereco','--')}",
        f"Estado: {ch.get('estado','--')}",
        f"CEP: {ch.get('cep','--')}",
        f"Cidade: {ch.get('cidade','--')}",
    ]


def _has_spare(ch: dict) -> bool:
    a = (ch.get("ativo") or "").upper()
    return "SPARE" in a or "SP" in a


def gerar_mensagem(loja: str, chamados: list[dict]) -> str:
    """
    Mensagem final por loja.
    - Não inclui 'Status' nem 'Tipo de atendimento', conforme seu pedido.
    - ISO entra na seção "É OBRIGATÓRIO LEVAR".
    - RAT sempre no final.
    - Se PDV == 300 OU ativo contém 'desktop' -> trata como Desktop para ISO.
    - Marca SPARE e DUPLICADO.
    """
    blocos: list[str] = []

    # duplicidade: (pdv, ativo)
    seen = set()
    dups = set()
    for c in chamados:
        key = (str(c.get("pdv")), str(c.get("ativo")).strip().lower())
        if key in seen:
            dups.add(key)
        else:
            seen.add(key)

    for c in chamados:
        warn = []
        if _has_spare(c):
            warn.append("SPARE")
        key = (str(c.get("pdv")), str(c.get("ativo")).strip().lower())
        if key in dups:
            warn.append("DUPLICADO")

        header = f"*{c.get('key','--')}*"
        if warn:
            header += "  " + " | ".join(f"[{w}]" for w in warn)

        linhas = [
            header,
            f"Loja: {loja}",
            f"PDV: {c.get('pdv','--')}",
            f"*ATIVO:* {c.get('ativo','--')}",
            f"Problema: {c.get('problema','--')}",
            "***"
        ]
        blocos.append("\n".join(linhas))

    # endereço (1 vez) — pego do último com dados
    ref = next((x for x in reversed(chados := chamados) if any(x.get(k) for k in ("endereco","estado","cep","cidade"))), None)  # noqa: F841
    if ref:
        blocos.append("\n".join(_fmt_endereco(ref)))

    # Bloco de obrigatórios
    # Define ISO pela presença de Desktop no ativo OU PDV == 300
    tem_desktop = any(("DESKTOP" in str(x.get("ativo","")).upper()) or str(x.get("pdv")) == "300" for x in chamados)
    iso_link = ISO_DESKTOP_URL if tem_desktop else ISO_PDV_URL

    obrig = [
        "------",
        "⚠️ *É OBRIGATÓRIO LEVAR:*",
        f"* ISO (do PDV) ({iso_link})",
        f"* RAT: ({RAT_URL})"
    ]
    blocos.append("\n".join(obrig))

    return "\n\n".join(blocos)
