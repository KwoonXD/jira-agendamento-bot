import streamlit as st
from streamlit_autorefresh import st_autorefresh
from datetime import datetime
from collections import defaultdict

from utils.jira_api import JiraAPI
from utils.messages import gerar_mensagem, verificar_duplicidade

# ── Configuração da página e auto‐refresh a cada 90 s ──
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

# ── Campos para busca ──
FIELDS = (
    "summary,customfield_14954,customfield_14829,customfield_14825,"
    "customfield_12374,customfield_12271,customfield_11993,"
    "customfield_11994,customfield_11948,customfield_12036"
)

# ── Carrega chamados ──
pendentes  = jira.buscar_chamados("project = FSA AND status = AGENDAMENTO", FIELDS)
agrup_pend = jira.agrupar_chamados(pendentes)

agendados     = jira.buscar_chamados('project = FSA AND status = AGENDADO', FIELDS)
grouped_sched = defaultdict(lambda: defaultdict(list))
for issue in agendados:
    f    = issue["fields"]
    loja = f.get("customfield_14954", {}).get("value", "Loja Desconhecida")
    raw  = f.get("customfield_12036")
    date = (
        datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S.%f%z")
        .strftime("%d/%m/%Y %H:%M")
        if raw else "Não definida"
    )
    grouped_sched[date][loja].append(issue)

# ── Sidebar: Ações e Transição ──
with st.sidebar:
    st.header("Ações")
    if st.button("↩️ Desfazer última ação"):
        if st.session_state.history:
            action  = st.session_state.history.pop()
            reverted = 0
            for key in action["keys"]:
                trans  = jira.get_transitions(key)
                rev_id = next(
                    (t["id"] for t in trans if t.get("to",{}).get("name") == action["from"]),
                    None
                )
                if rev_id and jira.transicionar_status(key, rev_id):
                    reverted += 1
            st.success(f"Revertido: {reverted} FSAs → {action['from']}")
        else:
            st.info("Nenhuma ação para desfazer.")

    st.markdown("---")
    st.header("Transição de Chamados")

    # 1) Seleção de loja (só as que têm pendentes)
    lojas_pend = sorted(agrup_pend.keys())
    loja_sel   = st.selectbox("Loja:", ["—"] + lojas_pend)

    # 2) Monta lista de FSAs pendentes + agendados
    fsas = []
    if loja_sel != "—":
        fsas += [ch["key"] for ch in agrup_pend.get(loja_sel, [])]
        for issues in grouped_sched.values():
            fsas += [ch["key"] for ch in issues.get(loja_sel, [])]
    fsas = sorted(set(fsas))

    # 3) Multiselect de FSAs atualiza ao escolher loja
    selected = st.multiselect(
        "FSAs (pend. + agend.):",
        options=fsas,
        default=fsas
    )

    # 4) Escolha de transição e montagem de payload só com data
    extra_fields = {}
    if selected:
        opts   = {t["name"]: t["id"] for t in jira.get_transitions(selected[0])}
        choice = st.selectbox("Transição:", ["—"] + list(opts.keys()))

        if choice and "agend" in choice.lower():
            st.markdown("**Preencha a data/hora obrigatória**")
            data = st.date_input("Data do Agendamento")
            hora = st.time_input("Hora do Agendamento")
            # monta no formato 2025-06-19T19:00:00.000-0300
            dt_str = datetime.combine(data, hora).strftime("%Y-%m-%dT%H:%M:%S.000-0300")
            extra_fields["customfield_12036"] = dt_str

    # 5) Botão que aplica a transição e exibe possíveis erros
    if st.button("Aplicar Transição"):
        prev = jira.get_issue(selected[0]).get("fields", {}).get("status", {}).get("name", "")
        erros = []
        for key in selected:
            res = jira.transicionar_status(key, opts[choice], fields=extra_fields or None)
            if res.status_code != 204:
                erros.append(f"{key}: {res.status_code} – {res.text}")
        if erros:
            st.error("Falhas ao transicionar:")
            for e in erros:
                st.code(e)
        else:
            st.success(f"{len(selected)} FSAs movidos → {choice}")
            st.session_state.history.append({"keys": selected, "from": prev})

    st.markdown("---")
    # filtro de loja para AGENDADOS (visualização)
    lojas_sched = sorted({l for stores in grouped_sched.values() for l in stores})
    st.multiselect(
        "Filtrar loja (AGENDADOS):",
        options=["Todas"] + lojas_sched,
        default=["Todas"],
        key="filter_sched"
    )

# ── Main ──
st.title("📱 Painel Field Service")
col1, col2 = st.columns(2)

with col1:
    st.header("⏳ Chamados PENDENTES de Agendamento")
    if not pendentes:
        st.warning("Nenhum chamado em AGENDAMENTO.")
    else:
        for loja, issues in agrup_pend.items():
            with st.expander(f"{loja} — {len(issues)} chamados"):
                st.code(gerar_mensagem(loja, issues), language="text")

with col2:
    st.header("📋 Chamados AGENDADOS")
    sel_sched = st.session_state.get("filter_sched", ["Todas"])
    for date, stores in grouped_sched.items():
        total = sum(len(v) for v in stores.values())
        if total == 0:
            continue
        st.subheader(f"{date} — {total} chamados")
        for loja, issues in stores.items():
            if "Todas" not in sel_sched and loja not in sel_sched:
                continue
            with st.expander(f"{loja} — {len(issues)} chamados"):
                detalhe = jira.agrupar_chamados(issues)[loja]
                st.code(gerar_mensagem(loja, detalhe), language="text")

st.markdown("---")
st.caption(f"Última atualização: {datetime.now():%d/%m/%Y %H:%M:%S}")
