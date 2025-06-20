import streamlit as st
from streamlit_autorefresh import st_autorefresh
from datetime import datetime, timedelta
from collections import defaultdict
import pandas as pd
import calendar

from utils.jira_api import JiraAPI
from utils.messages import gerar_mensagem, verificar_duplicidade

# FullCalendar component
from streamlit_fullcalendar import FullCalendar

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

# ── 2) Carrega AGENDADOS e agrupa por data → loja → lista de issues ──
agendados_raw = jira.buscar_chamados('project = FSA AND status = AGENDADO', FIELDS)
grouped_sched = defaultdict(lambda: defaultdict(list))
for issue in agendados_raw:
    f    = issue["fields"]
    loja = f.get("customfield_14954", {}).get("value", "Loja Desconhecida")
    raw  = f.get("customfield_12036")
    data_str = (
        datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S.%f%z").strftime("%d/%m/%Y")
        if raw else "Não definida"
    )
    grouped_sched[data_str][loja].append(issue)

# ── Sidebar (mantém espaço para Ações / undo) ──
with st.sidebar:
    st.header("Ações")
    if st.button("↩️ Desfazer última ação"):
        if st.session_state.history:
            action = st.session_state.history.pop()
            reverted = 0
            for key in action["keys"]:
                trans = jira.get_transitions(key)
                rev_id = next(
                    (t["id"] for t in trans if t.get("to", {}).get("name") == action["from"]),
                    None
                )
                if rev_id and jira.transicionar_status(key, rev_id).status_code == 204:
                    reverted += 1
            st.success(f"Revertido: {reverted} FSAs → {action['from']}")
        else:
            st.info("Nenhuma ação para desfazer.")

# ── Abas: Lista e Calendário Arrastável ──
tab_lista, tab_cal = st.tabs(["📋 Lista", "📆 Calendário Arrastável"])

with tab_lista:
    st.title("📱 Painel Field Service — Lista")
    col1, col2 = st.columns(2)

    # Pendentes
    with col1:
        st.subheader("⏳ Chamados PENDENTES de Agendamento")
        if not pendentes_raw:
            st.warning("Nenhum chamado em AGENDAMENTO.")
        else:
            for loja, issues in agrup_pend.items():
                with st.expander(f"{loja} — {len(issues)} chamado(s)", expanded=False):
                    st.code(gerar_mensagem(loja, issues), language="text")

    # Agendados
    with col2:
        st.subheader("📋 Chamados AGENDADOS")
        if not agendados_raw:
            st.info("Nenhum chamado em AGENDADO.")
        else:
            for date_str, stores in sorted(grouped_sched.items()):
                total = sum(len(v) for v in stores.values())
                st.markdown(f"**{date_str} — {total} chamado(s)**")
                for loja, issues in sorted(stores.items()):
                    detalhes  = jira.agrupar_chamados(issues)[loja]
                    dup_keys  = [
                        d["key"]
                        for d in detalhes
                        if (d["pdv"], d["ativo"]) in verificar_duplicidade(detalhes)
                    ]
                    spare_raw = jira.buscar_chamados(
                        f'project = FSA AND status = "Aguardando Spare" AND "Codigo da Loja[Dropdown]" = {loja}',
                        FIELDS
                    )
                    spare_keys = [i["key"] for i in spare_raw]
                    tags = []
                    if spare_keys: tags.append("Spare: " + ", ".join(spare_keys))
                    if dup_keys:   tags.append("Dup: "   + ", ".join(dup_keys))
                    tag_str = f" [{' • '.join(tags)}]" if tags else ""
                    with st.expander(f"{loja} — {len(issues)} chamado(s){tag_str}", expanded=False):
                        st.markdown("**FSAs:** " + ", ".join(d["key"] for d in detalhes))
                        st.code(gerar_mensagem(loja, detalhes), language="text")

with tab_cal:
    st.title("📆 Calendário Arrastável de Agendamentos")

    # prepara eventos para FullCalendar
    events = []
    for issue in agendados_raw:
        raw = issue["fields"].get("customfield_12036")
        if not raw:
            continue
        start = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S.%f%z")
        end   = start + timedelta(hours=1)
        events.append({
            "id":    issue["key"],
            "title": issue["key"],
            "start": start.isoformat(),
            "end":   end.isoformat(),
        })

    # renderiza o calendário apenas uma vez
    @st.cache_resource
    def _render_calendar(evts):
        return FullCalendar(
            events=evts,
            editable=True,
            initialView="dayGridMonth",
            height="700px",
            key="dragcal"
        )

    cal_response = _render_calendar(events)

    # captura evento de drag‐and‐drop
    if isinstance(cal_response, dict) and cal_response.get("action") == "eventDrop":
        ev        = cal_response["event"]
        key       = ev["id"]
        new_start = ev["start"]  # ex: "2025-06-25T15:00:00-03:00"
        # formata para Jira
        dt_jira = datetime.fromisoformat(new_start).strftime("%Y-%m-%dT%H:%M:%S.000-0300")
        # atualiza apenas o campo de data
        res = jira.transicionar_status(key, None, fields={"customfield_12036": dt_jira})
        if res.status_code == 204:
            st.success(f"{key} reagendado para {dt_jira}")
        else:
            st.error(f"Falha ao reagendar {key}: {res.status_code}")

# ── Rodapé ──
st.markdown("---")
st.caption(f"Última atualização: {datetime.now():%d/%m/%Y %H:%M:%S}")
