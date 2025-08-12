# streamlit_app.py
# -*- coding: utf-8 -*-
import os
from datetime import datetime
from typing import Dict, List, Tuple

import streamlit as st

from utils.jira_api import JiraAPI
from utils.messages import (
    gerar_mensagem,
    verificar_duplicidade,
    ISO_DESKTOP_URL,
    ISO_PDV_URL,
    RAT_URL,
)

# ====== tenta importar streamlit-sortables (várias versões) ======
sort_items_v031 = None
sort_items_legacy = None
try:
    from streamlit_sortables import sort_items as _sort_items_candidate
    sort_items_v031 = _sort_items_candidate
except Exception:
    pass
if sort_items_v031 is None:
    try:
        from streamlit_sortables import sort_items as _sort_items_legacy
        sort_items_legacy = _sort_items_legacy
    except Exception:
        pass

st.set_page_config(page_title="Painel Field Service", layout="wide", page_icon="📱")

# ====== tema / badges ======
BADGES = {
    "PENDENTE":  {"bg": "#FFB84D", "fg": "#261A00"},
    "AGENDADO":  {"bg": "#45D19F", "fg": "#00130D"},
    "TEC-CAMPO": {"bg": "#DCF3FF", "fg": "#00131B"},
}
def badge(texto: str) -> str:
    b = BADGES.get(texto.upper(), {"bg": "#EEE", "fg": "#111"})
    return (
        f"<span style='background:{b['bg']};padding:4px 8px;border-radius:8px;"
        f"font-weight:600;font-size:12px;color:{b['fg']};'>{texto}</span>"
    )

CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "30"))

JQLS = {
    "pend": 'project = FSA AND status = "AGENDAMENTO"',
    "agend": 'project = FSA AND status = "AGENDADO"',
    "tec": 'project = FSA AND status = "TEC-CAMPO"',
}

FIELDS = (
    "summary,customfield_14954,customfield_14829,customfield_14825,customfield_12374,"
    "customfield_12271,customfield_11993,customfield_11994,customfield_11948,"
    "customfield_12036,customfield_12279,status"
)

jira = JiraAPI(st.secrets["EMAIL"], st.secrets["API_TOKEN"], "https://delfia.atlassian.net")

@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _carregar_raw() -> Dict[str, list]:
    return {
        "pend": jira.buscar_chamados(JQLS["pend"], FIELDS),
        "agend": jira.buscar_chamados(JQLS["agend"], FIELDS),
        "tec": jira.buscar_chamados(JQLS["tec"], FIELDS),
    }

def _is_desktop(pdv, ativo) -> bool:
    pdv_str, ativo_str = str(pdv or "").strip(), str(ativo or "").lower()
    return pdv_str == "300" or "desktop" in ativo_str

def _agrupar_por_loja(issues: list) -> Dict[str, list]:
    return jira.agrupar_chamados(issues)

def _contar_pdv_desktop(detalhes: list) -> Tuple[int, int]:
    pdv = desk = 0
    for d in detalhes:
        if _is_desktop(d.get("pdv"), d.get("ativo")):
            desk += 1
        else:
            pdv += 1
    return pdv, desk

def _search_filter(chave: str, detalhes: list) -> list:
    if not chave:
        return detalhes
    c = chave.lower()
    out = []
    for d in detalhes:
        txt = " ".join(str(v) for v in d.values() if v is not None).lower()
        if c in txt:
            out.append(d)
    return out

def _render_header(title: str, status_nome: str, qtd: int):
    colA, colB = st.columns([0.75, 0.25])
    with colA:
        st.subheader(f"{title} ({qtd})")
    with colB:
        st.markdown(badge(status_nome), unsafe_allow_html=True)

def _expander_titulo(loja: str, detalhes: list) -> str:
    qtd = len(detalhes)
    q_pdv, q_desktop = _contar_pdv_desktop(detalhes)
    return f"{loja} — {qtd} chamado(s) ({q_pdv} PDV · {q_desktop} Desktop)"

# ============== KANBAN helpers (compat de versões) ==================
def _containers_payload(col1: List[str], col2: List[str], col3: List[str]) -> List[Dict]:
    """
    Formato que o streamlit-sortables (multi_containers=True) espera:
    [
      {'header': 'AGENDAMENTO', 'items': [...]},
      {'header': 'AGENDADO',    'items': [...]},
      {'header': 'TEC-CAMPO',   'items': [...]},
    ]
    """
    return [
        {"header": "AGENDAMENTO", "items": col1},
        {"header": "AGENDADO",    "items": col2},
        {"header": "TEC-CAMPO",   "items": col3},
    ]

