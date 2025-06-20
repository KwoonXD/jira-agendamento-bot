import streamlit as st
from streamlit_autorefresh import st_autorefresh
from datetime import datetime, timedelta
from collections import defaultdict

from utils.jira_api import JiraAPI
from utils.messages import gerar_mensagem, verificar_duplicidade

# componente FullCalendar
from streamlit_fullcalendar import FullCalendar

# ── Configurações iniciais ──
st.set_page_config(page_title="Painel Field Service", layout="wide")
st_autorefresh(interval=90_000, key="auto_refresh")   # auto–refresh a cada 1m30s

# histórico de undo
if "history" not in st.session_state:
    st.session_state.history = []

# instancia Jira API
jira = JiraAPI(
    st.secrets["EMAIL"],
    st.secrets["API_TOKEN"],
    "https://delfia.atlassian.net"
)

# campos que precisamos da API
FIELDS = (
    "summary,customfield_14954,customfield_14829,customfield_14825,"
    "customfield_12374,customfield_12271,customfield_11993,"
    "customfield_11994,customfield_11948,customfield_12036"
)

# busca pendentes e agrupa por loja
pendentes = jira.buscar_chamados("project = FSA AND status = AGENDAMENTO", FIELDS)
agrup_pend = jira.agrupar_chamados(pendentes)

# busca agendados e prepara agrupamento por data→loja
agendados = jira.buscar_chamados('project = FSA AND status = AGENDADO', FIELDS)
grouped = defaultdict(lambda: defaultdict(list))
for issue in agendados:
    f    = issue["fields"]
    loja = f.get("customfield_14954",{}).get("value","Loja Desconhecida")
    raw  = f.get("customfield_12036")
    date = (
        datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S.%f%z").strftime("%d/%m/%Y")
        if raw else "Não definida"
    )
    grouped[date][loja].append(issue)

# ── Sidebar: botões de undo ──
with st.sidebar:
    st.header("Ações")
    if st.button("↩️ Desfazer última ação"):
        if st.session_state.history:
            a = st.session_state.history.pop()
            count = 0
            for key in a["keys"]:
                trans = jira.get_transitions(key)
                rev   = next((t["id"] for t in trans if t.get("to",{}).get("name")==a["from"]),None)
                if rev and jira.transicionar_status(key,rev).status_code==204:
                    count += 1
            st.success(f"Revertido: {count} FSAs → {a['from']}")
        else:
            st.info("Nenhuma ação para desfazer.")

# ── Abas principais ──
tab_list, tab_cal = st.tabs(["📋 Lista", "📆 Arraste no Calendário"])

# — Aba “Lista” —
with tab_list:
    st.title("📱 Painel Field Service — Lista")
    c1,c2 = st.columns(2)

    with c1:
        st.header("⏳ Pendentes de Agendamento")
        if not pendentes:
            st.warning("Nenhum pendente.")
        else:
            for loja, lst in agrup_pend.items():
                with st.expander(f"{loja} — {len(lst)} chamados"):
                    st.code(gerar_mensagem(loja,lst),language="text")

    with c2:
        st.header("📋 Agendados")
        if not agendados:
            st.info("Nenhum agendado.")
        else:
            for date, stores in sorted(grouped.items()):
                total = sum(len(v) for v in stores.values())
                st.markdown(f"**{date} — {total} chamados**")
                for loja, lst in sorted(stores.items()):
                    det = jira.agrupar_chamados(lst)[loja]
                    dup = [d["key"] for d in det if (d["pdv"],d["ativo"]) in verificar_duplicidade(det)]
                    spare = jira.buscar_chamados(
                        f'project = FSA AND status = "Aguardando Spare" AND "Codigo da Loja[Dropdown]" = {loja}',
                        FIELDS
                    )
                    spk = [i["key"] for i in spare]
                    tags = []
                    if spk: tags.append("Spare: "+", ".join(spk))
                    if dup: tags.append("Dup: "+", ".join(dup))
                    tag_str = f" [{' • '.join(tags)}]" if tags else ""
                    with st.expander(f"{loja} — {len(lst)} chamados{tag_str}"):
                        st.markdown("**FSAs:** "+", ".join(d["key"] for d in det))
                        st.code(gerar_mensagem(loja,det),language="text")

# — Aba “Arraste no Calendário” —
with tab_cal:
    st.title("📆 Calendário Arrastável de Agendamentos")

    # prepara eventos
    evts = []
    for issue in agendados:
        raw = issue["fields"].get("customfield_12036")
        if not raw: continue
        start = datetime.strptime(raw,"%Y-%m-%dT%H:%M:%S.%f%z")
        end   = start + timedelta(hours=1)
        evts.append({
            "id":    issue["key"],
            "title": issue["key"],
            "start": start.isoformat(),
            "end":   end.isoformat()
        })

    # renderiza apenas uma vez
    @st.cache_resource
    def _mk_cal(events):
        return FullCalendar(
            events=events,
            editable=True,
            initialView="dayGridMonth",
            height="700px",
            key="dragcal"
        )

    resp = _mk_cal(evts)

    # ao soltar um evento em outra data…
    if isinstance(resp,dict) and resp.get("action")=="eventDrop":
        e = resp["event"]
        key = e["id"]
        ns  = e["start"]  # “2025-06-25T15:00:00-03:00”
        jira_dt = datetime.fromisoformat(ns).strftime("%Y-%m-%dT%H:%M:%S.000-0300")
        # atualiza só o campo de data (mesmo status)
        r = jira.transicionar_status(key,None, fields={"customfield_12036": jira_dt})
        if r.status_code==204:
            st.success(f"{key} reagendado → {jira_dt}")
        else:
            st.error(f"Erro ao reagendar {key}: {r.status_code}")

# ── Rodapé ──
st.markdown("---")
st.caption(f"Última atualização: {datetime.now():%d/%m/%Y %H:%M:%S}")
