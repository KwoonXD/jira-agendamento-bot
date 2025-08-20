import streamlit as st
from streamlit_autorefresh import st_autorefresh
from datetime import datetime
from collections import defaultdict
import base64, hashlib, re

from utils.jira_api import JiraAPI
from utils.messages import gerar_mensagem, verificar_duplicidade

# ── Página + Auto‐refresh (90s) ──
st.set_page_config(page_title="Painel Field Service", layout="wide")
st_autorefresh(interval=90_000, key="auto_refresh")

# ── Histórico de undo ──
if "history" not in st.session_state:
    st.session_state.history = []

# ── Carrega secrets ──
EMAIL = st.secrets.get("EMAIL", "")
API_TOKEN = st.secrets.get("API_TOKEN", "")
BASE_URL = "https://delfia.atlassian.net"

# ── Diagnósticos locais dos secrets ──
def token_fingerprint(tok: str) -> str:
    if not tok:
        return "(vazio)"
    h = hashlib.sha256(tok.encode("utf-8")).hexdigest()
    return f"sha256:{h[:8]}…"

def looks_like_token(tok: str) -> bool:
    # Tokens Atlassian geralmente são longos e base64-like com hífens/pontos
    return bool
