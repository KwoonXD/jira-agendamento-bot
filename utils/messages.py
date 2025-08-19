from datetime import datetime
from typing import Iterable


# Links (padrões – mude se quiser)
ISO_DESKTOP_URL = "https://drive.google.com/file/d/1GQ64blQmysK3rbM0s0Xlot89bDNAbj5L/view?usp=drive_link"
ISO_PDV_URL     = "https://drive.google.com/file/d/1vxfHUDlT3kDdMaN0HroA5Nm9_OxasTaf/view?usp=drive_link"
RAT_URL         = "https://drive.google.com/file/d/1_SG1RofIjoJLgwWYs0ya0fKlmVd74Lhn/view?usp=sharing"


def fmt_data_br(iso: str | None) -> str:
    if not iso:
        return "--"
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
        try:
            return datetime.strptime(iso, fmt).strftime("%d/%m/%Y %H:%M")
        except Exception:
            continue
    return iso


def is_desktop(pdv: str, ativo: str) -> bool:
    """
    Regras pedidas:
      - 'todo chamado que for PDV 300 é Desktop'
      - ou que apareça 'Desktop' em ativos
    """
    try:
        if int(str(pdv).strip()) == 300:
            return True
    except Exception:
        pass
    return "DESKTOP" in str(ativo).upper()


def gerar_mensagem_whatsapp(loja: str, chamados: Iterable[dict]) -> str:
    """
    Mensagem por loja (sem 'Status' e sem 'Tipo de atendimento'),
    com bloco 'É OBRIGATÓRIO LEVAR' ao final (ISO + RAT).
    """
    chamados = list(chamados)
    blocos: list[str] = []

    # 1) Cabeça por FSA
    for ch in chamados:
        linhas = [
            f"*{ch.get('key','--')}*",
            f"Loja: {ch.get('loja','--')}",
            f"PDV: {ch.get('pdv','--')}",
            f"*ATIVO: {ch.get('ativo','--')}*",
            f"Problema: {ch.get('problema','--')}",
            "***"
        ]
        blocos.append("\n".join(linhas))

    # 2) Endereço (uma vez no fim, pegando o que tiver informação)
    ref = next((c for c in reversed(chamados)
                if any(c.get(k) not in (None, "", "--") for k in ("endereco", "estado", "cep", "cidade"))),
               None)
    if ref:
        blocos.append("\n".join([
            f"Endereço: {ref.get('endereco','--')}",
            f"Estado: {ref.get('estado','--')}",
            f"CEP: {ref.get('cep','--')}",
            f"Cidade: {ref.get('cidade','--')}",
            "------",
        ]))

    # 3) Bloco obrigatório (ISO + RAT)
    #    Escolhe ISO por Desktop/PDV analisando TODOS os chamados da loja:
    any_desktop = any(is_desktop(c.get("pdv",""), c.get("ativo","")) for c in chamados)
    iso_url = ISO_DESKTOP_URL if any_desktop else ISO_PDV_URL
    blocos.append(
        "\n".join([
            "⚠️ *É OBRIGATÓRIO LEVAR:*",
            f"• ISO ({'Desktop' if any_desktop else 'do PDV'}) ({iso_url})",
            f"• RAT: ({RAT_URL})"
        ])
    )

    return "\n".join(blocos)


def encontrar_duplicados(chamados: Iterable[dict]) -> set[tuple]:
    seen = set()
    dup = set()
    for ch in chamados:
        k = ch.get("dup_key")
        if k in seen:
            dup.add(k)
        else:
            seen.add(k)
    return dup
