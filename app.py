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

# ── Inicializa JiraAPI ──
jira = JiraAPI(
    st.secrets["EMAIL"],
    st.secrets["API_TOKEN"],
    "https://delfia.atlassian.net"
)

# ── Quais campos puxar da API ──
FIELDS = (
    "summary,customfield_14954,customfield_14829,customfield_14825,"
    "customfield_12374,customfield_12271,customfield_11993,"
    "customfield_11994,customfield_11948,customfield_12036,customfield_12279"
)

# ── 1) Carrega PENDENTES e agrupa por loja ──
pendentes_raw = jira.buscar_chamados("project = FSA AND status = AGENDAMENTO", FIELDS)
agrup_pend    = jira.agrupar_chamados(pendentes_raw)

# ── 2) Carrega AGENDADOS e TEC-CAMPO e agrupa por data → loja → lista de issues ──
agendados_raw = jira.buscar_chamados('project = FSA AND status in (AGENDADO, TEC-CAMPO)', FIELDS)
grouped_sched = defaultdict(lambda: defaultdict(list))
for issue in agendados_raw:
    f    = issue["fields"]
    loja = f.get("customfield_14954", {}).get("value", "Loja Desconhecida")
    raw  = f.get("customfield_12036")
    data_str = (
        datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S.%f%z")
                .strftime("%d/%m/%Y")
        if raw else "Não definida"
    )
    grouped_sched[data_str][loja].append(issue)

# ── 3) Raw por loja (pendentes+agendados) para transições em massa ──
raw_by_loja = defaultdict(list)
for i in pendentes_raw + agendados_raw:
    loja = i["fields"].get("customfield_14954",{}).get("value","Loja Desconhecida")
    raw_by_loja[loja].append(i)

# ── Main ──
st.title("📱 Painel Field Service")
col1,col2=st.columns(2)

with col1:
    st.header("⏳ Chamados PENDENTES de Agendamento")
    if not pendentes_raw:
        st.warning("Nenhum chamado em AGENDAMENTO.")
    else:
        for loja,iss in agrup_pend.items():
            with st.expander(f"{loja} — {len(iss)} chamado(s)",expanded=False):
                st.code(gerar_mensagem(loja,iss),language="text")

with col2:
    st.header("📋 Chamados AGENDADOS + TEC-CAMPO")
    if not agendados_raw:
        st.info("Nenhum chamado em AGENDADO ou TEC-CAMPO.")
    else:
        for date, stores in sorted(grouped_sched.items()):
            total=sum(len(v) for v in stores.values())
            st.subheader(f"{date} — {total} chamado(s)")
            for loja,iss in sorted(stores.items()):
                detalhes=jira.agrupar_chamados(iss)[loja]
                dup_keys=[d["key"] for d in detalhes if (d["pdv"],d["ativo"]) in verificar_duplicidade(detalhes)]
                spare_raw=jira.buscar_chamados(
                    f'project = FSA AND status = "Aguardando Spare" AND "Codigo da Loja[Dropdown]" = {loja}',
                    FIELDS
                )
                spare_keys=[i["key"] for i in spare_raw]
                tec_campo_keys = [i["key"] for i in iss if i["fields"]["status"]["name"].upper() == "TEC-CAMPO"]
                tags=[]
                if spare_keys: tags.append("Spare: "+", ".join(spare_keys))
                if dup_keys:   tags.append("Dup: "+", ".join(dup_keys))
                if tec_campo_keys: tags.append("Tec-Campo: "+", ".join(tec_campo_keys))
                tag_str=f" [{' • '.join(tags)}]" if tags else ""
                with st.expander(f"{loja} — {len(iss)} chamado(s){tag_str}",expanded=False):
                    st.markdown("*FSAs:* "+", ".join(d["key"] for d in detalhes))
                    st.code(gerar_mensagem(loja,detalhes),language="text")

st.markdown("---")
st.caption(f"Última atualização: {datetime.now():%d/%m/%Y %H:%M:%S}")
