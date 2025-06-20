import streamlit as st
from datetime import datetime
from collections import defaultdict

from utils.jira_api import JiraAPI
from utils.messages import gerar_mensagem, verificar_duplicidade

# Configuração
st.set_page_config(page_title="Painel Field Service", layout="wide")
jira = JiraAPI(st.secrets["EMAIL"], st.secrets["API_TOKEN"], "https://delfia.atlassian.net")

# Botão manual de refresh
if st.button("🔄 Atualizar"):
    st.experimental_rerun()

# Histório para undo
if "history" not in st.session_state:
    st.session_state.history = []

# Sidebar: desfazer
st.sidebar.header("Ações")
if st.sidebar.button("↩️ Desfazer última ação") and st.session_state.history:
    action = st.session_state.history.pop()
    reverted = 0
    for key in action["keys"]:
        trans = jira.get_transitions(key)
        rev = next((t["id"] for t in trans if t["to"]["name"] == action["from"]), None)
        if rev and jira.transicionar_status(key, rev):
            reverted += 1
    st.sidebar.success(f"Revertido: {reverted} → {action['from']}")

# Sidebar: filtro loja para agendados
FIELDS = (
    "summary,customfield_14954,customfield_14829,customfield_14825,"
    "customfield_12374,customfield_12271,customfield_11993,"
    "customfield_11994,customfield_11948,customfield_12036"
)
all_agendados = jira.buscar_chamados('project=FSA AND status=AGENDADO', FIELDS)
lojas = sorted({i["fields"].get("customfield_14954",{}).get("value","") for i in all_agendados})
sel_lojas = st.sidebar.multiselect("Filtrar loja:", ["Todas"]+lojas, default=["Todas"])

st.title("📱 Painel Field Service")
col1, col2 = st.columns(2)

# ── PENDENTES (AGENDAMENTO) ──
with col1:
    st.header("⏳ AGENDAMENTO")
    pend = jira.buscar_chamados("project=FSA AND status=AGENDAMENTO", FIELDS)
    grp = jira.agrupar_chamados(pend)
    if not pend:
        st.warning("Nenhum pendente.")
    else:
        for loja, issues in grp.items():
            key = f"pend_{loja}"
            with st.expander(f"{loja} — {len(issues)} chamados", expanded=True, key=key):
                st.code(gerar_mensagem(loja, issues), language="text")
                # bulk
                keys = [i["key"] for i in issues]
                sel = st.multiselect("Selecionar FSAs:", keys, default=keys, key=key+"_sel")
                if sel:
                    opts = {t["name"]:t["id"] for t in jira.get_transitions(keys[0])}
                    choice = st.selectbox("Transição:", ["—"]+list(opts), key=key+"_tr")
                    if choice!="—" and st.button("Aplicar em todos", key=key+"_btn"):
                        prev = jira.get_issue(sel[0]).get("fields",{}).get("status",{}).get("name","")
                        for k in sel:
                            jira.transicionar_status(k, opts[choice])
                        st.session_state.history.append({"keys":sel,"from":prev})
                        st.success(f"{len(sel)} → {choice}")

# ── AGENDADOS ──
with col2:
    st.header("📋 AGENDADOS")
    grouped = defaultdict(lambda: defaultdict(list))
    for issue in all_agendados:
        f = issue["fields"]
        loja = f.get("customfield_14954",{}).get("value","Loja Desconhecida")
        raw = f.get("customfield_12036")
        date = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S.%f%z").strftime("%d/%m/%Y") if raw else "Não definida"
        grouped[date][loja].append(issue)

    for date, by_store in grouped.items():
        total = sum(len(v) for v in by_store.values())
        if total==0: continue
        st.subheader(f"{date} — {total} chamados")
        for loja, issues in by_store.items():
            if "Todas" not in sel_lojas and loja not in sel_lojas: continue

            detalhes = jira.agrupar_chamados(issues)[loja]
            dup = verificar_duplicidade(detalhes)
            fsas_dup = [c["key"] for c in detalhes if (c["pdv"],c["ativo"]) in dup]
            spare = jira.buscar_chamados(
                f'project=FSA AND status="Aguardando Spare" AND "Codigo da Loja[Dropdown]"={loja}', 
                FIELDS
            )
            fsas_spare = [c["key"] for c in spare]
            alerts = []
            if fsas_dup:   alerts.append("Dup: "+", ".join(fsas_dup))
            if fsas_spare: alerts.append("Spare: "+", ".join(fsas_spare))
            tag = " ["+" • ".join(alerts)+"]" if alerts else ""

            key = f"age_{date}_{loja}"
            with st.expander(f"{loja} — {len(issues)} chamados"+tag, expanded=True, key=key):
                st.code(gerar_mensagem(loja, detalhes), language="text")
                # bulk
                keys = [c["key"] for c in detalhes]
                sel = st.multiselect("Selecionar FSAs:", keys, default=keys, key=key+"_sel")
                if sel:
                    opts = {t["name"]:t["id"] for t in jira.get_transitions(keys[0])}
                    choice = st.selectbox("Transição:", ["—"]+list(opts), key=key+"_tr")
                    if choice!="—" and st.button("Aplicar em todos", key=key+"_btn"):
                        prev = jira.get_issue(sel[0]).get("fields",{}).get("status",{}).get("name","")
                        for k in sel:
                            jira.transicionar_status(k, opts[choice])
                        st.session_state.history.append({"keys":sel,"from":prev})
                        st.success(f"{len(sel)} → {choice}")

st.markdown("---")
st.caption(f"Última atualização: {datetime.now():%d/%m/%Y %H:%M:%S}")
