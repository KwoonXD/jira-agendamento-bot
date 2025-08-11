import streamlit as st
from streamlit_autorefresh import st_autorefresh
from datetime import datetime
from collections import defaultdict

from utils.jira_api import JiraAPI
from utils.messages import gerar_mensagem, verificar_duplicidade

# ───────────────── Config da página ─────────────────
st.set_page_config(page_title="Painel Field Service", layout="wide")
st_autorefresh(interval=90_000, key="auto_refresh")

# Histórico para desfazer
if "history" not in st.session_state:
    st.session_state.history = []

# ───────────────── Secrets / Parâmetros ─────────────────
JIRA_BASE   = st.secrets.get("JIRA_BASE", "https://delfia.atlassian.net")
EMAIL       = st.secrets["EMAIL"]
API_TOKEN   = st.secrets["API_TOKEN"]
PROJECT_KEY = st.secrets.get("PROJECT_KEY", "FSA")

# Nomes de status podem variar; permita setar via secrets
STATUS_PEND_ALIASES = st.secrets.get("STATUS_PEND_ALIASES", ["AGENDAMENTO", "Agendamento"])
STATUS_AG_ALIASES   = st.secrets.get("STATUS_AG_ALIASES",   ["AGENDADO", "Agendado"])

# ───────────────── Jira API ─────────────────
jira = JiraAPI(EMAIL, API_TOKEN, JIRA_BASE)

FIELDS = (
    "summary,customfield_14954,customfield_14829,customfield_14825,"
    "customfield_12374,customfield_12271,customfield_11993,"
    "customfield_11994,customfield_11948,customfield_12036,customfield_12279"
)

def parse_dt(raw: str) -> str:
    if not raw:
        return "Não definida"
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(raw, fmt).strftime("%d/%m/%Y")
        except ValueError:
            pass
    return "Não definida"

def jql_quote_if_needed(val):
    return f'"{val}"' if isinstance(val, str) and not val.isdigit() else str(val)

def jql_in_list(values):
    parts = []
    for v in values:
        parts.append(f'"{v}"' if isinstance(v, str) else str(v))
    return ", ".join(parts)

def try_fetch(jql: str):
    try:
        return jira.buscar_chamados(jql, FIELDS) or [], None
    except Exception as e:
        return [], str(e)

# ───────────────── Consultas ─────────────────
JQL_PEND   = f'project = {PROJECT_KEY} AND status in ({jql_in_list(STATUS_PEND_ALIASES)})'
JQL_AG     = f'project = {PROJECT_KEY} AND status in ({jql_in_list(STATUS_AG_ALIASES)})'
JQL_SANITY = f'project = {PROJECT_KEY} ORDER BY created DESC'

# 1) Pendentes
pendentes_raw, pend_err = try_fetch(JQL_PEND)
agrup_pend = jira.agrupar_chamados(pendentes_raw)

# 2) Agendados -> data → loja
agendados_raw, agend_err = try_fetch(JQL_AG)
grouped_sched = defaultdict(lambda: defaultdict(list))
for issue in agendados_raw:
    f    = issue["fields"]
    loja = f.get("customfield_14954", {}).get("value", "Loja Desconhecida")
    data_str = parse_dt(f.get("customfield_12036"))
    grouped_sched[data_str][loja].append(issue)

# 3) Raw por loja (pend+ag) para uso posterior
raw_by_loja = defaultdict(list)
for i in pendentes_raw + agendados_raw:
    loja = i["fields"].get("customfield_14954", {}).get("value", "Loja Desconhecida")
    raw_by_loja[loja].append(i)

