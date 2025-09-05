# streamlit_app.py
# -----------------
# Painel Field Service (Jira) + Heatmap gratuito (Nominatim/OSM)
# Cliente Jira resiliente a diferenças de payload entre /search/jql e /search
# Mostra diagnóstico quando houver erro de payload (400) ou remoção (410)

from __future__ import annotations
import os
import time
from datetime import datetime, timezone

import requests
from requests.auth import HTTPBasicAuth
import pandas as pd
import streamlit as st

# ============== CONFIG PÁGINA ==============
st.set_page_config(page_title="Painel Field Service", layout="wide", page_icon="📟")

# ============== AUTO-REFRESH (tolerante) ==============
if "auto_refresh_on" not in st.session_state:
    st.session_state.auto_refresh_on = True

with st.sidebar:
    st.markdown("### ⚙️ Preferências")
    st.checkbox(
        "🔄 Auto-refresh a cada 90s",
        value=st.session_state.auto_refresh_on,
        key="auto_refresh_on",
        help="Desligue para operar sem recarregar a página."
    )
    st.checkbox(
        "🛡️ Modo compatibilidade (multi-tentativa em /search*/payload)",
        value=st.session_state.get("compat_mode", True),
        key="compat_mode",
        help="Se ligado, o app tenta formatos alternativos quando 400/410 ocorrer."
    )

# Tenta usar o componente; se falhar, usa META refresh
if st.session_state.auto_refresh_on:
    used_component = False
    try:
        from streamlit_autorefresh import st_autorefresh
        st_autorefresh(interval=90_000, key="__tick")
        used_component = True
    except Exception:
        used_component = False
    if not used_component:
        st.markdown("""<meta http-equiv="refresh" content="90">""", unsafe_allow_html=True)
        st.caption("⏱️ Auto-refresh por fallback (meta refresh).")

# ============== SEGREDOS / CREDENCIAIS ==============
EMAIL = st.secrets.get("EMAIL", "")
API_TOKEN = st.secrets.get("API_TOKEN", "")
SITE_URL = st.secrets.get("SITE_URL", "").rstrip("/")
USE_EX_API = bool(st.secrets.get("USE_EX_API", True))
CLOUD_ID = st.secrets.get("CLOUD_ID", "")

if not EMAIL or not API_TOKEN:
    st.error("Configure EMAIL e API_TOKEN em `.streamlit/secrets.toml`.")
    st.stop()

HEADERS_JSON = {"Accept": "application/json", "Content-Type": "application/json"}
AUTH = HTTPBasicAuth(EMAIL, API_TOKEN)

# Campos do Jira a buscar
FIELDS = [
    "summary",
    "status",
    "customfield_14954",  # Loja
    "customfield_14829",  # PDV
    "customfield_14825",  # Ativo
    "customfield_12374",  # Problema
    "customfield_12271",  # Endereço
    "customfield_11993",  # CEP
    "customfield_11994",  # Cidade
    "customfield_11948",  # Estado
    "customfield_12036",  # Data Agendada (datetime)
    "customfield_12279",  # Técnicos (doc)
]
EXPECTED_COLS = [
    "key","loja","pdv","ativo","problema","endereco","cep","cidade","estado",
    "data_agendada","status"
]

# =========================
# HELPERS JIRA
# =========================
def jira_base() -> str:
    """
    Retorna a base correta da API v3:
      - EX API: https://api.atlassian.com/ex/jira/{CLOUD_ID}/rest/api/3
      - Site local: https://{site}.atlassian.net/rest/api/3
    """
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

def _normalize_search_response(j: dict) -> dict:
    """
    Normaliza resposta de /search/jql (results[0].issues) ou /search (issues).
    Retorna {"issues":[...]} ou {"issues":[]}.
    """
    if not isinstance(j, dict):
        return {"issues": []}
    if "results" in j and isinstance(j["results"], list) and j["results"]:
        first = j["results"][0]
        if isinstance(first, dict) and isinstance(first.get("issues"), list):
            return {"issues": first["issues"]}
    if isinstance(j.get("issues"), list):
        return {"issues": j["issues"]}
    return {"issues": []}

# Guardamos último diagnóstico de chamada:
_last_diag = st.session_state.get("_last_diag", None)

