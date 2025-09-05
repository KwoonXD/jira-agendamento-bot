# streamlit_app.py
# -----------------
# Painel Field Service (Jira) + Heatmap de lojas com geocodificação gratuita (Nominatim/OSM)
# - Toggle de auto-refresh na sidebar
# - Botão explícito para gerar/atualizar o mapa (sem reload automático)
# - Cache de geocodificação por 24h (st.cache_data) + gravação opcional em disco (fallback)
# - Seguro para campos ausentes do Jira (sem KeyError)

from __future__ import annotations
import os
import time
from datetime import datetime, timezone
from collections import defaultdict, Counter

import requests
from requests.auth import HTTPBasicAuth
import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

# =========================
# CONFIGURAÇÃO DA PÁGINA
# =========================
st.set_page_config(page_title="Painel Field Service", layout="wide", page_icon="📟")

# -------------------------
# ESTADO E AUTO-REFRESH
# -------------------------
if "auto_refresh_on" not in st.session_state:
    st.session_state.auto_refresh_on = True  # ligado por padrão

with st.sidebar:
    st.markdown("### ⚙️ Preferências")
    st.checkbox(
        "🔄 Auto-refresh a cada 90s",
        value=st.session_state.auto_refresh_on,
        key="auto_refresh_on",
        help="Desligue para evitar recarregar a página enquanto opera o painel.",
    )
    if st.session_state.auto_refresh_on:
        # tick apenas quando ligado
        st_autorefresh(interval=90_000, key="auto_refresh_tick")

# =========================
# SEGREDOS / CREDENCIAIS
# =========================
# Em .streamlit/secrets.toml:
# EMAIL="..."
# API_TOKEN="..."
# SITE_URL="https://sua-instancia.atlassian.net"
# USE_EX_API=true
# CLOUD_ID="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
EMAIL = st.secrets.get("EMAIL", "")
API_TOKEN = st.secrets.get("API_TOKEN", "")
SITE_URL = st.secrets.get("SITE_URL", "").rstrip("/")
USE_EX_API = bool(st.secrets.get("USE_EX_API", True))
CLOUD_ID = st.secrets.get("CLOUD_ID", "")

if not EMAIL or not API_TOKEN:
    st.error("Configure EMAIL e API_TOKEN em `.streamlit/secrets.toml`.")
    st.stop()

# =========================
# CONSTANTES/JIRA
# =========================
HEADERS_JSON = {"Accept": "application/json", "Content-Type": "application/json"}
AUTH = HTTPBasicAuth(EMAIL, API_TOKEN)

# campos utilizados nas telas (ajuste conforme seu Jira)
FIELDS = [
    "summary",
    "status",
    "customfield_14954",  # Loja (Dropdown)
    "customfield_14829",  # PDV
    "customfield_14825",  # Ativo (Dropdown)
    "customfield_12374",  # Problema
    "customfield_12271",  # Endereço
    "customfield_11993",  # CEP
    "customfield_11994",  # Cidade
    "customfield_11948",  # Estado (Dropdown)
    "customfield_12036",  # Data Agendada (datetime)
    "customfield_12279",  # Técnicos (doc)
]

STATUSES_INTERESSADOS = ["AGENDAMENTO", "Agendado", "TEC-CAMPO"]  # respeita maiúsc/min.

# =========================
# HELPERS JIRA
# =========================
def jira_base() -> str:
    if USE_EX_API:
        if not CLOUD_ID:
            st.error("USE_EX_API=true, mas CLOUD_ID não foi definido em secrets.")
            st.stop()
        return f"https://api.atlassian.com/ex/jira/{CLOUD_ID}/rest/api/3"
    else:
        if not SITE_URL:
            st.error("USE_EX_API=false, mas SITE_URL não foi definido em secrets.")
            st.stop()
        return f"{SITE_URL}/rest/api/3"

def jira_search_jql(jql: str, start_at: int = 0, max_results: int = 100, fields: list[str] | None = None) -> dict:
    base = jira_base()
    if USE_EX_API:
        # endpoint moderno aceita POST em /search/jql
        url = f"{base}/search/jql"
        payload = {
            "jql": jql,
            "startAt": start_at,
            "maxResults": max_results,
        }
        if fields:
            payload["fields"] = fields
        r = requests.post(url, headers=HEADERS_JSON, auth=AUTH, json=payload, timeout=60)
    else:
        # clássico: GET /search com params
        url = f"{base}/search"
        params = {
            "jql": jql,
            "startAt": start_at,
            "maxResults": max_results,
        }
        if fields:
            params["fields"] = ",".join(fields)
        r = requests.get(url, headers=HEADERS_JSON, auth=AUTH, params=params, timeout=60)

    if r.status_code not in (200, 201):
        return {"error": True, "status": r.status_code, "text": r.text}
    return r.json()

