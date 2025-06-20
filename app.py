import streamlit as st
from streamlit_autorefresh import st_autorefresh
from datetime import datetime
from utils.jira_api import JiraAPI
from utils.messages import gerar_mensagem, verificar_duplicidade
from collections import defaultdict

# --- Configuração inicial ---
st.set_page_config(page_title="Painel Field Service", layout="wide")
st_autorefresh(interval=60000, key="auto_refresh")

EMAIL = st.secrets["EMAIL"]
API_TOKEN = st.secrets["API_TOKEN"]
JIRA_URL = "https://delfia.atlassian.net"

jira = JiraAPI(EMAIL, API_TOKEN, JIRA_URL)

fields = "summary,customfield_14954,customfield_14829,customfield_14825,customfield_12374,customfield_12271,customfield_11993,customfield_11994,customfield_11948,customfield_12036"

# --- Título principal ---
st.title("📱 Painel Field Service")

# --- Layout em colunas ---
col_agendamento, col_agendado = st.columns(2)

# --- Coluna AGENDAMENTO ---
with col_agendamento:
    st.header("⏳ Chamados AGENDAMENTO")
    chamados_agendamento = jira.buscar_chamados("project = FSA AND status = AGENDAMENTO", fields)
    agrupado_agendamento = jira.agrupar_chamados(chamados_agendamento)

    if not chamados_agendamento:
        st.warning("Nenhum chamado pendente de AGENDAMENTO.")
    else:
        for loja, lista in agrupado_agendamento.items():
            with st.expander(f"{loja} - {len(lista)} chamado(s)", expanded=False):
                st.code(gerar_mensagem(loja, lista), language="text")

# --- Coluna AGENDADOS ---
with col_agendado:
    st.header("📋 Chamados AGENDADOS")
    chamados_agendados = jira.buscar_chamados("project = FSA AND status = AGENDADO", fields)

    # Agrupamento inicial dos chamados agendados
    agrupado_por_data = defaultdict(lambda: defaultdict(list))
    for issue in chamados_agendados:
        fields = issue["fields"]
        loja = fields.get("customfield_14954", {}).get("value", "Loja Desconhecida")
        data_agendada = fields.get("customfield_12036", "Não definida")
        if data_agendada != "Não definida":
            data_agendada = datetime.strptime(data_agendada, "%Y-%m-%dT%H:%M:%S.%f%z").strftime('%d/%m/%Y')

        agrupado_por_data[data_agendada][loja].append(issue)

    # Sidebar com filtros
    lojas_disponiveis = sorted({issue["fields"].get("customfield_14954", {}).get("value", "Loja Desconhecida") for issue in chamados_agendados})
    loja_filtro = st.sidebar.multiselect("🔍 Filtrar por loja:", ["Todas"] + lojas_disponiveis, default="Todas")

    # Loop principal para exibição com alertas detalhados
    for data, lojas in agrupado_por_data.items():
        lojas_filtradas = {loja: issues for loja, issues in lojas.items() if "Todas" in loja_filtro or loja in loja_filtro}
        total_chamados = sum(len(ch) for ch in lojas_filtradas.values())
        if total_chamados == 0:
            continue

        st.subheader(f"📅 {data} ({total_chamados} chamados)")
        for loja, issues in lojas_filtradas.items():
            chamados_detalhados = jira.agrupar_chamados(issues)[loja]
            duplicados = verificar_duplicidade(chamados_detalhados)

            # FSAs duplicadas explicitamente
            fsas_duplicadas = [ch['key'] for ch in chamados_detalhados if (ch['ativo'], ch['problema']) in duplicados]

            # FSAs em aguardando spare explicitamente
            com_spare = jira.buscar_chamados(f'project = FSA AND status = "Aguardando Spare" AND "Codigo da Loja[Dropdown]" = {loja}', fields)
            fsas_spare = [c["key"] for c in com_spare]

            # Mensagem de alerta detalhada
            alertas = ""
            if duplicados:
                alertas += f"🔴 Duplicidade: {', '.join(fsas_duplicadas)}. "
            if com_spare:
                alertas += f"⚠️ Aguardando Spare: {', '.join(fsas_spare)}."

            with st.expander(f"{loja} - {len(issues)} chamado(s) {alertas}", expanded=False):
                st.code(gerar_mensagem(loja, chamados_detalhados), language="text")

# --- Rodapé ---
st.markdown("---")
st.caption(f"🕒 Última atualização automática: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
