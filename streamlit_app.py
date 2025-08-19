# streamlit_app.py
# ------------------------------------------------------------
# Painel Field Service (versão enxuta e robusta)
# - Lê credenciais do st.secrets['jira']
# - Carrega issues do Jira em três JQLs
# - Agrupa por data e loja, gera mensagem e marca duplicidades
# - Tenta instanciar JiraAPI com api_token | token | posicional
# ------------------------------------------------------------
from __future__ import annotations

import json
from datetime import datetime
from collections import defaultdict

import streamlit as st

# ---- Dependências do projeto ----
from utils.jira_api import JiraAPI

try:
    # funções de mensagem e duplicidade (mantidas no seu repositório)
    from utils.messages import gerar_mensagem, verificar_duplicidade
except Exception:
    # fallback defensivo: se a função não existir por algum motivo
    def gerar_mensagem(loja: str, chamados: list) -> str:
        linhas = [f"Loja {loja}", "------"]
        for ch in chamados:
            linhas.append(
                "\n".join(
                    [
                        f"*{ch.get('key','--')}*",
                        f"PDV: {ch.get('pdv','--')}",
                        f"ATIVO: {ch.get('ativo','--')}",
                        f"Problema: {ch.get('problema','--')}",
                        "***",
                    ]
                )
            )
        return "\n".join(linhas)

    def verificar_duplicidade(chamados: list) -> set[tuple]:
        seen = set()
        dup = set()
        for ch in chamados:
            k = (ch.get("pdv"), ch.get("ativo"))
            if k in seen:
                dup.add(k)
            else:
                seen.add(k)
        return dup


# ========== CONFIG VISUAL ==========
st.set_page_config(page_title="Painel Field Service", layout="wide")
st.title("Painel Field Service")

# ======== CONSTANTES DO APP ========
# Campos mínimos para o painel (ajuste IDs à sua instância se necessário)
FIELDS = ",".join(
    [
        "key",
        "status",
        "customfield_14954",  # Loja (option)
        "customfield_14829",  # PDV
        "customfield_14825",  # Ativo (option)
        "customfield_12374",  # Problema
        "customfield_12271",  # Endereço
        "customfield_11948",  # Estado (option)
        "customfield_11993",  # CEP
        "customfield_11994",  # Cidade
        "customfield_12036",  # Data agendada
    ]
)

JQLS = {
    # Ajuste estes JQLs à sua realidade (mantive simples e neutros)
    "agendamento": 'project = FSA AND status = "AGENDAMENTO"',
    "agendado": 'project = FSA AND status = "AGENDADO"',
    "tec": 'project = FSA AND status = "TEC-CAMPO"',
}


# ========== FUNÇÕES DE CREDENCIAL ==========
def _show_missing_secrets_hint() -> None:
    st.error("Credenciais do Jira não encontradas em `st.secrets['jira']`.")
    st.code(
        "[jira]\n"
        'url   = "https://seu-dominio.atlassian.net"\n'
        'email = "seu-email@dominio"\n'
        'token = "seu_api_token"\n',
        language="toml",
    )
    st.stop()


def _read_secrets() -> dict:
    # Tenta bloco [jira]
    jira = st.secrets.get("jira", None)
    if isinstance(jira, dict):
        url = jira.get("url")
        email = jira.get("email")
        token = jira.get("token")
    else:
        # fallback: chaves soltas (legado)
        url = st.secrets.get("url")
        email = st.secrets.get("email")
        token = st.secrets.get("token")

    if not url or not email or not token:
        _show_missing_secrets_hint()

    return {"url": url.rstrip("/"), "email": email, "token": token}


# ========== CLIENTE JIRA ==========
@st.cache_resource(show_spinner=False)
def jira_client() -> JiraAPI:
    cred = _read_secrets()

    # Tenta as três assinaturas mais comuns
    try:
        # 1) Com api_token
        return JiraAPI(email=cred["email"], api_token=cred["token"], jira_url=cred["url"])
    except TypeError:
        try:
            # 2) Com token
            return JiraAPI(email=cred["email"], token=cred["token"], jira_url=cred["url"])
        except TypeError:
            # 3) Posicional
            return JiraAPI(cred["email"], cred["token"], cred["url"])


# ========== ADAPTADORES ==========
def _normalizar(issue: dict) -> dict:
    """Converte a issue do Jira para um dicionário simples usado no painel."""
    f = issue.get("fields", {})
    loja = f.get("customfield_14954") or {}
    estado = f.get("customfield_11948") or {}
    return {
        "key": issue.get("key", "--"),
        "status": (f.get("status") or {}).get("name", "--"),
        "loja": loja.get("value", "Loja"),
        "pdv": f.get("customfield_14829") or "--",
        "ativo": (f.get("customfield_14825") or {}).get("value", "--"),
        "problema": f.get("customfield_12374") or "--",
        "endereco": f.get("customfield_12271") or "--",
        "estado": estado.get("value", "--"),
        "cep": f.get("customfield_11993") or "--",
        "cidade": f.get("customfield_11994") or "--",
        "data_agendada": f.get("customfield_12036"),  # ISO string ou None
    }


