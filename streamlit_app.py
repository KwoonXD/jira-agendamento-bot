from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Dict, List

import streamlit as st
import requests

from utils.jira_api import JiraAPI
from utils.messages import gerar_mensagem, verificar_duplicidade


# ---------------- Configuração visual básica ----------------
st.set_page_config(page_title="Painel Field Service", layout="wide")
st.title("Painel Field Service")

# ---------------- JQLs (ajuste se precisar) ----------------
JQLS = {
    "agendamento": "project = FSA AND status = AGENDAMENTO ORDER BY created DESC",
    "agendado":    "project = FSA AND status = Agendado ORDER BY created DESC",
    "tec":         "project = FSA AND status = 'TEC-CAMPO' ORDER BY created DESC",
}


# ---------------- Sidebar: credenciais simples ---------------
def _init_state():
    ss = st.session_state
    ss.setdefault("jira_url", "")
    ss.setdefault("jira_email", "")
    ss.setdefault("jira_token", "")
    ss.setdefault("jira_ok", False)

_init_state()

with st.sidebar:
    st.subheader("Credenciais Jira")
    st.caption("Preencha e clique em **Usar credenciais**.")

    st.text_input("Jira URL", key="jira_url", placeholder="https://seu-dominio.atlassian.net")
    st.text_input("E-mail", key="jira_email", placeholder="seu-email@dominio")
    st.text_input("Token", key="jira_token", type="password")

    cols = st.columns(2)
    with cols[0]:
        if st.button("Usar credenciais", use_container_width=True):
            st.session_state["jira_ok"] = bool(
                st.session_state["jira_url"]
                and st.session_state["jira_email"]
                and st.session_state["jira_token"]
            )
    with cols[1]:
        if st.button("Testar conexão", use_container_width=True):
            try:
                cli = JiraAPI(
                    st.session_state["jira_url"],
                    st.session_state["jira_email"],
                    st.session_state["jira_token"],
                )
                me = cli.whoami()
                st.success(f"Conectado como **{me.get('displayName','?')}**")
            except Exception as e:
                st.error(f"Falha: {e}")

    if st.session_state["jira_ok"]:
        st.success("Credenciais em uso.")
    else:
        st.warning("Aguardando credenciais.")


# --------------- Helpers de dados (simples) ------------------
def _buscar(cli: JiraAPI, status_key: str) -> List[Dict]:
    """Busca issues do Jira já normalizadas (usa utils.jira_api)."""
    return cli.search_issues(JQLS[status_key])


def _agrupar_por_data(chamados: List[Dict]) -> Dict[str, List[Dict]]:
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
                    pass
        grupos[dia].append(c)
    # ordena com "Sem data" no fim
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


def _secao(cli: JiraAPI, status_key: str, cor: str) -> None:
    try:
        chamados = _buscar(cli, status_key)
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
                dups = verificar_duplicidade(itens)
                if dups:
                    texto = ", ".join([f"PDV {p or '--'} / ATIVO {a or '--'}" for (p, a) in dups])
                    st.warning(f"⚠️ Possíveis duplicidades: {texto}")

                st.caption("FSAs: " + ", ".join(d["key"] for d in itens))
                st.code(gerar_mensagem(loja, itens), language="text")
            st.divider()


# --------------- UI principal (somente se logado) ------------
if not st.session_state["jira_ok"]:
    st.stop()

cli = JiraAPI(
    st.session_state["jira_url"],
    st.session_state["jira_email"],
    st.session_state["jira_token"],
)

tab1, tab2, tab3 = st.tabs(["AGENDAMENTO", "AGENDADO", "TEC-CAMPO"])

with tab1:
    _secao(cli, "agendamento", "#FFB84D")

with tab2:
    _secao(cli, "agendado", "#B7F7BD")

with tab3:
    _secao(cli, "tec", "#C6E4FF")
