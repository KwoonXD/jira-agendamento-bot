import streamlit as st
from streamlit_autorefresh import st_autorefresh
from datetime import datetime
from collections import defaultdict

from utils.jira_api import JiraAPI
from utils.messages import gerar_mensagem, verificar_duplicidade

# --- Configuração inicial ---
st.set_page_config(page_title="Painel Field Service", layout="wide")
st_autorefresh(interval=60_000, key="auto_refresh")

EMAIL = st.secrets["EMAIL"]
API_TOKEN = st.secrets["API_TOKEN"]
JIRA_URL = "https://delfia.atlassian.net"

jira = JiraAPI(EMAIL, API_TOKEN, JIRA_URL)

FIELDS = (
    "summary,"
    "customfield_14954,"  # Loja
    "customfield_14829,"  # PDV
    "customfield_14825,"  # Ativo
    "customfield_12374,"  # Problema
    "customfield_12271,"  # Endereço
    "customfield_11993,"  # CEP
    "customfield_11994,"  # Cidade
    "customfield_11948,"  # Estado
    "customfield_12036"   # Data Agendada
)

# --- Título ---
st.title("📱 Painel Field Service")

# --- Layout em duas colunas ---
col_agendamento, col_agendado = st.columns(2)

# Coluna 1: Chamados em Agendamento
with col_agendamento:
    st.header("⏳ Chamados AGENDAMENTO")
    chamados_agendamento = jira.buscar_chamados(
        jql="project = FSA AND status = AGENDAMENTO",
        fields=FIELDS
    )
    agrupado_agendamento = jira.agrupar_chamados(chamados_agendamento)

    if not chamados_agendamento:
        st.warning("Nenhum chamado pendente de AGENDAMENTO.")
    else:
        for loja, lista in agrupado_agendamento.items():
            with st.expander(f"{loja} — {len(lista)} chamado(s)", expanded=False):
                st.code(gerar_mensagem(loja, lista), language="text")

# Coluna 2: Chamados Agendados
with col_agendado:
    st.header("📋 Chamados AGENDADOS")
    chamados_agendados = jira.buscar_chamados(
        jql='project = FSA AND status = AGENDADO',
        fields=FIELDS
    )

    # Agrupar por data e loja
    agrupado_por_data = defaultdict(lambda: defaultdict(list))
    for issue in chamados_agendados:
        f = issue["fields"]
        loja = f.get("customfield_14954", {}).get("value", "Loja Desconhecida")
        data_raw = f.get("customfield_12036")
        data_str = "Não definida"
        if data_raw:
            data_str = datetime.strptime(
                data_raw, "%Y-%m-%dT%H:%M:%S.%f%z"
            ).strftime("%d/%m/%Y")
        agrupado_por_data[data_str][loja].append(issue)

    # Filtro de loja na sidebar
    todas_lojas = sorted({
        issue["fields"]
             .get("customfield_14954", {})
             .get("value", "Loja Desconhecida")
        for issue in chamados_agendados
    })
    loja_filtro = st.sidebar.multiselect(
        "🔍 Filtrar por loja:",
        options=["Todas"] + todas_lojas,
        default=["Todas"]
    )

    # Exibição com alertas
    for data_str, lojas in agrupado_por_data.items():
        # aplica filtro de loja
        lojas_visiveis = {
            loja: issues
            for loja, issues in lojas.items()
            if "Todas" in loja_filtro or loja in loja_filtro
        }
        total = sum(len(issues) for issues in lojas_visiveis.values())
        if total == 0:
            continue

        st.subheader(f"📅 {data_str} — {total} chamado(s)")
        for loja, issues in lojas_visiveis.items():
            detalhes = jira.agrupar_chamados(issues)[loja]
            duplicados = verificar_duplicidade(detalhes)

            # FSAs duplicadas (mesmo PDV + Ativo)
            fsas_duplicadas = [
                ch["key"] for ch in detalhes
                if (ch["pdv"], ch["ativo"]) in duplicados
            ]

            # FSAs em "Aguardando Spare"
            spare_issues = jira.buscar_chamados(
                jql=(
                    'project = FSA AND status = "Aguardando Spare" '
                    f'AND "Codigo da Loja[Dropdown]" = {loja}'
                ),
                fields=FIELDS
            )
            fsas_spare = [c["key"] for c in spare_issues]

            # Monta alerta
            alertas = []
            if fsas_duplicadas:
                alertas.append(f"🔴 Duplicidade: {', '.join(fsas_duplicadas)}")
            if fsas_spare:
                alertas.append(f"⚠️ Aguardando Spare: {', '.join(fsas_spare)}")
            tag = f"  [{'  •  '.join(alertas)}]" if alertas else ""

            with st.expander(f"{loja} — {len(issues)} chamado(s){tag}", expanded=False):
                st.code(gerar_mensagem(loja, detalhes), language="text")

# Rodapé
st.markdown("---")
st.caption(f"🕒 Última atualização: {datetime.now():%d/%m/%Y %H:%M:%S}")
