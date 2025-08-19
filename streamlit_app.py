# streamlit_app.py
import streamlit as st
import requests
from utils.jira_api import JiraAPI

st.set_page_config(page_title="Jira Agendamento", layout="wide")

st.title("📅 Bot de Agendamento Jira")

# ------------------- carregar dados do Jira -------------------
@st.cache_data(ttl=120)
def _carregar_raw() -> dict:
    jira = JiraAPI(
        email=st.secrets["jira"]["email"],
        api_token=st.secrets["jira"]["api_token"],
        jira_url=st.secrets["jira"]["url"],
        timeout=25,
    )
    FIELDS = "key,status,customfield_14954,customfield_14829,customfield_14825,customfield_12374,customfield_12271,customfield_11948,customfield_11993,customfield_11994,customfield_12036"
    JQLS = {
        "pend": 'project = FSA AND status = "AGENDAMENTO"',
        "agend": 'project = FSA AND status = "AGENDADO"',
        "tec": 'project = FSA AND status = "TEC-CAMPO"',
    }

    return {
        "pend": jira.buscar_chamados(JQLS["pend"], FIELDS),
        "agend": jira.buscar_chamados(JQLS["agend"], FIELDS),
        "tec": jira.buscar_chamados(JQLS["tec"], FIELDS),
    }

try:
    raw = _carregar_raw()
except requests.HTTPError as e:
    st.error("❌ Falha ao consultar a API do Jira.")
    st.exception(e)  # mostra payload detalhado
    st.stop()
except Exception as e:
    st.error("❌ Erro inesperado ao carregar dados do Jira.")
    st.exception(e)
    st.stop()

# ------------------- interface simples -------------------
tab1, tab2, tab3 = st.tabs(["📋 Pendentes", "📆 Agendados", "🛠️ Técnico em campo"])

with tab1:
    st.subheader("Chamados Pendentes")
    st.write(f"Total: {len(raw['pend'])}")
    st.json(raw["pend"][:5])

with tab2:
    st.subheader("Chamados Agendados")
    st.write(f"Total: {len(raw['agend'])}")
    st.json(raw["agend"][:5])

with tab3:
    st.subheader("Chamados com Técnico em Campo")
    st.write(f"Total: {len(raw['tec'])}")
    st.json(raw["tec"][:5])