def _extract_items_from_containers(sorted_payload: List[Dict]) -> Tuple[List[str], List[str], List[str]]:
    if not isinstance(sorted_payload, (list, tuple)) or len(sorted_payload) != 3:
        return [], [], []
    a = list(sorted_payload[0].get("items", []))
    b = list(sorted_payload[1].get("items", []))
    c = list(sorted_payload[2].get("items", []))
    return a, b, c

def _sort_three_columns(col1: List[str], col2: List[str], col3: List[str], styles: dict):
    """
    Tenta as diferentes assinaturas do componente:
      1) sort_items(payload_multi, multi_containers=True, direction='vertical', styles=..., key=...)
      2) sort_items(payload_multi, multi_containers=True, direction='vertical', key=...)
      3) sort_items([col1, col2, col3])  # legado (uma versão bem antiga)
    Retorna sempre (list[str], list[str], list[str]).
    """
    payload_multi = _containers_payload(col1, col2, col3)

    if sort_items_v031:
        # tenta com styles
        try:
            res = sort_items_v031(
                payload_multi,
                multi_containers=True,
                direction="vertical",
                styles=styles,
                key="kanban",
            )
            a, b, c = _extract_items_from_containers(res)
            if a or b or c:
                return a, b, c
        except TypeError:
            pass
        # tenta sem styles
        try:
            res = sort_items_v031(
                payload_multi,
                multi_containers=True,
                direction="vertical",
                key="kanban",
            )
            a, b, c = _extract_items_from_containers(res)
            if a or b or c:
                return a, b, c
        except TypeError:
            pass
        # fallback bem antigo: listas simples
        try:
            res = sort_items_v031([col1, col2, col3])
            if isinstance(res, (list, tuple)) and len(res) == 3:
                return list(res[0]), list(res[1]), list(res[2])
        except Exception:
            pass

    if sort_items_legacy:
        try:
            res = sort_items_legacy([col1, col2, col3])
            if isinstance(res, (list, tuple)) and len(res) == 3:
                return list(res[0]), list(res[1]), list(res[2])
        except Exception:
            pass

    # Nada deu: devolve original
    return col1, col2, col3

# ====== session / topo ======
if "mudancas_pendentes" not in st.session_state:
    st.session_state.mudancas_pendentes = {}
if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = None

top_cols = st.columns([0.15, 0.2, 0.65])
with top_cols[0]:
    if st.button("🔄 Atualizar agora"):
        st.cache_data.clear()
        st.session_state.last_refresh = datetime.now()
        (getattr(st, "rerun", getattr(st, "experimental_rerun", lambda: None)))()
with top_cols[1]:
    st.caption(f"Último refresh: {st.session_state.last_refresh or '—'}")

# ====== carrega dados ======
raw = _carregar_raw()
grp_pend = _agrupar_por_loja(raw["pend"])
grp_agnd = _agrupar_por_loja(raw["agend"])
grp_tec  = _agrupar_por_loja(raw["tec"])

# ====== sidebar filtro global ======
with st.sidebar:
    filtro_global = st.text_input("Filtro global (FSA, Loja, PDV, Ativo…)", "").strip()

# ====== bloco reutilizável ======
def _search_local(filtro_local: str, detalhes: list) -> list:
    return _search_filter(filtro_local, detalhes) if filtro_local else detalhes

def bloco_por_loja(status_nome: str, loja: str, detalhes_raw: list):
    colf1, colf2, colf3 = st.columns([0.4, 0.3, 0.3])
    with colf1:
        filtro = st.text_input(f"Filtro {loja}:", value="", key=f"filtro-{status_nome}-{loja}")
    with colf2:
        only_pdv = st.toggle("Somente PDV", value=False, key=f"pdv-{status_nome}-{loja}")
    with colf3:
        only_desk = st.toggle("Somente Desktop", value=False, key=f"desk-{status_nome}-{loja}")

    # aplica filtro global + local
    detalhes = detalhes_raw
    if filtro_global:
        detalhes = _search_filter(filtro_global, detalhes)
    detalhes = _search_local(filtro, detalhes)
    if only_pdv:
        detalhes = [d for d in detalhes if not _is_desktop(d.get("pdv"), d.get("ativo"))]
    if only_desk:
        detalhes = [d for d in detalhes if _is_desktop(d.get("pdv"), d.get("ativo"))]

    st.markdown("**FSAs:** " + (", ".join(d["key"] for d in detalhes) if detalhes else "_Nenhum FSA._"))
    st.code(gerar_mensagem(loja, detalhes), language="text")

