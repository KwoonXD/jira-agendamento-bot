# -*- coding: utf-8 -*-
import os
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List, Tuple

import streamlit as st

# Dependências do seu projeto
from utils.jira_api import JiraAPI
from utils.messages import gerar_mensagem, verificar_duplicidade

# Opcional (arrastar-e-soltar)
# pip install streamlit-sortables==0.3.1  (recomendado)
try:
    from streamlit_sortables import sort_items as sort_items_v031  # >=0.3
except Exception:
    sort_items_v031 = None
try:
    # versões mais antigas exportavam sort_items com assinaturas diferentes
    from streamlit_sortables import sort_items as sort_items_legacy
except Exception:
    sort_items_legacy = None

# ───────────────────────────────────────────────────────────────────────────────
# CONFIGURAÇÕES GERAIS
# ───────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Painel Field Service",
    layout="wide",
    page_icon="📱",
)

# Tema/badges (cores ajustadas para casar com o seu tema escuro)
BADGES = {
    "PENDENTE": {"bg": "#FFB84D", "fg": "#261A00"},
    "AGENDADO": {"bg": "#45D19F", "fg": "#00130D"},
    "TEC-CAMPO": {"bg": "#DCF3FF", "fg": "#00131B"},
}

def badge(texto: str) -> str:
    b = BADGES.get(texto.upper(), {"bg": "#EEE", "fg": "#111"})
    # Usaremos em containers próprios, não no label do expander
    return f"<span style='background:{b['bg']};padding:4px 8px;border-radius:8px;font-weight:600;font-size:12px;color:{b['fg']};'>{texto}</span>"

# TTL do cache dos dados (ajuste para reduzir delay x frescor dos dados)
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "30"))

# JQLs principais
JQLS = {
    "pend": 'project = FSA AND status = "AGENDAMENTO"',
    "agend": 'project = FSA AND status = "AGENDADO"',
    "tec": 'project = FSA AND status = "TEC-CAMPO"',
}

# Campos que buscamos da API
FIELDS = (
    "summary,customfield_14954,customfield_14829,customfield_14825,"
    "customfield_12374,customfield_12271,customfield_11993,"
    "customfield_11994,customfield_11948,customfield_12036,customfield_12279,status"
)

# Links padrões (podem ser sobrescritos em st.secrets se quiser)
ISO_DESKTOP_URL = st.secrets.get("ISO_DESKTOP_URL", "https://drive.google.com/file/d/1GQ64blQmysK3rbM0s0Xlot89bDNAbj5L/view?usp=drive_link")
ISO_PDV_URL     = st.secrets.get("ISO_PDV_URL",     "https://drive.google.com/file/d/1vxfHUDlT3kDdMaN0HroA5Nm9_OxasTaf/view?usp=drive_link")
RAT_URL         = st.secrets.get("RAT_URL",         "https://drive.google.com/file/d/1_SG1RofIjoJLgwWYs0ya0fKlmVd74Lhn/view?usp=sharing")

# Jira credentials (via st.secrets)
jira = JiraAPI(
    st.secrets["EMAIL"],
    st.secrets["API_TOKEN"],
    "https://delfia.atlassian.net",
)

# ───────────────────────────────────────────────────────────────────────────────
# HELPERS
# ───────────────────────────────────────────────────────────────────────────────

def _is_desktop(pdv, ativo) -> bool:
    """Regra de classificação:
       - PDV == 300  => Desktop
       - ou ATIVO contém 'desktop' (case-insensitive)
    """
    pdv_str = str(pdv).strip()
    ativo_str = str(ativo or "").lower()
    return pdv_str == "300" or "desktop" in ativo_str

@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _carregar_raw() -> Dict[str, list]:
    """Busca dados crus do Jira e devolve por status."""
    pend = jira.buscar_chamados(JQLS["pend"], FIELDS)
    agnd = jira.buscar_chamados(JQLS["agend"], FIELDS)
    tec  = jira.buscar_chamados(JQLS["tec"], FIELDS)
    return {"pend": pend, "agend": agnd, "tec": tec}

def _agrupar_por_loja(issues: list) -> Dict[str, list]:
    """Usa util do projeto para compor a lista por loja já normalizada."""
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
    """Filtro global simples por texto."""
    if not chave:
        return detalhes
    c = chave.lower()
    out = []
    for d in detalhes:
        texto = " ".join(str(v) for v in d.values() if v is not None).lower()
        if c in texto:
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

# ───────────────────────────────────────────────────────────────────────────────
# KANBAN (drag & drop) — wrappers de compatibilidade
# ───────────────────────────────────────────────────────────────────────────────

