# streamlit_app.py
from __future__ import annotations
import os
import yaml
from collections import defaultdict
from datetime import datetime
from typing import Dict, List

import streamlit as st

from utils.jira_api import JiraAPI
from utils.messages import gerar_mensagem, verificar_duplicidade


# =========================
# CONFIG
# =========================
st.set_page_config(page_title="Painel Field Service", layout="wide")
st.title("Painel Field Service")

# JQLs fixos
JQLS = {
    "agendamento": "project = FSA AND status = AGENDAMENTO ORDER BY created DESC",
    "agendado":    "project = FSA AND status = Agendado ORDER BY created DESC",
    "tec":         "project = FSA AND status = 'TEC-CAMPO' ORDER BY created DESC",
}


# =========================
# CREDENTIALS
# =========================
def carregar_credenciais() -> Dict[str, str]:
    """
    Modelo “antigo”: lemos sempre de credentials.yaml (na raiz).
    """
    cred_path = os.path.join(os.path.dirname(__file__), "credentials.yaml")
    if not os.path.exists(cred_path):
        st.error("Arquivo credentials.yaml não encontrado na raiz do projeto.")
        st.stop()

    with open(cred_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    try:
        jira = cfg["jira"]
        return {
            "url": jira["url"],
            "email": jira["email"],
            "token": jira["token"],
        }
    except Exception as e:
        st.error(f"Erro ao ler credentials.yaml: {e}")
        st.stop()


creds = carregar_credenciais()
jira = JiraAPI(creds["url"], creds["email"], creds["token"])


# =========================
# HELPERS
# =========================
@st.cache_data(ttl=120, show_spinner=True)
def buscar(status_key: str) -> List[Dict]:
    """Busca no Jira e retorna lista de dicts normalizados."""
    return jira.search_issues(JQLS[status_key])


def agrupar_por_data(chamados: List[Dict]) -> Dict[str, List[Dict]]:
    """
    Agrupa por data “dd/mm/aaaa” usando, na ordem:
    - data_agendada (se disponível)
    - created (fallback)
    - “Sem data”
    """
    grupos = defaultdict(list)
    for c in chamados:
        raw = c.get("data_agendada") or c.get("created")
        dia = "Sem data"
        if raw:
            for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%fZ"):
                try:
                    dt = datetime.strptime(raw, fmt)
                    dia = dt.strftime("%d/%m/%Y")
                    break
                except Exception:
                    continue
        grupos[dia].append(c)
    return dict(sorted(grupos.items(), key=lambda kv: (kv[0] == "Sem data", kv[0])))


def agrupar_por_loja(chamados: List[Dict]) -> Dict[str, List[Dict]]:
    g = defaultdict(list)
    for c in chamados:
        g[str(c.get("loja") or "Loja --")].append(c)
    return dict(sorted(g.items()))


def _header_badge(texto: str, cor_fundo: str, cor_texto: str = "#0D0D0D") -> str:
    return (
        f"<span style='background:{cor_fundo};padding:4px 8px;"
        f"border-radius:8px;font-weight:600;font-size:12px;color:{cor_texto};'>{texto}</span>"
    )


def _mostrar_secao(status_nome: str, cor_badge: str):
    chamados = buscar(status_nome)
    if not chamados:
        st.info(f"Nenhum chamado em **{status_nome.upper()}**.")
        return

    grupos_data = agrupar_por_data(chamados)

    total = sum(len(v) for v in grupos_data.values())
    st.markdown(
        f"### Chamados {status_nome.upper()} ({total}) "
        + _header_badge(status_nome.upper(), cor_badge),
        unsafe_allow_html=True,
    )

    for dia, lista_no_dia in grupos_data.items():
        lojas = agrupar_por_loja(lista_no_dia)
        qtd = sum(len(v) for v in lojas.values())
        with st.expander(f"{dia} — {qtd} chamado(s)", expanded=False):

            for loja, itens in lojas.items():
                # possíveis duplicidades (PDV/ATIVO)
                dups = verificar_duplicidade(itens)
                if dups:
                    duplas = ", ".join([f"PDV {pdv or '--'} / ATIVO {ativo or '--'}" for pdv, ativo in dups])
                    st.warning(f"⚠️ Possíveis duplicidades: {duplas}")

                st.caption(f"FSAs: {', '.join(d['key'] for d in itens)}")
                st.code(
                    gerar_mensagem(loja, itens),
                    language="text",
                )
            st.divider()


# =========================
# UI (abas)
# =========================
tab1, tab2, tab3 = st.tabs(["AGENDAMENTO", "AGENDADO", "TEC-CAMPO"])

with tab1:
    _mostrar_secao("agendamento", "#FFB84D")

with tab2:
    _mostrar_secao("agendado", "#B7F7BD")

with tab3:
    _mostrar_secao("tec", "#C6E4FF")
