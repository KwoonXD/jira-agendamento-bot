from __future__ import annotations

import os
from datetime import datetime
from typing import Iterable, List, Dict

import requests
from requests.auth import HTTPBasicAuth
import streamlit as st

# ============================
# CONFIG BÁSICA DA PÁGINA
# ============================
st.set_page_config(page_title="Painel Field Service", layout="wide")

# ============================
# LINKS PADRÃO (edite se quiser)
# ============================
ISO_DESKTOP_URL = "https://drive.google.com/file/d/1GQ64blQmysK3rbM0s0Xlot89bDNAbj5L/view?usp=drive_link"
ISO_PDV_URL     = "https://drive.google.com/file/d/1vxfHUDlT3kDdMaN0HroA5Nm9_OxasTaf/view?usp=drive_link"
RAT_URL         = "https://drive.google.com/file/d/1_SG1RofIjoJLgwWYs0ya0fKlmVd74Lhn/view?usp=sharing"

# ============================
# JQLs e FIELDS usados
# ============================
FIELDS = ",".join([
    "status",
    "created",
    "customfield_14954",  # Loja
    "customfield_14829",  # PDV
    "customfield_14825",  # Ativo
    "customfield_12374",  # Problema
    "customfield_12271",  # Endereço
    "customfield_11948",  # Estado
    "customfield_11993",  # CEP
    "customfield_11994",  # Cidade
    "customfield_12036",  # Data agendada
])

JQLS = {
    "agendamento": 'project = FSA AND status = "AGENDAMENTO"',
    "agendado":    'project = FSA AND status = "AGENDADO"',
    "tec":         'project = FSA AND status = "TEC-CAMPO"',
}


# ============================
# CLIENTE JIRA SIMPLES
# ============================
class JiraAPI:
    def __init__(self, email: str, api_token: str, base_url: str):
        self.email = email
        self.api_token = api_token
        self.base_url = base_url.rstrip("/")
        self._auth = HTTPBasicAuth(email, api_token)
        self._headers = {"Accept": "application/json"}

    def _get(self, path: str, params: Dict | None = None) -> dict:
        url = f"{self.base_url}{path}"
        r = requests.get(url, headers=self._headers, auth=self._auth, params=params or {}, timeout=20)
        r.raise_for_status()
        return r.json()

    def buscar_chamados(self, jql: str, fields: str = FIELDS, max_results: int = 200) -> List[dict]:
        params = {"jql": jql, "fields": fields, "maxResults": max_results}
        data = self._get("/rest/api/3/search", params=params)
        return data.get("issues", [])

    def whoami(self) -> dict:
        return self._get("/rest/api/3/myself")

    @staticmethod
    def normalizar_issue(issue: dict) -> dict:
        f = issue.get("fields", {})
        loja = (f.get("customfield_14954") or {}).get("value") or "Loja Desconhecida"
        estado = (f.get("customfield_11948") or {}).get("value") or "--"
        ativo = (f.get("customfield_14825") or {}).get("value") or "--"
        return {
            "key": issue.get("key", "--"),
            "status": (f.get("status") or {}).get("name") or "--",
            "created": f.get("created"),
            "loja": loja,
            "pdv": str(f.get("customfield_14829") or "--"),
            "ativo": str(ativo),
            "problema": str(f.get("customfield_12374") or "--"),
            "endereco": str(f.get("customfield_12271") or "--"),
            "estado": str(estado),
            "cep": str(f.get("customfield_11993") or "--"),
            "cidade": str(f.get("customfield_11994") or "--"),
            "data_agendada": f.get("customfield_12036"),
        }


# ============================
# HELPERS DE MENSAGEM/AGRUPAMENTO
# ============================
def _fmt_iso_date(raw: str | None) -> str | None:
    if not raw:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(raw, fmt).strftime("%d/%m/%Y")
        except Exception:
            pass
    return None

def _is_desktop(pdv: str, ativo: str) -> bool:
    pdv = str(pdv or "").strip()
    ativo = str(ativo or "").lower()
    return pdv == "300" or ("desktop" in ativo)

def _endereco_bloco(ch: dict) -> List[str]:
    iso_link = ISO_DESKTOP_URL if _is_desktop(ch.get("pdv"), ch.get("ativo")) else ISO_PDV_URL
    iso_label = "Desktop" if _is_desktop(ch.get("pdv"), ch.get("ativo")) else "do PDV"
    return [
        f"Endereço: {ch.get('endereco','--')}",
        f"Estado: {ch.get('estado','--')}",
        f"CEP: {ch.get('cep','--')}",
        f"Cidade: {ch.get('cidade','--')}",
        "------",
        "⚠️ *É OBRIGATÓRIO LEVAR:*",
        f"• ISO ({iso_label}) ({iso_link})",
        f"• RAT: ({RAT_URL})",
    ]

def gerar_mensagem_por_loja(loja: str, chamados: Iterable[dict]) -> str:
    chamados = list(chamados)
    blocos: List[str] = []
    for ch in chamados:
        linhas = [
            f"*{ch.get('key','--')}*",
            f"Loja: {loja}",
            f"PDV: {ch.get('pdv','--')}",
            f"*ATIVO: {ch.get('ativo','--')}*",
            f"Problema: {ch.get('problema','--')}",
            "***",
        ]
        blocos.append("\n".join(linhas))
    ref = next((c for c in reversed(chamados) if any(c.get(k) for k in ("endereco","estado","cep","cidade"))), None)
    if ref:
        blocos.append("\n".join(_endereco_bloco(ref)))
    return "\n\n".join(blocos)

def group_by_date(issues: Iterable[dict]) -> dict[str, List[dict]]:
    out: dict[str, List[dict]] = {}
    for it in issues:
        d = _fmt_iso_date(it.get("data_agendada")) or _fmt_iso_date(it.get("created")) or "Sem data"
        out.setdefault(d, []).append(it)
    return out

