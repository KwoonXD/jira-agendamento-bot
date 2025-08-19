from collections import defaultdict

import streamlit as st

from utils.jira_api import JiraAPI
from utils.messages import agrupar_por_data, gerar_mensagem_whatsapp, ISO_PDV_URL, RAT_URL

st.set_page_config(page_title="Painel Field Service", layout="wide")
st.title("Painel Field Service")

# ------------------- Somente st.secrets -------------------
def _get_secret_or_fail():
    try:
        cfg = st.secrets["jira"]
        url   = cfg["url"]
        email = cfg["email"]
        token = cfg["token"]
        if not (url and email and token):
            raise KeyError("Valores vazios em secrets.")
        return url, email, token
    except Exception:
        st.error(
            "Credenciais do Jira não encontradas em `st.secrets['jira']`.\n\n"
            "Adicione no **secrets.toml** (local) ou nas **App secrets** (Streamlit Cloud):\n\n"
            "```toml\n"
            "[jira]\n"
            "url   = \"https://delfia.atlassian.net\"\n"
            "email = \"seu-email@dominio\"\n"
            "token = \"seu_api_token\"\n"
            "```\n"
        )
        st.stop()

JIRA_URL, JIRA_EMAIL, JIRA_TOKEN = _get_secret_or_fail()

# ----------------- JQLs & fields --------------------------
JQLS = {
    "agendamento": 'project = FSA AND status = "AGENDAMENTO"',
    "agendado":    'project = FSA AND status = "AGENDADO"',
    "tec":         'project = FSA AND status = "TEC-CAMPO"',
}
FIELDS = ",".join([
    "status",
    "customfield_14954","customfield_14829","customfield_14825","customfield_12374",
    "customfield_12271","customfield_11948","customfield_11993","customfield_11994",
    "customfield_12036",
])

def _cli() -> JiraAPI:
    return JiraAPI(email=JIRA_EMAIL, api_token=JIRA_TOKEN, jira_url=JIRA_URL)

@st.cache_data(show_spinner=False, ttl=120)
def _carregar():
    cli = _cli()
    data = {}
    for nome, jql in JQLS.items():
        issues = cli.buscar_chamados(jql, FIELDS)
        data[nome] = [cli.normalizar(i) for i in issues]
    return data

# ----------------- Carrega e mostra -----------------------
try:
    raw = _carregar()
    st.success(f"Conectado como **{JIRA_EMAIL}**")
except Exception as e:
    st.exception(e)
    st.stop()

tabs = st.tabs(["AGENDAMENTO", "AGENDADO", "TEC-CAMPO"])
mapa_status = {"AGENDAMENTO":"agendamento", "AGENDADO":"agendado", "TEC-CAMPO":"tec"}

def _render_status(chamados: list[dict], titulo: str):
    if not chamados:
        st.info("Nenhum chamado.")
        return

    por_data = agrupar_por_data(chamados)
    for data_ag, lista in por_data.items():
        por_loja = defaultdict(list)
        for ch in lista:
            por_loja[str(ch.get("loja","--"))].append(ch)

        with st.expander(f"{data_ag} — {len(lista)} chamado(s)", expanded=False):
            for loja, dets in sorted(por_loja.items(), key=lambda kv: kv[0]):
                st.markdown(f"**Loja {loja}** — FSAs: " + ", ".join(d['key'] for d in dets))
                st.code(gerar_mensagem_whatsapp(loja, dets))

with tabs[0]:
    _render_status(raw[mapa_status["AGENDAMENTO"]], "AGENDAMENTO")

with tabs[1]:
    _render_status(raw[mapa_status["AGENDADO"]], "AGENDADO")

with tabs[2]:
    _render_status(raw[mapa_status["TEC-CAMPO"]], "TEC-CAMPO")

st.caption(f"Links rápidos:  ISO (PDV): {ISO_PDV_URL}  •  RAT: {RAT_URL}")
