# utils/messages.py
from __future__ import annotations
from typing import Dict, List, Tuple, Set


def is_desktop(ativo: str | None, pdv: str | int | None) -> bool:
    """
    Regras combinadas:
      - PDV numérico >= 300 => Desktop
      - Ou se o texto do ativo contiver "desktop"
    """
    if isinstance(pdv, int) and pdv >= 300:
        return True
    if isinstance(pdv, str):
        s = pdv.strip()
        if s.isdigit() and int(s) >= 300:
            return True
    if isinstance(ativo, str) and "desktop" in ativo.lower():
        return True
    return False


def gerar_mensagem(loja: str, chamados: List[Dict]) -> str:
    """
    Gera mensagem por loja para envio (WhatsApp/Teams/Email).
    NÃO inclui tipo de atendimento nem status (pedido recente).
    A ISO e RAT são tratados na tela.
    """
    blocos: List[str] = []
    ref_end = None

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

        if any(ch.get(k) for k in ("endereco", "estado", "cep", "cidade")):
            ref_end = ch  # última referência com endereço válido

    if ref_end:
        blocos.append("\n".join([
            f"Endereço: {ref_end.get('endereco','--')}",
            f"Estado: {ref_end.get('estado','--')}",
            f"CEP: {ref_end.get('cep','--')}",
            f"Cidade: {ref_end.get('cidade','--')}",
        ]))

    return "\n\n".join(blocos)


def verificar_duplicidade(chamados: List[Dict]) -> Set[Tuple[str | None, str | None]]:
    """
    Retorna tuplas (pdv, ativo) duplicadas dentro da coleção de chamados.
    Útil para destacar potenciais duplicidades.
    """
    seen: set[Tuple[str | None, str | None]] = set()
    dup: set[Tuple[str | None, str | None]] = set()
    for ch in chamados:
        key = (ch.get("pdv"), ch.get("ativo"))
        if key in seen:
            dup.add(key)
        else:
            seen.add(key)
    return dup
