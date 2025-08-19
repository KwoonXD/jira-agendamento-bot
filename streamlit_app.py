from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Dict, List

import streamlit as st

from utils.jira_api import JiraAPI
from utils.messages import gerar_mensagem, verificar_duplicidade


# =========================
# Configuração básica da página
# =========================
st.set_page_config(page_title="Painel Field Service", layout="wide")
st.title("Painel Field Service")


# =========================
# JQLs – ajuste aqui se necessário
# =========================
JQLS = {
    "agendamento": "project = FSA AND status = AGENDAMENTO ORDER BY created DESC",
    "agendado":    "project = FSA AND status = Agendado ORDER BY created DESC",
    "tec":         "project = FSA AND status = 'TEC-CAMPO' ORDER BY created DESC",
}


# =========================
# Carrega credenciais SOMENTE de st.secrets['jira']
# =========================
try:
    JIRA_URL = st.secrets["jira"]["url"]
    JIRA_EMAIL = st.secrets["jira"]["email"]
    JIRA_TOKEN = st.secrets["jira"]["token"]
except KeyError:
    st.error("Credenciais do Jira não encontradas em `st.secrets['jira']`.")
    st.stop()


# =========================
# Conexão com o Jira
# =========================
try:
    jira = JiraAPI(JIRA_URL, JIRA_EMAIL, JIRA_TOKEN)
    me = jira.whoami()
    st.caption(f"Conectado ao Jira como **{me.get('displayName', JIRA_EMAIL)}**")
except Exception as e:
    st.error(f"Falha na conexão com o Jira: {e}")
    st.stop()


# =========================
# Funções auxiliares de dados
# =========================
def _buscar(status_key: str) -> List[Dict]:
    """Busca issues normalizadas (usa utils.jira_api)."""
    return jira.search_issues(JQLS[status_key])


def _agrupar_por_data(chamados: List[Dict]) -> Dict[str, List[Dict]]:
    grupos = defaultdict(list)
    for c in chamados:
        # usa data_agendada se houver; senão created
        raw = c.get("data_agendada") or c.get("created")
        dia = "Sem data"
        if raw:
            for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%fZ"):
                try:
                    dt = datetime.strptime(raw, fmt)
                    dia = dt.strftime("%d/%m/%Y")
                    break
                except Exception:
                    pass
        grupos[dia].append(c)
    # Ordena por data, deixando "Sem data" por último
    return dict(sorted(grupos.items(), key=lambda kv: (kv[0] == "Sem data", kv[0])))


def _agrupar_por_loja(chamados: List[Dict]) -> Dict[str, List[Dict]]:
    g = defaultdict(list)
    for c in chamados:
        g[str(c.get("loja") or "Loja --")].append(c)
    return dict(sorted(g.items()))


def _badge(txt: str, bg: str) -> str:
    return (
        f"<span style='background:{bg};padding:4px 8px;border-radius:8px;"
        f"font-weight:600;font-size:12px;color:#0D0D0D;'>{txt}</span>"
    )


def _secao(status_key: str, cor: str) -> None:
    try:
        chamados = _buscar(status_key)
    except Exception as e:
        st.error(f"Falha ao carregar **{status_key.upper()}**: {e}")
        return

    if not chamados:
        st.info(f"Nenhum chamado em **{status_key.upper()}**.")
        return

    grupos_data = _agrupar_por_data(chamados)
    total = sum(len(v) for v in grupos_data.values())

    st.markdown(
        f"### Chamados {status_key.upper()} ({total}) " + _badge(status_key.upper(), cor),
        unsafe_allow_html=True,
    )

    for dia, itens_dia in grupos_data.items():
        lojas = _agrupar_por_loja(itens_dia)
        qtd = sum(len(v) for v in lojas.values())

        with st.expander(f"{dia} — {qtd} chamado(s)", expanded=False):
            for loja, itens in lojas.items():
                # alerta de duplicidade (PDV, ATIVO)
                dups = verificar_duplicidade(itens)
                if dups:
                    texto = ", ".join([f"PDV {p or '--'} / ATIVO {a or '--'}" for (p, a) in dups])
                    st.warning(f"⚠️ Possíveis duplicidades: {texto}")

                # FSAs listadas
                st.caption("FSAs: " + ", ".join(d["key"] for d in itens))

                # Mensagem padrão (com ISO e RAT no final), vinda do utils/messages.py
                st.code(gerar_mensagem(loja, itens), language="text")

            st.divider()


# =========================
# UI principal – abas
# =========================
tab1, tab2, tab3 = st.tabs(["AGENDAMENTO", "AGENDADO", "TEC-CAMPO"])

with tab1:
    _secao("agendamento", "#FFB84D")

with tab2:
    _secao("agendado", "#B7F7BD")

with tab3:
    _secao("tec", "#C6E4FF")
