# utils/messages.py
from datetime import datetime
from typing import Iterable, Dict, Any, List, Set, Tuple

ISO_DESKTOP_URL = "https://drive.google.com/file/d/1GQ64blQmysK3rbM0s0Xlot89bDNAbj5L/view?usp=drive_link"
ISO_PDV_URL     = "https://drive.google.com/file/d/1vxfHUDlT3kDdMaN0HroA5Nm9_OxasTaf/view?usp=drive_link"
RAT_URL         = "https://drive.google.com/file/d/1_SG1RofIjoJLgwWYs0ya0fKlmVd74Lhn/view?usp=sharing"

def _is_desktop(ch: Dict[str, Any]) -> bool:
    # Regra: PDV == 300 => Desktop, OU texto do ativo menciona 'desktop'
    pdv = str(ch.get("pdv") or "")
    ativo = (ch.get("ativo") or "").lower()
    return pdv == "300" or "desktop" in ativo

def _iso_link(ch: Dict[str, Any]) -> str:
    return ISO_DESKTOP_URL if _is_desktop(ch) else ISO_PDV_URL

def _fmt_endereco(ch: Dict[str, Any]) -> List[str]:
    return [
        f"Endereço: {ch.get('endereco','--')}",
        f"Estado: {ch.get('estado','--')}",
        f"CEP: {ch.get('cep','--')}",
        f"Cidade: {ch.get('cidade','--')}",
    ]

def gerar_mensagem(loja: str, chamados: Iterable[Dict[str, Any]]) -> str:
    """
    Gera o texto para WhatsApp/Teams (sem Status e sem Tipo de atendimento).
    Inclui bloco '⚠️ É OBRIGATÓRIO LEVAR' no final com ISO e RAT.
    """
    chamados = list(chados for chados in chamados)  # materializa
    blocos: List[str] = []

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

    # Endereço (uma vez por loja — pega do último chamado não vazio)
    ref = next((c for c in reversed(chados) if any(c.get(k) for k in ("endereco","estado","cep","cidade"))), None)
    if ref:
        blocos.append("\n".join(_fmt_endereco(ref)))

    # Bloco obrigatório com links
    # Se houver misto Desktop/PDV, mostramos os dois links de ISO.
    any_desktop = any(_is_desktop(c) for c in chamados)
    any_pdv     = any(not _is_desktop(c) for c in chamados)

    obrigatorio: List[str] = ["------", "⚠️ *É OBRIGATÓRIO LEVAR:*"]
    if any_desktop:
        obrigatorio.append(f"• ISO (Desktop): {ISO_DESKTOP_URL}")
    if any_pdv:
        obrigatorio.append(f"• ISO (PDV): {ISO_PDV_URL}")
    obrigatorio.append(f"• RAT: {RAT_URL}")

    blocos.append("\n".join(obrigatorio))
    return "\n\n".join(blocos)

def verificar_duplicidade(chamados: Iterable[Dict[str, Any]]) -> Set[Tuple[str, str]]:
    """
    Retorna pares (pdv, ativo) repetidos.
    """
    seen: Set[Tuple[str, str]] = set()
    dup: Set[Tuple[str, str]] = set()
    for ch in chamados:
        key = (str(ch.get("pdv") or ""), str(ch.get("ativo") or ""))
        if key in seen:
            dup.add(key)
        else:
            seen.add(key)
    return dup
