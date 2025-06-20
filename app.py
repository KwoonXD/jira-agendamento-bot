import streamlit as st
from streamlit_autorefresh import st_autorefresh
from datetime import datetime
from collections import defaultdict

from utils.jira_api import JiraAPI
from utils.messages import gerar_mensagem, verificar_duplicidade

# ── Configuração da página ─────────────────────────────────────────────────
st.set_page_config(page_title="Painel Field Service", layout="wide")
view = st.sidebar.selectbox("Visão:", ["Lista", "Reagendar"])
if view == "Lista":
    st_autorefresh(interval=90_000, key="auto_refresh")

# ── Conecta ao Jira ────────────────────────────────────────────────────────
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

# ── Busca dados ────────────────────────────────────────────────────────────
pendentes = jira.buscar_chamados("project = FSA AND status = AGENDAMENTO", FIELDS)
agendados = jira.buscar_chamados('project = FSA AND status = AGENDADO', FIELDS)

# ── Agrupa pendentes por loja ──────────────────────────────────────────────
agrup_pend = jira.agrupar_chamados(pendentes)

# ── Agrupa agendados por loja para tabela de reagendamento ────────────────
tabela = []
for issue in agendados:
    f = issue["fields"]
    loja = f.get("customfield_14954", {}).get("value", "Loja Desconhecida")
    raw = f.get("customfield_12036", "")
    try:
        ag_dt = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S.%f%z")
    except:
        ag_dt = None
    tabela.append({
        "key": issue["key"],
        "loja": loja,
        "data_agendada": ag_dt
    })

# ── Histórico de undo ──────────────────────────────────────────────────────
if "history" not in st.session_state:
    st.session_state.history = []

with st.sidebar:
    st.header("Ações")
    if st.button("↩️ Desfazer última ação"):
        if st.session_state.history:
            act = st.session_state.history.pop()
            count = 0
            for key in act["keys"]:
                trans = jira.get_transitions(key)
                rev   = next((t["id"] for t in trans
                              if t.get("to",{}).get("name")==act["from"]), None)
                if rev and jira.transicionar_status(key, rev).status_code == 204:
                    count += 1
            st.success(f"Revertido: {count} FSAs → {act['from']}")
        else:
            st.info("Nada a desfazer.")

# ── VISÃO “LISTA” ──────────────────────────────────────────────────────────
if view == "Lista":
    st.title("📋 Painel Field Service — Lista")
    col1, col2 = st.columns(2)

    # Pendentes
    with col1:
        st.header("⏳ Chamados PENDENTES de Agendamento")
        if not pendentes:
            st.warning("Nenhum pendente.")
        else:
            for loja, lst in agrup_pend.items():
                with st.expander(f"{loja} — {len(lst)} chamado(s)", expanded=False):
                    st.code(gerar_mensagem(loja, lst), language="text")

    # Agendados
    with col2:
        st.header("📅 Chamados AGENDADOS")
        if not agendados:
            st.info("Nenhum agendado.")
        else:
            # reagrupa por data depois por loja
            by_date = defaultdict(lambda: defaultdict(list))
            for issue in agendados:
                f = issue["fields"]
                loja = f.get("customfield_14954", {}).get("value", "Loja Desconhecida")
                raw  = f.get("customfield_12036","")
                date = "--"
                try:
                    date = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S.%f%z").strftime("%d/%m/%Y")
                except: pass
                by_date[date][loja].append(issue)
            for date, stores in sorted(by_date.items()):
                total = sum(len(v) for v in stores.values())
                st.subheader(f"{date} — {total} chamado(s)")
                for loja, lst in sorted(stores.items()):
                    det       = jira.agrupar_chamados(lst)[loja]
                    dup_keys  = [d["key"] for d in det
                                 if (d["pdv"],d["ativo"]) in verificar_duplicidade(det)]
                    spare     = jira.buscar_chamados(
                        f'project = FSA AND status = "Aguardando Spare" '
                        f'AND "Codigo da Loja[Dropdown]" = {loja}', FIELDS
                    )
                    spare_keys= [i["key"] for i in spare]
                    tags=[]
                    if spare_keys: tags.append("Spare: "+", ".join(spare_keys))
                    if dup_keys:   tags.append("Dup: "+", ".join(dup_keys))
                    tag_str = f" [{' • '.join(tags)}]" if tags else ""
                    with st.expander(f"{loja} — {len(lst)} chamado(s){tag_str}", expanded=False):
                        st.markdown("**FSAs:** "+", ".join(d["key"] for d in det))
                        st.code(gerar_mensagem(loja, det), language="text")

# ── VISÃO “REAGENDAR” ───────────────────────────────────────────────────────
else:
    st.title("🔄 Reagendar Chamados Agendados")

    # Tabela interativa de FSAs
    df = st.data_editor(
        pd.DataFrame(tabela),
        column_config={
            "key":        st.column_config.TextColumn("FSA", disabled=True),
            "loja":       st.column_config.TextColumn("Loja", disabled=True),
            "data_agendada": st.column_config.DatetimeColumn("Data Agendada", format="DD/MM/YYYY HH:mm", width="small")
        },
        hide_index=True,
        use_container_width=True,
    )

    # Seleciona quais reagendar
    sel = st.multiselect(
        "Selecione FSAs para atualizar data/hora:",
        options=list(df["key"]),
        default=[]
    )

    # Novo agendamento
    new_date = st.date_input("Nova Data", key="rdate")
    new_time = st.time_input("Nova Hora", key="rtime")
    if st.button("Aplicar Reagendamento") and sel:
        iso = datetime.combine(new_date, new_time).strftime("%Y-%m-%dT%H:%M:%S.000-0300")
        count=0
        for key in sel:
            ok = jira.transicionar_status(key, None, fields={"customfield_12036": iso})
            if ok:
                count+=1
        # guarda para undo
        prev_names = [jira.get_issue(k)["fields"]["status"]["name"] for k in sel]
        st.session_state.history.append({"keys": sel, "from": prev_names[0] if prev_names else ""})
        st.success(f"{count} FSAs reagendados para {iso}")

# ── RODAPÉ ─────────────────────────────────────────────────────────────────
st.markdown("---")
st.caption(f"Última atualização: {datetime.now():%d/%m/%Y %H:%M:%S}")
