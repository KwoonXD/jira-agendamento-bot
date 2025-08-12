import os
from collections import defaultdict
from datetime import datetime
from itertools import chain

import streamlit as st

from utils.jira_api import JiraAPI
from utils.messages import (
    gerar_mensagem_whatsapp,
    verificar_duplicidade,
    ISO_DESKTOP_URL,
    ISO_PDV_URL,
    RAT_URL,
)

# ============ CONFIG / THEME ============
st.set_page_config(page_title="Painel Field Service", layout="wide")
THEME = {
    "bg": "#0B0F14",
    "panel": "#141923",
    "pend": "#FFB84D",
    "agend": "#2BD686",
    "tec": "#4DA3FF",
}
st.markdown(
    f"""
    <style>
      .css-18ni7ap, .stTabs [data-baseweb="tab-list"] {{ gap: 8px; }}
      .stTabs [data-baseweb="tab"] {{
          background:{THEME['panel']}; padding:10px 16px; border-radius:10px; color:#ddd;
      }}
      .stButton > button {{ border-radius:10px; }}
      .x-badge {{ padding:4px 8px; border-radius:8px; font-weight:600; font-size:12px; }}
      .x-pend {{ background:{THEME['pend']}; color:#261A00; }}
      .x-ag {{ background:#CFFFEA; color:#00391F; }}
      .x-tec {{ background:#D6E8FF; color:#00131B; }}
      .x-tag {{ font-size:12px; opacity:.75; }}
      .x-kanban-card {{
          background:#db5252; color:#fff; border-radius:8px; padding:8px 12px; text-align:center;
          margin:6px 0; font-weight:600;
      }}
    </style>
    """,
    unsafe_allow_html=True,
)

# ============ PARAMS / CONSTANTES ============
JQLS = {
    "pend": 'project = FSA AND status = "AGENDAMENTO"',
    "agend": 'project = FSA AND status = "AGENDADO"',
    "tec": 'project = FSA AND status = "TEC-CAMPO"',
}

FIELDS = (
    "summary,status,customfield_14954,customfield_14829,customfield_14825,"
    "customfield_12374,customfield_12271,customfield_11993,customfield_11994,"
    "customfield_11948,customfield_12036,customfield_12279"
)

EMAIL = st.secrets["EMAIL"]
TOKEN = st.secrets["API_TOKEN"]
BASE = "https://delfia.atlassian.net"
jira = JiraAPI(EMAIL, TOKEN, BASE)

# ============ CACHE ============

@st.cache_data(ttl=60, show_spinner=False)
def _fetch_all():
    out = {}
    for k, jql in JQLS.items():
        out[k] = jira.buscar_chamados(jql, FIELDS)
    return out


def _parse_dt(raw):
    if not raw:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(raw, fmt)
        except Exception:
            pass
    return None


def _badge(label: str, kind: str) -> str:
    cls = {"pend": "x-pend", "ag": "x-ag", "tec": "x-tec"}[kind]
    return f'<span class="x-badge {cls}">{label}</span>'


# ============ BUSCA ============

with st.spinner("Carregando chamados…"):
    data = _fetch_all()

pendentes_raw = data["pend"]
agendados_raw = data["agend"]
tec_raw = data["tec"]

agrup_pend = jira.agrupar_chamados(pendentes_raw)
agrup_ag = jira.agrupar_chamados(agendados_raw)
agrup_tec = jira.agrupar_chamados(tec_raw)

# ============ FILTRO GLOBAL ============
with st.sidebar:
    st.header("Ações")
    st.caption("O cache se renova automaticamente a cada 60s.")
    filtro = st.text_input("Filtro global (por FSA, Loja, PDV, Ativo…)", placeholder="ex.: 1519 ou FSA-97…").strip().lower()

def _filtra_lista(lst: list) -> list:
    if not filtro:
        return lst
    out = []
    for d in lst:
        txt = " ".join(str(v) for v in d.values()).lower()
        if filtro in txt:
            out.append(d)
    return out

# ============ UI HELPERS ============
def _expander_header(loja: str, dets: list, kind: str):
    qtd_pdv = sum(1 for d in dets if (d.get("pdv") or "") != "300")
    qtd_desktop = sum(1 for d in dets if (d.get("pdv") or "") == "300" or "desktop" in (d.get("ativo","").lower()))
    titulo = f"{loja} — {len(dets)} chamado(s) ({qtd_pdv} PDV · {qtd_desktop} Desktop)"
    exp = st.expander(titulo, expanded=False)
    with exp:
        st.markdown(_badge({"pend":"PENDENTE","ag":"AGENDADO","tec":"TEC-CAMPO"}[kind], {"pend":"pend","ag":"ag","tec":"tec"}[kind]), unsafe_allow_html=True)
    return exp


def _bloco_loja(kind: str, loja: str, dets_raw: list):
    dets = _filtra_lista(dets_raw)
    if not dets:
        st.info("Nenhum item após filtro.")
        return
    exp = _expander_header(loja, dets, kind)
    with exp:
        st.code(gerar_mensagem_whatsapp(loja, dets, ISO_DESKTOP_URL, ISO_PDV_URL, RAT_URL), language="text")


