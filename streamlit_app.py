# streamlit_app.py
import os
from collections import defaultdict
from datetime import datetime
from itertools import chain

import streamlit as st

# Kanban (drag & drop)
try:
    from streamlit_sortables import sort_items
    SORTABLES_AVAILABLE = True
except Exception:
    SORTABLES_AVAILABLE = False

from utils.jira_api import JiraAPI
from utils.messages import gerar_mensagem_whatsapp, verificar_duplicidade

# ===================== Config & Links =====================
st.set_page_config(page_title="Painel Field Service", layout="wide")

ISO_DESKTOP_URL = os.getenv("ISO_DESKTOP_URL", "https://drive.google.com/file/d/1GQ64blQmysK3rbM0s0Xlot89bDNAbj5L/view?usp=drive_link")
ISO_PDV_URL     = os.getenv("ISO_PDV_URL",     "https://drive.google.com/file/d/1vxfHUDlT3kDdMaN0HroA5Nm9_OxasTaf/view?usp=drive_link")
RAT_URL         = os.getenv("RAT_URL",         "https://drive.google.com/file/d/1_SG1RofIjoJLgwWYs0ya0fKlmVd74Lhn/view?usp=sharing")

JQLS = {
    "pend":  'project = FSA AND status = "AGENDAMENTO"',
    "agend": 'project = FSA AND status = "AGENDADO"',
    "tec":   'project = FSA AND status = "TEC-CAMPO"',
}

FIELDS = (
    "status,summary,customfield_14954,customfield_14829,customfield_14825,"
    "customfield_12374,customfield_12271,customfield_11993,"
    "customfield_11994,customfield_11948,customfield_12036,customfield_12279"
)

# ===================== Jira API =====================
jira = JiraAPI(
    st.secrets["EMAIL"],
    st.secrets["API_TOKEN"],
    "https://delfia.atlassian.net"
)

@st.cache_data(ttl=60, show_spinner=False)
def load_issues(jql: str, fields: str):
    return jira.buscar_chamados(jql, fields)

def group_by_date_store(issues: list):
    g = defaultdict(lambda: defaultdict(list))
    for it in issues:
        f = it.get("fields", {})
        loja = f.get("customfield_14954", {}).get("value", "Loja Desconhecida")
        raw  = f.get("customfield_12036")
        if raw:
            try:
                dt = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S.%f%z")
            except Exception:
                try:
                    dt = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S%z")
                except Exception:
                    dt = None
        else:
            dt = None
        data_str = dt.strftime("%d/%m/%Y") if dt else "Sem data"
        g[data_str][loja].append(it)
    return g

def group_by_store(issues: list):
    g = defaultdict(list)
    for it in issues:
        f = it.get("fields", {})
        loja = f.get("customfield_14954", {}).get("value", "Loja Desconhecida")
        g[loja].append(it)
    return g

def detalhe(loja, issues):
    return jira.agrupar_chamados(issues).get(loja, [])

def _item_label(issue):
    f = issue.get("fields", {})
    loja = f.get("customfield_14954", {}).get("value", "Loja Desconhecida")
    return f"{issue.get('key','?')} | {loja}"

def _find_transition(issue_key: str, to_name_contains: str):
    trans = jira.get_transitions(issue_key)
    return next((t["id"] for t in trans if to_name_contains.lower() in t.get("to", {}).get("name", "").lower()), None)

# ===================== Kanban wrapper (compat) =====================
def _sort_three_columns(col1_items, col2_items, col3_items, styles):
    """
    Funciona com várias versões do streamlit-sortables.
    Sempre tenta usar multi_containers=True.
    """
    attempts = [
        # novas assinaturas
        {"items": [col1_items, col2_items, col3_items],
         "multi_containers": True, "index": [0, 1, 2],
         "direction": "vertical", "styles": styles, "key": "kanban"},
        {"items": [col1_items, col2_items, col3_items],
         "multi_containers": True, "index": [0, 1, 2],
         "direction": "vertical", "key": "kanban"},
        {"items": [col1_items, col2_items, col3_items],
         "multi_containers": True, "key": "kanban"},
        {"items": [col1_items, col2_items, col3_items],
         "multi_containers": True},
    ]
    for params in attempts:
        try:
            return sort_items(**params)
        except TypeError:
            continue
    # fallback ultra-antigo
    try:
        return sort_items([col1_items, col2_items, col3_items], True)
    except Exception as e:
        st.warning(f"Kanban indisponível nesta versão do streamlit-sortables: {e}")
        return col1_items, col2_items, col3_items

