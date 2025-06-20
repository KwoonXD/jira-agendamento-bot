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

# ── Campos para busca ──
FIELDS = (
    "summary,customfield_14954,customfield_14829,customfield_14825,"
    "customfield_12374,customfield_12271,customfield_11993,"
    "customfield_11994,customfield_11948,customfield_12036,customfield_12279"
)

# ── Carrega chamados PENDENTES e agrupa por loja ──
pendentes = jira.buscar_chamados("project = FSA AND status = AGENDAMENTO", FIELDS)
agrup_pend = jira.agrupar_chamados(pendentes)

# ── Carrega chamados AGENDADOS e agrupa em lista por loja ──
agendados = jira.buscar_chamados('project = FSA AND status = AGENDADO', FIELDS)
grouped_sched = defaultdict(list)
for issue in agendados:
    f    = issue["fields"]
    loja = f.get("customfield_14954", {}).get("value", "Loja Desconhecida")
    grouped_sched[loja].append(issue)

# ── Sidebar: Ações e Transição ──
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

    st.markdown("---")
    st.header("Transição de Chamados")

    # Seleção da loja
    lojas = sorted(set(agrup_pend.keys()) | set(grouped_sched.keys()))
    loja_sel = st.selectbox("Selecione a loja:", ["—"] + lojas)

    if loja_sel != "—":
        # Checkbox para mover tudo direto a Tec-Campo
        em_campo = st.checkbox("Técnico está em campo? (mover tudo)")
        if em_campo:
            # juntar pendentes e agendados
            issues_loja = [i["key"] for i in pendentes if i["fields"].get("customfield_14954", {}).get("value") == loja_sel]
            issues_loja += [i["key"] for i in grouped_sched.get(loja_sel, [])]
            if st.button(f"Mover {len(issues_loja)} chamados → Tec-Campo"):
                trans2_errors = []
                moved_tc = 0
                for key in issues_loja:
                    trans = jira.get_transitions(key)
                    id_tc = next(
                        (t["id"] for t in trans
                         if "tec-campo" in t.get("to", {}).get("name", "").lower()),
                        None
                    )
                    if id_tc:
                        res2 = jira.transicionar_status(key, id_tc)
                        if res2.status_code == 204:
                            moved_tc += 1
                        else:
                            trans2_errors.append(f"{key}: {res2.status_code}")
                if trans2_errors:
                    st.error("Erros ao mover para Tec-Campo:")
                    for e in trans2_errors:
                        st.code(e)
                else:
                    st.success(f"{moved_tc} chamados movidos → Tec-Campo")
                    st.session_state.history.append({"keys": issues_loja, "from": "AGENDADO"})
        else:
            # fluxo de agendamento manual
            # FSAs pendentes+agendados dessa loja
            opts_fsas = [i["key"] for i in pendentes if i["fields"].get("customfield_14954", {}).get("value") == loja_sel]
            opts_fsas += [i["key"] for i in grouped_sched.get(loja_sel, [])]
            selected = st.multiselect("Selecione FSAs:", options=sorted(set(opts_fsas)), default=[])

            extra_fields = {}
            if selected:
                trans_opts = {t["name"]: t["id"] for t in jira.get_transitions(selected[0])}
                choice = st.selectbox("Transição:", ["—"] + list(trans_opts.keys()))
                if choice and "agend" in choice.lower():
                    st.markdown("**Campos de Agendamento**")
                    data = st.date_input("Data do Agendamento")
                    hora = st.time_input("Hora do Agendamento")
                    tecnico = st.text_input("Dados dos Técnicos (Nome-CPF-RG-TEL)")
                    dt_iso = datetime.combine(data, hora).strftime("%Y-%m-%dT%H:%M:%S.000-0300")
                    extra_fields["customfield_12036"] = dt_iso
                    if tecnico:
                        extra_fields["customfield_12279"] = {
                            "type": "doc", "version": 1,
                            "content": [{"type": "paragraph", "content": [{"type": "text", "text": tecnico}]}]
                        }
            else:
                choice = None
                trans_opts = {}

            if st.button("Aplicar"):
                if not selected or choice in (None, "—"):
                    st.warning("Selecione ao menos uma FSA e uma transição válida.")
                else:
                    prev = jira.get_issue(selected[0])["fields"]["status"]["name"]
                    errs = []
                    moved = 0
                    for key in selected:
                        tid = trans_opts[choice]
                        res1 = jira.transicionar_status(key, tid, fields=extra_fields or None)
                        if res1.status_code == 204:
                            moved += 1
                        else:
                            errs.append(f"{key}: {res1.status_code}")
                    if errs:
                        st.error("Falhas ao transicionar:")
                        for e in errs:
                            st.code(e)
                    else:
                        st.success(f"{moved} FSAs movidos → {choice}")
                        st.session_state.history.append({"keys": selected, "from": prev})

# ── Main ──
st.title("📱 Painel Field Service")
col1, col2 = st.columns(2)

with col1:
    st.header("⏳ Chamados PENDENTES de Agendamento")
    if not pendentes:
        st.warning("Nenhum chamado em AGENDAMENTO.")
    else:
        for loja, issues in agrup_pend.items():
            with st.expander(f"{loja} — {len(issues)} chamados", expanded=False):
                st.code(gerar_mensagem(loja, issues), language="text")

with col2:
    st.header("📋 Chamados AGENDADOS")
    if not grouped_sched:
        st.info("Nenhum chamado em AGENDADO.")
    else:
        for loja, issues in grouped_sched.items():
            with st.expander(f"{loja} — {len(issues)} chamados", expanded=False):
                st.code(gerar_mensagem(loja, issues), language="text")

st.markdown("---")
st.caption(f"Última atualização: {datetime.now():%d/%m/%Y %H:%M:%S}")
