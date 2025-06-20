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

# ── Conexão com Jira ──────────────────────────────────────────────────────
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

# ── Busca chamados ────────────────────────────────────────────────────────
pendentes = jira.buscar_chamados("project = FSA AND status = AGENDAMENTO", FIELDS)
agendados = jira.buscar_chamados('project = FSA AND status = AGENDADO', FIELDS)

# ── Agrupa pendentes por loja ──────────────────────────────────────────────
agrup_pend = jira.agrupar_chamados(pendentes)

# ── Prepara tabela de agendados ───────────────────────────────────────────
rows = []
for issue in agendados:
    f = issue["fields"]
    loja = f.get("customfield_14954", {}).get("value", "Loja Desconhecida")
    raw = f.get("customfield_12036", "")
    try:
        ts = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S.%f%z")
    except:
        ts = None
    rows.append({"FSA": issue["key"], "Loja": loja, "Agendado em": ts})
df_ag = pd.DataFrame(rows)

# ── Histórico de undo ─────────────────────────────────────────────────────
if "history" not in st.session_state:
    st.session_state.history = []

with st.sidebar:
    st.header("Ações")
    if st.button("↩️ Desfazer última ação"):
        if st.session_state.history:
            act = st.session_state.history.pop()
            reverted = 0
            for key, prev in zip(act["keys"], act["prev_times"]):
                # volta o campo customfield_12036 ao valor anterior
                ok = jira.transicionar_status(key, None, fields={"customfield_12036": prev})
                if ok: reverted += 1
            st.success(f"Revertido: {reverted} FSAs para horários anteriores")
        else:
            st.info("Nada a desfazer.")

# ── VISÃO “LISTA” ─────────────────────────────────────────────────────────
if view == "Lista":
    st.title("📋 Painel Field Service — Lista")
    left, right = st.columns(2)

    # Pendentes
    with left:
        st.header("⏳ Chamados PENDENTES")
        if not pendentes:
            st.warning("Nenhum chamado em AGENDAMENTO.")
        else:
            for loja, lst in agrup_pend.items():
                with st.expander(f"{loja} — {len(lst)} chamado(s)", expanded=False):
                    st.code(gerar_mensagem(loja, lst), language="text")

    # Agendados
    with right:
        st.header("📅 Chamados AGENDADOS")
        if df_ag.empty:
            st.info("Nenhum chamado AGENDADO.")
        else:
            # agrupamento por data → loja
            by_date = defaultdict(lambda: defaultdict(list))
            for _, row in df_ag.iterrows():
                label = row["Agendado em"].strftime("%d/%m/%Y %H:%M") if row["Agendado em"] else "--"
                by_date[label][row["Loja"]].append(row["FSA"])
            for date_label, stores in sorted(by_date.items()):
                total = sum(len(v) for v in stores.values())
                st.subheader(f"{date_label} — {total} chamado(s)")
                for loja, keys in sorted(stores.items()):
                    det = [{"key":k, "pdv":"--","ativo":"--","problema":"--",
                            "endereco":"--","estado":"--","cep":"--","cidade":"--",
                            "data_agendada": jira.buscar_chamados(f'key={k}',FIELDS)[0]["fields"].get("customfield_12036","")}
                           for k in keys]
                    dup = verificar_duplicidade(det)
                    dup_keys = [k for k in keys
                                if ( next(x for x in det if x["key"]==k)["pdv"],
                                     next(x for x in det if x["key"]==k)["ativo"]
                                   ) in dup]
                    spare = jira.buscar_chamados(
                        f'project = FSA AND status = "Aguardando Spare" '
                        f'AND "Codigo da Loja[Dropdown]" = {loja}', FIELDS
                    )
                    spk = [i["key"] for i in spare]
                    tags = []
                    if spk: tags.append("Spare: "+", ".join(spk))
                    if dup_keys: tags.append("Dup: "+", ".join(dup_keys))
                    tag_str = f" [{' • '.join(tags)}]" if tags else ""
                    with st.expander(f"{loja} — {len(keys)} chamado(s){tag_str}", expanded=False):
                        st.markdown("**FSAs:** " + ", ".join(keys))
                        st.code(gerar_mensagem(loja, det), language="text")

# ── VISÃO “REAGENDAR” ───────────────────────────────────────────────────────
else:
    st.title("🔄 Reagendar Chamados Agendados")
    if df_ag.empty:
        st.info("Nenhum agendamento para reagendar.")
    else:
        sel = st.multiselect("Selecione FSAs:", df_ag["FSA"].tolist())
        new_date = st.date_input("Nova Data")
        new_time = st.time_input("Nova Hora")
        if st.button("Aplicar Reagendamento") and sel:
            iso_new = datetime.combine(new_date, new_time).strftime("%Y-%m-%dT%H:%M:%S.000-0300")
            prev_times = []
            count = 0
            for key in sel:
                # captura time antigo para undo
                old_raw = next(r["Agendado em"] for r in rows if r["FSA"]==key)
                prev_times.append(
                    old_raw.strftime("%Y-%m-%dT%H:%M:%S.000-0300") if old_raw else ""
                )
                ok = jira.transicionar_status(key, None, fields={"customfield_12036": iso_new})
                if ok: count += 1
            # grava histórico de undo
            st.session_state.history.append({
                "keys": sel,
                "prev_times": prev_times
            })
            st.success(f"{count} FSA(s) reagendado(s) para {iso_new}")

# ── Rodapé ───────────────────────────────────────────────────────────────
st.markdown("---")
st.caption(f"Última atualização: {datetime.now():%d/%m/%Y %H:%M:%S}")
