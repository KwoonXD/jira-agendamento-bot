import os
import time
from datetime import datetime
from collections import defaultdict

import streamlit as st

from utils.jira_api import JiraAPI
from utils.messages import gerar_mensagem_whatsapp, verificar_duplicidade

# =========================
# Config / Tema / Constantes
# =========================
st.set_page_config(page_title="Painel Field Service", layout="wide")
THEME_BG = "#0B0F14"     # casa com tema escuro atual
THEME_CARD = "#171C23"
THEME_SOFT = "#1F2833"
THEME_TEXT = "#E6EEF7"

STATUS_COLORS = {
    "PENDENTE": "#FFB84D",
    "AGENDADO": "#42D392",
    "TEC-CAMPO": "#3DA2FF",
}

def badge(text: str, kind: str) -> str:
    color = STATUS_COLORS.get(kind.upper(), "#888")
    fg = "#261A00" if kind.upper() == "PENDENTE" else "#00131B" if kind.upper()=="TEC-CAMPO" else "#002310"
    return (
        f"<span style='background:{color};padding:4px 8px;border-radius:8px;"
        f"font-weight:600;font-size:12px;color:{fg};'>{text}</span>"
    )

def h2(title: str, kind: str, total: int) -> None:
    st.markdown(
        f"### {title} ({total}) {badge(kind, kind)}",
        unsafe_allow_html=True
    )

# =========================
# Credenciais (Streamlit Secrets)
# =========================
EMAIL = st.secrets["EMAIL"]
TOKEN = st.secrets["API_TOKEN"]
BASE  = "https://delfia.atlassian.net"

# Links (defaults)
ISO_DESKTOP_URL = "https://drive.google.com/file/d/1GQ64blQmysK3rbM0s0Xlot89bDNAbj5L/view?usp=drive_link"
ISO_PDV_URL     = "https://drive.google.com/file/d/1vxfHUDlT3kDdMaN0HroA5Nm9_OxasTaf/view?usp=drive_link"
RAT_URL         = "https://drive.google.com/file/d/1_SG1RofIjoJLgwWYs0ya0fKlmVd74Lhn/view?usp=sharing"

# =========================
# Jira API helper
# =========================
jira = JiraAPI(EMAIL, TOKEN, BASE)

FIELDS = (
    "summary,customfield_14954,customfield_14829,customfield_14825,"
    "customfield_12374,customfield_12271,customfield_11993,"
    "customfield_11994,customfield_11948,customfield_12036,customfield_12279,status"
)

@st.cache_data(ttl=30, show_spinner=False)
def _fetch_issues():
    """Trazer issues por status com cache de 30s."""
    jqls = {
        "pend": 'project = FSA AND status = "AGENDAMENTO"',
        "agend": 'project = FSA AND status = "AGENDADO"',
        "tec": 'project = FSA AND status = "TEC-CAMPO"',
    }
    pend = jira.buscar_chamados(jqls["pend"], FIELDS)
    agnd = jira.buscar_chamados(jqls["agend"], FIELDS)
    tec  = jira.buscar_chamados(jqls["tec"], FIELDS)
    return pend, agnd, tec, jqls

def _group_by_loja(issues: list) -> dict[str, list]:
    """Agrupa issues por loja com os campos já normalizados para UI/Mensagem."""
    agrup = defaultdict(list)
    for issue in issues:
        f = issue.get("fields", {})
        loja = f.get("customfield_14954", {}).get("value", "Loja Desconhecida")
        agrup[loja].append({
            "key": issue.get("key", "--"),
            "status": f.get("status", {}).get("name", "--"),
            "pdv": f.get("customfield_14829", "--"),
            "ativo": f.get("customfield_14825", {}).get("value", "--"),
            "problema": f.get("customfield_12374", "--"),
            "endereco": f.get("customfield_12271", "--"),
            "estado": f.get("customfield_11948", {}).get("value", "--"),
            "cep": f.get("customfield_11993", "--"),
            "cidade": f.get("customfield_11994", "--"),
            "data_agendada": f.get("customfield_12036"),
            "self_checkout": "Não"  # manter campo textual
        })
    return agrup

def _count_pdv_desktop(items: list[dict]) -> tuple[int,int]:
    """Conta quantos PDV e quantos Desktop (PDV=300 ou ativo contém 'desktop')."""
    pdv = 0
    desk = 0
    for d in items:
        pdv_code = str(d.get("pdv","")).strip()
        ativo    = str(d.get("ativo","")).lower()
        if pdv_code == "300" or "desktop" in ativo:
            desk += 1
        else:
            pdv += 1
    return pdv, desk

