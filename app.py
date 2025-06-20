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

# ── Busca e agrupa pendentes ──
pendentes_raw = jira.buscar_chamados("project = FSA AND status = AGENDAMENTO", FIELDS)
agrup_pend    = jira.agrupar_chamados(pendentes_raw)

# ── Busca e agrupa agendados (normalizado) ──
agendados_raw  = jira.buscar_chamados('project = FSA AND status = AGENDADO', FIELDS)
agrup_sched    = jira.agrupar_chamados(agendados_raw)

# ── Raw grouping por loja para transições em massa ──
raw_by_loja = defaultdict(list)
for issue in pendentes_raw + agendados_raw:
    loja = issue["fields"].get("customfield_14954", {}).get("value", "Loja Desconhecida")
    raw_by_loja[loja].append(issue)

# ── Sidebar: Ações e Transição ──
with st.sidebar:
    st.header("Ações")
    if st.button("↩️ Desfazer última ação"):
        if st.session_state.history:
            action = st.session_state.history.pop()
            cnt = 0
            for key in action["keys"]:
                trans = jira.get_transitions(key)
                rev_id = next(
                    (t["id"] for t in trans if t.get("to", {}).get("name") == action["from"]),
                    None
                )
                if rev_id and jira.transicionar_status(key, rev_id).status_code == 204:
                    cnt += 1
            st.success(f"Revertido: {cnt} FSAs → {action['from']}")
        else:
            st.info("Nenhuma ação para desfazer.")

    st.markdown("---")
    st.header("Transição de Chamados")

    # 1) Seleção de loja
    lojas = sorted(set(agrup_pend) | set(agrup_sched))
    loja_sel = st.selectbox("Selecione a loja:", ["—"] + lojas)

    if loja_sel != "—":
        # 2) Checkbox para fluxo completo Tec-Campo
        em_campo = st.checkbox("Técnico está em campo? (agendar + mover tudo)")

        if em_campo:
            # 3) Dados de agendamento necessários
            st.markdown("**Preencha dados de agendamento**")
            data    = st.date_input("Data do Agendamento")
            hora    = st.time_input("Hora do Agendamento")
            tecnico = st.text_input("Dados dos Técnicos (Nome-CPF-RG-TEL)")

            # monta payload de agendamento
            dt_iso = datetime.combine(data, hora).strftime("%Y-%m-%dT%H:%M:%S.000-0300")
            extra_ag = {"customfield_12036": dt_iso}
            if tecnico:
                extra_ag["customfield_12279"] = {
                    "type": "doc", "version": 1,
                    "content": [{"type": "paragraph", "content": [{"type": "text", "text": tecnico}]}]
                }

            # 4) Botão único para agendar + mover
            keys_pend    = [i["key"] for i in pendentes_raw    if i["fields"].get("customfield_14954", {}).get("value") == loja_sel]
            keys_sched   = [i["key"] for i in agendados_raw   if i["fields"].get("customfield_14954", {}).get("value") == loja_sel]
            all_keys     = keys_pend + keys_sched

            if st.button(f"Agendar e mover {len(all_keys)} chamados → Tec-Campo"):
                errors = []
                moved  = 0

                # a) primeiro, agendar todos os pendentes
                for key in keys_pend:
                    trans = jira.get_transitions(key)
                    ag_id = next((t["id"] for t in trans if "agend" in t["name"].lower()), None)
                    if ag_id:
                        r = jira.transicionar_status(key, ag_id, fields=extra_ag)
                        if r.status_code != 204:
                            errors.append(f"{key} agend: {r.status_code}")
                    else:
                        errors.append(f"{key} sem transição agend")

                # b) depois, mover TODOS para Tec-Campo
                for key in all_keys:
                    trans = jira.get_transitions(key)
                    tc_id = next((t["id"] for t in trans if "tec-campo" in t["to"]["name"].lower()), None)
                    if tc_id:
                        r = jira.transicionar_status(key, tc_id)
                        if r.status_code == 204:
                            moved += 1
                        else:
                            errors.append(f"{key} tc: {r.status_code}")
                    else:
                        errors.append(f"{key} sem transição tec-campo")

                # c) resultado
                if errors:
                    st.error("Ocorreram erros:")
                    for e in errors:
                        st.code(e)
                else:
                    st.success(f"{len(all_keys)} FSAs agendados e movidos → Tec-Campo")
                    st.session_state.history.append({"keys": all_keys, "from": "AGENDADO"})

        else:
            # Fluxo manual: escolher subset FSAs para agendar/transicionar
            opts_p = [i["key"] for i in pendentes_raw  if i["fields"].get("customfield_14954", {}).get("value") == loja_sel]
            opts_a = [i["key"] for i in agendados_raw if i["fields"].get("customfield_14954", {}).get("value") == loja_sel]
            selected = st.multiselect("Selecione FSAs pend.+agend.:", options=sorted(set(opts_p + opts_a)))

            extra = {}
            if selected:
                trans_opts = {t["name"]: t["id"] for t in jira.get_transitions(selected[0])}
                choice     = st.selectbox("Transição:", ["—"] + list(trans_opts.keys()))
                if choice and "agend" in choice.lower():
                    st.markdown("**Campos de Agendamento**")
                    d = st.date_input("Data do Agendamento")
                    h = st.time_input("Hora do Agendamento")
                    tec = st.text_input("Dados dos Técnicos (Nome-CPF-RG-TEL)")
                    iso= datetime.combine(d, h).strftime("%Y-%m-%dT%H:%M:%S.000-0300")
                    extra["customfield_12036"] = iso
                    if tec:
                        extra["customfield_12279"] = {
                            "type": "doc", "version": 1,
                            "content":[{"type":"paragraph","content":[{"type":"text","text":tec}]}]
                        }
            else:
                choice = None
                trans_opts = {}

            if st.button("Aplicar"):
                if not selected or choice in (None, "—"):
                    st.warning("Selecione FSAs e transição válida.")
                else:
                    prev = jira.get_issue(selected[0])["fields"]["status"]["name"]
                    errs = []
                    mv   = 0
                    for key in selected:
                        tid = trans_opts[choice]
                        r   = jira.transicionar_status(key, tid, fields=extra or None)
                        if r.status_code == 204:
                            mv += 1
                        else:
                            errs.append(f"{key}: {r.status_code}")
                    if errs:
                        st.error("Falhas:")
                        for e in errs:
                            st.code(e)
                    else:
                        st.success(f"{mv} FSAs movidos → {choice}")
                        st.session_state.history.append({"keys": selected, "from": prev})

# ── Main ──
st.title("📱 Painel Field Service")
col1, col2 = st.columns(2)

with col1:
    st.header("⏳ Chamados PENDENTES de Agendamento")
    if not pendentes_raw:
        st.warning("Nenhum chamado em AGENDAMENTO.")
    else:
        for loja, lst in agrup_pend.items():
            with st.expander(f"{loja} — {len(lst)} chamados", expanded=False):
                st.code(gerar_mensagem(loja, lst), language="text")

with col2:
    st.header("📋 Chamados AGENDADOS")
    if not agrup_sched:
        st.info("Nenhum chamado em AGENDADO.")
    else:
        for loja, lst in agrup_sched.items():
            with st.expander(f"{loja} — {len(lst)} chamados", expanded=False):
                st.code(gerar_mensagem(loja, lst), language="text")

st.markdown("---")
st.caption(f"Última atualização: {datetime.now():%d/%m/%Y %H:%M:%S}")
