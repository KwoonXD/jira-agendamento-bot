# utils/messages.py
# links padrão
ISO_DESKTOP_URL = "https://drive.google.com/file/d/1GQ64blQmysK3rbM0s0Xlot89bDNAbj5L/view?usp=drive_link"
ISO_PDV_URL     = "https://drive.google.com/file/d/1vxfHUDlT3kDdMaN0HroA5Nm9_OxasTaf/view?usp=drive_link"
RAT_URL         = "https://drive.google.com/file/d/1_SG1RofIjoJLgwWYs0ya0fKlmVd74Lhn/view?usp=sharing"


def _is_desktop(ch: dict) -> bool:
    """Desktop se PDV == 300 ou se 'desktop' aparecer no ATIVO."""
    try:
        pdv = str(ch.get("pdv", "")).strip()
        ativo = str(ch.get("ativo", "")).lower()
        return pdv == "300" or "desktop" in ativo
    except Exception:
        return False


def _line(label: str, value: str) -> str:
    return f"{label}: {value}"


def gerar_mensagem_whatsapp(loja: str, chamados: list) -> str:
    """
    Geração de texto para WhatsApp/operacional.
    - NÃO mostra 'Status' nem 'Tipo de atendimento'
    - ISO e RAT apenas no bloco final '⚠️ É OBRIGATÓRIO LEVAR'
    """
    blocos = []
    endereco_info = None
    algum_desktop = False

    for ch in chamados:
        if _is_desktop(ch):
            algum_desktop = True

        linhas = [
            f"*{ch.get('key','--')}*",
            _line("Loja", loja),
            _line("PDV", str(ch.get("pdv", "--"))),
            f"*ATIVO:* {ch.get('ativo','--')}",
            _line("Problema", ch.get("problema", "--")),
            "***",
        ]
        blocos.append("\n".join(linhas))

        # endereço: apenas 1 vez (último do loop serve)
        endereco_info = (
            ch.get("endereco", "--"),
            ch.get("estado", "--"),
            ch.get("cep", "--"),
            ch.get("cidade", "--"),
        )

    if endereco_info:
        iso_label = "• ISO do Desktop" if algum_desktop else "• ISO do PDV"
        iso_link  = ISO_DESKTOP_URL if algum_desktop else ISO_PDV_URL
        blocos.append(
            "\n".join(
                [
                    _line("Endereço", endereco_info[0]),
                    _line("Estado",   endereco_info[1]),
                    _line("CEP",      endereco_info[2]),
                    _line("Cidade",   endereco_info[3]),
                    "------",
                    "⚠️ *É OBRIGATÓRIO LEVAR:*",
                    _line(iso_label, iso_link),
                    _line("• RAT", RAT_URL),
                ]
            )
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
