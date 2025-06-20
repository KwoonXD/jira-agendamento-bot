import streamlit as st
from streamlit_autorefresh import st_autorefresh
from datetime import datetime
from collections import defaultdict

from utils.jira_api import JiraAPI
from utils.messages import gerar_mensagem, verificar_duplicidade

# --- Configuração inicial ---
st.set_page_config(page_title="Painel Field Service", layout="wide")
st_autorefresh(interval=60_000, key="auto_refresh")

EMAIL      = st.secrets["EMAIL"]
API_TOKEN  = st.secrets["API_TOKEN"]
JIRA_URL   = "https://delfia.atlassian.net"
jira       = JiraAPI(EMAIL, API_TOKEN, JIRA_URL)

FIELDS = (
    "summary,"
    "customfield_14954,"
    "customfield_14829,"
    "customfield_14825,"
    "customfield_12374,"
    "customfield_12271,"
    "customfield_11993,"
    "customfield_11994,"
    "customfield_11948,"
    "customfield_12036"
)

st.title("📱 Painel Field Service")
col_agendamento, col_agendado = st.columns(2)

# ————————————— Coluna 1: AGENDAMENTO ————————————— #
with col_agendamento:
    st.header("⏳ Chamados AGENDAMENTO")
    pendentes = jira.buscar_chamados("project = FSA AND status = AGENDAMENTO", FIELDS)
    agrup = jira.agrupar_chamados(pendentes)

    if not pendentes:
        st.warning("Nenhum chamado pendente de AGENDAMENTO.")
    else:
        for loja, issues in agrup.items():
            with st.expander(f"{loja} — {len(issues)} chamado(s)", expanded=False):
                st.code(gerar_mensagem(loja, issues), language="text")

# ————————————— Coluna 2: AGENDADOS ————————————— #
with col_agendado:
    st.header("📋 Chamados AGENDADOS")
    agendados = jira.buscar_chamados('project = FSA AND status = AGENDADO', FIELDS)

    # agrupa por data + loja
    agrupado = defaultdict(lambda: defaultdict(list))
    for issue in agendados:
        f = issue["fields"]
        loja = f.get("customfield_14954", {}).get("value", "Loja Desconhecida")
        raw = f.get("customfield_12036")
        data = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S.%f%z").strftime("%d/%m/%Y") if raw else "Não definida"
        agrupado[data][loja].append(issue)

    # filtro de loja
    lojas = sorted({i["fields"].get("customfield_14954",{}).get("value","") for i in agendados})
    sel_lojas = st.sidebar.multiselect("🔍 Filtrar por loja:", ["Todas"]+lojas, default=["Todas"])

    for data, por_loja in agrupado.items():
        # filtra as lojas
        vis = {l:isl for l,isl in por_loja.items() if "Todas" in sel_lojas or l in sel_lojas}
        total = sum(len(v) for v in vis.values())
        if total==0: continue

        st.subheader(f"📅 {data} — {total} chamado(s)")
        for loja, issues in vis.items():
            detalhes = jira.agrupar_chamados(issues)[loja]
            duplicados = verificar_duplicidade(detalhes)

            # detecta FSAs duplicadas
            fsas_dup = [c["key"] for c in detalhes if (c["pdv"],c["ativo"]) in duplicados]
            # detecta FSAs aguardando spare
            spare = jira.buscar_chamados(
                f'project = FSA AND status = "Aguardando Spare" '
                f'AND "Codigo da Loja[Dropdown]" = {loja}', FIELDS
            )
            fsas_spare = [c["key"] for c in spare]

            # texto de alerta
            alertas = []
            if fsas_dup:   alertas.append(f"🔴 Duplicidade: {', '.join(fsas_dup)}")
            if fsas_spare: alertas.append(f"⚠️ Spare: {', '.join(fsas_spare)}")
            tag = f"  [{'  •  '.join(alertas)}]" if alertas else ""

            with st.expander(f"{loja} — {len(issues)} chamado(s){tag}", expanded=False):
                # lista cada chamado e oferece transição
                for ch in detalhes:
                    key = ch["key"]
                    st.markdown(f"**{key}**  | PDV: {ch['pdv']}  | Ativo: {ch['ativo']}")
                    # busca transições disponíveis
                    trans = jira.get_transitions(key)
                    opções = {t["name"]: t["id"] for t in trans}
                    escolha = st.selectbox(f"Transição para {key}", ["—"]+list(opções.keys()), key=f"sel_{key}")
                    if escolha != "—":
                        if st.button(f"▶️ Aplicar em {key}", key=f"btn_{key}"):
                            ok = jira.transicionar_status(key, opções[escolha])
                            if ok:
                                st.success(f"{key} → {escolha}")
                            else:
                                st.error(f"Falha ao transicionar {key}")
                    st.markdown("---")

# ————————————— Rodapé ————————————— #
st.markdown("---")
st.caption(f"🕒 Última atualização: {datetime.now():%d/%m/%Y %H:%M:%S}")