# ───────────────── Sidebar ─────────────────
with st.sidebar:
    st.header("Ações")

    if st.button("↩️ Desfazer última ação"):
        if st.session_state.history:
            action = st.session_state.history.pop()
            reverted = 0
            for key in action["keys"]:
                trans = jira.get_transitions(key)
                rev_id = next((t["id"] for t in trans if t.get("to", {}).get("name") == action["from"]), None)
                if rev_id and jira.transicionar_status(key, rev_id).status_code == 204:
                    reverted += 1
            st.success(f"Revertido: {reverted} FSAs → {action['from']}")
        else:
            st.info("Nenhuma ação para desfazer.")

    st.markdown("---")
    st.header("Transição de Chamados")

    # ↓↓↓ FIX: cálculo de lojas SEM usar next(iter(...)) ↓↓↓
    lojas_pend = set(agrup_pend.keys()) if agrup_pend else set()
    lojas_ag   = {loja for stores in grouped_sched.values() for loja in stores.keys()}
    lojas      = sorted(lojas_pend | lojas_ag)
    # ↑↑↑ FIX: evita StopIteration quando não há agendados ↑↑↑

    loja_sel = st.selectbox("Selecione a loja:", ["—"] + lojas)

    if loja_sel != "—":
        em_campo = st.checkbox("Técnico está em campo? (agendar + mover tudo)")

        if em_campo:
            st.markdown("*Dados de Agendamento*")
            data    = st.date_input("Data do Agendamento")
            hora    = st.time_input("Hora do Agendamento")
            tecnico = st.text_input("Dados dos Técnicos (Nome-CPF-RG-TEL)")

            dt_iso = datetime.combine(data, hora).strftime("%Y-%m-%dT%H:%M:%S.000-0300")
            extra_ag = {"customfield_12036": dt_iso}
            if tecnico:
                extra_ag["customfield_12279"] = {
                    "type":"doc","version":1,
                    "content":[{"type":"paragraph","content":[{"type":"text","text":tecnico}]}]
                }

            keys_pend  = [i["key"] for i in pendentes_raw  if i["fields"].get("customfield_14954", {}).get("value") == loja_sel]
            keys_sched = [i["key"] for i in agendados_raw if i["fields"].get("customfield_14954", {}).get("value") == loja_sel]
            all_keys   = keys_pend + keys_sched

            if st.button(f"Agendar e mover {len(all_keys)} FSAs → Tec-Campo"):
                errors = []
                moved  = 0
                # a) agendar pendentes
                for k in keys_pend:
                    trans = jira.get_transitions(k)
                    agid  = next((t["id"] for t in trans if "agend" in t["name"].lower()), None)
                    if agid:
                        r = jira.transicionar_status(k, agid, fields=extra_ag)
                        if r.status_code != 204:
                            errors.append(f"{k}⏳{r.status_code}")
                # b) mover todos para Tec-Campo
                for k in all_keys:
                    trans = jira.get_transitions(k)
                    tcid = next((t["id"] for t in trans if "tec-campo" in t.get("to", {}).get("name", "").lower()), None)
                    if tcid:
                        r = jira.transicionar_status(k, tcid)
                        if r.status_code == 204:
                            moved += 1
                        else:
                            errors.append(f"{k}➡️{r.status_code}")
                if errors:
                    st.error("Erros:")
                    for e in errors:
                        st.code(e)
                else:
                    st.success(f"{len(all_keys)} FSAs agendados e movidos → Tec-Campo")
                    st.session_state.history.append({"keys": all_keys, "from": "AGENDADO"})
                    detail  = jira.agrupar_chamados(raw_by_loja[loja_sel])[loja_sel]
                    novos   = [d for d in detail if d["key"] in keys_pend]
                    antigos = [d for d in detail if d["key"] in keys_sched]
                    st.markdown("### 🆕 Novos Agendados")
                    st.code(gerar_mensagem(loja_sel, novos), language="text")
                    if antigos:
                        st.markdown("### 📋 Já Agendados")
                        st.code(gerar_mensagem(loja_sel, antigos), language="text")

        else:
            # Fluxo manual
            opts = [i["key"] for i in pendentes_raw if i["fields"].get("customfield_14954", {}).get("value") == loja_sel]
            opts += [i["key"] for i in agendados_raw if i["fields"].get("customfield_14954", {}).get("value") == loja_sel]
            sel = st.multiselect("Selecione FSAs pend.+age.:", sorted(set(opts)))
            extra = {}
            choice = None
            trans_opts = {}
            if sel:
                trans_opts = {t["name"]: t["id"] for t in jira.get_transitions(sel[0])}
                choice = st.selectbox("Transição:", ["—"] + list(trans_opts))
                if choice and "agend" in choice.lower():
                    st.markdown("*Dados de Agendamento*")
                    d   = st.date_input("Data do Agendamento")
                    h   = st.time_input("Hora do Agendamento")
                    tec = st.text_input("Dados dos Técnicos (Nome-CPF-RG-TEL)")
                    iso = datetime.combine(d, h).strftime("%Y-%m-%dT%H:%M:%S.000-0300")
                    extra["customfield_12036"] = iso
                    if tec:
                        extra["customfield_12279"] = {
                            "type":"doc","version":1,
                            "content":[{"type":"paragraph","content":[{"type":"text","text":tec}]}]
                        }
            if st.button("Aplicar"):
                if not sel or choice in (None, "—"):
                    st.warning("Selecione FSAs e transição.")
                else:
                    prev = jira.get_issue(sel[0])["fields"]["status"]["name"]
                    errs = []
                    mv   = 0
                    for k in sel:
                        r = jira.transicionar_status(k, trans_opts[choice], fields=extra or None)
                        if r.status_code == 204:
                            mv += 1
                        else:
                            errs.append(f"{k}:{r.status_code}")
                    if errs:
                        st.error("Falhas:")
                        for e in errs:
                            st.code(e)
                    else:
                        st.success(f"{mv} FSAs movidos → {choice}")
                        st.session_state.history.append({"keys": sel, "from": prev})

