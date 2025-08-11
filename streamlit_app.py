import streamlit as st
from streamlit_autorefresh import st_autorefresh
from datetime import datetime
from collections import defaultdict
from itertools import chain

from utils.jira_api import JiraAPI
from utils.messages import gerar_mensagem, verificar_duplicidade

# Links
ISO_DESKTOP_URL = "https://drive.google.com/file/d/1GQ64blQmysK3rbM0s0Xlot89bDNAbj5L/view?usp=drive_link"
ISO_PDV_URL     = "https://drive.google.com/file/d/1vxfHUDlT3kDdMaN0HroA5Nm9_OxasTaf/view?usp=drive_link"
RAT_URL         = None  # não exibiremos RAT no rodapé (como pediu). Coloque a URL se quiser voltar.

# Config
st.set_page_config(page_title="Painel Field Service", layout="wide")
st_autorefresh(interval=90_000, key="auto_refresh")
if "history" not in st.session_state:
    st.session_state.history = []

# Helpers
def parse_dt(raw):
    if not raw:
        return "Não definida"
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(raw, fmt).strftime("%d/%m/%Y")
        except Exception:
            pass
    return "Não definida"

def _contar_tipos(itens):
    desktop = 0
    for ch in itens:
        pdv_val = str(ch.get("pdv", "")).strip()
        ativo   = str(ch.get("ativo", "")).lower()
        if pdv_val == "300" or "desktop" in ativo:
            desktop += 1
    pdv = len(itens) - desktop
    return pdv, desktop

# Jira
jira = JiraAPI(
    st.secrets["EMAIL"],
    st.secrets["API_TOKEN"],
    "https://delfia.atlassian.net",
)

PEND_JQL = 'project = FSA AND status = "AGENDAMENTO"'
AGEN_JQL = 'project = FSA AND status = "AGENDADO"'
TEC_JQL  = 'project = FSA AND status = "TEC-CAMPO"'

FIELDS = (
    "summary,customfield_14954,customfield_14829,customfield_14825,"
    "customfield_12374,customfield_12271,customfield_11993,"
    "customfield_11994,customfield_11948,customfield_12036,customfield_12279,status"
)

pendentes_raw = jira.buscar_chamados(PEND_JQL, FIELDS)
agendados_raw = jira.buscar_chamados(AGEN_JQL, FIELDS)
tec_campo_raw = jira.buscar_chamados(TEC_JQL,  FIELDS)

grouped_agendados = defaultdict(lambda: defaultdict(list))
for issue in agendados_raw:
    f = issue.get("fields", {})
    loja = f.get("customfield_14954", {}).get("value") or "Loja Desconhecida"
    grouped_agendados[parse_dt(f.get("customfield_12036"))][loja].append(issue)

grouped_tec_campo = defaultdict(lambda: defaultdict(list))
for issue in tec_campo_raw:
    f = issue.get("fields", {})
    loja = f.get("customfield_14954", {}).get("value") or "Loja Desconhecida"
    grouped_tec_campo[parse_dt(f.get("customfield_12036"))][loja].append(issue)

agrup_pend = jira.agrupar_chamados(pendentes_raw)

raw_by_loja = defaultdict(list)
for i in chain(pendentes_raw, agendados_raw, tec_campo_raw):
    loja = i["fields"].get("customfield_14954", {}).get("value") or "Loja Desconhecida"
    raw_by_loja[loja].append(i)

# Sidebar (mantive igual ao seu fluxo)
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

    lojas_pend = set(agrup_pend.keys())
    lojas_ag   = set(chain.from_iterable(stores.keys() for stores in grouped_agendados.values())) if grouped_agendados else set()
    lojas_tc   = set(chain.from_iterable(stores.keys() for stores in grouped_tec_campo.values())) if grouped_tec_campo else set()
    lojas = sorted(lojas_pend | lojas_ag | lojas_tc)

    loja_sel = st.selectbox("Selecione a loja:", ["—"] + lojas)

# Abas
st.title("Painel Field Service")
tab1, tab2, tab3 = st.tabs(["PENDENTES", "AGENDADOS", "TEC-CAMPO"])

def _render_whatsapp_block(loja: str, detalhes: list[dict]):
    """Renderiza exatamente no formato do WhatsApp e dentro de um bloco copiável."""
    texto = gerar_mensagem(
        loja, detalhes,
        ISO_DESKTOP_URL, ISO_PDV_URL, RAT_URL,
        whatsapp_style=True
    )
    st.code(texto, language="text")

with tab1:
    st.header(f"Chamados PENDENTES de Agendamento ({len(pendentes_raw)})")
    if not pendentes_raw:
        st.warning("Nenhum chamado em AGENDAMENTO.")
    else:
        for loja, iss in sorted(agrup_pend.items()):
            qtd_pdv, qtd_desktop = _contar_tipos(iss)
            titulo = f"{loja} — {len(iss)} chamado(s) ({qtd_pdv} PDV • {qtd_desktop} Desktop)"
            with st.expander(titulo, expanded=False):
                _render_whatsapp_block(loja, iss)

with tab2:
    st.header(f"Chamados AGENDADOS ({len(agendados_raw)})")
    if not agendados_raw:
        st.info("Nenhum chamado em AGENDADO.")
    else:
        for date, stores in sorted(grouped_agendados.items()):
            total = sum(len(v) for v in stores.values())
            st.subheader(f"{date} — {total} chamado(s)")
            for loja, iss in sorted(stores.items()):
                detalhes = jira.agrupar_chamados(iss)[loja]
                qtd_pdv, qtd_desktop = _contar_tipos(detalhes)
                dup_keys = [d["key"] for d in detalhes if (d["pdv"], d["ativo"]) in verificar_duplicidade(detalhes)]
                tag_str = f" [Dup: {', '.join(dup_keys)}]" if dup_keys else ""
                titulo = f"{loja} — {len(iss)} chamado(s) ({qtd_pdv} PDV • {qtd_desktop} Desktop){tag_str}"
                with st.expander(titulo, expanded=False):
                    st.markdown("*FSAs:* " + ", ".join(d["key"] for d in detalhes))
                    _render_whatsapp_block(loja, detalhes)

with tab3:
    st.header(f"Chamados TEC-CAMPO ({len(tec_campo_raw)})")
    if not tec_campo_raw:
        st.info("Nenhum chamado em TEC-CAMPO.")
    else:
        for date, stores in sorted(grouped_tec_campo.items()):
            total = sum(len(v) for v in stores.values())
            st.subheader(f"{date} — {total} chamado(s)")
            for loja, iss in sorted(stores.items()):
                detalhes = jira.agrupar_chamados(iss)[loja]
                qtd_pdv, qtd_desktop = _contar_tipos(detalhes)
                titulo = f"{loja} — {len(iss)} chamado(s) ({qtd_pdv} PDV • {qtd_desktop} Desktop)"
                with st.expander(titulo, expanded=False):
                    st.markdown(f"*FSAs:* {', '.join(d['key'] for d in detalhes)}")
                    _render_whatsapp_block(loja, detalhes)

st.markdown("---")
st.caption(f"Última atualização: {datetime.now():%d/%m/%Y %H:%M:%S}")
