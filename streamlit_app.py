# streamlit_app.py
# ---------------------------------------------
# Painel Field Service - versão simples e direta
# ---------------------------------------------
from __future__ import annotations

import sys
from datetime import datetime
from typing import Dict, List

import streamlit as st

# ---- Imports do projeto
from utils.jira_api import JiraAPI
from utils.messages import gerar_mensagem, verificar_duplicidade

# ---------------------------------------------
# Configuração geral da página (tema escuro ok)
# ---------------------------------------------
st.set_page_config(
    page_title="Painel Field Service",
    page_icon="🛠️",
    layout="wide",
)

# ---------------------------------------------
# Leitura de credenciais do Streamlit Secrets
# (padrão: App settings > Secrets)
# ---------------------------------------------
def _read_secrets() -> Dict[str, str]:
    try:
        s = st.secrets["jira"]
        return {
            "url": s["url"],
            "email": s["email"],
            "token": s["token"],
        }
    except Exception:
        with st.sidebar:
            st.error("Credenciais do Jira não encontradas em `st.secrets['jira']`.")
            st.markdown(
                "Adicione no App secrets (Streamlit Cloud) ou em `secrets.toml` local:\n\n"
                "```toml\n"
                "[jira]\n"
                "url   = \"https://seu-domínio.atlassian.net\"\n"
                "email = \"seu-email@dominio\"\n"
                "token = \"seu_api_token\"\n"
                "```"
            )
        st.stop()


# ---------------------------------------------
# JQLs básicos e campos que usamos (API v3)
# Ajuste as strings abaixo conforme seu fluxo
# ---------------------------------------------
JQLS = {
    "agendamento": 'project = FSA AND status = "AGENDAMENTO"',
    "agendado": 'project = FSA AND status = "AGENDADO"',
    "tec_campo": 'project = FSA AND status = "TEC-CAMPO"',
}

# Campos necessários para gerar a mensagem e agrupar
# (nomes de customfields iguais aos que você já usa)
FIELDS = ",".join(
    [
        "status",
        "customfield_14954",  # loja (Option)
        "customfield_14829",  # PDV
        "customfield_14825",  # ATIVO (Option)
        "customfield_12374",  # Problema
        "customfield_12271",  # Endereço
        "customfield_11948",  # Estado (Option)
        "customfield_11993",  # CEP
        "customfield_11994",  # Cidade
        "customfield_12036",  # Data agendada (seu campo)
    ]
)

# ---------------------------------------------
# Cliente Jira a partir do secrets
# ---------------------------------------------
@st.cache_resource(show_spinner=False)
def jira_client() -> JiraAPI:
    cred = _read_secrets()
    return JiraAPI(
        email=cred["email"],
        api_token=cred["token"],
        jira_url=cred["url"],
    )


# ---------------------------------------------
# Busca e normalização dos dados (com cache)
# ---------------------------------------------
@st.cache_data(ttl=60, show_spinner=False)
def carregar() -> Dict[str, Dict[str, List[Dict]]]:
    """
    Retorna um dict com 3 chaves: agendamento, agendado, tec_campo
    Cada valor é outro dict: { loja: [chamados normalizados] }
    """
    cli = jira_client()

    # Buscar issues por status
    pend = cli.buscar_chamados(JQLS["agendamento"], FIELDS)
    agnd = cli.buscar_chamados(JQLS["agendado"], FIELDS)
    tecc = cli.buscar_chamados(JQLS["tec_campo"], FIELDS)

    # Agrupar por loja com o método existente no seu utils
    g_pend = cli.agrupar_chamados(pend)
    g_agnd = cli.agrupar_chamados(agnd)
    g_tecc = cli.agrupar_chamados(tecc)

    return {"agendamento": g_pend, "agendado": g_agnd, "tec_campo": g_tecc}