def group_by_store(issues: Iterable[dict]) -> dict[str, List[dict]]:
    out: dict[str, List[dict]] = {}
    for it in issues:
        loja = it.get("loja") or "Loja Desconhecida"
        out.setdefault(loja, []).append(it)
    return out

def _badge(text: str) -> str:
    return f"<span style='background:#111827;padding:4px 8px;border-radius:8px;font-weight:600;font-size:12px;color:#E5E7EB'>{text}</span>"


# ============================
# SIDEBAR: CREDENCIAIS (opcional)
# ============================
with st.sidebar:
    st.header("Conexão Jira (opcional)")
    st.caption("Preencha para buscar dados reais. Em branco = usa dados de exemplo.")
    url = st.text_input("URL do Jira", value=st.session_state.get("jira_url", os.getenv("JIRA_URL","")))
    email = st.text_input("E‑mail", value=st.session_state.get("jira_email", os.getenv("JIRA_EMAIL","")))
    token = st.text_input("API Token", type="password", value=st.session_state.get("jira_token", os.getenv("JIRA_API_TOKEN","")))
    col = st.columns(2)
    with col[0]:
        if st.button("Salvar sessão"):
            st.session_state["jira_url"] = url
            st.session_state["jira_email"] = email
            st.session_state["jira_token"] = token
            st.success("Credenciais guardadas nesta sessão.")
    with col[1]:
        if st.button("Testar conexão Jira (/myself)"):
            if url and email and token:
                try:
                    who = JiraAPI(email, token, url).whoami()
                    st.success(f"Conectado como: {who.get('displayName') or who.get('emailAddress') or 'OK'}")
                except Exception as e:
                    st.error(f"Falhou: {e}")
            else:
                st.warning("Preencha URL / e‑mail / token para testar.")

# ============================
# CARGA DE DADOS
# ============================
@st.cache_data(show_spinner=True, ttl=180)
def carregar(url: str, email: str, token: str) -> dict[str, list]:
    """Busca no Jira; se faltar credencial, retorna amostra local."""
    def _norm(xs: list) -> list:
        return [JiraAPI.normalizar_issue(i) for i in xs]

    # sem credenciais => dados fake
    if not (url and email and token):
        sample = [
            {
                "key": "FSA-99901", "status": "AGENDAMENTO", "created": "2025-08-10T09:00:00.000+0000",
                "loja": "L296", "pdv": "309", "ativo": "CPU", "problema": "Tela preta",
                "endereco": "AV. TESTE 1000", "estado": "SP", "cep": "01000-000", "cidade": "São Paulo",
                "data_agendada": None,
            },
            {
                "key": "FSA-99902", "status": "AGENDADO", "created": "2025-08-10T10:00:00.000+0000",
                "loja": "L174", "pdv": "300", "ativo": "Desktop", "problema": "Sem boot",
                "endereco": "RUA TESTE 200", "estado": "BA", "cep": "40000-000", "cidade": "Salvador",
                "data_agendada": "2025-08-11T13:00:00.000+0000",
            },
            {
                "key": "FSA-99903", "status": "TEC-CAMPO", "created": "2025-08-09T10:00:00.000+0000",
                "loja": "L296", "pdv": "305", "ativo": "CPU", "problema": "Reboot constante",
                "endereco": "AV. TESTE 1000", "estado": "SP", "cep": "01000-000", "cidade": "São Paulo",
                "data_agendada": "2025-08-12T09:00:00.000+0000",
            },
        ]
        return {"agendamento": [sample[0]], "agendado": [sample[1]], "tec": [sample[2]]}

    # com credenciais => Jira real
    cli = JiraAPI(email, token, url)
    agendamento = _norm(cli.buscar_chamados(JQLS["agendamento"], FIELDS))
    agendado    = _norm(cli.buscar_chamados(JQLS["agendado"],    FIELDS))
    tec         = _norm(cli.buscar_chamados(JQLS["tec"],          FIELDS))
    return {"agendamento": agendamento, "agendado": agendado, "tec": tec}

# Botão de refresh
rcol = st.columns([1,3,6])[0]
if rcol.button("🔄 Atualizar agora"):
    st.cache_data.clear()
    st.rerun()

# Carrega
DATA = carregar(
    st.session_state.get("jira_url", url),
    st.session_state.get("jira_email", email),
    st.session_state.get("jira_token", token),
)

# ============================
# UI PRINCIPAL
# ============================
st.title("Painel Field Service")
st.caption(
    f"Links: ISO Desktop: {ISO_DESKTOP_URL} • ISO PDV: {ISO_PDV_URL} • RAT: {RAT_URL}"
)

tab1, tab2, tab3 = st.tabs(["AGENDAMENTO", "AGENDADO", "TEC‑CAMPO"])

def _desenhar(chamados: list, rotulo: str):
    por_data = group_by_date(chamados)
    for data_str in sorted(por_data.keys()):
        itens_dia = por_data[data_str]
        badge = _badge(rotulo)
        with st.expander(f"{data_str} — {len(itens_dia)} chamado(s)  {badge}", expanded=False):
            por_loja = group_by_store(itens_dia)
            for loja, dets in sorted(por_loja.items(), key=lambda x: x[0]):
                st.markdown(f"**Loja {loja}** — FSAs: " + ", ".join(d['key'] for d in dets))
                st.code(gerar_mensagem_por_loja(loja, dets), language="text")

with tab1:
    _desenhar(DATA["agendamento"], "AGENDAMENTO")

with tab2:
    _desenhar(DATA["agendado"], "AGENDADO")

with tab3:
    _desenhar(DATA["tec"], "TEC-CAMPO")
