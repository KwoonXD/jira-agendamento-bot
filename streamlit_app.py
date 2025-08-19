import os
from pathlib import Path
from collections import defaultdict

import streamlit as st

from utils.jira_api import JiraAPI
from utils.messages import agrupar_por_data, gerar_mensagem_whatsapp, ISO_PDV_URL, RAT_URL

st.set_page_config(page_title="Painel Field Service", layout="wide")
st.title("Painel Field Service")

# ---------------- Persistência de credenciais ----------------
CREDS_FILE = Path("credentials.yaml")

def _load_from_secrets() -> tuple[str,str,str] | None:
    try:
        s = st.secrets["jira"]
        return s["url"], s["email"], s["token"]
    except Exception:
        return None

def _load_from_yaml() -> tuple[str,str,str] | None:
    try:
        import yaml  # já está em requirements
        if CREDS_FILE.exists():
            data = yaml.safe_load(CREDS_FILE.read_text(encoding="utf-8")) or {}
            j = data.get("jira", {})
            return j.get("url"), j.get("email"), j.get("token")
        return None
    except Exception:
        return None

def _save_yaml(url: str, email: str, token: str):
    import yaml
    CREDS_FILE.write_text(yaml.safe_dump({"jira":{"url":url,"email":email,"token":token}}, sort_keys=False), encoding="utf-8")

def carregar_credenciais():
    c = _load_from_secrets()
    if c and all(c):
        return c, "secrets"
    c = _load_from_yaml()
    if c and all(c):
        return c, "yaml"
    return (None, None), None

(creds, origem) = carregar_credenciais()
url, email, token = (creds if creds != (None, None) else ("","",""))

with st.sidebar:
    st.caption("Autenticação")
    url = st.text_input("Jira URL", url or "https://delfia.atlassian.net")
    email = st.text_input("E-mail", email or "")
    token = st.text_input("Token", token or "", type="password")
    col = st.columns(2)
    with col[0]:
        testar = st.button("Testar conexão", use_container_width=True)
    with col[1]:
        salvar = st.button("Salvar localmente", use_container_width=True)
    if salvar:
        _save_yaml(url, email, token)
        st.success("Credenciais salvas em credentials.yaml")

# --------------- JQLs & fields (simples) ---------------------
JQLS = {
    "agendamento": 'project = FSA AND status = "AGENDAMENTO"',
    "agendado":    'project = FSA AND status = "AGENDADO"',
    "tec":         'project = FSA AND status = "TEC-CAMPO"',
}
FIELDS = ",".join([
    "status",
    # customfields mapeados no JiraAPI.normalizar
    "customfield_14954","customfield_14829","customfield_14825","customfield_12374",
    "customfield_12271","customfield_11948","customfield_11993","customfield_11994",
    "customfield_12036",
])

def _cli() -> JiraAPI:
    return JiraAPI(email=email, api_token=token, jira_url=url)

@st.cache_data(show_spinner=False, ttl=120)
def _carregar():
    cli = _cli()
    data = {}
    for nome, jql in JQLS.items():
        issues = cli.buscar_chamados(jql, FIELDS)
        data[nome] = [cli.normalizar(i) for i in issues]
    return data

# Teste rápido
if testar:
    try:
        _ = _carregar()
        st.sidebar.success(f"Conectado como {email.split('@')[0].upper()}")
    except Exception as e:
        st.sidebar.exception(e)

# Evita rodar sem credencial
if not (url and email and token):
    st.info("Informe as credenciais ao lado e clique **Testar conexão**.")
    st.stop()

# ----------------- Conteúdo -----------------------
try:
    raw = _carregar()
except Exception as e:
    st.exception(e)
    st.stop()

tabs = st.tabs(["AGENDAMENTO", "AGENDADO", "TEC-CAMPO"])
mapa_status = {"AGENDAMENTO":"agendamento", "AGENDADO":"agendado", "TEC-CAMPO":"tec"}

def _render_status(chamados: list[dict], titulo: str):
    if not chamados:
        st.info("Nenhum chamado.")
        return

    # agrupa por data agendada (ou “Sem data”)
    por_data = agrupar_por_data(chamados)
    for data_ag, lista in por_data.items():
        # agrupa por loja
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

# Rodapé rápido
st.caption(f"Links rápidos:  ISO (PDV): {ISO_PDV_URL}  •  RAT: {RAT_URL}")
