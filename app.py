import streamlit as st
from streamlit_autorefresh import st_autorefresh
from datetime import datetime
from collections import defaultdict
import pandas as pd

from utils.jira_api import JiraAPI
from utils.messages import gerar_mensagem, verificar_duplicidade

# ── Configuração da página ───────────────────────────────────────────────
st.set_page_config(page_title="Painel Field Service", layout="wide")
view = st.sidebar.selectbox("Visão:", ["Lista", "Reagendar"])
if view == "Lista":
    st_autorefresh(interval=90_000, key="auto_refresh")

# ── Inicializa JiraAPI ────────────────────────────────────────────────────
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

# ── Busca pendentes e agendados ────────────────────────────────────────────
pendentes = jira.buscar_chamados("project = FSA AND status = AGENDAMENTO", FIELDS)
agendados = jira.buscar_chamados('project = FSA AND status = AGENDADO', FIELDS)

# ── Agrupa pendentes por loja ──────────────────────────────────────────────
agrup_pend = jira.agrupar_chamados(pendentes)

# ── Prepara tabela de agendados para reagendar ─────────────────────────────
rows = []
for issue in agendados:
    f = issue["fields"]
    loja = f.get("customfield_14954", {}).get("value", "Loja Desconhecida")
    raw = f.get("customfield_12036", "")
    try:
        ts = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S.%f%z")
    except:
        ts = None
    rows.append({
        "key": issue["key"],
        "loja": loja,
        "data_agendada": ts
    })
df_ag = pd.DataFrame(rows)

# ── Histórico de undo ─────────────────────────────────────────────────────
if "history" not in st.session_state:
    st.session_state.history = []

with st.sidebar:
    st.header("Ações")
    if st.button("↩️ Desfazer última ação"):
        if st.session_state.history:
            act = st.session_state.history.pop()
            cnt = 0
            for key in act["keys"]:
                trans = jira.get_transitions(key)
                rev   = next((t["id"] for t in trans
                              if t.get("to",{}).get("name")==act["from"]), None)
                if rev and jira.transicionar_status(key, rev).status_code == 204:
                    cnt += 1
            st.success(f"Revertido: {cnt} FSAs → {act['from']}")
        else:
            st.info("Nada a desfazer.")

# ── VISÃO “LISTA” ─────────────────────────────────────────────────────────
if view == "Lista":
    st.title("📋 Painel Field Service — Lista")
    c1, c2 = st.columns(2)

    with c1:
        st.header("⏳ Chamados PENDENTES de Agendamento")
        if not pendentes:
            st.warning("Nenhum pendente.")
        else:
            for loja, lst in agrup_pend.items():
                with st.expander(f"{loja} — {len(lst)} chamado(s)", expanded=False):
                    st.code(gerar_mensagem(loja, lst), language="text")

    with c2:
        st.header("📅 Chamados AGENDADOS")
        if df_ag.empty:
            st.info("Nenhum agendado.")
        else:
            # agrupa por data → loja
            by_date = defaultdict(lambda: defaultdict(list))
            for _, row in df_ag.iterrows():
                date = row["data_agendada"].strftime("%d/%m/%Y") if row["data_agendada"] else "--"
                by_date[date][row["loja"]].append(row["key"])
            for date, stores in sorted(by_date.items()):
                total = sum(len(v) for v in stores.values())
                st.subheader(f"{date} — {total} chamado(s)")
                for loja, keys in sorted(stores.items()):
                    det = [{"key": k, **jira.get_issue(k)["fields"]} for k in keys]
                    # reutiliza gerar_mensagem só precisa montar lista minimal
                    stub = [{"key":k, "pdv":"--","ativo":"--","problema":"--",
                             "endereco":"--","estado":"--","cep":"--","cidade":"--",
                             "data_agendada": jira.get_issue(k)["fields"].get("customfield_12036","")}
                            for k in keys]
                    dup = verificar_duplicidade(stub)
                    dup_keys = [k for k in keys
                                if any((d["pdv"],d["ativo"]) in dup for d in stub)]
                    spare = jira.buscar_chamados(
                        f'project = FSA AND status = "Aguardando Spare" '
                        f'AND "Codigo da Loja[Dropdown]" = {loja}',
                        FIELDS
                    )
                    spk = [i["key"] for i in spare]
                    tags = []
                    if spk: tags.append("Spare: "+", ".join(spk))
                    if dup_keys: tags.append("Dup: "+", ".join(dup_keys))
                    tag_str = f" [{' • '.join(tags)}]" if tags else ""
                    with st.expander(f"{loja} — {len(keys)} chamado(s){tag_str}", expanded=False):
                        st.markdown("**FSAs:** " + ", ".join(keys))
                        st.code(gerar_mensagem(loja, [{"key":k,"pdv":"--","ativo":"--",
                                                        "problema":"--","endereco":"--",
                                                        "estado":"--","cep":"--","cidade":"--",
                                                        "data_agendada": jira.get_issue(k)["fields"].get("customfield_12036","")}
                                                       for k in keys]), language="text")

# ── VISÃO “REAGENDAR” ───────────────────────────────────────────────────────
else:
    st.title("🔄 Reagendar Chamados Agendados")

    if df_ag.empty:
        st.info("Nenhum agendado para reagendar.")
    else:
        sel = st.multiselect(
            "Selecione FSAs:",
            options=df_ag["key"].tolist()
        )
        new_date = st.date_input("Nova Data")
        new_time = st.time_input("Nova Hora")
        if st.button("Aplicar Reagendamento") and sel:
            iso = datetime.combine(new_date, new_time).strftime("%Y-%m-%dT%H:%M:%S.000-0300")
            cnt = 0
            for key in sel:
                ok = jira.transicionar_status(key, None, fields={"customfield_12036": iso})
                if ok: cnt += 1
            st.session_state.history.append({"keys": sel, "from": "AGENDADO"})
            st.success(f"{cnt} FSAs reagendados para {iso}")

# ── Rodapé ───────────────────────────────────────────────────────────────
st.markdown("---")
st.caption(f"Atualizado em {datetime.now():%d/%m/%Y %H:%M:%S}")
