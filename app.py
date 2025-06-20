import streamlit as st
from streamlit_autorefresh import st_autorefresh
from datetime import datetime
from collections import defaultdict

from utils.jira_api import JiraAPI
from utils.messages import gerar_mensagem, verificar_duplicidade

# ── Configuração da página e auto‐refresh (90s) ──
st.set_page_config(page_title="Painel Field Service", layout="wide")
st_autorefresh(interval=90_000, key="auto_refresh")

# ── Histórico de undo ──
if "history" not in st.session_state:
    st.session_state.history = []

# ── Instancia JiraAPI ──
jira = JiraAPI(
    st.secrets["EMAIL"],
    st.secrets["API_TOKEN"],
    "https://delfia.atlassian.net"
)

# ── Campos para busca ──
FIELDS = (
    "summary,customfield_14954,customfield_14829,customfield_14825,"
    "customfield_12374,customfield_12271,customfield_11993,"
    "customfield_11994,customfield_11948,customfield_12036"
)

# ── Busca e agrupa pendentes ──
pendentes_raw = jira.buscar_chamados("project = FSA AND status = AGENDAMENTO", FIELDS)
agrup_pend    = jira.agrupar_chamados(pendentes_raw)

# ── Busca raw de agendados ──
agendados_raw = jira.buscar_chamados('project = FSA AND status = AGENDADO', FIELDS)

# ── Agrupa agendados por data e loja ──
grouped = defaultdict(lambda: defaultdict(list))
for issue in agendados_raw:
    f = issue["fields"]
    loja = f.get("customfield_14954", {}).get("value", "Loja Desconhecida")
    raw  = f.get("customfield_12036")
    date = (
        datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S.%f%z")
                .strftime("%d/%m/%Y")
        if raw else "Não definida"
    )
    grouped[date][loja].append(issue)

# ── Sidebar: Ações e Transição (mantém seu fluxo atual) ──
with st.sidebar:
    st.header("Ações")
    # ... (seu código de desfazer e transições)

# ── Main ──
st.title("📱 Painel Field Service")
col1, col2 = st.columns(2)

# Coluna 1: Pendentes
with col1:
    st.header("⏳ Chamados PENDENTES de Agendamento")
    if not pendentes_raw:
        st.warning("Nenhum chamado em AGENDAMENTO.")
    else:
        for loja, issues in agrup_pend.items():
            with st.expander(f"{loja} — {len(issues)} chamados", expanded=False):
                st.code(gerar_mensagem(loja, issues), language="text")

# Coluna 2: Agendados (com data, spare, duplicados, FSA)
with col2:
    st.header("📋 Chamados AGENDADOS")
    if not agendados_raw:
        st.info("Nenhum chamado em AGENDADO.")
    else:
        # percorre datas
        for date_str, stores in sorted(grouped.items()):
            total = sum(len(lst) for lst in stores.values())
            st.subheader(f"{date_str} — {total} chamado(s)")
            for loja, issues in sorted(stores.items()):
                # prepara detalhes normalizados
                detalhes = jira.agrupar_chamados(issues)[loja]
                # identifica duplicados (mesmo PDV+Ativo)
                dup_keys   = [d["key"] for d in detalhes if (d["pdv"], d["ativo"]) in verificar_duplicidade(detalhes)]
                # busca spare para esta loja
                spare_raw  = jira.buscar_chamados(
                    f'project = FSA AND status = "Aguardando Spare" AND "Codigo da Loja[Dropdown]" = {loja}',
                    FIELDS
                )
                spare_keys = [i["key"] for i in spare_raw]
                # monta tags
                tags = []
                if spare_keys: tags.append("Spare: " + ", ".join(spare_keys))
                if dup_keys:   tags.append("Dup: "   + ", ".join(dup_keys))
                tag_str = f" [{' • '.join(tags)}]" if tags else ""

                with st.expander(f"{loja} — {len(issues)} chamado(s){tag_str}", expanded=False):
                    # lista de keys
                    st.markdown("**FSAs:** " + ", ".join([d["key"] for d in detalhes]))
                    # detalhes completos
                    st.code(gerar_mensagem(loja, detalhes), language="text")

st.markdown("---")
st.caption(f"Última atualização: {datetime.now():%d/%m/%Y %H:%M:%S}")