def _record_diag(method: str, url: str, body_or_params, status: int, text: str):
    global _last_diag
    _last_diag = {
        "method": method,
        "url": url,
        "payload": body_or_params,
        "status": status,
        "response": text[:1000],  # evita texto gigante
    }
    st.session_state["_last_diag"] = _last_diag

def jira_search_resilient(jql: str, start_at: int = 0, max_results: int = 100, fields: list[str] | None = None) -> dict:
    """
    Estratégia:
      1) POST /search/jql com queries[].jql + fields no topo
      2) POST /search/jql com queries[].query + fields no topo
      3) POST /search      com {"jql": "...", "fields":[...]} (fallback)
    Retorna {"issues":[...]} ou {"error":True, "status":..., "text":...}
    """
    base = jira_base()

    # 1) /search/jql com queries[].jql
    url1 = f"{base}/search/jql"
    body1 = {
        "queries": [{
            "jql": jql,
            "startAt": start_at,
            "maxResults": max_results,
        }]
    }
    if fields:
        body1["fields"] = fields
    try:
        r1 = requests.post(url1, headers=HEADERS_JSON, auth=AUTH, json=body1, timeout=60)
        _record_diag("POST", url1, body1, r1.status_code, r1.text)
        if r1.status_code in (200, 201):
            return _normalize_search_response(r1.json())
        # Se não estamos no modo compatibilidade, já retorna o erro
        if not st.session_state.get("compat_mode", True):
            return {"error": True, "status": r1.status_code, "text": r1.text}
    except Exception as e:
        _record_diag("POST", url1, body1, 0, f"Falha de conexão: {e}")
        if not st.session_state.get("compat_mode", True):
            return {"error": True, "status": 0, "text": str(e)}

    # 2) /search/jql com queries[].query
    url2 = f"{base}/search/jql"
    body2 = {
        "queries": [{
            "query": jql,
            "startAt": start_at,
            "maxResults": max_results,
        }]
    }
    if fields:
        body2["fields"] = fields
    try:
        r2 = requests.post(url2, headers=HEADERS_JSON, auth=AUTH, json=body2, timeout=60)
        _record_diag("POST", url2, body2, r2.status_code, r2.text)
        if r2.status_code in (200, 201):
            return _normalize_search_response(r2.json())
        if not st.session_state.get("compat_mode", True):
            return {"error": True, "status": r2.status_code, "text": r2.text}
    except Exception as e:
        _record_diag("POST", url2, body2, 0, f"Falha de conexão: {e}")
        if not st.session_state.get("compat_mode", True):
            return {"error": True, "status": 0, "text": str(e)}

    # 3) /search (fallback “clássico”) com body direto
    url3 = f"{base}/search"
    body3 = {
        "jql": jql,
        "startAt": start_at,
        "maxResults": max_results,
    }
    if fields:
        body3["fields"] = fields
    try:
        r3 = requests.post(url3, headers=HEADERS_JSON, auth=AUTH, json=body3, timeout=60)
        _record_diag("POST", url3, body3, r3.status_code, r3.text)
        if r3.status_code in (200, 201):
            return _normalize_search_response(r3.json())
        # 410 (removido) ou outro — retorna erro final
        return {"error": True, "status": r3.status_code, "text": r3.text}
    except Exception as e:
        _record_diag("POST", url3, body3, 0, f"Falha de conexão: {e}")
        return {"error": True, "status": 0, "text": str(e)}

def buscar_todos(jql: str, fields: list[str]) -> list[dict]:
    """Paginação até 1000 resultados, com cliente resiliente."""
    issues = []
    start = 0
    while True:
        data = jira_search_resilient(jql, start_at=start, max_results=100, fields=fields)
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
    data_fmt = "--"
    if data_ag:
        try:
            data_fmt = (
                datetime.fromisoformat(data_ag.replace("Z","+00:00"))
                .astimezone(timezone.utc)
                .strftime("%d/%m/%Y %H:%M")
            )
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
        "data_agendada": data_fmt,
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

# ============== NOMINATIM (OSM) – geocodificação gratuita ==============
GEOCACHE_PATH = ".geo_cache.json"