def _kanban_items(keys: List[str]) -> List[dict]:
    """Formata itens no formato exigido por streamlit-sortables >=0.3."""
    return [{"header": k, "index": k} for k in keys]

def _sort_three_columns(col1: List[str], col2: List[str], col3: List[str], styles: dict):
    """Compatibilidade entre versões do streamlit-sortables."""
    items = [_kanban_items(col1), _kanban_items(col2), _kanban_items(col3)]
    # 1) Nova (>=0.3.x)
    if sort_items_v031:
        return sort_items_v031(
            items,
            multi_containers=True,
            direction="vertical",
            styles=styles,
            key="kanban"
        )
    # 2) Antigas (sem styles/multi_containers)
    if sort_items_legacy:
        # versões antigas esperavam list[str] por coluna e retornavam tupla
        res = sort_items_legacy([col1, col2, col3])
        # normaliza pra mesmo formato de retorno: list[list[str]]
        if isinstance(res, (list, tuple)) and len(res) == 3:
            return list(res)
    # 3) Fallback: sem mover nada
    return [col1, col2, col3]

# ───────────────────────────────────────────────────────────────────────────────
# ESTADO DE SESSÃO
# ───────────────────────────────────────────────────────────────────────────────

if "mudancas_pendentes" not in st.session_state:
    st.session_state.mudancas_pendentes = {}  # { "FSA-123": "AGENDADO", ... }

if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = None

# Botões topo
top_cols = st.columns([0.15, 0.2, 0.65])
with top_cols[0]:
    if st.button("🔄 Atualizar agora"):
        st.cache_data.clear()
        st.session_state.last_refresh = datetime.now()
        # rerun compatível
        rr = getattr(st, "rerun", getattr(st, "experimental_rerun", None))
        if callable(rr):
            rr()
with top_cols[1]:
    st.caption(f"Último refresh: {st.session_state.last_refresh or '—'}")

# ───────────────────────────────────────────────────────────────────────────────
# CARREGA DADOS
# ───────────────────────────────────────────────────────────────────────────────

raw = _carregar_raw()
grp_pend = _agrupar_por_loja(raw["pend"])
grp_agnd = _agrupar_por_loja(raw["agend"])
grp_tec  = _agrupar_por_loja(raw["tec"])

# ───────────────────────────────────────────────────────────────────────────────
# TABS
# ───────────────────────────────────────────────────────────────────────────────

tab1, tab2, tab3, tab4 = st.tabs(["PENDENTES", "AGENDADOS", "TEC-CAMPO", "KANBAN (arrastar & soltar)"])

# ───────────────────────────────────────────────────────────────────────────────
# COMPONENTE REUTILIZÁVEL: bloco por loja
# ───────────────────────────────────────────────────────────────────────────────

def bloco_por_loja(status_nome: str, loja: str, detalhes_raw: list):
    # Filtros locais
    colf1, colf2, colf3 = st.columns([0.4, 0.3, 0.3])
    with colf1:
        filtro = st.text_input(f"Filtro {loja}:", value="", key=f"filtro-{status_nome}-{loja}")
    with colf2:
        only_pdv = st.toggle("Somente PDV", value=False, key=f"pdv-{status_nome}-{loja}")
    with colf3:
        only_desk = st.toggle("Somente Desktop", value=False, key=f"desk-{status_nome}-{loja}")

    detalhes = _search_filter(filtro, detalhes_raw)
    if only_pdv:
        detalhes = [d for d in detalhes if not _is_desktop(d.get("pdv"), d.get("ativo"))]
    if only_desk:
        detalhes = [d for d in detalhes if _is_desktop(d.get("pdv"), d.get("ativo"))]

    # Duplicidades e “spare” (exemplo mantém sua estrutura)
    dup_keys = []
    if detalhes:
        dups = verificar_duplicidade(detalhes)
        dup_keys = [d["key"] for d in detalhes if (d.get("pdv"), d.get("ativo")) in dups]

    # Mensagem
    st.markdown("**FSAs:** " + ", ".join(d["key"] for d in detalhes) if detalhes else "_Nenhum FSA._")
    # Gerar mensagem no formato que você vinha usando
    st.code(
        gerar_mensagem(loja, detalhes),
        language="text",
    )

# ───────────────────────────────────────────────────────────────────────────────
# ABA 1 — PENDENTES
# ───────────────────────────────────────────────────────────────────────────────
with tab1:
    total = sum(len(v) for v in grp_pend.values())
    _render_header("Chamados PENDENTES", "PENDENTE", total)

    if not grp_pend:
        st.info("Nenhum chamado em AGENDAMENTO.")
    else:
        for loja, detalhes in sorted(grp_pend.items()):
            with st.expander(_expander_titulo(loja, detalhes), expanded=False):
                bloco_por_loja("pendentes", loja, detalhes)