# ===================== UI helpers =====================
def badge(text, tone="pending"):
    colors = {
        "pending":  ("#FFB84D", "#261A00"),
        "scheduled":("#3DDC84", "#001A0E"),
        "tec":      ("#4FC3F7", "#00131B"),
    }
    bg, fg = colors.get(tone, ("#444", "#000"))
    return (
        f"<span style='background:{bg};padding:4px 8px;border-radius:8px;"
        f"font-weight:600;font-size:12px;color:{fg};'>{text}</span>"
    )

def pdv_counts(dets):
    pdv = sum(1 for d in dets if str(d.get("pdv","")).strip() not in ("", "300"))
    desktop = sum(1 for d in dets if (str(d.get("pdv","")) == "300") or ("desktop" in str(d.get("ativo","")).lower()))
    return pdv, desktop

# ===================== Page =====================
st.title("Painel Field Service")

tab1, tab2, tab3, tab4 = st.tabs(["PENDENTES", "AGENDADOS", "TEC-CAMPO", "KANBAN (arrastar & soltar)"])

with st.sidebar:
    st.caption("Transição de Chamados")
    st.button("↩️ Desfazer última ação", disabled=True)  # placeholder para manter layout

# ---------- Dados ----------
pendentes_raw = load_issues(JQLS["pend"], FIELDS)
agendados_raw = load_issues(JQLS["agend"], FIELDS)
teccampo_raw  = load_issues(JQLS["tec"], FIELDS)

agrup_pend = group_by_store(pendentes_raw)
grouped_sched = group_by_date_store(agendados_raw)
agrup_tec = group_by_date_store(teccampo_raw)

# ---------- PENDENTES ----------
with tab1:
    st.subheader(f"Chamados PENDENTES ({sum(len(v) for v in agrup_pend.values())}) {badge('PENDENTE','pending')}", divider=True)
    if not agrup_pend:
        st.info("Nenhum chamado em AGENDAMENTO.")
    else:
        for loja, iss in sorted(agrup_pend.items()):
            dets = detalhe(loja, iss)
            dups = verificar_duplicidade(dets)
            pdv, desk = pdv_counts(dets)
            hdr = f"{loja} — {len(iss)} chamado(s) ({pdv} PDV · {desk} Desktop)"
            with st.expander(hdr, expanded=False):
                st.markdown("**FSAs:** " + ", ".join(d["key"] for d in dets))
                st.code(
                    gerar_mensagem_whatsapp(
                        loja, dets, ISO_DESKTOP_URL, ISO_PDV_URL, RAT_URL
                    ),
                    language="text",
                )
                if dups:
                    st.warning("Possíveis duplicidades: " + ", ".join(f"{p}/{a}" for p,a in dups))

# ---------- AGENDADOS ----------
with tab2:
    st.subheader(f"Chamados AGENDADOS ({len(agendados_raw)}) {badge('AGENDADO','scheduled')}", divider=True)
    if not agendados_raw:
        st.info("Nenhum chamado em AGENDADO.")
    else:
        for date, stores in sorted(grouped_sched.items()):
            total = sum(len(v) for v in stores.values())
            st.markdown(f"### {date} — {total} chamado(s)")
            for loja, iss in sorted(stores.items()):
                dets = detalhe(loja, iss)
                pdv, desk = pdv_counts(dets)
                hdr = f"{loja} — {len(iss)} chamado(s) ({pdv} PDV · {desk} Desktop)"
                with st.expander(hdr, expanded=False):
                    st.markdown("**FSAs:** " + ", ".join(d["key"] for d in dets))
                    st.code(
                        gerar_mensagem_whatsapp(
                            loja, dets, ISO_DESKTOP_URL, ISO_PDV_URL, RAT_URL
                        ),
                        language="text",
                    )

