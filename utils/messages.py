# utils/messages.py
from typing import Iterable, Dict, Any, List, Set, Tuple

# Links padrão – personalize se quiser via st.secrets no app
ISO_DESKTOP_URL = "https://drive.google.com/file/d/1GQ64blQmysK3rbM0s0Xlot89bDNAbj5L/view?usp=drive_link"
ISO_PDV_URL     = "https://drive.google.com/file/d/1vxfHUDlT3kDdMaN0HroA5Nm9_OxasTaf/view?usp=drive_link"
RAT_URL         = "https://drive.google.com/file/d/1_SG1RofIjoJLgwWYs0ya0fKlmVd74Lhn/view?usp=sharing"

def _is_desktop(pdv: str | int | None, ativo: str | None) -> bool:
    pdv_str = str(pdv or "").strip()
    ativo_str = (ativo or "").lower()
    return pdv_str == "300" or "desktop" in ativo_str

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
    Inclui bloco '⚠️ É OBRIGATÓRIO LEVAR' no final com ISO(s) e RAT.
    """
    chamados = list(chamados)  # materializa
    blocos: List[str] = []

    for ch in chamados:
        linhas = [
            f"*{ch.get('key','--')}*",
            f"Loja: {loja}",
            f"PDV: {ch.get('pdv','--')}",
            f"*ATIVO:* {ch.get('ativo','--')}",
            f"Problema: {ch.get('problema','--')}",
            "***",
        ]
        blocos.append("\n".join(linhas))

    # Endereço (uma vez por loja — pega do último chamado que tenha dados)
    ref = next(
        (c for c in reversed(chorados := chamados)  # noqa: F841 (apenas pra manter compat lint, mas não usar 'chorados')
        if any(c.get(k) for k in ("endereco", "estado", "cep", "cidade"))),
        None
    )
    # corrigindo explicitamente o nome usado:
    ref = next(
        (c for c in reversed(chamados)
         if any(c.get(k) for k in ("endereco", "estado", "cep", "cidade"))),
        None
    )
    if ref:
        blocos.append("\n".join(_fmt_endereco(ref)))

    # Bloco obrigatório com links
    any_desktop = any(_is_desktop(c.get("pdv"), c.get("ativo")) for c in chamados)
    any_pdv     = any(not _is_desktop(c.get("pdv"), c.get("ativo")) for c in chamados)

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
    vistos: Set[Tuple[str, str]] = set()
    dup: Set[Tuple[str, str]] = set()
    for ch in chamados:
        key = (str(ch.get("pdv") or ""), str(ch.get("ativo") or ""))
        if key in vistos:
            dup.add(key)
        else:
            vistos.add(key)
    return dup
