# utils/messages.py
from __future__ import annotations
from datetime import datetime
from typing import Iterable, List, Tuple

# === Links padrão (edite se necessário) ======================================
ISO_DESKTOP_URL = "https://drive.google.com/file/d/1GQ64blQmysK3rbM0s0Xlot89bDNAbj5L/view?usp=drive_link"
ISO_PDV_URL     = "https://drive.google.com/file/d/1vxfHUDlT3kDdMaN0HroA5Nm9_OxasTaf/view?usp=drive_link"
RAT_URL         = "https://drive.google.com/file/d/1_SG1RofIjoJLgwWYs0ya0fKlmVd74Lhn/view?usp=sharing"
# ============================================================================


def _fmt_iso_datetime(raw: str | None) -> str | None:
    if not raw:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(raw, fmt).strftime("%d/%m/%Y")
        except Exception:
            pass
    return None


def _is_desktop(pdv: str, ativo: str) -> bool:
    """Desktop se PDV == '300' ou texto do ativo contém 'desktop'."""
    pdv = str(pdv or "").strip()
    ativo = str(ativo or "").lower()
    return pdv == "300" or ("desktop" in ativo)


def _endereco_bloco(ch: dict) -> List[str]:
    return [
        f"Endereço: {ch.get('endereco','--')}",
        f"Estado: {ch.get('estado','--')}",
        f"CEP: {ch.get('cep','--')}",
        f"Cidade: {ch.get('cidade','--')}",
        "------",
        "⚠️ *É OBRIGATÓRIO LEVAR:*",
        f"• ISO ({'Desktop' if _is_desktop(ch.get('pdv'), ch.get('ativo')) else 'do PDV'}) "
        f"({ISO_DESKTOP_URL if _is_desktop(ch.get('pdv'), ch.get('ativo')) else ISO_PDV_URL})",
        f"• RAT: ({RAT_URL})",
    ]


def gerar_mensagem_por_loja(loja: str, chamados: Iterable[dict]) -> str:
    """
    Gera a mensagem compacta por loja, sem status/tipo/ data_agendada na
    parte do chamado. Os links ISO/RAT vêm após o endereço (uma vez).
    """
    chamados = list(chamados)
    blocos: List[str] = []
    # monta os chamados
    for ch in chamados:
        linhas = [
            f"*{ch.get('key','--')}*",
            f"Loja: {loja}",
            f"PDV: {ch.get('pdv','--')}",
            f"*ATIVO: {ch.get('ativo','--')}*",
            f"Problema: {ch.get('problema','--')}",
            "***",
        ]
        blocos.append("\n".join(linhas))

    # endereço + ISO/RAT uma vez (usa o último chamado que tiver endereço)
    ref = next((c for c in reversed(chamados) if any(c.get(k) for k in ("endereco", "estado", "cep", "cidade"))), None)
    if ref:
        blocos.append("\n".join(_endereco_bloco(ref)))

    return "\n\n".join(blocos)


def group_by_date(issues: Iterable[dict]) -> dict[str, List[dict]]:
    """
    Agrupa por data (prioriza `data_agendada`; senão `created`).
    Usa formato dd/mm/aaaa.
    """
    out: dict[str, List[dict]] = {}
    for it in issues:
        d = _fmt_iso_datetime(it.get("data_agendada")) or _fmt_iso_datetime(it.get("created")) or "Sem data"
        out.setdefault(d, []).append(it)
    return out


def group_by_store(issues: Iterable[dict]) -> dict[str, List[dict]]:
    """Agrupa por campo normalizado 'loja'."""
    out: dict[str, List[dict]] = {}
    for it in issues:
        loja = it.get("loja") or "Loja Desconhecida"
        out.setdefault(loja, []).append(it)
    return out