def _parse_date(raw) -> str:
    if not raw: 
        return "Sem Data"
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(raw, fmt).strftime("%d/%m/%Y")
        except Exception:
            pass
    return "Sem Data"

# ========= sortables (arrastar/soltar) – API nova e fallback ==========
def _build_item_str(loja: str, d: dict) -> str:
    return f"{d['key']} | {loja}"

def _to_v2_payload(col1: list[str], col2: list[str], col3: list[str]):
    """API antiga (multi_containers=True mas aceita lista de listas de strings em versões antigas)."""
    return [col1, col2, col3]

def _to_v3_payload(col1: list[str], col2: list[str], col3: list[str]):
    """API nova do streamlit-sortables (>=0.3.x): precisa de list[dict] com keys específicas."""
    return [
        {"header": "AGENDAMENTO", "items": col1, "id": "col1"},
        {"header": "AGENDADO",    "items": col2, "id": "col2"},
        {"header": "TEC-CAMPO",   "items": col3, "id": "col3"},
    ]

def _sort_three_columns(col1_items, col2_items, col3_items, styles):
    """Tenta API nova; se não, cai na velha."""
    try:
        from streamlit_sortables import sort_items
    except Exception:
        st.warning("Instale o pacote: streamlit-sortables==0.3.1")
        return col1_items, col2_items, col3_items

    # 1) Tenta API nova: dicts + multi_containers
    try:
        v3_items = _to_v3_payload(col1_items, col2_items, col3_items)
        result = sort_items(
            items=v3_items,
            multi_containers=True,
            direction="vertical",
            key="kanban-v3",
        )
        # result deve ser list[dict] com ".items"
        return result[0]["items"], result[1]["items"], result[2]["items"]
    except TypeError:
        # 2) Fallback API antiga (lista de listas de strings)
        try:
            v2_items = _to_v2_payload(col1_items, col2_items, col3_items)
            result = sort_items(v2_items, multi_containers=True, direction="vertical", key="kanban-v2")
            return result[0], result[1], result[2]
        except Exception as e:
            st.error(f"Drag & drop indisponível ({e}).")
            return col1_items, col2_items, col3_items


# =========================
# Sidebar (ações rápidas)
# =========================
with st.sidebar:
    st.header("Ações")
    if st.button("🔄 Recarregar agora"):
        _fetch_issues.clear()   # limpa o cache do fetch
        st.experimental_rerun()

    st.markdown("---")
    st.header("Filtro global")
    global_filter = st.text_input("Buscar por FSA / Loja / PDV / Ativo").strip().lower()


# =========================
# Carrega dados (cache)
# =========================
pend_raw, agend_raw, tec_raw, JQLS = _fetch_issues()

# Agrupar por loja
pend_by_loja  = _group_by_loja(pend_raw)
agend_by_loja = _group_by_loja(agend_raw)
tec_by_loja   = _group_by_loja(tec_raw)

# ========= TABS ===========
tab1, tab2, tab3, tab4 = st.tabs(["PENDENTES", "AGENDADOS", "TEC-CAMPO", "KANBAN (arrastar & soltar)"])

# =========================
# PENDENTES
# =========================
with tab1:
    total = sum(len(v) for v in pend_by_loja.values())
    h2("Chamados PENDENTES", "PENDENTE", total)

    for loja, itens in sorted(pend_by_loja.items()):
        if global_filter:
            if (global_filter not in loja.lower() and
                all(global_filter not in d['key'].lower() and global_filter not in str(d.get('pdv','')).lower() and global_filter not in str(d.get('ativo','')).lower() for d in itens)):
                continue

        pdv_q, desk_q = _count_pdv_desktop(itens)
        header = f"{loja} — {len(itens)} chamado(s) ({pdv_q} PDV · {desk_q} Desktop)  {badge('PENDENTE','PENDENTE')}"
        with st.expander(header, expanded=False):
            st.code(
                gerar_mensagem_whatsapp(
                    loja, itens,
                    ISO_DESKTOP_URL, ISO_PDV_URL, RAT_URL,
                    incluir_status=False, incluir_tipo=False
                ),
                language="text"
            )

