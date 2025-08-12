# utils/messages.py
from datetime import datetime

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


def _fmt_line_link(label: str, url: str) -> str:
    # formato já bom pra colar no WhatsApp (exibe como link clicável)
    return f"{label}: {url}"


def gerar_mensagem_whatsapp(loja: str, chamados: list) -> str:
    """
    Mensagem por loja no formato solicitado (sem data agendada no corpo do chamado)
    e com a ISO dentro do bloco '⚠️ É OBRIGATÓRIO LEVAR', seguida da RAT.
    """
    blocos = []
    endereco_info = None
    algum_desktop = False

    for ch in chamados:
        is_desktop = _is_desktop(ch)
        if is_desktop:
            algum_desktop = True

        linhas = [
            f"*{ch.get('key','--')}*",
            f"Loja: {loja}",
            f"Status: {ch.get('status','--')}",
            f"PDV: {ch.get('pdv','--')}",
            f"*ATIVO:* {ch.get('ativo','--')}",
            f"Tipo de atendimento: {'Desktop' if is_desktop else 'PDV'}",
            f"Problema: {ch.get('problema','--')}",
            "***"
        ]
        blocos.append("\n".join(linhas))

        # guardo 1x o endereço (o último sobrescreve, o que é OK: todos da loja são iguais)
        endereco_info = (
            ch.get('endereco','--'),
            ch.get('estado','--'),
            ch.get('cep','--'),
            ch.get('cidade','--')
        )

    # bloco de endereço
    if endereco_info:
        blocos.append(
            "\n".join([
                f"Endereço: {endereco_info[0]}",
                f"Estado: {endereco_info[1]}",
                f"CEP: {endereco_info[2]}",
                f"Cidade: {endereco_info[3]}",
                "------",
                "⚠️ *É OBRIGATÓRIO LEVAR:*",
                # ISO (PDV ou Desktop) fica AQUI
                _fmt_line_link("• ISO do Desktop" if algum_desktop else "• ISO do PDV",
                               ISO_DESKTOP_URL if algum_desktop else ISO_PDV_URL),
                _fmt_line_link("• RAT", RAT_URL)
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
