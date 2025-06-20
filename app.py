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

# ── Inicializa JiraAPI ──
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

# ── Sidebar: filtro por loja para AGENDADOS ──
all_agendados = jira.buscar_chamados('project = FSA AND status = AGENDADO', FIELDS)
lojas = sorted({
    issue["fields"]
         .get("customfield_14954", {})
         .get("value", "")
    for issue in all_agendados
})
sel_lojas = st.sidebar.multiselect("Filtrar loja:", ["Todas"] + lojas, default=["Todas"])

# ── Título e layout ──
st.title("📱 Painel Field Service")
col_pend, col_age = st.columns(2)

# ── Coluna 1: AGENDAMENTO ──
with col_pend:
    st.header("⏳ AGENDAMENTO")
    pendentes = jira.buscar_chamados("project = FSA AND status = AGENDAMENTO", FIELDS)
    agrup_pend = jira.agrupar_chamados(pendentes)

    if not pendentes:
        st.warning("Nenhum pendente.")
    else:
        for loja, issues in agrup_pend.items():
            label = f"{loja} — {len(issues)} chamados"
            with st.expander(label, expanded=False):
                st.code(gerar_mensagem(loja, issues), language="text")

# ── Coluna 2: AGENDADOS ──
with col_age:
    st.header("📋 AGENDADOS")
    grouped = defaultdict(lambda: defaultdict(list))
    for issue in all_agendados:
        f = issue["fields"]
        loja = f.get("customfield_14954", {}).get("value", "Loja Desconhecida")
        raw = f.get("customfield_12036")
        date = (
            datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S.%f%z").strftime("%d/%m/%Y")
            if raw else "Não definida"
        )
        grouped[date][loja].append(issue)

    for date, by_store in grouped.items():
        total = sum(len(v) for v in by_store.values())
        if total == 0:
            continue
        st.subheader(f"{date} — {total} chamados")

        for loja, issues in by_store.items():
            if "Todas" not in sel_lojas and loja not in sel_lojas:
                continue

            detalhes = jira.agrupar_chamados(issues)[loja]
            dup = verificar_duplicidade(detalhes)
            fsas_dup = [c["key"] for c in detalhes if (c["pdv"], c["ativo"]) in dup]
            spare = jira.buscar_chamados(
                f'project = FSA AND status = "Aguardando Spare" AND "Codigo da Loja[Dropdown]" = {loja}',
                FIELDS
            )
            fsas_spare = [c["key"] for c in spare]
            alerts = []
            if fsas_dup:
                alerts.append(f"Dup: {', '.join(fsas_dup)}")
            if fsas_spare:
                alerts.append(f"Spare: {', '.join(fsas_spare)}")
            tag = f" [{' • '.join(alerts)}]" if alerts else ""

            label = f"{loja} — {len(issues)} chamados{tag}"
            with st.expander(label, expanded=False):
                st.code(gerar_mensagem(loja, detalhes), language="text")

# ── Painel de Transição Global (por loja) ──
st.header("▶️ Transição de Chamados")
lojas_trans = sorted(agrup_pend.keys())
if not lojas_trans:
    st.info("Não há lojas com chamados em AGENDAMENTO.")
else:
    loja_sel = st.selectbox("Selecione a loja:", ["—"] + lojas_trans)
    if loja_sel != "—":
        # reúne FSAs pendentes e agendados desta loja
        pend = agrup_pend.get(loja_sel, [])
        ag = grouped  # reorganizado em dict de date->loja->issues
        sched = []
        for issues in grouped.values():
            sched += issues.get(loja_sel, [])
        # junta apenas chave e rótulo
        fsas = [i["key"] for i in pend] + [i["key"] for i in sched]
        fsas = sorted(set(fsas))
        selected = st.multiselect("FSAs desta loja:", fsas, default=fsas)
        if selected:
            trans = jira.get_transitions(selected[0])
            opts = {t["name"]: t["id"] for t in trans}
            choice = st.selectbox("Transição:", ["—"] + list(opts.keys()), key="trans_choice")
            if choice != "—" and st.button("Aplicar Transição"):
                prev = jira.get_issue(selected[0]).get("fields", {}).get("status", {}).get("name", "")
                for key in selected:
                    jira.transicionar_status(key, opts[choice])
                st.success(f"{len(selected)} FSAs movidos → {choice}")
                st.session_state.history.append({"keys": selected, "from": prev})

# ── Rodapé ──
st.markdown("---")
st.caption(f"Última atualização: {datetime.now():%d/%m/%Y %H:%M:%S}")
