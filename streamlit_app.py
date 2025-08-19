# streamlit_app.py
import streamlit as st
import yaml
import os

from utils.jira_api import JiraAPI
from utils.messages import gerar_mensagem, verificar_duplicidade
from utils.export_utils import exportar_para_excel


# ===============================================================
# Carregar credenciais do arquivo credentials.yaml
# ===============================================================
def load_credentials():
    cred_path = os.path.join(os.path.dirname(__file__), "credentials.yaml")
    if not os.path.exists(cred_path):
        st.error("Arquivo credentials.yaml não encontrado!")
        st.stop()

    with open(cred_path, "r") as f:
        creds = yaml.safe_load(f)

    try:
        jira_cfg = creds["jira"]
        return jira_cfg["url"], jira_cfg["email"], jira_cfg["token"]
    except Exception as e:
        st.error(f"Erro ao carregar credentials.yaml: {e}")
        st.stop()


# ===============================================================
# Inicialização
# ===============================================================
st.set_page_config(page_title="Painel Field Service", layout="wide")
st.title("Painel Field Service")

jira_url, jira_email, jira_token = load_credentials()

# Instanciar JiraAPI
jira = JiraAPI(url=jira_url, email=jira_email, token=jira_token)


# ===============================================================
# Funções auxiliares
# ===============================================================
def buscar_chamados(jql: str):
    try:
        return jira.search_issues(jql)
    except Exception as e:
        st.error(f"Erro ao buscar dados do Jira: {e}")
        return []


# ===============================================================
# Layout principal
# ===============================================================
tab_agendamento, tab_agendado, tab_teccampo = st.tabs(
    ["AGENDAMENTO", "AGENDADO", "TEC-CAMPO"]
)

with tab_agendamento:
    st.subheader("Chamados em AGENDAMENTO")
    jql = "project = FSA AND status = AGENDAMENTO ORDER BY created DESC"
    issues = buscar_chamados(jql)
    if issues:
        st.write(issues)
        if st.button("Exportar Excel - AGENDAMENTO"):
            exportar_para_excel(issues, "Agendamento.xlsx")
    else:
        st.info("Nenhum chamado encontrado em AGENDAMENTO.")

with tab_agendado:
    st.subheader("Chamados AGENDADOS")
    jql = "project = FSA AND status = Agendado ORDER BY created DESC"
    issues = buscar_chamados(jql)
    if issues:
        st.write(issues)
        if st.button("Exportar Excel - AGENDADO"):
            exportar_para_excel(issues, "Agendado.xlsx")
    else:
        st.info("Nenhum chamado encontrado em AGENDADO.")

with tab_teccampo:
    st.subheader("Chamados em TEC-CAMPO")
    jql = "project = FSA AND status = 'Tec-campo' ORDER BY created DESC"
    issues = buscar_chamados(jql)
    if issues:
        st.write(issues)
        if st.button("Exportar Excel - TEC-CAMPO"):
            exportar_para_excel(issues, "TecCampo.xlsx")
    else:
        st.info("Nenhum chamado encontrado em TEC-CAMPO.")
