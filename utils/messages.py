from datetime import datetime

# Links padrão – personalize à vontade
ISO_DESKTOP_URL = "https://drive.google.com/file/d/1GQ64blQmysK3rbM0s0Xlot89bDNAbj5L/view?usp=drive_link"
ISO_PDV_URL     = "https://drive.google.com/file/d/1vxfHUDlT3kDdMaN0HroA5Nm9_OxasTaf/view?usp=drive_link"
RAT_URL         = "https://drive.google.com/file/d/1_SG1RofIjoJLgwWYs0ya0fKlmVd74Lhn/view?usp=sharing"


def _is_desktop(pdv: str, ativo: str) -> bool:
    return (pdv or "").strip() == "300" or "desktop" in (ativo or "").lower()


def _fmt(msg: str) -> str:
    return (msg or "").strip()


def gerar_mensagem_whatsapp(loja: str, chamados: list,
                            url_iso_desktop: str = ISO_DESKTOP_URL,
                            url_iso_pdv: str = ISO_PDV_URL,
                            url_rat: str = RAT_URL) -> str:
    """
    Gera texto para WhatsApp agrupado por loja.
    Regras:
    - NÃO exibe "Status" nem "Tipo de atendimento".
    - A seção 'É OBRIGATÓRIO LEVAR' contém ISO (Desktop/PDV) e RAT.
    """
    blocos = []
    endereco_ref = None
    precisa_desktop = False
    precisa_pdv = False

    for ch in chamados:
        pdv = _fmt(ch.get("pdv"))
        ativo = _fmt(ch.get("ativo"))
        desktop = _is_desktop(pdv, ativo)
        if desktop:
            precisa_desktop = True
        else:
            precisa_pdv = True

        linhas = [
            f"*{ch.get('key','')}*",
            f"Loja: {loja}",
            f"PDV: {pdv}",
            f"*ATIVO:* {ativo}",
            f"Problema: {_fmt(ch.get('problema'))}",
            "***",
        ]
        blocos.append("\n".join(linhas))

        endereco_ref = (
            _fmt(ch.get("endereco")),
            _fmt(ch.get("estado")),
            _fmt(ch.get("cep")),
            _fmt(ch.get("cidade")),
        )

    if endereco_ref:
        end_txt = "\n".join(
            [
                f"Endereço: {endereco_ref[0]}",
                f"Estado: {endereco_ref[1]}",
                f"CEP: {endereco_ref[2]}",
                f"Cidade: {endereco_ref[3]}",
                "------",
                "⚠️ *É OBRIGATÓRIO LEVAR:*",
                f"• ISO do {'Desktop' if precisa_desktop and not precisa_pdv else 'PDV'}"
                f" ({'Desktop' if precisa_desktop else 'PDV'}): "
                f"{url_iso_desktop if precisa_desktop else url_iso_pdv}",
                f"• RAT: {url_rat}",
            ]
        )
        blocos.append(end_txt)

    return "\n\n".join(blocos)


def verificar_duplicidade(chamados: list) -> set[tuple[str, str]]:
    vistos, dup = set(), set()
    for ch in chamados:
        key = (_fmt(ch.get("pdv")), _fmt(ch.get("ativo")))
        if key in vistos:
            dup.add(key)
        else:
            vistos.add(key)
    return dup
