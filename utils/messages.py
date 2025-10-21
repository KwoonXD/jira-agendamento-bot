"""Utilitários para gerar mensagens de despacho."""
from __future__ import annotations

from datetime import datetime
from typing import Dict, Iterable, List

TEMPLATE_PADRAO = "padrao"
TEMPLATE_URGENTE = "urgente"
TEMPLATE_RESUMIDO = "resumido"

_TEMPLATES: Dict[str, str] = {
    TEMPLATE_PADRAO: (
        "Bom dia!\n\n"
        "*Despacho Loja {loja}*\n\n"
        "{lista_chamados}\n\n"
        "{bloco_endereco}\n\n"
        "*SEMPRE AO CHEGAR NO LOCAL É NECESSÁRIO ACIONAR O SUPORTE E ENVIAR AS FOTOS NECESSÁRIAS*"
    ),
    TEMPLATE_URGENTE: (
        "*ATENÇÃO: ATENDIMENTO URGENTE*\n\n"
        "Loja {loja}\n\n"
        "{lista_chamados}\n\n"
        "{bloco_endereco}\n\n"
        "Favor priorizar este chamado e confirmar o deslocamento imediatamente."
    ),
    TEMPLATE_RESUMIDO: (
        "Loja {loja}\n"
        "{lista_chamados}\n\n"
        "{bloco_endereco}"
    ),
}

TEMPLATES_DISPONIVEIS: Dict[str, str] = {
    TEMPLATE_PADRAO: "Padrão",
    TEMPLATE_URGENTE: "Urgente",
    TEMPLATE_RESUMIDO: "Resumo",
}


def _formatar_bloco_chamado(chamado: Dict[str, str]) -> str:
    linhas = [
        f"*{chamado.get('key', '--')}*",
        f"Loja: {chamado.get('loja', '--')}",
        f"PDV: {chamado.get('pdv', '--')}",
        f"*ATIVO: {chamado.get('ativo', '--')}*",
        f"Problema: {chamado.get('problema', '--')}",
    ]

    agenda = chamado.get("data_agendada") or chamado.get("data_agendada_raw")
    if agenda:
        try:
            agenda_dt = datetime.fromisoformat(str(agenda).replace("Z", "+00:00"))
            linhas.append(f"Agendado para: {agenda_dt.strftime('%d/%m/%Y %H:%M')}")
        except ValueError:
            linhas.append(f"Agendado para: {agenda}")

    linhas.append("***")
    return "\n".join(linhas)


def _montar_bloco_endereco(chamados: Iterable[Dict[str, str]]) -> str:
    endereco_info = None
    for chamado in chamados:
        endereco_info = (
            chamado.get("endereco", "--"),
            chamado.get("estado", "--"),
            chamado.get("cep", "--"),
            chamado.get("cidade", "--"),
        )
    if endereco_info:
        endereco, estado, cep, cidade = endereco_info
        return "\n".join(
            [
                f"Endereço: {endereco}",
                f"Estado: {estado}",
                f"CEP: {cep}",
                f"Cidade: {cidade}",
            ]
        )
    return "Endereço não informado"


def gerar_mensagem(loja: str, chamados: List[Dict[str, str]], template_id: str = TEMPLATE_PADRAO) -> str:
    """Gera a mensagem para os chamados de uma loja usando um template."""

    if not chamados:
        return "Sem chamados para esta loja."

    template = _TEMPLATES.get(template_id, _TEMPLATES[TEMPLATE_PADRAO])
    blocos = [_formatar_bloco_chamado(ch) for ch in chamados]
    bloco_endereco = _montar_bloco_endereco(chamados)

    corpo = template.format(
        loja=loja,
        lista_chamados="\n\n".join(blocos),
        bloco_endereco=bloco_endereco,
    )
    return corpo.strip()


def verificar_duplicidade(chamados: Iterable[Dict[str, str]]):
    """Retorna conjunto de tuplas (pdv, ativo) duplicadas."""

    vistos = {}
    duplicados = set()
    for chamado in chamados:
        chave = (chamado.get("pdv"), chamado.get("ativo"))
        if chave in vistos:
            duplicados.add(chave)
        else:
            vistos[chave] = True
    return duplicados

