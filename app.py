import streamlit as st
from streamlit_autorefresh import st_autorefresh
from datetime import datetime
from collections import defaultdict

from utils.jira_api import JiraAPI
from utils.messages import gerar_mensagem, verificar_duplicidade

# --- Configurações iniciais ---
st.set_page_config(page_title="Painel Field Service", layout="wide")
st_autorefresh(interval=60_000, key="auto_refresh")

EMAIL     = st.secrets["EMAIL"]
API_TOKEN = st.secrets["API_TOKEN"]
JIRA_URL  = "https://delfia.atlassian.net"
jira      = JiraAPI(EMAIL, API_TOKEN, JIRA_URL)

FIELDS = (
    "summary,customfield_14954,customfield_14829,customfield_14825,"
    "customfield_12374,customfield_12271,customfield_11993,"
    "customfield_11994,customfield_11948,customfield_12036"
)

st.title("📱 Painel Field Service")
col_pend, col_age = st.columns(2)

# ——— Pending (AGENDAMENTO) ———
with col_pend:
    st.header("⏳ Chamados AGENDAMENTO")
    pendentes = jira.buscar_chamados("project = FSA AND status = AGENDAMENTO", FIELDS)
    agrup_pend = jira.agrupar_chamados(pendentes)

    if not pendentes:
        st.warning("Nenhum chamado pendente de AGENDAMENTO.")
    else:
        for loja, issues in agrup_pend.items():
            with st.expander(f"{loja} — {len(issues)} chamados", expanded=False):
                st.code(gerar_mensagem(loja, issues), language="text")

                # bulk select + transition
                keys = [i["key"] for i in issues]
                sel = st.multiselect("Selecionar FSAs:", keys, default=keys, key=f"pend_sel_{loja}")
                if sel:
                    tr = jira.get_transitions(keys[0])
                    opts = {t["name"]: t["id"] for t in tr}
                    choice = st.selectbox("Transição:", ["—"] + list(opts), key=f"pend_tr_{loja}")
                    if choice != "—" and st.button("Aplicar em todos", key=f"pend_btn_{loja}"):
                        for k in sel:
                            jira.transicionar_status(k, opts[choice])
                        st.success(f"{len(sel)} FSAs movidos → {choice}")

# ——— Scheduled (AGENDADOS) ———
with col_age:
    st.header("📋 Chamados AGENDADOS")
    agendados = jira.buscar_chamados('project = FSA AND status = AGENDADO', FIELDS)

    # filtro de loja
    lojas = sorted({iss["fields"].get("customfield_14954",{}).get("value","") for iss in agendados})
    sel_lojas = st.sidebar.multiselect("Filtrar loja:", ["Todas"] + lojas, default=["Todas"])

    # agrupar por data e loja
    grouped = defaultdict(lambda: defaultdict(list))
    for iss in agendados:
        f = iss["fields"]
        loja = f.get("customfield_14954",{}).get("value","Loja Desconhecida")
        raw = f.get("customfield_12036")
        date = (datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S.%f%z")
                .strftime("%d/%m/%Y")) if raw else "Não definida"
        grouped[date][loja].append(iss)

    for date, by_store in grouped.items():
        total = sum(len(lst) for lst in by_store.values())
        if total == 0:
            continue
        st.subheader(f"{date} — {total} chamados")

        for loja, issues in by_store.items():
            if "Todas" not in sel_lojas and loja not in sel_lojas:
                continue

            detalhes = jira.agrupar_chamados(issues)[loja]
            dup = verificar_duplicidade(detalhes)
            fsas_dup   = [c["key"] for c in detalhes if (c["pdv"], c["ativo"]) in dup]
            spare_iss  = jira.buscar_chamados(
                f'project = FSA AND status = "Aguardando Spare" AND "Codigo da Loja[Dropdown]" = {loja}',
                FIELDS
            )
            fsas_spare = [c["key"] for c in spare_iss]

            alerts = []
            if fsas_dup:    alerts.append(f"Dup: {', '.join(fsas_dup)}")
            if fsas_spare:  alerts.append(f"Spare: {', '.join(fsas_spare)}")
            tag = f" [{' • '.join(alerts)}]" if alerts else ""

            with st.expander(f"{loja} — {len(issues)} chamados{tag}", expanded=False):
                st.code(gerar_mensagem(loja, detalhes), language="text")

                # bulk select + transition
                keys = [c["key"] for c in detalhes]
                sel = st.multiselect("Selecionar FSAs:", keys, default=keys, key=f"age_sel_{date}_{loja}")
                if sel:
                    tr = jira.get_transitions(keys[0])
                    opts = {t["name"]: t["id"] for t in tr}
                    choice = st.selectbox("Transição:", ["—"] + list(opts), key=f"age_tr_{date}_{loja}")
                    if choice != "—" and st.button("Aplicar em todos", key=f"age_btn_{date}_{loja}"):
                        for k in sel:
                            jira.transicionar_status(k, opts[choice])
                        st.success(f"{len(sel)} FSAs movidos → {choice}")

st.markdown("---")
st.caption(f"Última atualização: {datetime.now():%d/%m/%Y %H:%M:%S}")
