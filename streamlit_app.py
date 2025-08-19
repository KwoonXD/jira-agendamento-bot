# streamlit_app.py
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional, Dict, Any

import requests
from requests.auth import HTTPBasicAuth

import streamlit as st

# ======================================================================================
# Fallbacks e utilitários
# ======================================================================================

DEFAULT_JIRA_URL = "https://delfia.atlassian.net"  # mude se quiser outro padrão


@dataclass
class JiraCreds:
    url: str
    email: str
    token: str


def _toml_section_like(d: Dict[str, Any], section: str) -> Dict[str, Any]:
    """Retorna d[section] se existir; caso contrário, d."""
    if isinstance(d, dict) and section in d and isinstance(d[section], dict):
        return d[section]
    return d


def _pick_first(*values: Optional[str]) -> Optional[str]:
    for v in values:
        if v and str(v).strip():
            return str(v).strip()
    return None


def resolve_creds() -> Optional[JiraCreds]:
    """
    Resolve credenciais do Jira em várias fontes/formatações:
    - st.secrets['jira'] (url/email/token)
    - st.secrets (EMAIL, email, TOKEN, token, URL, url, jira_url, api_token)
    - variáveis de ambiente (JIRA_URL, JIRA_EMAIL, JIRA_TOKEN)
    - st.session_state['creds'] (digitado no sidebar)
    - se url faltar, usa DEFAULT_JIRA_URL ou tenta inferir pelo domínio do email
    """
    # 1) st.secrets: aceita com ou sem [jira]
    secrets_raw: Dict[str, Any] = dict(getattr(st, "secrets", {}))
    secrets_flat = _toml_section_like(secrets_raw, "jira")

    # Chaves possíveis
    url = _pick_first(
        secrets_flat.get("url"),
        secrets_flat.get("URL"),
        secrets_flat.get("jira_url"),
        secrets_raw.get("url"),
        secrets_raw.get("URL"),
        secrets_raw.get("jira_url"),
        os.getenv("JIRA_URL"),
        os.getenv("jira_url"),
    )
    email = _pick_first(
        secrets_flat.get("email"),
        secrets_flat.get("EMAIL"),
        secrets_raw.get("email"),
        secrets_raw.get("EMAIL"),
        os.getenv("JIRA_EMAIL"),
        os.getenv("jira_email"),
    )
    token = _pick_first(
        secrets_flat.get("token"),
        secrets_flat.get("TOKEN"),
        secrets_flat.get("api_token"),
        secrets_raw.get("token"),
        secrets_raw.get("TOKEN"),
        secrets_raw.get("api_token"),
        os.getenv("JIRA_TOKEN"),
        os.getenv("jira_token"),
        os.getenv("api_token"),
    )

    # 2) fallback vindo da sessão (digitado no sidebar anteriormente)
    if st.session_state.get("creds_cache"):
        sess = st.session_state["creds_cache"]
        url = _pick_first(url, sess.get("url"))
        email = _pick_first(email, sess.get("email"))
        token = _pick_first(token, sess.get("token"))

    # 3) Se ainda faltar URL, tenta inferir por domínio do e‑mail ou usa DEFAULT_JIRA_URL
    if not url:
        if email and "@" in email:
            domain = email.split("@", 1)[-1]
            # heurística comum do Jira Cloud: subdomínio = nome da empresa
            # como fallback final, mantenho DEFAULT_JIRA_URL
            url = DEFAULT_JIRA_URL
        else:
            url = DEFAULT_JIRA_URL

    if email and token:
        return JiraCreds(url=url, email=email, token=token)

    return None


# ======================================================================================
# Cliente Jira direto (sem depender de utils) – simples para o teste de conexão
# ======================================================================================