def _render_grupo(titulo: str, status_nome: str, grupo: Dict[str, list], tab_key: str):
    total = sum(len(v) for v in grupo.values())
    _render_header(titulo, status_nome, total)
    if not grupo:
        st.info(f"Nenhum chamado em {status_nome}.")
        return
    for loja, detalhes in sorted(grupo.items()):
        with st.expander(_expander_titulo(loja, detalhes), expanded=False):
            bloco_por_loja(tab_key, loja, detalhes)

# ====== TABS ======
tab1, tab2, tab3, tab4 = st.tabs(["PENDENTES", "AGENDADOS", "TEC-CAMPO", "KANBAN (arrastar & soltar)"])

with tab1:
    _render_grupo("Chamados PENDENTES", "PENDENTE", grp_pend, "pendentes")

with tab2:
    _render_grupo("Chamados AGENDADOS", "AGENDADO", grp_agnd, "agendados")

with tab3:
    _render_grupo("Chamados TEC‑CAMPO", "TEC-CAMPO", grp_tec, "tec")

with tab4:
    st.markdown("Dica: arraste; ao finalizar, clique em **Aplicar mudanças**.")

    def keys_por_loja(grupo: Dict[str, list]) -> List[str]:
        out = []
        for loja, dets in grupo.items():
            for d in dets:
                out.append(f"{d['key']} | {loja}")
        return out

    col1_items = keys_por_loja(grp_pend)
    col2_items = keys_por_loja(grp_agnd)
    col3_items = keys_por_loja(grp_tec)

    cols = st.columns(3)
    with cols[0]: st.markdown("**AGENDAMENTO**")
    with cols[1]: st.markdown("**AGENDADO**")
    with cols[2]: st.markdown("**TEC-CAMPO**")

    styles = {
        "container": {"background": "#0B0F14", "minHeight": "280px", "padding": "8px"},
        "item": {"background": "#0D3B66", "padding": "10px", "margin": "8px",
                 "borderRadius": "8px", "color": "#fff"},
    }

    new_col1, new_col2, new_col3 = _sort_three_columns(col1_items, col2_items, col3_items, styles)

    def _col_of(item: str, c1, c2, c3) -> str:
        if item in c1: return "AGENDAMENTO"
        if item in c2: return "AGENDADO"
        if item in c3: return "TEC-CAMPO"
        return "?"

    original = {i: _col_of(i, col1_items, col2_items, col3_items) for i in (col1_items + col2_items + col3_items)}
    atual    = {i: _col_of(i, new_col1,   new_col2,   new_col3)   for i in (new_col1   + new_col2   + new_col3)}

    pendentes = {}
    for k, old in original.items():
        new = atual.get(k, old)
        if new != old and new in ("AGENDAMENTO", "AGENDADO", "TEC-CAMPO"):
            fsa_key = k.split("|")[0].strip()
            pendentes[fsa_key] = new

    st.session_state.mudancas_pendentes = pendentes

    if pendentes:
        st.warning(f"{len(pendentes)} mudança(s) pendente(s).")
    else:
        st.info("Nenhuma mudança pendente.")

    if st.button("Aplicar mudanças", type="primary", disabled=(not pendentes)):
        ok, falhas = 0, []
        for issue_key, novo_status in pendentes.items():
            try:
                trans = jira.get_transitions(issue_key)
                tid = next(
                    (t["id"] for t in trans if (t.get("to", {}) or {}).get("name", "").upper() == novo_status.upper()),
                    None
                )
                if not tid:
                    falhas.append(f"{issue_key}: transição para '{novo_status}' não disponível")
                    continue
                r = jira.transicionar_status(issue_key, tid)
                if r.status_code == 204:
                    ok += 1
                else:
                    falhas.append(f"{issue_key}: HTTP {r.status_code}")
            except Exception as e:
                falhas.append(f"{issue_key}: {e}")

        if ok: st.success(f"{ok} chamado(s) atualizado(s).")
        if falhas:
            st.error("Algumas falharam:")
            st.code("\n".join(falhas))

        st.cache_data.clear()
        (getattr(st, "rerun", getattr(st, "experimental_rerun", lambda: None)))()

st.markdown("---")
st.caption(f"Última atualização: {datetime.now():%d/%m/%Y %H:%M:%S}")
