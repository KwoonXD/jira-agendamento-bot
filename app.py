import streamlit as st
from streamlit_autorefresh import st_autorefresh
from datetime import datetime
from collections import defaultdict

from utils.jira_api import JiraAPI
from utils.messages import gerar_mensagem, verificar_duplicidade

# Configuração da página e auto‐refresh (90s)
st.set_page_config(page_title="Painel Field Service", layout="wide")
st_autorefresh(interval=90_000, key="auto_refresh")

# Histórico de undo
if "history" not in st.session_state:
    st.session_state.history = []

# Inicializa JiraAPI
jira = JiraAPI(
    st.secrets["EMAIL"],
    st.secrets["API_TOKEN"],
    "https://delfia.atlassian.net"
)

# Campos para busca
FIELDS = (
    "summary,customfield_14954,customfield_14829,customfield_14825,"
    "customfield_12374,customfield_12271,customfield_11993,"
    "customfield_11994,customfield_11948,customfield_12036,customfield_12279"
)

# Carrega chamados
pendentes = jira.buscar_chamados("project = FSA AND status = AGENDAMENTO", FIELDS)
agrup_pend = jira.agrupar_chamados(pendentes)

agendados = jira.buscar_chamados('project = FSA AND status = AGENDADO', FIELDS)
grouped_sched = defaultdict(lambda: defaultdict(list))
for issue in agendados:
    f = issue["fields"]
    loja = f.get("customfield_14954", {}).get("value", "Loja Desconhecida")
    grouped_sched[loja].append(issue)

# Sidebar: Ações e Transição
with st.sidebar:
    st.header("Ações")
    if st.button("↩️ Desfazer última ação"):
        if st.session_state.history:
            action = st.session_state.history.pop()
            reverted = 0
            for key in action["keys"]:
                trans = jira.get_transitions(key)
                rev_id = next(
                    (t["id"] for t in trans if t.get("to",{}).get("name") == action["from"]),
                    None
                )
                if rev_id and jira.transicionar_status(key, rev_id).status_code == 204:
                    reverted += 1
            st.success(f"Revertido: {reverted} FSAs → {action['from']}")
        else:
            st.info("Nenhuma ação para desfazer.")

    st.markdown("---")
    st.header("Transição de Chamados")

    # Seleção da loja
    lojas = sorted(set(list(agrup_pend.keys()) + list(grouped_sched.keys())))
    loja_sel = st.selectbox("Selecione a loja:", ["—"] + lojas)
    if loja_sel != "—":
        # checkbox para técnico em campo
        em_campo = st.checkbox("Técnico está em campo?")
        if em_campo:
            # Pega todos os issues pendentes e agendados dessa loja
            issues_loja = [ch["key"] for ch in agrup_pend.get(loja_sel, [])]
            issues_loja += [ch["key"] for ch in grouped_sched.get(loja_sel, [])]
            if st.button(f"Mover {len(issues_loja)} chamados → Tec-Campo"):
                prev = None
                moved = 0
                errors = []
                for key in issues_loja:
                    # busca transição para Tec-Campo
                    trans = jira.get_transitions(key)
                    id_tc = next((t["id"] for t in trans if "tec-campo" in t.get("to",{}).get("name","" ).lower()), None)
                    if id_tc:
                        res = jira.transicionar_status(key, id_tc)
                        if res.status_code == 204:
                            moved += 1
                        else:
                            errors.append(f"{key}: {res.status_code}")
                if errors:
                    st.error("Alguns erros:")
                    for e in errors:
                        st.code(e)
                else:
                    st.success(f"{moved} chamados movidos → Tec-Campo")
                    st.session_state.history.append({"keys": issues_loja, "from": "*varios*"})
        else:
            # Fluxo normal: selecionar e agendar
            issues_pend = agrup_pend.get(loja_sel, [])
            issues_ag = grouped_sched.get(loja_sel, [])
            options = [ch["key"] for ch in issues_pend + issues_ag]
            selected = st.multiselect("Selecione FSAs:", options, default=options)
            # montar campo de agendamento
            choice = st.selectbox("Ação:", ["—","Agendar"])
            extra = {}
            if choice == "Agendar" and selected:
                data = st.date_input("Data:")
                hora = st.time_input("Hora:")
                dt_iso = datetime.combine(data,hora).strftime("%Y-%m-%dT%H:%M:%S.000-0300")
                extra["customfield_12036"] = dt_iso
            if st.button("Aplicar") and choice == "Agendar":
                moved=0; errs=[]
                for key in selected:
                    tid = {t["name"]:t["id"] for t in jira.get_transitions(key)}.get("Agendado")
                    if tid:
                        res = jira.transicionar_status(key, tid, fields=extra)
                        if res.status_code==204: moved+=1
                        else: errs.append(key)
                if errs:
                    st.error("Erros em:"+",".join(errs))
                else:
                    st.success(f"{moved} FSAs agendados")
                    st.session_state.history.append({"keys": selected, "from": "AGENDAMENTO"})

# Main
st.title("📱 Painel Field Service")
col1, col2 = st.columns(2)

with col1:
    st.header("⏳ Pendentes")
    if not pendentes:
        st.warning("Nenhum pendente.")
    else:
        for loja, lst in agrup_pend.items():
            with st.expander(f"{loja} — {len(lst)}"): st.code(gerar_mensagem(loja,lst))
with col2:
    st.header("📋 Agendados")
    for loja, lst in grouped_sched.items():
        with st.expander(f"{loja} — {len(lst)}"): st.code(gerar_mensagem(loja,lst))

st.markdown("---")
st.caption(f"Última atualização: {datetime.now():%d/%m/%Y %H:%M:%S}")
