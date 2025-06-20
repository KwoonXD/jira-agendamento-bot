import streamlit as st
from streamlit_autorefresh import st_autorefresh
from datetime import datetime, timedelta
from collections import defaultdict

from utils.jira_api import JiraAPI
from utils.messages import gerar_mensagem, verificar_duplicidade

# componente FullCalendar
from streamlit_fullcalendar import FullCalendar

# ── Configuração da página ──
st.set_page_config(page_title="Painel Field Service", layout="wide")

# ── Qual visão? ──
view = st.sidebar.selectbox("Visão:", ["Lista", "Calendário"])

# ── Autorefresh (só na Lista) ──
if view == "Lista":
    st_autorefresh(interval=90_000, key="auto_refresh")

# ── Histórico de undo ──
if "history" not in st.session_state:
    st.session_state.history = []

# ── Conecta no Jira ──
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

# ── Carrega dados ──
pendentes = jira.buscar_chamados("project = FSA AND status = AGENDAMENTO", FIELDS)
agendados = jira.buscar_chamados('project = FSA AND status = AGENDADO', FIELDS)

# ── Agrupamento para a Lista ──
agrup_pend = jira.agrupar_chamados(pendentes)
grouped    = defaultdict(lambda: defaultdict(list))
for issue in agendados:
    f    = issue["fields"]
    loja = f.get("customfield_14954",{}).get("value","Loja Desconhecida")
    raw  = f.get("customfield_12036")
    date = (
        datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S.%f%z")
                .strftime("%d/%m/%Y")
        if raw else "Não definida"
    )
    grouped[date][loja].append(issue)

# ── Sidebar: desfazer ──
with st.sidebar:
    st.header("Ações")
    if st.button("↩️ Desfazer última ação"):
        if st.session_state.history:
            action = st.session_state.history.pop()
            cnt = 0
            for k in action["keys"]:
                trans = jira.get_transitions(k)
                rev_id = next((t["id"] 
                               for t in trans 
                               if t.get("to",{}).get("name")==action["from"]), None)
                if rev_id and jira.transicionar_status(k, rev_id).status_code==204:
                    cnt += 1
            st.success(f"Revertido: {cnt} FSAs → {action['from']}")
        else:
            st.info("Nada para desfazer.")

# ── View: Lista ──
if view == "Lista":
    st.title("📱 Painel Field Service — Lista")
    c1, c2 = st.columns(2)

    with c1:
        st.header("⏳ Pendentes de Agendamento")
        if not pendentes:
            st.warning("Nenhum pendente.")
        else:
            for loja, lst in agrup_pend.items():
                with st.expander(f"{loja} — {len(lst)} chamados", expanded=False):
                    st.code(gerar_mensagem(loja, lst), language="text")

    with c2:
        st.header("📋 Agendados")
        if not agendados:
            st.info("Nenhum agendado.")
        else:
            for date_str, stores in sorted(grouped.items()):
                total = sum(len(v) for v in stores.values())
                st.markdown(f"**{date_str} — {total} chamados**")
                for loja, lst in sorted(stores.items()):
                    det     = jira.agrupar_chamados(lst)[loja]
                    dup     = [d["key"] 
                               for d in det 
                               if (d["pdv"],d["ativo"]) in verificar_duplicidade(det)]
                    spare   = jira.buscar_chamados(
                        f'project = FSA AND status = "Aguardando Spare" '
                        f'AND "Codigo da Loja[Dropdown]" = {loja}', FIELDS
                    )
                    spk     = [i["key"] for i in spare]
                    tags    = []
                    if spk: tags.append("Spare: "+", ".join(spk))
                    if dup: tags.append("Dup: "+", ".join(dup))
                    tag_str = f" [{' • '.join(tags)}]" if tags else ""
                    with st.expander(f"{loja} — {len(lst)} chamados{tag_str}", expanded=False):
                        st.markdown("**FSAs:** " + ", ".join(d["key"] for d in det))
                        st.code(gerar_mensagem(loja, det), language="text")

# ── View: Calendário Arrastável ──
else:
    st.title("📆 Calendário Arrastável de Agendamentos")

    # prepara eventos
    events = []
    for issue in agendados:
        raw = issue["fields"].get("customfield_12036")
        if not raw:
            continue
        start = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S.%f%z")
        end   = start + timedelta(hours=1)
        events.append({
            "id":    issue["key"],
            "title": issue["key"],
            "start": start.isoformat(),
            "end":   end.isoformat()
        })

    # renderiza somente uma vez
    @st.cache_resource
    def _make_cal(evts):
        return FullCalendar(
            events=evts,
            editable=True,
            initialView="dayGridMonth",
            height="700px",
            key="dragcal"
        )

    resp = _make_cal(events)

    if isinstance(resp, dict) and resp.get("action") == "eventDrop":
        ev        = resp["event"]
        key       = ev["id"]
        new_start = ev["start"]  # ex: "2025-06-25T15:00:00-03:00"
        jira_dt   = datetime.fromisoformat(new_start).strftime("%Y-%m-%dT%H:%M:%S.000-0300")
        r = jira.transicionar_status(key, None, fields={"customfield_12036": jira_dt})
        if r.status_code == 204:
            st.success(f"{key} reagendado → {jira_dt}")
        else:
            st.error(f"Falha ao reagendar {key}: {r.status_code}")

# ── Rodapé ──
st.markdown("---")
st.caption(f"Última atualização: {datetime.now():%d/%m/%Y %H:%M:%S}")