# =========================
# AGENDADOS
# =========================
with tab2:
    # agrupar por data -> loja
    grouped = defaultdict(lambda: defaultdict(list))
    for loja, lst in agend_by_loja.items():
        for d in lst:
            grouped[_parse_date(d["data_agendada"])][loja].append(d)

    total = sum(len(vv) for v in grouped.values() for vv in v.values())
    h2("Chamados AGENDADOS", "AGENDADO", total)

    for date_str, stores in sorted(grouped.items()):
        total_dia = sum(len(v) for v in stores.values())
        st.subheader(f"{date_str} — {total_dia} chamado(s)")

        for loja, itens in sorted(stores.items()):
            if global_filter:
                if (global_filter not in loja.lower() and
                    all(global_filter not in d['key'].lower() and global_filter not in str(d.get('pdv','')).lower() and global_filter not in str(d.get('ativo','')).lower() for d in itens)):
                    continue

            pdv_q, desk_q = _count_pdv_desktop(itens)
            header = f"{loja} — {len(itens)} chamado(s) ({pdv_q} PDV · {desk_q} Desktop)  {badge('AGENDADO','AGENDADO')}"
            with st.expander(header, expanded=False):
                st.code(
                    gerar_mensagem_whatsapp(
                        loja, itens,
                        ISO_DESKTOP_URL, ISO_PDV_URL, RAT_URL,
                        incluir_status=False, incluir_tipo=False
                    ),
                    language="text"
                )

# =========================
# TEC-CAMPO
# =========================
with tab3:
    total = sum(len(v) for v in tec_by_loja.values())
    h2("Chamados TEC-CAMPO", "TEC-CAMPO", total)

    for loja, itens in sorted(tec_by_loja.items()):
        if global_filter:
            if (global_filter not in loja.lower() and
                all(global_filter not in d['key'].lower() and global_filter not in str(d.get('pdv','')).lower() and global_filter not in str(d.get('ativo','')).lower() for d in itens)):
                continue

        pdv_q, desk_q = _count_pdv_desktop(itens)
        header = f"{loja} — {len(itens)} chamado(s) ({pdv_q} PDV · {desk_q} Desktop)  {badge('TEC-CAMPO','TEC-CAMPO')}"
        with st.expander(header, expanded=False):
            st.code(
                gerar_mensagem_whatsapp(
                    loja, itens,
                    ISO_DESKTOP_URL, ISO_PDV_URL, RAT_URL,
                    incluir_status=False, incluir_tipo=False
                ),
                language="text"
            )

# =========================
# KANBAN – arrastar & soltar
# =========================
with tab4:
    st.subheader("Kanban por Loja (arraste os FSAs entre colunas)")

    # 1) Montar listas de strings no formato "FSA-123 | LOJA"
    col1_items = []
    for loja, lst in pend_by_loja.items():
        for d in lst:
            col1_items.append(_build_item_str(loja, d))

    col2_items = []
    for loja, lst in agend_by_loja.items():
        for d in lst:
            col2_items.append(_build_item_str(loja, d))

    col3_items = []
    for loja, lst in tec_by_loja.items():
        for d in lst:
            col3_items.append(_build_item_str(loja, d))

    # 2) Filtro global no kanban
    if global_filter:
        f = global_filter
        col1_items = [s for s in col1_items if f in s.lower()]
        col2_items = [s for s in col2_items if f in s.lower()]
        col3_items = [s for s in col3_items if f in s.lower()]

    styles = {
        "container": {"background": THEME_BG, "minHeight": "220px"},
        "item": {"background": THEME_CARD},
    }

    try:
        new_col1, new_col2, new_col3 = _sort_three_columns(col1_items, col2_items, col3_items, styles)
    except Exception as e:
        st.error(f"Kanban indisponível ({e})")
        new_col1, new_col2, new_col3 = col1_items, col2_items, col3_items

    cols = st.columns(3)
    with cols[0]:
        st.markdown(badge("AGENDAMENTO", "PENDENTE"), unsafe_allow_html=True)
        st.write("\n".join([f"- {s}" for s in new_col1]) or "_Sem itens_")
    with cols[1]:
        st.markdown(badge("AGENDADO", "AGENDADO"), unsafe_allow_html=True)
        st.write("\n".join([f"- {s}" for s in new_col2]) or "_Sem itens_")
    with cols[2]:
        st.markdown(badge("TEC-CAMPO", "TEC-CAMPO"), unsafe_allow_html=True)
        st.write("\n".join([f"- {s}" for s in new_col3]) or "_Sem itens_")

st.caption(f"Última atualização: {datetime.now():%d/%m/%Y %H:%M:%S}")
