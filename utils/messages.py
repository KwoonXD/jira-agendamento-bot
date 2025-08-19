from datetime import datetime
from collections import defaultdict

# Links fixos
ISO_PDV_URL = "https://drive.google.com/file/d/1vxfHUDlT3kDdMaN0HroA5Nm9_OxasTaf/view?usp=drive_link"
RAT_URL     = "https://drive.google.com/file/d/1_SG1RofIj0JLgwWYS0ya0fKLmVd74Lhn/view?usp=sharing"

def _fmt_data(raw: str | None) -> str:
    if not raw:
        return "Sem data"
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(raw, fmt).strftime("%d/%m/%Y")
        except Exception:
            pass
    return "Sem data"

def _fmt_endereco(c: dict) -> list[str]:
    return [
        f"Endereço: {c.get('endereco','--')}",
        f"Estado: {c.get('estado','--')}",
        f"CEP: {c.get('cep','--')}",
        f"Cidade: {c.get('cidade','--')}",
        "------",
        "⚠️ *É OBRIGATÓRIO LEVAR:*",
        f"• ISO (do PDV) ({ISO_PDV_URL})",
        f"• RAT: ({RAT_URL})"
    ]

def is_spare(ativo: str) -> bool:
    a = (ativo or "").upper()
    return "SPARE" in a or "RESERVA" in a

def verificar_duplicidade(chamados: list[dict]) -> set[tuple]:
    seen = {}
    dups = set()
    for ch in chamados:
        key = (str(ch.get("pdv","")).strip(), str(ch.get("ativo","")).strip().upper())
        if key in seen:
            dups.add(key)
        else:
            seen[key] = True
    return dups

def agrupar_por_data(chamados: list[dict]) -> dict[str, list[dict]]:
    grp = defaultdict(list)
    for ch in chamados:
        grp[_fmt_data(ch.get("data_agendada"))].append(ch)
    return dict(sorted(grp.items(), key=lambda kv: kv[0]))

def gerar_mensagem_whatsapp(loja: str, chamados: list[dict]) -> str:
    """
    Gera o bloco de mensagem por LOJA, com ISO/RAT no final e sem mostrar status.
    Marca SPARE e DUPLICADO em cada chamado.
    """
    linhas = []
    dups = verificar_duplicidade(chamados)

    for ch in chamados:
        pdv = ch.get("pdv","--")
        ativo = ch.get("ativo","--")
        spare = " ⚙️SPARE" if is_spare(ativo) else ""
        dup   = " 🔁DUPLICADO" if (str(pdv).strip(), str(ativo).strip().upper()) in dups else ""

        linhas.extend([
            f"*{ch.get('key','--')}*{spare}{dup}",
            f"Loja: {loja}",
            f"PDV: {pdv}",
            f"*ATIVO: {ativo}*",
            f"Problema: {ch.get('problema','--')}",
            "***",
            ""
        ])

    # endereço uma vez (pega do último com endereço não-vazio)
    ref = next((c for c in reversed(chamados) if any(c.get(k) for k in ("endereco","estado","cep","cidade"))), None)
    if ref:
        linhas.extend(_fmt_endereco(ref))

    return "\n".join(linhas).strip()
