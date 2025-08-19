# utils/messages.py
# -*- coding: utf-8 -*-
"""
Geração de mensagem por loja + verificação de duplicidade.

Compatível com Python 3.11 (sem walrus operator dentro de comprehensions, etc.).
"""

ISO_DESKTOP_URL = "https://drive.google.com/file/d/1GQ64blQmysK3rbM0s0Xlot89bDNAbj5L/view?usp=drive_link"
ISO_PDV_URL     = "https://drive.google.com/file/d/1vxfHUDLT3kDDMaN0HroA5Nm9_OxasTaf/view?usp=drive_link"
RAT_URL         = "https://drive.google.com/file/d/1_SG1RofIjoJLgwWYs0ya0fKlmVd74Lhn/view?usp=sharing"


def _is_pdv(ch: dict) -> bool:
    """PDV 300+ é PDV; se 'Desktop' aparece no ativo, tratamos como Desktop."""
    pdv = str(ch.get("pdv", "")).strip()
    ativo = str(ch.get("ativo", "")).lower()
    try:
        pdv_num = int(pdv)
    except Exception:
        pdv_num = -1
    return pdv_num >= 300 and "desktop" not in ativo


def _bloco_endereco(ch: dict) -> list[str]:
    """Bloco final com endereço + links ISO/RAT (ISO por tipo)."""
    iso = ISO_PDV_URL if _is_pdv(ch) else ISO_DESKTOP_URL
    iso_label = "ISO (do PDV)" if _is_pdv(ch) else "ISO (Desktop)"

    linhas = [
        f"Endereço: {ch.get('endereco', '--')}",
        f"Estado: {ch.get('estado', '--')}",
        f"CEP: {ch.get('cep', '--')}",
        f"Cidade: {ch.get('cidade', '--')}",
        "------",
        "⚠️ *É OBRIGATÓRIO LEVAR:*",
        f"• {iso_label} ({iso})",
        f"• RAT: ({RAT_URL})",
    ]
    return linhas


def gerar_mensagem(loja: str, chamados: list[dict]) -> str:
    """
    Gera a mensagem (um bloco por chamado) e adiciona o endereço/links apenas 1x ao final.
    Sem status e sem data, como você pediu anteriormente.
    """
    linhas: list[str] = []
    for ch in chamados:
        linhas.extend(
            [
                f"*{ch.get('key', '--')}*",
                f"Loja: {loja}",
                f"PDV: {ch.get('pdv', '--')}",
                f"*ATIVO:* {ch.get('ativo', '--')}",
                f"Problema: {ch.get('problema', '--')}",
                "***",
            ]
        )

    # Endereço uma única vez: pega o último chamado que tenha pelo menos um dos campos.
    ref = None
    for c in reversed(chados := chamados):  # NÃO usar o valor 'chados' depois; só para manter a ordem
        if any(c.get(k) for k in ("endereco", "estado", "cep", "cidade")):
            ref = c
            break
    if ref:
        linhas.extend(_bloco_endereco(ref))

    return "\n".join(linhas)


def verificar_duplicidade(chamados: list[dict]) -> set[tuple[str, str]]:
    """Retorna pares (pdv, ativo) que se repetem."""
    vistos = set()
    dups = set()
    for ch in chamados:
        chave = (str(ch.get("pdv")), str(ch.get("ativo")))
        if chave in vistos:
            dups.add(chave)
        else:
            vistos.add(chave)
    return dups