def buscar_todos(jql: str, fields: list[str]) -> list[dict]:
    """Paginação até 1000 por segurança."""
    issues = []
    start = 0
    while True:
        data = jira_search_jql(jql, start_at=start, max_results=100, fields=fields)
        if isinstance(data, dict) and data.get("error"):
            st.warning(f"Falha JQL ({data['status']}): {data.get('text','')}")
            return issues
        lote = data.get("issues", [])
        issues.extend(lote)
        if len(lote) < 100 or len(issues) >= 1000:
            return issues
        start += 100

def field_val(f: dict, key: str, default="--"):
    v = f.get(key)
    if isinstance(v, dict):
        # pega 'value' se houver (Dropdowns) ou 'text' se doc
        return v.get("value") or v.get("text") or default
    return v if (v not in (None, "")) else default

def parse_issue(issue: dict) -> dict:
    f = issue.get("fields", {}) or {}
    loja = field_val(f, "customfield_14954", "Loja Desconhecida")
    pdv = field_val(f, "customfield_14829", "--")
    ativo = field_val(f, "customfield_14825", "--")
    problema = field_val(f, "customfield_12374", "--")
    endereco = field_val(f, "customfield_12271", "--")
    cep = field_val(f, "customfield_11993", "--")
    cidade = field_val(f, "customfield_11994", "--")
    estado = field_val(f, "customfield_11948", "--")
    data_ag = f.get("customfield_12036")
    data_fmt = None
    if data_ag:
        try:
            data_fmt = datetime.fromisoformat(data_ag.replace("Z","+00:00")).astimezone(timezone.utc).strftime("%d/%m/%Y %H:%M")
        except Exception:
            data_fmt = data_ag
    status_name = (f.get("status") or {}).get("name", "--")
    return {
        "key": issue.get("key"),
        "loja": loja,
        "pdv": pdv,
        "ativo": ativo,
        "problema": problema,
        "endereco": endereco,
        "cep": cep,
        "cidade": cidade,
        "estado": estado,
        "data_agendada": data_fmt or "--",
        "status": status_name,
    }

def format_msg_por_loja(loja: str, chamados: list[dict]) -> str:
    blocos = []
    endereco_info = None
    for ch in chamados:
        linhas = [
            f"*{ch['key']}*",
            f"Loja: {loja}",
            f"Status: {ch['status']}",
            f"PDV: {ch['pdv']}",
            f"*ATIVO: {ch['ativo']}*",
            f"Problema: {ch['problema']}",
            "***"
        ]
        blocos.append("\n".join(linhas))
        endereco_info = (ch["endereco"], ch["estado"], ch["cep"], ch["cidade"])
    if endereco_info:
        blocos.append("\n".join([
            f"Endereço: {endereco_info[0]}",
            f"Estado: {endereco_info[1]}",
            f"CEP: {endereco_info[2]}",
            f"Cidade: {endereco_info[3]}",
        ]))
    return "\n\n".join(blocos)

# =========================
# Nominatim (OSM) – geocodificação gratuita
# =========================

# cache leve em disco (opcional) + cache em memória/servidor por 24h
GEOCACHE_PATH = ".geo_cache.json"

def _load_disk_cache() -> dict:
    try:
        if os.path.exists(GEOCACHE_PATH):
            return pd.read_json(GEOCACHE_PATH, orient="index").to_dict()["coord"]
    except Exception:
        pass
    return {}

def _save_disk_cache(d: dict):
    try:
        # salva como DataFrame para simplicidade
        df = pd.DataFrame.from_dict(d, orient="index", columns=["coord"])
        df.to_json(GEOCACHE_PATH, orient="index")
    except Exception:
        pass

@st.cache_data(show_spinner=False, ttl=86400)
def cache24h() -> dict:
    # cache em memória/processo do Streamlit
    return {}

# Recomendação do serviço: fornecer User-Agent identificável
NOMINATIM_HEADERS = {
    "User-Agent": "FieldService-Streamlit/1.0 (contact: ops@example.com)"
}