def _dia_str(iso_dt: str | None) -> str:
    """Retorna dd/mm/aaaa a partir do campo de data agendada; se vazio, 'Sem data'."""
    if not iso_dt:
        return "Sem data"
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            d = datetime.strptime(iso_dt, fmt)
            return d.strftime("%d/%m/%Y")
        except Exception:
            pass
    return "Sem data"


# ========== CARGA DE DADOS ==========
@st.cache_data(ttl=120, show_spinner=True)
def carregar() -> dict[str, list[dict]]:
    cli = jira_client()

    def _buscar(jql: str) -> list[dict]:
        # Espera que seu JiraAPI tenha método buscar_chamados(jql, fields)
        raw = cli.buscar_chamados(jql, FIELDS)  # retorna issues (list)
        return [_normalizar(it) for it in raw]

    return {
        "agendamento": _buscar(JQLS["agendamento"]),
        "agendado": _buscar(JQLS["agendado"]),
        "tec": _buscar(JQLS["tec"]),
    }


# ========== UI AUXILIARES ==========
def _grupo_por_dia_e_loja(items: list[dict]) -> dict[str, dict[str, list[dict]]]:
    """{dia: {loja: [chamados]}}"""
    g: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for ch in items:
        dia = _dia_str(ch.get("data_agendada"))
        g[dia][ch["loja"]].append(ch)
    return g


def _badge(texto: str, cor_bg: str, cor_tx: str = "#00131B"):
    return f"<span style='background:{cor_bg};padding:4px 8px;border-radius:8px;font-weight:600;font-size:12px;color:{cor_tx};'>{texto}</span>"


def _expander_titulo(loja: str, chamados: list[dict]) -> str:
    qtd = len(chamados)
    qtd_pdv = sum(1 for c in chamados if str(c.get("pdv")).strip() not in ("", "--") and str(c.get("pdv")).isdigit() and int(c.get("pdv")) >= 300)
    qtd_desktop = qtd - qtd_pdv
    return f"{loja} — {qtd} chamado(s) ({qtd_pdv} PDV · {qtd_desktop} Desktop)"


def _bloco_loja(loja: str, chamados: list[dict]):
    dups = verificar_duplicidade(chamados)
    if dups:
        st.warning(f"⚠️ Possíveis duplicidades: {', '.join([f'PDV {p or \"--\"} / ATIVO {a or \"--\"}' for (p, a) in dups])}")

    st.markdown("**FSAs:** " + ", ".join(c["key"] for c in chamados))
    st.code(gerar_mensagem(loja, chamados), language="text")


# ========== UI PRINCIPAL ==========
try:
    data = carregar()
except Exception as e:
    st.error(f"Falha ao carregar dados do Jira: {e}")
    st.stop()

tab_agdm, tab_agd, tab_tec = st.tabs(["AGENDAMENTO", "AGENDADO", "TEC‑CAMPO"])

with tab_agdm:
    st.caption("Chamados com status **AGENDAMENTO**")
    grupos = _grupo_por_dia_e_loja(data["agendamento"])
    for dia in sorted(grupos.keys(), key=lambda s: datetime.strptime(s, "%d/%m/%Y") if s != "Sem data" else datetime.max):
        lojas = grupos[dia]
        header = f"{dia} — {sum(len(v) for v in lojas.values())} chamado(s) " + _badge("PENDENTE", "#FFB84D")
        with st.expander(header, expanded=False):
            for loja, itens in sorted(lojas.items()):
                with st.container(border=True):
                    st.markdown(f"##### { _expander_titulo(loja, itens) }")
                    _bloco_loja(loja, itens)

with tab_agd:
    st.caption("Chamados com status **AGENDADO**")
    grupos = _grupo_por_dia_e_loja(data["agendado"])
    for dia in sorted(grupos.keys(), key=lambda s: datetime.strptime(s, "%d/%m/%Y") if s != "Sem data" else datetime.max):
        lojas = grupos[dia]
        header = f"{dia} — {sum(len(v) for v in lojas.values())} chamado(s) " + _badge("AGENDADO", "#D6E8FF")
        with st.expander(header, expanded=False):
            for loja, itens in sorted(lojas.items()):
                with st.container(border=True):
                    st.markdown(f"##### { _expander_titulo(loja, itens) }")
                    _bloco_loja(loja, itens)

with tab_tec:
    st.caption("Chamados com status **TEC‑CAMPO**")
    grupos = _grupo_por_dia_e_loja(data["tec"])
    for dia in sorted(grupos.keys(), key=lambda s: datetime.strptime(s, "%d/%m/%Y") if s != "Sem data" else datetime.max):
        lojas = grupos[dia]
        header = f"{dia} — {sum(len(v) for v in lojas.values())} chamado(s) " + _badge("TEC-CAMPO", "#FCF3F7")
        with st.expander(header, expanded=False):
            for loja, itens in sorted(lojas.items()):
                with st.container(border=True):
                    st.markdown(f"##### { _expander_titulo(loja, itens) }")
                    _bloco_loja(loja, itens)

st.caption(f"Última atualização: {datetime.now():%d/%m/%Y %H:%M:%S}")
