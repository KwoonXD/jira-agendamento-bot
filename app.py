import streamlit as st
from streamlit_autorefresh import st_autorefresh
from datetime import datetime
from collections import defaultdict

from utils.jira_api import JiraAPI
from utils.messages import gerar_mensagem, verificar_duplicidade

# --- Configuração inicial ---
st.set_page_config(page_title="Painel Field Service", layout="wide")
st_autorefresh(interval=60_000, key="auto_refresh")

EMAIL     = st.secrets["EMAIL"]
API_TOKEN = st.secrets["API_TOKEN"]
JIRA_URL  = "https://delfia.atlassian.net"
jira      = JiraAPI(EMAIL, API_TOKEN, JIRA_URL)

FIELDS = (
    "summary,customfield_14954,customfield_14829,customfield_14825,"
    "customfield_12374,customfield_12271,customfield_11993,"
    "customfield_11994,customfield_11948,customfield_12036"
)

st.title("📱 Painel Field Service")
col_agendamento, col_agendado = st.columns(2)

# --- Coluna 1: Chamados PENDENTES (AGENDAMENTO) ---
with col_agendamento:
    st.header("⏳ Chamados AGENDAMENTO")
    pendentes = jira.buscar_chamados("project = FSA AND status = AGENDAMENTO", FIELDS)
    agrup_pend = jira.agrupar_chamados(pendentes)

    if not pendentes:
        st.warning("Nenhum chamado pendente de AGENDAMENTO.")
    else:
        for loja, issues in agrup_pend.items():
            with st.expander(f"{loja} — {len(issues)} chamado(s)", expanded=False):
                # Mensagem padrão
                st.code(gerar_mensagem(loja, issues), language="text")
                st.markdown("**▶️ Transicionar chamados**")
                for ch in issues:
                    key = ch["key"]
                    st.markdown(f"- **{key}**  | PDV {ch['pdv']} | Ativo {ch['ativo']}")
                    trans = jira.get_transitions(key)
                    opts = {t["name"]: t["id"] for t in trans}
                    escolha = st.selectbox(f"Para onde mover {key}?", ["—"] + list(opts.keys()), key=f"sel_pend_{key}")
                    if escolha != "—":
                        if st.button(f"Aplicar {key}", key=f"btn_pend_{key}"):
                            ok = jira.transicionar_status(key, opts[escolha])
                            if ok:
                                st.success(f"{key} → {escolha}")
                            else:
                                st.error(f"Falha ao mover {key}")
                st.markdown("---")

# --- Coluna 2: Chamados AGENDADOS ---
with col_agendado:
    st.header("📋 Chamados AGENDADOS")
    agendados = jira.buscar_chamados('project = FSA AND status = AGENDADO', FIELDS)

    # agrupar por data e loja
    agrup = defaultdict(lambda: defaultdict(list))
    for issue in agendados:
        f = issue["fields"]
        loja = f.get("customfield_14954", {}).get("value", "Loja Desconhecida")
        raw = f.get("customfield_12036")
        data = (
            datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S.%f%z")
            .strftime("%d/%m/%Y") if raw else "Não definida"
        )
        agrup[data][loja].append(issue)

    # filtro de loja
    lojas = sorted({i["fields"].get("customfield_14954",{}).get("value","") for i in agendados})
    sel_lojas = st.sidebar.multiselect("🔍 Filtrar por loja:", ["Todas"] + lojas, default=["Todas"])

    for data, por_loja in agrup.items():
        vis = {l: lst for l, lst in por_loja.items() if "Todas" in sel_lojas or l in sel_lojas}
        total = sum(len(lst) for lst in vis.values())
        if total == 0:
            continue

        st.subheader(f"📅 {data} — {total} chamado(s)")
        for loja, issues in vis.items():
            detalhes = jira.agrupar_chamados(issues)[loja]
            duplicados = verificar_duplicidade(detalhes)
            fsas_dup = [c["key"] for c in detalhes if (c["pdv"], c["ativo"]) in duplicados]
            spare = jira.buscar_chamados(
                f'project = FSA AND status = "Aguardando Spare" '
                f'AND "Codigo da Loja[Dropdown]" = {loja}', FIELDS
            )
            fsas_spare = [c["key"] for c in spare]

            # montar tag de alerta
            alerta = []
            if fsas_dup:
                alerta.append(f"🔴 Dup: {', '.join(fsas_dup)}")
            if fsas_spare:
                alerta.append(f"⚠️ Spare: {', '.join(fsas_spare)}")
            tag = f"  [{'  •  '.join(alerta)}]" if alerta else ""

            with st.expander(f"{loja} — {len(issues)} chamado(s){tag}", expanded=False):
                # mensagem detalhada
                st.code(gerar_mensagem(loja, detalhes), language="text")
                st.markdown("**▶️ Transicionar chamados**")
                for ch in detalhes:
                    key = ch["key"]
                    st.markdown(f"- **{key}**  | PDV {ch['pdv']} | Ativo {ch['ativo']}")
                    trans = jira.get_transitions(key)
                    opts = {t["name"]: t["id"] for t in trans}
                    escolha = st.selectbox(f"Para onde mover {key}?", ["—"] + list(opts.keys()), key=f"sel_age_{key}")
                    if escolha != "—":
                        if st.button(f"Aplicar {key}", key=f"btn_age_{key}"):
                            ok = jira.transicionar_status(key, opts[escolha])
                            if ok:
                                st.success(f"{key} → {escolha}")
                            else:
                                st.error(f"Falha ao mover {key}")
                st.markdown("---")

# --- Rodapé ---
st.markdown("---")
st.caption(f"🕒 Última atualização: {datetime.now():%d/%m/%Y %H:%M:%S}")
