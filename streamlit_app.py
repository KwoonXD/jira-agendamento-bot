# streamlit_app.py
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Dict, List

import streamlit as st

from utils.jira_api import JiraAPI
from utils.messages import gerar_mensagem, verificar_duplicidade


# ======================================================
# CONFIGURAÇÃO BÁSICA
# ======================================================
st.set_page_config(page_title="Painel Field Service", layout="wide")
st.title("Painel Field Service")

# JQLs usados (ajuste conforme seu fluxo)
JQLS = {
    "agendamento": "project = FSA AND status = AGENDAMENTO ORDER BY created DESC",
    "agendado":    "project = FSA AND status = Agendado ORDER BY created DESC",
    "tec":         "project = FSA AND status = 'TEC-CAMPO' ORDER BY created DESC",
}


# ======================================================
# CREDENCIAIS EXCLUSIVAMENTE PELO st.secrets
# ======================================================
def _get_jira_from_secrets() -> Dict[str, str]:
    """
    Lê SOMENTE de st.secrets['jira'].
    Se não existir, mostra instruções e interrompe.
    """
    try:
        sec = st.secrets["jira"]
        url = sec["url"]
        email = sec["email"]
        token = sec["token"]
        if not (url and email and token):
            raise KeyError("Parâmetros vazios.")
        return {"url": url, "email": email, "token": token}
    except Exception:
        st.error("Credenciais não encontradas.")
        st.markdown(
            """
**Configure App secrets** com a tabela `[jira]`:

```toml
[jira]
url   = "https://seu-dominio.atlassian.net"
email = "seu-email@dominio"
token = "seu_api_token"
