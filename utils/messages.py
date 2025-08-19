# utils/messages.py
from __future__ import annotations
from datetime import datetime
from typing import List, Dict, Tuple

# LINKS PADRÃO
ISO_DESKTOP_URL = "https://drive.google.com/file/d/1GQ64blQmysK3rbM0s0Xlot89bDNAbj5L/view?usp=drive_link"
ISO_PDV_URL     = "https://drive.google.com/file/d/1vxfHUDlT3kDdMaN0HroA5Nm9_OxasTaf/view?usp=drive_link"
RAT_URL         = "https://drive.google.com/file/d/1_SG1RofIjoJLgwWYs0ya0fKlmVd74Lhn/view?usp=sharing"


def _fmt_data(raw: str | None) -> str:
    if not raw:
        return "--"
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%fZ"):
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.strftime("%d/%m/%Y %H:%M")
        except Exception:
            pass
    return raw


def _tipo_atendimento(d: Dict[str, str | int | None]) -> str:
    pdv = d.get("pdv")
    ativo = (d.get("ativo") or "").upper()
    try:
        if pdv is not None and int(pdv) >= 300:
            return "Desktop"
    except Exception:
        pass
    if "DESKTOP" in ativo:
        return "Desktop"
    return "PDV"


def _bloco_chamado(d: Dict[str, str | int | None]) -> str:
    return "\n".join([
        f"*{d.get('key','--')}*",
        f"Loja: {d.get('loja','--')}",
        f"PDV: {d.get('pdv','--')}",
        f"*ATIVO: {d.get('ativo','--')}*",
        f"Problema: {d.get('problema','--')}",
        "***",
    ])


def _bloco_endereco(ref: Dict[str, str | int | None]) -> str:
    return "\n".join([
        f"Endereço: {ref.get('endereco','--')}",
        f"Estado: {ref.get('estado','--')}",
        f"CEP: {ref.get('cep','--')}",
        f"Cidade: {ref.get('cidade','--')}",
        "------",
    ])


def _links_obrigatorios(detalhes: List[Dict[str, str | int | None]]) -> str:
    tem_desktop = any(_tipo_atendimento(x) == "Desktop" for x in detalhes)
    tem_pdv = any(_tipo_atendimento(x) == "PDV" for x in detalhes)

    linhas = ["⚠️ *É OBRIGATÓRIO LEVAR:*"]
    if tem_pdv:
        linhas.append(f"• ISO (do PDV) ({ISO_PDV_URL})")
    if tem_desktop:
        linhas.append(f"• ISO (Desktop) ({ISO_DESKTOP_URL})")
    linhas.append(f"• RAT: ({RAT_URL})")
    return "\n".join(linhas)


def gerar_mensagem(loja: str, chamados: List[Dict[str, str | int | None]]) -> str:
    if not chamados:
        return ""

    blocos = []
    for ch in chamados:
        blocos.append(_bloco_chamado(ch))

    ref = next((c for c in chamados if any(c.get(k) for k in ("endereco", "estado", "cep", "cidade"))), None)
    if ref:
        blocos.append(_bloco_endereco(ref))

    blocos.append(_links_obrigatorios(chamados))
    return "\n".join(blocos)


def verificar_duplicidade(chamados: List[Dict[str, str | int | None]]) -> List[Tuple[str | None, str | None]]:
    seen = {}
    dups = set()
    for ch in chamados:
        key = (str(ch.get("pdv")), str(ch.get("ativo")))
        if key in seen:
            dups.add(key)
        else:
            seen[key] = True
    return sorted(dups)