def geocode_nominatim(query: str) -> tuple[float,float] | None:
    """Geocodifica usando Nominatim com caches (memória+disco)."""
    mem = cache24h()
    disk = _load_disk_cache()
    if query in mem:
        return mem[query]
    if query in disk:
        mem[query] = disk[query]
        return disk[query]

    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": query, "format": "json", "limit": 1, "addressdetails": 0}
    try:
        r = requests.get(url, params=params, headers=NOMINATIM_HEADERS, timeout=30)
        if r.status_code == 200 and r.json():
            j = r.json()[0]
            coord = (float(j["lat"]), float(j["lon"]))
            mem[query] = coord
            disk[query] = coord
            _save_disk_cache(disk)
            return coord
    except Exception:
        return None
    return None

# =========================
# BUSCA DOS DADOS
# =========================
st.title("📟 Painel Field Service")

# Filtros simples (poderia ser persistido)
colf1, colf2 = st.columns([2,1])
with colf1:
    st.caption("Buscando chamados nos status: **AGENDAMENTO • Agendado • TEC-CAMPO**")
with colf2:
    dt_now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    st.caption(f"Última atualização: {dt_now}")

# Monta uma JQL que pegue todos os 3 status de uma vez
jql_all = 'project = FSA AND status in ("AGENDAMENTO","Agendado","TEC-CAMPO") ORDER BY created DESC'
issues_raw = buscar_todos(jql_all, FIELDS)

# Normaliza
parsed = [parse_issue(i) for i in issues_raw]
df = pd.DataFrame(parsed)

# Guarda info por status
df_agendamento = df[df["status"].str.upper()=="AGENDAMENTO"]
df_agendado    = df[df["status"].str.upper()=="AGENDADO"]
df_teccampo    = df[df["status"].str.upper()=="TEC-CAMPO"]

# -------------------------
# Lojas com 2+ chamados (qualquer um dos 3 status)
# -------------------------
agr = df.groupby(["loja","cidade"])["key"].count().reset_index().rename(columns={"key":"chamados"})
hot = agr[agr["chamados"]>=2].sort_values(["chamados","loja"], ascending=[False,True])

# =========================
# TABS (Chamados primeiro, depois Visão Geral)
# =========================
tab1, tab2 = st.tabs(["📋 Chamados", "📊 Visão Geral"])

# =========================================================
# 📋 CHAMADOS (detalhamento por status + mensagens por loja)
# =========================================================
with tab1:
    st.subheader("🔎 Resumo por status")
    c1, c2, c3 = st.columns(3)
    c1.metric("AGENDAMENTO", int(df_agendamento.shape[0]))
    c2.metric("Agendado", int(df_agendado.shape[0]))
    c3.metric("TEC-CAMPO", int(df_teccampo.shape[0]))

    st.markdown("---")

    # ----- PENDENTES (AGENDAMENTO)
    st.markdown("### ⏳ Chamados **PENDENTES** de Agendamento")
    if df_agendamento.empty:
        st.info("Nenhum chamado em **AGENDAMENTO**.")
    else:
        for loja, g in df_agendamento.groupby("loja"):
            detalhes = g.to_dict(orient="records")
            with st.expander(f"{loja} — {len(detalhes)} chamado(s)", expanded=False):
                st.code(format_msg_por_loja(loja, detalhes), language="text")

    # ----- AGENDADOS
    st.markdown("### 📋 Chamados **AGENDADOS**")
    if df_agendado.empty:
        st.info("Nenhum chamado em **Agendado**.")
    else:
        # agrupar por data (texto) e loja
        df_age = df_agendado.copy()
        # cria coluna data simples (dd/mm/aaaa) a partir do campo já formatado
        df_age["data_dia"] = df_age["data_agendada"].str[:10]
        for dia, bloco in df_age.groupby("data_dia"):
            total = bloco.shape[0]
            st.subheader(f"{dia or 'Sem data'} — {total} chamado(s)")
            for loja, g in bloco.groupby("loja"):
                detalhes = g.to_dict(orient="records")
                with st.expander(f"{loja} — {len(detalhes)} chamado(s)", expanded=False):
                    st.markdown("**FSAs:** "+", ".join(d["key"] for d in detalhes))
                    st.code(format_msg_por_loja(loja, detalhes), language="text")

    # ----- TEC-CAMPO
    st.markdown("### 🧰 Chamados **TEC-CAMPO**")
    if df_teccampo.empty:
        st.info("Nenhum chamado em **TEC-CAMPO**.")
    else:
        for loja, g in df_teccampo.groupby("loja"):
            detalhes = g.to_dict(orient="records")
            with st.expander(f"{loja} — {len(detalhes)} chamado(s)", expanded=False):
                st.code(format_msg_por_loja(loja, detalhes), language="text")