class SimpleJira:
    def __init__(self, url: str, email: str, token: str):
        self.base_url = url.rstrip("/")
        self.auth = HTTPBasicAuth(email, token)
        self.headers = {"Accept": "application/json"}

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        r = requests.get(
            f"{self.base_url}{path}",
            auth=self.auth,
            headers=self.headers,
            params=params or {},
            timeout=15,
        )
        r.raise_for_status()
        return r.json()

    def whoami(self) -> Dict[str, Any]:
        return self._get("/rest/api/3/myself")


# ======================================================================================
# UI
# ======================================================================================

st.set_page_config(page_title="Painel Field Service", layout="wide")
st.title("Painel Field Service")

with st.sidebar:
    st.header("Credenciais")
    st.caption(
        "O app tenta carregar automaticamente de **st.secrets**, "
        "**variáveis de ambiente** e **sessão**. "
        "Se faltar algo, preencha abaixo para esta sessão."
    )

    url_in = st.text_input("Jira URL (opcional)", value=DEFAULT_JIRA_URL)
    email_in = st.text_input("E‑mail", value=st.session_state.get("creds_cache", {}).get("email", ""))
    token_in = st.text_input("API Token", value=st.session_state.get("creds_cache", {}).get("token", ""), type="password")
    col_btn = st.columns(2)
    with col_btn[0]:
        if st.button("Usar credenciais digitadas"):
            st.session_state["creds_cache"] = {"url": url_in.strip(), "email": email_in.strip(), "token": token_in.strip()}
            st.success("Credenciais armazenadas para esta sessão.")

    with col_btn[1]:
        if st.button("Limpar sessão"):
            st.session_state.pop("creds_cache", None)
            st.info("Sessão limpa.")

# ======================================================================================
# Carrega credenciais e testa conexão
# ======================================================================================

creds = resolve_creds()

if not creds:
    st.error(
        "Credenciais não encontradas.\n\n"
        "Configure **App secrets** com uma das opções:\n\n"
        "```toml\n"
        "[jira]\n"
        'url = "https://delfia.atlassian.net"\n'
        'email = "wt@parceiro.delfia.tech"\n'
        'token = "seu_api_token"\n'
        "```\n"
        "ou defina as variáveis de ambiente `JIRA_URL`, `JIRA_EMAIL`, `JIRA_TOKEN`,\n"
        "ou preencha no sidebar e clique em **Usar credenciais digitadas**."
    )
    st.stop()

# Mostra o resumo de como ficou (sem exibir token)
with st.expander("Credenciais em uso (resumo)"):
    st.write(
        {
            "url": creds.url,
            "email": creds.email,
            "token": f"***{creds.token[-6:]}" if creds.token else None,
            "origem": "secrets/env/sessão (auto)",
        }
    )

# Teste de conexão
try:
    jira = SimpleJira(creds.url, creds.email, creds.token)
    who = jira.whoami()
    st.success(f"Conectado ao Jira como **{who.get('displayName', creds.email)}**")
except requests.HTTPError as e:
    st.error(f"Falhou conectar ao Jira: {e}")
    with st.expander("Detalhes do erro"):
        st.exception(e)
    st.stop()
except Exception as e:
    st.error(f"Erro inesperado ao conectar: {e}")
    with st.expander("Detalhes do erro"):
        st.exception(e)
    st.stop()

# ======================================================================================
# Se chegou aqui, conexão OK – coloque sua lógica/painéis
# ======================================================================================

tab_agendamento, tab_agendado, tab_tec = st.tabs(["AGENDAMENTO", "AGENDADO", "TEC‑CAMPO"])

with tab_agendamento:
    st.subheader("Chamados em AGENDAMENTO")
    st.info("👉 Aqui você pode plugar sua busca por issues status = 'AGENDAMENTO'")

with tab_agendado:
    st.subheader("Chamados AGENDADOS")
    st.info("👉 Aqui você pode plugar sua busca por issues status = 'AGENDADO'")

with tab_tec:
    st.subheader("Chamados TEC‑CAMPO")
    st.info("👉 Aqui você pode plugar sua busca por issues status = 'TEC‑CAMPO'")
