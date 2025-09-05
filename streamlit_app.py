# streamlit_app.py
# -----------------
# Painel Field Service (Jira) + Heatmap gratuito (Nominatim/OSM)
# ✅ /rest/api/3/search/jql com payload correto: queries[].jql + fields no topo
# ✅ Auto-refresh opcional: tenta streamlit_autorefresh; se falhar, usa meta refresh
# ✅ Robustez contra DF vazio / campos faltando

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
        # Fallback: meta refresh a cada 90s sem dependências externas
        st.markdown(
            """<meta http-equiv="refresh" content="90">""",
            unsafe_allow_html=True
        )
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

# ============== HELPERS JIRA ==============
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
    Normaliza resposta do /search/jql:
      {"results":[{"issues":[...], ...}]}
    Retorna {"issues":[...]} mesmo sem resultados.
    """
    if not isinstance(j, dict):
        return {"issues": []}
    res = j.get("results")
    if isinstance(res, list) and res:
        first = res[0]
        if isinstance(first, dict) and isinstance(first.get("issues"), list):
            return {"issues": first["issues"]}
    # fallback (alguns proxies devolvem "issues" direto)
    if isinstance(j.get("issues"), list):
        return {"issues": j["issues"]}
    return {"issues": []}

def jira_search_jql(jql: str, start_at: int = 0, max_results: int = 100, fields: list[str] | None = None) -> dict:
    """
    ✅ Usa SOMENTE POST /rest/api/3/search/jql (evita 410).
    ✅ Payload correto: queries[].**jql** + fields no TOPO.
    """
    base = jira_base()
    url = f"{base}/search/jql"

    body = {
        "queries": [{
            "jql": jql,           # <- CHAVE CORRETA
            "startAt": start_at,
            "maxResults": max_results,
        }]
    }
    if fields:
        body["fields"] = fields  # <- fields no topo (não dentro de queries)

    try:
        r = requests.post(url, headers=HEADERS_JSON, auth=AUTH, json=body, timeout=60)
    except Exception as e:
        return {"error": True, "status": 0, "text": f"Falha de conexão: {e}"}

    if r.status_code in (200, 201):
        return _normalize_search_response(r.json())

    # Propaga 400 (payload/JQL), 401/403 (auth/permissão), etc.
    return {"error": True, "status": r.status_code, "text": r.text}

def buscar_todos(jql: str, fields: list[str]) -> list[dict]:
    """Paginação até 1000 resultados."""
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
# Se ainda der 400, teste progressivamente: 'ORDER BY created DESC' -> 'project = FSA' -> adicionar status.
JQL_ALL = 'project = FSA AND status in ("AGENDAMENTO","Agendado","TEC-CAMPO") ORDER BY created DESC'
issues_raw = buscar_todos(JQL_ALL, FIELDS)

parsed = [parse_issue(i) for i in issues_raw]
df = pd.DataFrame(parsed)

# Garante colunas (evita KeyError em DF vazio)
for col in EXPECTED_COLS:
    if col not in df.columns:
        df[col] = pd.Series(dtype="object")

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