def _load_disk_cache() -> dict:
    try:
        if os.path.exists(GEOCACHE_PATH):
            df = pd.read_json(GEOCACHE_PATH, orient="index")
            return df["coord"].to_dict()
    except Exception:
        pass
    return {}

def _save_disk_cache(d: dict):
    try:
        df = pd.DataFrame.from_dict(d, orient="index", columns=["coord"])
        df.to_json(GEOCACHE_PATH, orient="index")
    except Exception:
        pass

@st.cache_data(show_spinner=False, ttl=86400)
def cache24h() -> dict:
    return {}

NOMINATIM_HEADERS = {
    "User-Agent": "FieldService-Streamlit/1.0 (contact: ops@example.com)"
}

def geocode_nominatim(query: str):
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

# ============== UI – cabeçalho ==============
st.title("📟 Painel Field Service")
c1, c2 = st.columns([2,1])
with c1:
    st.caption("Chamados nos status: **AGENDAMENTO • Agendado • TEC-CAMPO**")
with c2:
    st.caption(f"Última atualização: {datetime.now():%d/%m/%Y %H:%M:%S}")

# ============== JQL e busca ==============
# Ajuste os nomes exatos do projeto/status conforme aparecem na sua instância Jira.
JQL_ALL = 'project = FSA AND status in ("AGENDAMENTO","Agendado","TEC-CAMPO") ORDER BY created DESC'
issues_raw = buscar_todos(JQL_ALL, FIELDS)

parsed = [parse_issue(i) for i in issues_raw]
df = pd.DataFrame(parsed)

# Garante colunas (evita KeyError em DF vazio)
for col in EXPECTED_COLS:
    if col not in df.columns:
        df[col] = pd.Series(dtype="object")

# Mostra diagnóstico quando não há resultados e houve erro recente
if df.empty and st.session_state.get("_last_diag"):
    with st.expander("🩺 Diagnóstico da última chamada Jira", expanded=False):
        d = st.session_state["_last_diag"]
        st.code(
            f"METHOD: {d['method']}\nURL: {d['url']}\n\nPAYLOAD:\n{d['payload']}\n\nSTATUS: {d['status']}\nRESPONSE:\n{d['response']}",
            language="text"
        )
        st.caption("Dica: teste JQL simples como `ORDER BY created DESC` ou apenas `project = FSA` para isolar problema de JQL.")

# Filtros por status (robustos p/ vazio)
status_upper = df["status"].astype(str).str.upper()
df_agendamento = df[status_upper == "AGENDAMENTO"]
df_agendado    = df[status_upper == "AGENDADO"]
df_teccampo    = df[status_upper == "TEC-CAMPO"]

# Lojas com 2+ chamados (todos os 3 status)
agr = df.groupby(["loja","cidade"], dropna=False)["key"].count().reset_index().rename(columns={"key":"chamados"})
hot = agr[agr["chamados"]>=2].sort_values(["chamados","loja"], ascending=[False,True])

# ============== TABS – Chamados / Visão Geral ==============
tab1, tab2 = st.tabs(["📋 Chamados", "📊 Visão Geral"])

# ---- 📋 CHAMADOS ----
with tab1:
    st.subheader("🔎 Resumo por status")
    mc1, mc2, mc3 = st.columns(3)
    mc1.metric("AGENDAMENTO", int(df_agendamento.shape[0]))
    mc2.metric("Agendado", int(df_agendado.shape[0]))
    mc3.metric("TEC-CAMPO", int(df_teccampo.shape[0]))

    st.markdown("---")

    st.markdown("### ⏳ PENDENTES de Agendamento")
    if df_agendamento.empty:
        st.info("Nenhum chamado em **AGENDAMENTO**.")
    else:
        for loja, g in df_agendamento.groupby("loja", dropna=False):
            detalhes = g.to_dict(orient="records")
            with st.expander(f"{loja} — {len(detalhes)} chamado(s)", expanded=False):
                st.code(format_msg_por_loja(str(loja), detalhes), language="text")

    st.markdown("### 📋 AGENDADOS")
    if df_agendado.empty:
        st.info("Nenhum chamado em **Agendado**.")
    else:
        df_age = df_agendado.copy()
        df_age["data_dia"] = df_age["data_agendada"].astype(str).str[:10]
        for dia, bloco in df_age.groupby("data_dia", dropna=False):
            total = bloco.shape[0]
            st.subheader(f"{dia or 'Sem data'} — {total} chamado(s)")
            for loja, g in bloco.groupby("loja", dropna=False):
                detalhes = g.to_dict(orient="records")
                with st.expander(f"{loja} — {len(detalhes)} chamado(s)", expanded=False):
                    st.markdown("**FSAs:** "+", ".join(d["key"] for d in detalhes))
                    st.code(format_msg_por_loja(str(loja), detalhes), language="text")

    st.markdown("### 🧰 TEC-CAMPO")
    if df_teccampo.empty:
        st.info("Nenhum chamado em **TEC-CAMPO**.")
    else:
        for loja, g in df_teccampo.groupby("loja", dropna=False):
            detalhes = g.to_dict(orient="records")
            with st.expander(f"{loja} — {len(detalhes)} chamado(s)", expanded=False):
                st.code(format_msg_por_loja(str(loja), detalhes), language="text")

