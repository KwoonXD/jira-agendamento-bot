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

if "chamados_sem_tecnico" not in st.session_state:
    st.session_state.chamados_sem_tecnico = []

# ── Inicializa JiraAPI ──
jira = JiraAPI(
    st.secrets["EMAIL"],
    st.secrets["API_TOKEN"],
    "https://delfia.atlassian.net"
)

FIELDS = (
    "summary,customfield_14954,customfield_14829,customfield_14825,"
    "customfield_12374,customfield_12271,customfield_11993,"
    "customfield_11994,customfield_11948,customfield_12036,customfield_12279"
)

pendentes_raw = jira.buscar_chamados("project = FSA AND status = AGENDAMENTO", FIELDS)
agrup_pend = jira.agrupar_chamados(pendentes_raw)

agendados_raw = jira.buscar_chamados('project = FSA AND status = AGENDADO', FIELDS)
tec_campo_raw = jira.buscar_chamados('project = FSA AND status = TEC-CAMPO', FIELDS)
agendados_raw.extend(tec_campo_raw)

grouped_sched = defaultdict(lambda: defaultdict(list))
for issue in agendados_raw:
    f = issue["fields"]
    loja = f.get("customfield_14954", {}).get("value", "Loja Desconhecida")
    raw = f.get("customfield_12036")
    data_str = (
        datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S.%f%z")
                .strftime("%d/%m/%Y")
        if raw else "Não definida"
    )
    grouped_sched[data_str][loja].append(issue)

raw_by_loja = defaultdict(list)
for i in pendentes_raw + agendados_raw:
    loja = i["fields"].get("customfield_14954", {}).get("value", "Loja Desconhecida")
    raw_by_loja[loja].append(i)

# ── Sidebar ──
with st.sidebar:
    st.header("Transição de Chamados")

    lojas = sorted(set(agrup_pend) | set(grouped_sched[next(iter(grouped_sched))].keys()))
    loja_sel = st.selectbox("Selecione a loja:", ["—"] + lojas)

    if loja_sel != "—":
        em_campo = st.checkbox("Técnico está em campo? (agendar + mover tudo)")
        tem_tecnico = st.checkbox("Possui técnico definido?", value=True)

        if em_campo:
            st.markdown("**Dados de Agendamento**")
            data = st.date_input("Data do Agendamento")
            hora = st.time_input("Hora do Agendamento")
            tecnico = ""
            if tem_tecnico:
                tecnico = st.text_input("Dados dos Técnicos (Nome-CPF-RG-TEL)")

            dt_iso = datetime.combine(data, hora).strftime("%Y-%m-%dT%H:%M:%S.000-0300")
            extra_ag = {"customfield_12036": dt_iso}

            if tecnico:
                extra_ag["customfield_12279"] = {"type": "doc", "version": 1, "content": [
                    {"type": "paragraph", "content": [{"type": "text", "text": tecnico}]}
                ]}

            keys_pend = [i["key"] for i in pendentes_raw if i["fields"].get("customfield_14954", {}).get("value") == loja_sel]
            keys_sched = [i["key"] for i in agendados_raw if i["fields"].get("customfield_14954", {}).get("value") == loja_sel]
            all_keys = keys_pend + keys_sched

            if st.button(f"Agendar e mover {len(all_keys)} FSAs"):
                chamados_sem_tecnico = []
                moved = 0
                for k in keys_pend:
                    trans = jira.get_transitions(k)
                    agid = next((t["id"] for t in trans if "agend" in t["name"].lower()), None)
                    if agid:
                        jira.transicionar_status(k, agid, fields=extra_ag)

                for k in all_keys:
                    if tem_tecnico:
                        trans = jira.get_transitions(k)
                        tcid = next((t["id"] for t in trans if "tec-campo" in t.get("to", {}).get("name", "").lower()), None)
                        if tcid:
                            jira.transicionar_status(k, tcid)
                            moved += 1
                    else:
                        chamados_sem_tecnico.append(k)

                if chamados_sem_tecnico:
                    st.session_state.chamados_sem_tecnico.extend(chamados_sem_tecnico)
                    st.warning(f"Chamados sem técnico: {', '.join(chamados_sem_tecnico)}")
                else:
                    st.success(f"{moved} FSAs movidos com técnico.")

# Chamados SEM TÉCNICO
st.sidebar.markdown("---")
st.sidebar.header("Chamados SEM TÉCNICO 📌")
for c in st.session_state.chamados_sem_tecnico:
    st.sidebar.write(f"- {c}")
