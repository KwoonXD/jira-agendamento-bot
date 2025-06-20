import streamlit as st
from streamlit_autorefresh import st_autorefresh
from datetime import datetime
from collections import defaultdict

from utils.jira_api import JiraAPI
from utils.messages import gerar_mensagem, verificar_duplicidade

# ── Configuração da página e auto‐refresh ──
st.set_page_config(page_title="Painel Field Service", layout="wide")
st_autorefresh(interval=90_000, key="auto_refresh")  # 1m30s

# ── Botão manual de refresh ──
if st.button("🔄 Atualizar agora"):
    st.experimental_rerun()

# ── Histórico de undo ──
if "history" not in st.session_state:
    st.session_state.history = []

# ── Instancia JiraAPI ──
jira = JiraAPI(
    st.secrets["EMAIL"],
    st.secrets["API_TOKEN"],
    "https://delfia.atlassian.net"
)

FIELDS = (
    "summary,customfield_14954,customfield_14829,customfield_14825,"
    "customfield_12374,customfield_12271,customfield_11993,"
    "customfield_11994,customfield_11948,customfield_12036"
)

# ── Sidebar: desfazer última ação ──
st.sidebar.header("Ações")
if st.sidebar.button("↩️ Desfazer última ação"):
    if st.session_state.history:
        action = st.session_state.history.pop()
        reverted = 0
        for key in action["keys"]:
            trans = jira.get_transitions(key)
            rev_id = next(
                (t["id"] for t in trans if t.get("to", {}).get("name") == action["from"]),
                None
            )
            if rev_id and jira.transicionar_status(key, rev_id):
                reverted += 1
        st.sidebar.success(f"Revertido: {reverted} FSAs → {action['from']}")
    else:
        st.sidebar.info("Nenhuma ação para desfazer.")

# ── Cabeçalho e layout ──
st.title("📱 Painel Field Service")
col_pending, col_scheduled = st.columns(2)

# ── Coluna 1: Pendentes de Agendamento ──
with col_pending:
    st.header("⏳ Chamados PENDENTES de Agendamento")
    pending_issues = jira.buscar_chamados("project = FSA AND status = AGENDAMENTO", FIELDS)
    grouped_pending = jira.agrupar_chamados(pending_issues)

    if not pending_issues:
        st.warning("Nenhum chamado em AGENDAMENTO.")
    else:
        for loja, issues in grouped_pending.items():
            with st.expander(f"{loja} — {len(issues)} chamados", expanded=False):
                st.code(gerar_mensagem(loja, issues), language="text")

# ── Coluna 2: Agendados ──
with col_scheduled:
    st.header("📋 Chamados AGENDADOS")
    scheduled_issues = jira.buscar_chamados('project = FSA AND status = AGENDADO', FIELDS)
    grouped_scheduled = defaultdict(lambda: defaultdict(list))

    for issue in scheduled_issues:
        f = issue["fields"]
        loja = f.get("customfield_14954", {}).get("value", "Loja Desconhecida")
        raw = f.get("customfield_12036")
        date = (
            datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S.%f%z").strftime("%d/%m/%Y")
            if raw else "Não definida"
        )
        grouped_scheduled[date][loja].append(issue)

    for date, stores in grouped_scheduled.items():
        total = sum(len(iss) for iss in stores.values())
        if total == 0:
            continue
        st.subheader(f"{date} — {total} chamados")
        for loja, issues in stores.items():
            with st.expander(f"{loja} — {len(issues)} chamados", expanded=False):
                st.code(gerar_mensagem(loja, jira.agrupar_chamados(issues)[loja]), language="text")

# ── Painel de Transição (pendentes apenas) ──
st.markdown("---")
st.header("▶️ Transição de Chamados em Agendamento")

# lojas com pendentes
lojas_pend = sorted(grouped_pending.keys())
if not lojas_pend:
    st.info("Não há lojas com chamados em AGENDAMENTO.")
else:
    loja_sel = st.selectbox("Selecione a loja:", ["—"] + lojas_pend)
    if loja_sel != "—":
        issues = grouped_pending[loja_sel]
        fsas = [ch["key"] for ch in issues]
        selected = st.multiselect(
            "FSAs em Agendamento:",
            options=fsas,
            default=fsas,
            key="fsas_to_transition"
        )

        if selected:
            trans = jira.get_transitions(selected[0])
            opts = {t["name"]: t["id"] for t in trans}
            choice = st
