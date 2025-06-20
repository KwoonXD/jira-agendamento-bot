import streamlit as st
import streamlit.components.v1 as components
from streamlit_autorefresh import st_autorefresh
from datetime import datetime
from collections import defaultdict
import json

from utils.jira_api import JiraAPI
from utils.messages import gerar_mensagem, verificar_duplicidade

# ────────────────────────────────────────────────────────────────
# CONFIGURAÇÃO DA PÁGINA E AUTO-REFRESH
# ────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Painel Field Service", layout="wide")
view = st.sidebar.selectbox("Visão:", ["Lista", "Calendário Arrastável"])
if view == "Lista":
    st_autorefresh(interval=90_000, key="auto_refresh")  # só na Lista

# ────────────────────────────────────────────────────────────────
# INICIALIZAÇÃO DA API Jira
# ────────────────────────────────────────────────────────────────
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

# ────────────────────────────────────────────────────────────────
# BUSCA E AGRUPAMENTO DE CHAMADOS
# ────────────────────────────────────────────────────────────────
pendentes = jira.buscar_chamados("project = FSA AND status = AGENDAMENTO", FIELDS)
agendados = jira.buscar_chamados('project = FSA AND status = AGENDADO', FIELDS)

# pendentes por loja
agrup_pend = jira.agrupar_chamados(pendentes)

# agendados por data→loja
grouped = defaultdict(lambda: defaultdict(list))
for issue in agendados:
    f    = issue["fields"]
    loja = f.get("customfield_14954", {}).get("value", "Loja Desconhecida")
    raw  = f.get("customfield_12036")
    date = (
        datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S.%f%z").strftime("%d/%m/%Y")
        if raw else "Não definida"
    )
    grouped[date][loja].append(issue)

# histórico de undo
if "history" not in st.session_state:
    st.session_state.history = []

# ────────────────────────────────────────────────────────────────
# SIDEBAR: desfazer última ação
# ────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Ações")
    if st.button("↩️ Desfazer última ação"):
        if st.session_state.history:
            act = st.session_state.history.pop()
            count = 0
            for key in act["keys"]:
                trans = jira.get_transitions(key)
                rev   = next((t["id"] for t in trans
                              if t.get("to", {}).get("name") == act["from"]), None)
                if rev and jira.transicionar_status(key, rev).status_code == 204:
                    count += 1
            st.success(f"Revertido: {count} FSAs → {act['from']}")
        else:
            st.info("Nenhuma ação para desfazer.")

# ────────────────────────────────────────────────────────────────
# VISÃO “LISTA”
# ────────────────────────────────────────────────────────────────
if view == "Lista":
    st.title("📋 Painel Field Service — Lista")
    c1, c2 = st.columns(2)

    with c1:
        st.header("⏳ Chamados PENDENTES")
        if not pendentes:
            st.warning("Nenhum pendente.")
        else:
            for loja, lst in agrup_pend.items():
                with st.expander(f"{loja} — {len(lst)} chamado(s)", expanded=False):
                    st.code(gerar_mensagem(loja, lst), language="text")

    with c2:
        st.header("📅 Chamados AGENDADOS")
        if not agendados:
            st.info("Nenhum agendado.")
        else:
            for date, stores in sorted(grouped.items()):
                total = sum(len(v) for v in stores.values())
                st.subheader(f"{date} — {total} chamado(s)")
                for loja, lst in sorted(stores.items()):
                    det      = jira.agrupar_chamados(lst)[loja]
                    dup_keys = [d["key"] for d in det
                                if (d["pdv"], d["ativo"]) in verificar_duplicidade(det)]
                    spare    = jira.buscar_chamados(
                        f'project = FSA AND status = "Aguardando Spare" '
                        f'AND "Codigo da Loja[Dropdown]" = {loja}',
                        FIELDS
                    )
                    spk      = [i["key"] for i in spare]
                    tags     = []
                    if spk: tags.append("Spare: " + ", ".join(spk))
                    if dup_keys: tags.append("Dup: " + ", ".join(dup_keys))
                    tag_str  = f" [{' • '.join(tags)}]" if tags else ""
                    with st.expander(f"{loja} — {len(lst)} chamado(s){tag_str}", expanded=False):
                        st.markdown("**FSAs:** " + ", ".join(d["key"] for d in det))
                        st.code(gerar_mensagem(loja, det), language="text")

# ────────────────────────────────────────────────────────────────
# VISÃO “CALENDÁRIO ARRASTÁVEL” (FullCalendar via HTML/JS)
# ────────────────────────────────────────────────────────────────
else:
    st.title("📆 Calendário Arrastável de Agendamentos")

    # prepara JSON de eventos
    events = []
    for issue in agendados:
        raw = issue["fields"].get("customfield_12036")
        if not raw:
            continue
        dt  = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S.%f%z")
        events.append({
            "id":    issue["key"],
            "title": issue["key"],
            "start": dt.isoformat(),
            "allDay": True
        })
    events_json = json.dumps(events)

    # HTML/JS que injeta FullCalendar via CDN e posta mensagens
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <link href="https://cdn.jsdelivr.net/npm/fullcalendar@6.1.7/index.global.min.css" rel="stylesheet" />
      <script src="https://cdn.jsdelivr.net/npm/fullcalendar@6.1.7/index.global.min.js"></script>
      <style>
        body {{ margin:0; padding:0; }}
        #calendar {{ max-width: 100%; margin: 0 auto; }}
      </style>
    </head>
    <body>
      <div id="calendar"></div>
      <script>
        document.addEventListener('DOMContentLoaded', function() {{
          const calendar = new FullCalendar.Calendar(document.getElementById('calendar'), {{
            initialView: 'dayGridMonth',
            editable: true,
            events: {events_json},
            eventDrop: function(info) {{
              const msg = {{
                key: info.event.id,
                date: info.event.start.toISOString()
              }};
              window.parent.postMessage(msg, '*');
            }}
          }});
          calendar.render();
        }});
      </script>
    </body>
    </html>
    """

    # injeta no Streamlit e aguarda retorno do postMessage
    msg = components.html(html, height=600, scrolling=False)

    # se JS enviou nova data, atualiza o Jira
    if isinstance(msg, dict) and msg.get("key"):
        new_dt  = datetime.fromisoformat(msg["date"])
        jira_iso = new_dt.strftime("%Y-%m-%dT%H:%M:%S.000-0300")
        ok = jira.transicionar_status(msg["key"], None, fields={"customfield_12036": jira_iso})
        if ok:
            st.success(f"{msg['key']} reagendado → {jira_iso}")
        else:
            st.error(f"Erro ao reagendar {msg['key']} (status {ok}).")

# ────────────────────────────────────────────────────────────────
# RODAPÉ
# ────────────────────────────────────────────────────────────────
st.markdown("---")
st.caption(f"Última atualização: {datetime.now():%d/%m/%Y %H:%M:%S}")
