import streamlit as st
from streamlit_autorefresh import st_autorefresh
from datetime import datetime
from utils.jira_api import JiraAPI
from utils.messages import gerar_mensagem
from collections import defaultdict

# Configuração inicial
st.set_page_config(page_title="Chamados em Agendamento", layout="wide")
st_autorefresh(interval=60000, key="auto_refresh")

# Carregar secrets
EMAIL = st.secrets["EMAIL"]
API_TOKEN = st.secrets["API_TOKEN"]
JIRA_URL = "https://delfia.atlassian.net"

jira = JiraAPI(EMAIL, API_TOKEN, JIRA_URL)

# Chamados em AGENDAMENTO
st.title("📱 Chamados em Agendamento")
st.header("⏳ Chamados PENDENTES de Agendamento")

fields = "summary,customfield_14954,customfield_14829,customfield_14825,customfield_12374,customfield_12271,customfield_11993,customfield_11994,customfield_11948,customfield_12036"
chamados = jira.buscar_chamados("project = FSA AND status = AGENDAMENTO", fields)
agrupado = jira.agrupar_chamados(chamados)

if not chamados:
    st.warning("Nenhum chamado em AGENDAMENTO encontrado no momento.")
else:
    st.success(f"{len(chamados)} chamados em AGENDAMENTO encontrados.")
    for loja, lista in agrupado.items():
        with st.expander(f"Loja {loja} - {len(lista)} chamado(s)", expanded=False):
            st.code(gerar_mensagem(loja, lista), language="text")

# Chamados em AGENDADO
st.header("📋 Chamados AGENDADOS")
chamados_agendados = jira.buscar_chamados("project = FSA AND status = AGENDADO", fields)
agrupado_por_data = defaultdict(lambda: defaultdict(list))

for issue in chamados_agendados:
    fields = issue["fields"]
    loja = fields.get("customfield_14954", {}).get("value", "Loja Desconhecida")
    data_agendada = fields.get("customfield_12036", "Não definida")
    if data_agendada != "Não definida":
        data_agendada = datetime.strptime(data_agendada, "%Y-%m-%dT%H:%M:%S.%f%z").strftime('%d/%m/%Y')

    agrupado_por_data[data_agendada][loja].append(issue)

loja_selecionada = st.sidebar.selectbox("🔎 Filtrar por loja:", ["Todas"] + sorted({loja for data in agrupado_por_data for loja in agrupado_por_data[data]}))

for data, lojas in agrupado_por_data.items():
    total_chamados = sum(len(ch) for loja, ch in lojas.items() if loja_selecionada in ["Todas", loja])
    if total_chamados == 0:
        continue
    st.subheader(f"📅 Data: {data} ({total_chamados} chamado(s))")
    for loja, lista in lojas.items():
        if loja_selecionada not in ["Todas", loja]:
            continue
        with st.expander(f"Loja {loja} ({len(lista)})", expanded=False):
            chamados_detalhados = jira.agrupar_chamados(lista)[loja]
            st.code(gerar_mensagem(loja, chamados_detalhados), language="text")

# Última atualização
st.markdown("---")
st.caption(f"🕒 Última atualização: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