# =========================================================
# 📊 VISÃO GERAL (hotlist, top 5, heatmap)
# =========================================================
with tab2:
    st.subheader("🏪 Lojas com 2+ chamados (AGENDAMENTO • Agendado • TEC-CAMPO)")
    with st.expander(f"🔖 {len(hot)} loja(s) com 2+ chamados — ver tabela", expanded=True):
        if hot.empty:
            st.info("Nenhuma loja com 2+ chamados.")
        else:
            st.dataframe(
                hot.rename(columns={"loja":"Loja","cidade":"Cidade","chamados":"Chamados"}),
                use_container_width=True,
                hide_index=True,
            )

    # ----- TOP 5 LOJAS
    st.markdown("### 🏆 Top 5 lojas mais críticas")
    if hot.empty:
        st.info("Sem dados para o ranking.")
    else:
        top5 = hot.head(5).reset_index(drop=True)
        k1,k2,k3,k4,k5 = st.columns(5)
        cols = [k1,k2,k3,k4,k5]
        for i, (_,row) in enumerate(top5.iterrows()):
            with cols[i]:
                st.metric(f"{row['loja']} — {row['cidade']}", int(row["chamados"]), help="Chamados totais (3 status)")

    st.markdown("---")
    st.subheader("📚 Heatmap de lojas (auto, via endereço/CEP do Jira)")

    # Preparar inputs para geocodificação
    # Considera lojas únicas (com peso = número de chamados para o efeito de heat)
    lojas_info = (
        df[["loja","cidade","estado","cep","endereco"]]
        .fillna("--")
        .drop_duplicates(subset=["loja"])
    )
    # ordem de importância por volume (peso)
    pesagem = df.groupby("loja")["key"].count().to_dict()
    lojas_unicas = []
    for _, row in lojas_info.iterrows():
        loja = str(row["loja"])
        cidade = str(row["cidade"])
        estado = str(row["estado"])
        cep = str(row["cep"])
        endereco = str(row["endereco"])
        # Monta uma query progressiva
        # prioridade: CEP > Endereço + cidade/estado > loja + cidade/estado
        query = cep if cep and cep != "--" else endereco
        if not query or query == "--":
            query = f"{loja}, {cidade}, {estado}, Brasil"
        else:
            query = f"{query}, {cidade}, {estado}, Brasil"
        lojas_unicas.append((loja, query, pesagem.get(loja, 1)))

    with st.expander("⚙️ Configurar geocodificação", expanded=False):
        st.caption("Usa Nominatim (OpenStreetMap) com cache de 24h + cache em disco local.")
        max_geocode = st.slider(
            "Máximo de lojas para geocodificar por execução",
            min_value=10, max_value=max(10, len(lojas_unicas)), value=min(150, len(lojas_unicas))
        )
        pause = st.slider(
            "Pausa entre chamadas (segundos)",
            min_value=0.0, max_value=2.0, value=0.5, step=0.1,
            help="Respeite a política do Nominatim (evite alta taxa de requisições)."
        )

    run_geo = st.button("🗺️ Gerar/Atualizar mapa", type="primary")
    if run_geo and lojas_unicas:
        with st.spinner("Geocodificando endereços das lojas..."):
            pontos = []
            geocoded = 0
            for loja, query, peso in lojas_unicas[:max_geocode]:
                coords = geocode_nominatim(query)
                if coords:
                    lat, lon = coords
                    # multiplica pontos para reforçar peso no heatmap básico do st.map
                    pontos += [{"lat": lat, "lon": lon} for _ in range(max(1, int(peso)))]
                geocoded += 1
                if pause > 0:
                    time.sleep(pause)

            if pontos:
                st.map(pd.DataFrame(pontos), use_container_width=True)
            else:
                st.info("Nenhuma loja geocodificada com sucesso nesta execução.")
            st.caption(f"Geocodificadas: {geocoded} / {len(lojas_unicas)} loja(s)")
    else:
        st.info("Clique em **Gerar/Atualizar mapa** para exibir o heatmap.")

# Rodapé
st.markdown("---")
st.caption("© Field Service • Atualizado: " + datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
