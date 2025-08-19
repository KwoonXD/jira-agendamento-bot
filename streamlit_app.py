# streamlit_app.py
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Dict, List

import streamlit as st

from utils.jira_api import JiraAPI
from utils.messages import gerar_mensagem, verificar_duplicidade


# ---------------------- Config da página ----------------------
st.set_page_config(page_title="Painel Field Service", layout="wide")
st.title("Painel Field Service")


# ---------------------- JQLs (ajuste se precisar) -------------
JQLS = {
    "agendamento": "project = FSA AND status = AGENDAMENTO ORDER BY created DESC",
    "agendado":    "project = FSA AND status = Agendado ORDER BY created DESC",
    "tec":         "project = FSA AND status = 'TEC-CAMPO' ORDER BY created DESC",
}


# ---------------------- Secrets obrigatórios -------------------
def _secrets_or_stop() -> Dict[str, str]:
    """
    Lê SOMENTE st.secrets['jira'].
    Se faltar algo, exibe instruções e interrompe com st.stop().
    """
    try:
        sec = st.secrets["jira"]
        url   = str(sec["url"]).strip()
        email = str(sec["email"]).strip()
        token = str(sec["token"]).strip()
        if not url or not email or not token:
            raise KeyError("Parâmetros vazios.")
        return {"url": url, "email": email, "token": token}
    except Exception:
        st.error("Credenciais do Jira não encontradas em st.secrets['jira'].")
        guia = (
            "[jira]\n"
            'url   = "https://seu-dominio.atlassian.net"\n'
            'email = "seu-email@dominio"\n'
            'token = "seu_api_token"\n'
        )
        st.markdown(
            (
                "**Como configurar** (Streamlit Cloud → ••• → *Settings* → *Secrets*):\n\n"
                "```toml\n" + guia + "```\n"
            )
        )
        st.stop()


creds = _secrets_or_stop()
jira = JiraAPI(creds["url"], creds["email"], creds["token"])


# ---------------------- Helpers de dados -----------------------
@st.cache_data(ttl=120, show_spinner=True)
def buscar(status_key: str) -> List[Dict]:
    return jira.search_issues(JQLS[status_key])


def agrupar_por_data(chamados: List[Dict]) -> Dict[str, List[Dict]]:
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
    return dict(sorted(grupos.items(), key=lambda kv: (kv[0] == "Sem data", kv[0])))


def agrupar_por_loja(chamados: List[Dict]) -> Dict[str, List[Dict]]:
    g = defaultdict(list)
    for c in chamados:
        g[str(c.get("loja") or "Loja --")].append(c)
    return dict(sorted(g.items()))


def _badge(texto: str, cor_fundo: str, cor_texto: str = "#0D0D0D") -> str:
    return (
        "<span style='background:{bg};padding:4px 8px;border-radius:8px;"
        "font-weight:600;font-size:12px;color:{fg};'>{t}</span>"
    ).format(bg=cor_fundo, fg=cor_texto, t=texto)


def _secao(status_nome: str, cor_badge: str) -> None:
    chamados = buscar(status_nome)
    if not chamados:
        st.info(f"Nenhum chamado em **{status_nome.upper()}**.")
        return

    grupos_data = agrupar_por_data(chamados)
    total = sum(len(v) for v in grupos_data.values())

    st.markdown(
        f"### Chamados {status_nome.upper()} ({total}) " + _badge(status_nome.upper(), cor_badge),
        unsafe_allow_html=True,
    )

    for dia, lista_no_dia in grupos_data.items():
        lojas = agrupar_por_loja(lista_no_dia)
        qtd = sum(len(v) for v in lojas.values())

        with st.expander(f"{dia} — {qtd} chamado(s)", expanded=False):
            for loja, itens in lojas.items():
                dups = verificar_duplicidade(itens)
                if dups:
                    # monta “PDV X / ATIVO Y” sem f-string aninhada
                    duplas = ", ".join(["PDV {p} / ATIVO {a}".format(p=pdv or "--", a=ativo or "--") for pdv, ativo in dups])
                    st.warning(f"⚠️ Possíveis duplicidades: {duplas}")

                st.caption(f"FSAs: {', '.join(d['key'] for d in itens)}")
                st.code(gerar_mensagem(loja, itens), language="text")
            st.divider()


# ---------------------- UI (abas) ------------------------------
tab1, tab2, tab3 = st.tabs(["AGENDAMENTO", "AGENDADO", "TEC-CAMPO"])

with tab1:
    _secao("agendamento", "#FFB84D")

with tab2:
    _secao("agendado", "#B7F7BD")

with tab3:
    _secao("tec", "#C6E4FF")