# ============ TABS ============
tab1, tab2, tab3, tab4 = st.tabs(["PENDENTES", "AGENDADOS", "TEC-CAMPO", "KANBAN (arrastar & soltar)"])

with tab1:
    st.subheader(f"Chamados PENDENTES ({len(pendentes_raw)})")
    for loja, dets in sorted(agrup_pend.items()):
        _bloco_loja("pend", loja, dets)

with tab2:
    st.subheader(f"Chamados AGENDADOS ({len(agendados_raw)})")
    # agrupar por data > loja
    by_date = defaultdict(lambda: defaultdict(list))
    for it in agendados_raw:
        f = it["fields"]
        loja = f.get("customfield_14954", {}).get("value", "Loja Desconhecida")
        data_str = _parse_dt(f.get("customfield_12036"))
        ch = jira.agrupar_chamados([it])[loja][0]
        by_date[(data_str or datetime.min).date()][loja].append(ch)

    for date, stores in sorted(by_date.items()):
        total = sum(len(v) for v in stores.values())
        st.markdown(f"### {date.strftime('%d/%m/%Y')} — {total} chamado(s)")
        for loja, dets in sorted(stores.items()):
            _bloco_loja("ag", loja, dets)

with tab3:
    st.subheader(f"Chamados TEC‑CAMPO ({len(tec_raw)})")
    for loja, dets in sorted(agrup_tec.items()):
        _bloco_loja("tec", loja, dets)

# ========================= KANBAN =========================

with tab4:
    st.subheader("Kanban por Loja (arraste os FSAs entre colunas)  ↻")
    # montar três colunas de strings "FSA-XXXX | LOJA"
    def _mk_cards(issues):
        cards = []
        for it in issues:
            f = it["fields"]
            loja = f.get("customfield_14954", {}).get("value", "Loja Desconhecida")
            cards.append(f"{it['key']} | {loja}")
        return cards

    col1_items = _mk_cards(pendentes_raw)
    col2_items = _mk_cards(agendados_raw)
    col3_items = _mk_cards(tec_raw)

    # Exibir com streamlit-sortables (multi_containers)
    try:
        from streamlit_sortables import sort_items

        containers = [
            {"header": "AGENDAMENTO", "items": col1_items},
            {"header": "AGENDADO", "items": col2_items},
            {"header": "TEC-CAMPO", "items": col3_items},
        ]
        styles = {
            "container": {"background": THEME["panel"], "minHeight": "280px"},
            "header": {"background": THEME["panel"], "color": "#e4e4e4", "fontWeight": "700"},
            "item": {"background": "#db5252", "padding": "8px", "borderRadius": "8px", "color": "white"},
        }
        result = sort_items(containers, multi_containers=True, direction="vertical", styles=styles, key="kanban_v2")
        new_col1, new_col2, new_col3 = [r["items"] for r in result]
    except Exception:
        # fallback simples: sem estilos
        from streamlit_sortables import sort_items as sort_simple

        result = sort_simple(
            [
                {"header": "AGENDAMENTO", "items": col1_items},
                {"header": "AGENDADO", "items": col2_items},
                {"header": "TEC-CAMPO", "items": col3_items},
            ],
            multi_containers=True,
            key="kanban_simple",
        )
        new_col1, new_col2, new_col3 = [r["items"] for r in result]

    # detectar mudanças
    before = {
        "AGENDAMENTO": set(col1_items),
        "AGENDADO": set(col2_items),
        "TEC-CAMPO": set(col3_items),
    }
    after = {
        "AGENDAMENTO": set(new_col1),
        "AGENDADO": set(new_col2),
        "TEC-CAMPO": set(new_col3),
    }

    movimentos = []
    for destino, novo_set in after.items():
        for card in novo_set:
            origem = next((k for k, v in before.items() if card in v), None)
            if origem and origem != destino:
                key = card.split("|")[0].strip()
                movimentos.append((key, origem, destino))

    st.caption("Dica: arraste; ao finalizar, clique em **Aplicar mudanças**.")
    if movimentos:
        st.warning(f"{len(movimentos)} mudança(s) pendente(s).")
        if st.button("Aplicar mudanças", type="primary"):
            ok, falhas = 0, []
            map_to = {"AGENDAMENTO": "AGENDAMENTO", "AGENDADO": "AGENDADO", "TEC-CAMPO": "TEC-CAMPO"}
            for issue_key, _orig, destino in movimentos:
                try:
                    trans = jira.get_transitions(issue_key)
                    target = map_to[destino]
                    tid = next(
                        (t["id"] for t in trans if t.get("to", {}).get("name", "").upper() == target),
                        None,
                    )
                    if tid:
                        jira.transicionar_status(issue_key, tid)
                        ok += 1
                    else:
                        falhas.append(f"{issue_key}: transição '{destino}' não encontrada")
                except Exception as e:
                    falhas.append(f"{issue_key}: {e}")
            if falhas:
                st.error("Algumas falharam:")
                st.code("\n".join(falhas))
            if ok:
                st.success(f"{ok} chamado(s) atualizado(s).")
                st.cache_data.clear()
                st.experimental_rerun()

st.caption(f"Última atualização: {datetime.now():%d/%m/%Y %H:%M:%S}")