# ───────────────────────────────────────────────────────────────────────────────
# ABA 2 — AGENDADOS
# ───────────────────────────────────────────────────────────────────────────────
with tab2:
    total = sum(len(v) for v in grp_agnd.values())
    _render_header("Chamados AGENDADOS", "AGENDADO", total)

    if not grp_agnd:
        st.info("Nenhum chamado em AGENDADO.")
    else:
        for loja, detalhes in sorted(grp_agnd.items()):
            with st.expander(_expander_titulo(loja, detalhes), expanded=False):
                bloco_por_loja("agendados", loja, detalhes)

# ───────────────────────────────────────────────────────────────────────────────
# ABA 3 — TEC-CAMPO
# ───────────────────────────────────────────────────────────────────────────────
with tab3:
    total = sum(len(v) for v in grp_tec.values())
    _render_header("Chamados TEC‑CAMPO", "TEC-CAMPO", total)

    if not grp_tec:
        st.info("Nenhum chamado em TEC‑CAMPO.")
    else:
        for loja, detalhes in sorted(grp_tec.items()):
            with st.expander(_expander_titulo(loja, detalhes), expanded=False):
                bloco_por_loja("tec", loja, detalhes)

# ───────────────────────────────────────────────────────────────────────────────
# ABA 4 — KANBAN (Arrastar & Soltar)
# ───────────────────────────────────────────────────────────────────────────────
with tab4:
    st.markdown("Dica: arraste; ao finalizar, clique em **Aplicar mudanças**.")

    # Entradas do kanban (só chaves |loja)
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
    with cols[0]:
        st.markdown("**AGENDAMENTO**")
    with cols[1]:
        st.markdown("**AGENDADO**")
    with cols[2]:
        st.markdown("**TEC-CAMPO**")

    styles = {
        "container": {"background": "#0B0F14", "minHeight": "280px"},
        "item": {"background": "#F15B5B", "padding": "10px", "margin": "8px", "borderRadius": "8px"},
    }

    result = _sort_three_columns(col1_items, col2_items, col3_items, styles)

    if isinstance(result, list) and len(result) == 3:
        new_col1, new_col2, new_col3 = result
    else:
        new_col1, new_col2, new_col3 = col1_items, col2_items, col3_items

    # Calcula o delta (o que mudou de coluna)
    def _col_of(item: str, c1, c2, c3) -> str:
        if item in c1:
            return "AGENDAMENTO"
        if item in c2:
            return "AGENDADO"
        if item in c3:
            return "TEC-CAMPO"
        return "?"

    pendentes = {}

    original = {i: _col_of(i, col1_items, col2_items, col3_items) for i in (col1_items + col2_items + col3_items)}
    atual    = {i: _col_of(i, new_col1,   new_col2,   new_col3)   for i in (new_col1   + new_col2   + new_col3)}

    for k, old in original.items():
        new = atual.get(k, old)
        if new != old and new in ("AGENDAMENTO", "AGENDADO", "TEC-CAMPO"):
            fsa_key = k.split("|")[0].strip()  # "FSA-12345"
            pendentes[fsa_key] = new

    st.session_state.mudancas_pendentes = pendentes

    # Painel de mudanças
    if pendentes:
        st.warning(f"{len(pendentes)} mudança(s) pendente(s).")
    else:
        st.info("Nenhuma mudança pendente.")

    # ── Botão Aplicar mudanças (compatível com 1.48 e anteriores)
    if st.button("Aplicar mudanças", type="primary", disabled=(not pendentes)):
        ok = 0
        for issue_key, novo_status in pendentes.items():
            try:
                # Obtém as transições possíveis e escolhe a que leva ao status desejado
                trans = jira.get_transitions(issue_key)
                alvo = None
                for t in trans:
                    to_name = (t.get("to", {}) or {}).get("name", "")
                    if to_name.upper() == novo_status.upper():
                        alvo = t["id"]
                        break
                if not alvo:
                    raise RuntimeError(f"Transição para '{novo_status}' não disponível em {issue_key}")

                r = jira.transicionar_status(issue_key, alvo)
                if r.status_code == 204:
                    ok += 1
                else:
                    st.error(f"{issue_key}: HTTP {r.status_code}")
            except Exception as e:
                st.error(f"Erro em {issue_key}: {e}")

        if ok:
            st.success(f"{ok} chamado(s) atualizado(s).")
        st.cache_data.clear()
        rerun_func = getattr(st, "rerun", getattr(st, "experimental_rerun", None))
        if callable(rerun_func):
            rerun_func()

# Rodapé
st.markdown("---")
st.caption(f"Última atualização: {datetime.now():%d/%m/%Y %H:%M:%S}")
