from datetime import datetime

def _fmt_data_agendada(raw):
    if not raw:
        return "--"
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(raw, fmt).strftime("%d/%m/%Y %H:%M")
        except Exception:
            pass
    return "--"

def _is_desktop(ch):
    # Desktop = PDV 300 OU 'desktop' em ATIVO
    pdv = str(ch.get("pdv","")).strip()
    ativo = str(ch.get("ativo","")).lower()
    return pdv == "300" or "desktop" in ativo

def gerar_mensagem_whatsapp(
    loja: str,
    chamados: list[dict],
    iso_desktop_url: str,
    iso_pdv_url: str,
    rat_url: str,
    incluir_status: bool = False,
    incluir_tipo: bool = False,
) -> str:
    """
    Mensagem por loja, listando FSAs e exibindo endereço uma única vez.
    - NÃO coloca Status nem Tipo de atendimento quando flags=False
    - ISO e RAT vão APENAS na seção 'É OBRIGATÓRIO LEVAR'
    """
    blocos = []
    endereco_info = None

    for ch in chamados:
        linhas = []
        linhas.append(f"*{ch.get('key','--')}*")
        linhas.append(f"Loja: {loja}")
        # Status e Tipo só se solicitado explicitamente
        if incluir_status:
            linhas.append(f"Status: {ch.get('status','--')}")
        if incluir_tipo:
            linhas.append(f"Tipo de atendimento: {'Desktop' if _is_desktop(ch) else 'PDV'}")

        linhas.append(f"PDV: {ch.get('pdv','--')}")
        linhas.append(f"*ATIVO:* {ch.get('ativo','--')}")
        linhas.append(f"Problema: {ch.get('problema','--')}")
        # NÃO mostrar data agendada na mensagem ao técnico (pedido do usuário)
        # linhas.append(f"Data agendada: {_fmt_data_agendada(ch.get('data_agendada'))}")
        linhas.append("***")

        blocos.append("\n".join(linhas))

        # armazenar endereço para mostrar 1 única vez ao final
        endereco_info = (
            ch.get('endereco','--'),
            ch.get('estado','--'),
            ch.get('cep','--'),
            ch.get('cidade','--'),
        )

    # Endereço único
    if endereco_info:
        blocos.append(
            "\n".join([
                f"Endereço: {endereco_info[0]}",
                f"Estado: {endereco_info[1]}",
                f"CEP: {endereco_info[2]}",
                f"Cidade: {endereco_info[3]}",
            ])
        )

    # Seção obrigatória (ISO escolhida por PDV/Desktop + RAT)
    precisa_desktop = any(_is_desktop(ch) for ch in chamados)
    iso_url = iso_desktop_url if precisa_desktop else iso_pdv_url

    blocos.append(
        "\n".join([
            "------",
            "⚠️ *É OBRIGATÓRIO LEVAR:*",
            f"• ISO ({'Desktop' if precisa_desktop else 'PDV'}) <{iso_url}>",
            f"• RAT <{rat_url}>",
        ])
    )

    return "\n".join(blocos)

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
