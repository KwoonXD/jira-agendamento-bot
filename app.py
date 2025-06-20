import streamlit as st
import yaml
import streamlit_authenticator as stauth

# ── Autenticação ───────────────────────────────────────────────────────────
with open("credentials.yaml") as f:
    creds = yaml.safe_load(f)

auth = stauth.Authenticate(
    creds["credentials"],
    creds["cookie"]["name"],
    creds["cookie"]["key"],
    creds["cookie"]["expiry_days"],
)

name, status, username = auth.login("Login", "main")

if status is False:
    st.error("Usuário ou senha inválidos")
    st.stop()
elif status is None:
    st.warning("Por favor, faça login")
    st.stop()

# opcional: mostra quem está logado e logout
st.sidebar.write(f"👤 Olá, **{name}**")
st.sidebar.button("Logout", on_click=auth.logout, args=("main",))

# ── O RESTO DO SEU CÓDIGO ──────────────────────────────────────────────────
from streamlit_autorefresh import st_autorefresh
from datetime import datetime, timedelta
from collections import defaultdict
import pandas as pd
import calendar

from utils.jira_api import JiraAPI
from utils.messages import gerar_mensagem, verificar_duplicidade

# page config, refresh etc.
st.set_page_config(page_title="Painel Field Service", layout="wide")
st_autorefresh(interval=90_000, key="auto_refresh")

if "history" not in st.session_state:
    st.session_state.history = []

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

# 1) Pendentes
pendentes_raw = jira.buscar_chamados("project = FSA AND status = AGENDAMENTO", FIELDS)
agrup_pend    = jira.agrupar_chamados(pendentes_raw)

# 2) Agendados
agendados_raw = jira.buscar_chamados('project = FSA AND status = AGENDADO', FIELDS)
grouped_sched = defaultdict(lambda: defaultdict(list))
for issue in agendados_raw:
    f    = issue["fields"]
    loja = f.get("customfield_14954",{}).get("value","Loja Desconhecida")
    raw  = f.get("customfield_12036","")
    date = (
        datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S.%f%z")
                .strftime("%d/%m/%Y")
        if raw else "Não definida"
    )
    grouped_sched[date][loja].append(issue)

# 3) df_cal para calendário
rows=[]
for issue in agendados_raw:
    raw = issue["fields"].get("customfield_12036")
    if not raw: continue
    dt = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S.%f%z")
    loja = issue["fields"].get("customfield_14954",{}).get("value","Loja Desconhecida")
    rows.append({"data": dt.date(), "key": issue["key"], "loja": loja})
df_cal = pd.DataFrame(rows)

# Sidebar de undo e transições...
with st.sidebar:
    st.header("Ações")
    if st.button("↩️ Desfazer última ação"):
        if st.session_state.history:
            act = st.session_state.history.pop()
            for key, prev in zip(act["keys"], act["prev_fields"]):
                jira.transicionar_status(key, None, fields=prev)
            st.success("Undo realizado")
        else:
            st.info("Nada a desfazer.")
    st.markdown("---")
    st.header("Transição de Chamados")
    lojas = sorted(set(agrup_pend) | set(grouped_sched.keys()))
    loja_sel = st.selectbox("Loja:", ["—"] + lojas)
    if loja_sel != "—":
        em_campo = st.checkbox("Técnico em campo? (agendar+mover tudo)")
        if em_campo or st.checkbox("Agendar avulso"):
            data = st.date_input("Data Agendamento")
            hora = st.time_input("Hora Agendamento")
            tecnico = st.text_input("Dados Técnico")
            dt_iso = datetime.combine(data,hora).strftime("%Y-%m-%dT%H:%M:%S.000-0300")
            extra = {"customfield_12036": dt_iso}
            if tecnico:
                extra["customfield_12279"] = {
                    "type":"doc","version":1,
                    "content":[{"type":"paragraph","content":[{"type":"text","text":tecnico}]}]
                }
        keys_pend  = [i["key"] for i in pendentes_raw  if i["fields"].get("customfield_14954",{}).get("value")==loja_sel]
        keys_sched = [i["key"] for i in agendados_raw if i["fields"].get("customfield_14954",{}).get("value")==loja_sel]
        all_keys   = keys_pend+keys_sched
        if st.button("Aplicar Transição"):
            prev_fields=[]
            for k in all_keys:
                prev_raw = jira.buscar_chamados(f"key={k}",FIELDS)[0]["fields"]
                prev_fields.append({"customfield_12036": prev_raw.get("customfield_12036","")})
                if k in keys_pend:
                    trans = jira.get_transitions(k)
                    agid = next((t["id"] for t in trans if "agend" in t["name"].lower()),None)
                    if agid: jira.transicionar_status(k,agid,fields=extra)
                trans = jira.get_transitions(k)
                tcid  = next((t["id"] for t in trans if "tec-campo" in t.get("to",{}).get("name","").lower()),None)
                if tcid: jira.transicionar_status(k,tcid)
            st.session_state.history.append({"keys":all_keys,"prev_fields":prev_fields})
            st.success(f"{len(all_keys)} FSAs processadas.")

# Abas Lista e Calendário (mantém seu layout anterior)...
tab1, tab2 = st.tabs(["📋 Lista","📆 Calendário"])
with tab1:
    st.header("Pendentes")
    # ... (coluna de pendentes e agendados como antes)
with tab2:
    st.header("Calendário")
    # ... (seu código de calendário html)

st.markdown("---")
st.caption(f"Última atualização: {datetime.now():%d/%m/%Y %H:%M:%S}")