# ───────────────── Main ─────────────────
st.title("📱 Painel Field Service")
col1, col2 = st.columns(2)

with col1:
    st.header("⏳ Chamados PENDENTES de Agendamento")
    if not pendentes_raw:
        st.warning("Nenhum chamado em AGENDAMENTO.")
    else:
        for loja, iss in agrup_pend.items():
            with st.expander(f"{loja} — {len(iss)} chamado(s)", expanded=False):
                st.code(gerar_mensagem(loja, iss), language="text")

with col2:
    st.header("📋 Chamados AGENDADOS")
    if not agendados_raw:
        st.info("Nenhum chamado em AGENDADO.")
    else:
        for date, stores in sorted(grouped_sched.items()):
            total = sum(len(v) for v in stores.values())
            st.subheader(f"{date} — {total} chamado(s)")
            for loja, iss in sorted(stores.items()):
                detalhes = jira.agrupar_chamados(iss)[loja]
                dup_keys = [d["key"] for d in detalhes if (d["pdv"], d["ativo"]) in verificar_duplicidade(detalhes)]

                loja_for_jql = jql_quote_if_needed(loja)
                spare_raw, _ = try_fetch(
                    f'project = {PROJECT_KEY} AND status = "Aguardando Spare" AND "Codigo da Loja[Dropdown]" = {loja_for_jql}'
                )
                spare_keys = [i["key"] for i in spare_raw]

                tags = []
                if spare_keys:
                    tags.append("Spare: " + ", ".join(spare_keys))
                if dup_keys:
                    tags.append("Dup: " + ", ".join(dup_keys))
                tag_str = f" [{' • '.join(tags)}]" if tags else ""
                with st.expander(f"{loja} — {len(iss)} chamado(s){tag_str}", expanded=False):
                    st.markdown("*FSAs:* " + ", ".join(d["key"] for d in detalhes))
                    st.code(gerar_mensagem(loja, detalhes), language="text")

st.markdown("---")
st.caption(f"Última atualização: {datetime.now():%d/%m/%Y %H:%M:%S}")

# ───────────────── Mini‑debug (pode remover depois) ─────────────────
with st.sidebar.expander("🛠️ Debug rápido", expanded=False):
    st.caption(f"pend={len(pendentes_raw)}  ag={len(agendados_raw)}  datas_ag={list(grouped_sched.keys())[:3]}")
    if st.secrets.get("show_jql", False):
        st.code(f"PEND: {JQL_PEND}\nAG:   {JQL_AG}", language="text")
    if pend_err:
        st.error("Erro pendentes: " + str(pend_err))
    if agend_err:
        st.error("Erro agendados: " + str(agend_err))