# ---------------------------------------------
# UI helpers
# ---------------------------------------------
def badge(texto: str, cor: str) -> str:
    cores = {
        "pend": "#FFB84D",      # laranja
        "agnd": "#1AD18E",      # verde
        "tec": "#42A5F5",       # azul
        "dup": "#FF6B6B",       # vermelho
        "ok": "#7EE081",        # verde suave
        "info": "#9CA3AF",      # cinza
    }
    bg = cores.get(cor, "#9CA3AF")
    return (
        f"<span style='background:{bg};padding:4px 8px;border-radius:8px;"
        f"font-weight:600;font-size:12px;color:#0B0F14'>{texto}</span>"
    )


def header_grupo(titulo: str, qtd: int, tag: str) -> None:
    if tag == "pend":
        b = badge("PENDENTE", "pend")
    elif tag == "agnd":
        b = badge("AGENDADO", "agnd")
    else:
        b = badge("TEC-CAMPO", "tec")

    st.markdown(
        f"### {titulo} {b}  "
        f"<span style='color:#9CA3AF;font-size:13px'>({qtd} lojas)</span>",
        unsafe_allow_html=True,
    )


def expander_titulo(loja: str, chamados: List[Dict]) -> str:
    """
    Texto do expander: `LOJA — N chamado(s) (X PDV • Y Desktop)` + badges de tipo
    """
    qtd = len(chamados)
    # PDV = 300 é Desktop? -> a regra de "PDV 300 = Desktop" foi usada nas mensagens,
    # aqui apenas mostramos contagens de PDV vs "Desktop" por heurística de ativo.
    n_pdv = sum(1 for c in chamados if str(c.get("pdv", "")).isdigit())
    n_desk = sum(
        1
        for c in chamados
        if "desktop" in str(c.get("ativo", "")).lower() or str(c.get("pdv")) == "300"
    )
    return f"{loja} — {qtd} chamado(s) ({n_pdv} PDV • {n_desk} Desktop)"


def bloco_por_loja(loja: str, detalhes: List[Dict]) -> None:
    """
    Exibe um expander com a mensagem pronta por loja.
    Mostra também alerta de duplicidade (PDV+ATIVO repetidos).
    """
    with st.expander(expander_titulo(loja, detalhes), expanded=False):
        # Duplicidade (PDV + ATIVO)
        dups = verificar_duplicidade(detalhes)
        if dups:
            st.markdown(badge("DUPLICADO (PDV+ATIVO)", "dup"), unsafe_allow_html=True)
            st.caption(", ".join(f"PDV {pdv} • ATIVO {ativo}" for (pdv, ativo) in dups))
            st.divider()

        # Mensagem no formato WhatsApp/operacional
        st.code(gerar_mensagem(loja, detalhes), language="text")


# ---------------------------------------------
# Layout principal
# ---------------------------------------------
st.title("Painel Field Service")

try:
    dados = carregar()
except Exception as e:
    st.error(f"Falha ao carregar dados do Jira: {e}")
    st.stop()

tab1, tab2, tab3 = st.tabs(["AGENDAMENTO", "AGENDADO", "TEC-CAMPO"])

with tab1:
    grp = dados["agendamento"]
    if not grp:
        st.info("Nenhum chamado em **AGENDAMENTO**.")
    else:
        header_grupo("Chamados AGENDAMENTO", len(grp), "pend")
        for loja, dets in sorted(grp.items()):
            bloco_por_loja(loja, dets)

with tab2:
    grp = dados["agendado"]
    if not grp:
        st.info("Nenhum chamado **AGENDADO**.")
    else:
        header_grupo("Chamados AGENDADOS", len(grp), "agnd")
        for loja, dets in sorted(grp.items()):
            bloco_por_loja(loja, dets)

with tab3:
    grp = dados["tec_campo"]
    if not grp:
        st.info("Nenhum chamado em **TEC‑CAMPO**.")
    else:
        header_grupo("Chamados TEC‑CAMPO", len(grp), "tec")
        for loja, dets in sorted(grp.items()):
            bloco_por_loja(loja, dets)

st.caption(f"Última atualização: {datetime.now():%d/%m/%Y %H:%M:%S}")
