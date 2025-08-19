import os
import streamlit as st
from utils.jira_api import JiraAPI
from utils.messages import gerar_mensagem, agrupar_por_data, agrupar_por_loja

FIELDS = ",".join([
    "status","created",
    "customfield_14954","customfield_14829","customfield_14825","customfield_12374",
    "customfield_12271","customfield_11948","customfield_11993","customfield_11994","customfield_12036"
])
JQLS = {
    "agendamento": 'project = FSA AND status = "AGENDAMENTO"',
    "agendado": 'project = FSA AND status = "AGENDADO"',
    "tec": 'project = FSA AND status = "TEC-CAMPO"',
}

st.set_page_config(page_title="Painel Field Service", layout="wide")

# Sidebar
with st.sidebar:
    url = st.text_input("Jira URL", value=os.getenv("JIRA_URL",""))
    email = st.text_input("E-mail", value=os.getenv("JIRA_EMAIL",""))
    token = st.text_input("Token", type="password", value=os.getenv("JIRA_TOKEN",""))
    if st.button("Testar conexão"):
        try:
            me = JiraAPI(email, token, url).whoami()
            st.success(f"Conectado como {me.get('displayName')}")
        except Exception as e:
            st.error(str(e))

@st.cache_data(ttl=180)
def carregar(url,email,token):
    if not (url and email and token):
        return {
            "agendamento":[{"key":"FSA-1","loja":"L001","pdv":"309","ativo":"CPU","problema":"Teste","created":"2025-08-12T10:00:00.000+0000"}],
            "agendado":[],
            "tec":[]
        }
    cli = JiraAPI(email,token,url)
    return {
        "agendamento":[JiraAPI.normalizar(i) for i in cli.buscar_chamados(JQLS["agendamento"],FIELDS)],
        "agendado":[JiraAPI.normalizar(i) for i in cli.buscar_chamados(JQLS["agendado"],FIELDS)],
        "tec":[JiraAPI.normalizar(i) for i in cli.buscar_chamados(JQLS["tec"],FIELDS)],
    }

DATA = carregar(url,email,token)

st.title("Painel Field Service")
tabs = st.tabs(["AGENDAMENTO","AGENDADO","TEC-CAMPO"])
for (nome,chaves),tab in zip(DATA.items(),tabs):
    with tab:
        por_data = agrupar_por_data(chaves)
        for d,lista in sorted(por_data.items()):
            with st.expander(f"{d} — {len(lista)} chamado(s)"):
                por_loja = agrupar_por_loja(lista)
                for loja,chamados in por_loja.items():
                    st.markdown(f"**{loja}**")
                    st.code(gerar_mensagem(loja,chamados),language="text")