# ---------- TEC-CAMPO ----------
with tab3:
    st.subheader(f"Chamados TEC‑CAMPO ({len(teccampo_raw)}) {badge('TEC-CAMPO','tec')}", divider=True)
    if not teccampo_raw:
        st.info("Nenhum chamado em TEC‑CAMPO.")
    else:
        for date, stores in sorted(agrup_tec.items()):
            total = sum(len(v) for v in stores.values())
            st.markdown(f"### {date} — {total} chamado(s)")
            for loja, iss in sorted(stores.items()):
                dets = detalhe(loja, iss)
                pdv, desk = pdv_counts(dets)
                hdr = f"{loja} — {len(iss)} chamado(s) ({pdv} PDV · {desk} Desktop)  {badge('TEC-CAMPO','tec')}"
                with st.expander(hdr, expanded=False):
                    st.markdown("**FSAs:** " + ", ".join(d["key"] for d in dets))
                    st.code(
                        gerar_mensagem_whatsapp(
                            loja, dets, ISO_DESKTOP_URL, ISO_PDV_URL, RAT_URL
                        ),
                        language="text",
                    )

# ---------- KANBAN ----------
with tab4:
    st.subheader("Kanban por Loja (arraste os FSAs entre colunas para transicionar)", divider=True)
    if not SORTABLES_AVAILABLE:
        st.warning("Instale o pacote `streamlit-sortables` para habilitar o Kanban.")
    else:
        # 3 colunas: AGENDAMENTO / AGENDADO / TEC-CAMPO (apenas exibição e transição simples)
        colA, colB, colC = st.columns(3)
        with colA: st.markdown(badge("AGENDAMENTO", "pending"), unsafe_allow_html=True)
        with colB: st.markdown(badge("AGENDADO", "scheduled"), unsafe_allow_html=True)
        with colC: st.markdown(badge("TEC-CAMPO", "tec"), unsafe_allow_html=True)

        col1_items = [_item_label(i) for i in pendentes_raw]
        col2_items = [_item_label(i) for i in agendados_raw]
        col3_items = [_item_label(i) for i in teccampo_raw]

        styles = {
            "container": {"background":"#0B0F14", "minHeight":"260px", "padding":"8px", "border":"1px solid #222", "borderRadius":"12px"},
            "dragItem": {"background":"#121820", "border":"1px solid #222", "borderRadius":"8px", "padding":"6px 8px", "margin":"6px 0"},
            "dragItemActive": {"background":"#1A2430"},
            "dragItemGhost": {"opacity":"0.22"},
        }

        new_col1, new_col2, new_col3 = _sort_three_columns(col1_items, col2_items, col3_items, styles)

        # Botão aplicar mudanças
        if st.button("Aplicar mudanças", type="primary", use_container_width=True):
            # Mapeia "KEY | LOJA" -> KEY
            def keys_from(items):
                out = []
                for it in items:
                    key = it.split("|", 1)[0].strip()
                    out.append(key)
                return out

            tgt1, tgt2, tgt3 = map(keys_from, (new_col1, new_col2, new_col3))
            src1, src2, src3 = map(keys_from, (col1_items, col2_items, col3_items))

            moved_to_agend  = set(tgt2) - set(src2)
            moved_to_tec    = set(tgt3) - set(src3)
            moved_to_pend   = set(tgt1) - set(src1)

            errors = []
            ok = 0

            # AGENDAMENTO -> AGENDADO
            for key in moved_to_agend:
                tid = _find_transition(key, "AGENDADO")
                if tid:
                    r = jira.transicionar_status(key, tid)
                    ok += 1 if r.status_code == 204 else 0
                else:
                    errors.append(f"{key} sem transição para AGENDADO.")

            # qualquer -> TEC-CAMPO
            for key in moved_to_tec:
                tid = _find_transition(key, "TEC-CAMPO")
                if tid:
                    r = jira.transicionar_status(key, tid)
                    ok += 1 if r.status_code == 204 else 0
                else:
                    errors.append(f"{key} sem transição para TEC-CAMPO.")

            # qualquer -> AGENDAMENTO
            for key in moved_to_pend:
                tid = _find_transition(key, "AGENDAMENTO")
                if tid:
                    r = jira.transicionar_status(key, tid)
                    ok += 1 if r.status_code == 204 else 0
                else:
                    errors.append(f"{key} sem transição para AGENDAMENTO.")

            if errors:
                st.error("Algumas transições falharam:")
                for e in errors:
                    st.code(e)
            st.success(f"{ok} transições aplicadas.")
            st.cache_data.clear()

st.caption(f"Última atualização: {datetime.now():%d/%m/%Y %H:%M:%S}")