# ---- 📊 VISÃO GERAL ----
with tab2:
    st.subheader("🏪 Lojas com 2+ chamados (AGENDAMENTO • Agendado • TEC-CAMPO)")
    with st.expander(f"🔖 {len(hot)} loja(s) com 2+ chamados — ver tabela", expanded=True):
        if hot.empty:
            st.info("Nenhuma loja com 2+ chamados.")
        else:
            st.dataframe(
                hot.rename(columns={"loja":"Loja","cidade":"Cidade","chamados":"Chamados"}),
                use_container_width=True, hide_index=True
            )

    st.markdown("### 🏆 Top 5 lojas mais críticas")
    if hot.empty:
        st.info("Sem dados para o ranking.")
    else:
        top5 = hot.head(5).reset_index(drop=True)
        cols = st.columns(len(top5))
        for i, (_,row) in enumerate(top5.iterrows()):
            with cols[i]:
                st.metric(f"{row['loja']} — {row['cidade']}", int(row["chamados"]))

    st.markdown("---")
    st.subheader("📚 Heatmap de lojas (via endereço/CEP do Jira) — gratuito (OSM/Nominatim)")

    # Lojas únicas + peso = total de chamados
    lojas_info = (
        df[["loja","cidade","estado","cep","endereco"]]
        .fillna("--")
        .drop_duplicates(subset=["loja"])
    )
    pesagem = df.groupby("loja")["key"].count().to_dict()
    lojas_unicas = []
    for _, row in lojas_info.iterrows():
        loja = str(row["loja"])
        cidade = str(row["cidade"])
        estado = str(row["estado"])
        cep = str(row["cep"])
        endereco = str(row["endereco"])
        query = cep if cep and cep != "--" else endereco
        if not query or query == "--":
            query = f"{loja}, {cidade}, {estado}, Brasil"
        else:
            query = f"{query}, {cidade}, {estado}, Brasil"
        lojas_unicas.append((loja, query, pesagem.get(row["loja"], 1)))

    with st.expander("⚙️ Configurar geocodificação", expanded=False):
        st.caption("Usa Nominatim (OpenStreetMap) com cache de 24h + cache local.")
        max_geocode = st.slider(
            "Máximo de lojas para geocodificar por execução",
            min_value=10, max_value=max(10, len(lojas_unicas)), value=min(150, len(lojas_unicas))
        )
        pause = st.slider(
            "Pausa entre chamadas (segundos)",
            min_value=0.0, max_value=2.0, value=0.5, step=0.1,
            help="Respeite a política do Nominatim."
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
                    # Reforça o “peso” no heatmap básico do st.map
                    pontos += [{"lat": lat, "lon": lon} for _ in range(max(1, int(peso)))]
                geocoded += 1
                if pause > 0:
                    time.sleep(pause)
            if pontos:
                st.map(pd.DataFrame(pontos), use_container_width=True)
            else:
                st.info("Nenhuma loja geocodificada nesta execução.")
            st.caption(f"Geocodificadas: {geocoded} / {len(lojas_unicas)} loja(s)")
    else:
        st.info("Clique em **Gerar/Atualizar mapa** para exibir o heatmap.")

st.markdown("---")
st.caption("© Field Service • " + datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
