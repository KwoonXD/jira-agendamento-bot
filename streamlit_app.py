# -*- coding: utf-8 -*-
import json
from datetime import datetime
from collections import defaultdict
from itertools import chain

# streamlit_app.py
import streamlit as st
from collections import defaultdict
from utils.jira_api import JiraAPI
from utils.messages import gerar_mensagem_whatsapp, verificar_duplicidade
from streamlit_sortables import sort_items

# ── Config ─────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Painel Field Service", layout="wide")

# Paleta/coerência com tema Streamlit Dark
def badge(text, kind="pending"):
    colors = {
        "pending":  ("#FFB84D", "🟧"),
        "scheduled":("#31D0AA", "🟩"),
        "tec":      ("#2DA1FF", "🟦"),
    }
    bg, _ = colors.get(kind, ("#444", "⬛"))
    return (
        f'<span style="background:{bg}33; padding:4px 10px; '
        f'border-radius:10px; font-weight:700; font-size:12px; '
        f'border:1px solid {bg}; color:#fff;">{text}</span>'
    )

st.title("📱 Painel Field Service")

# ── Jira client ────────────────────────────────────────────────────────────
jira = JiraAPI(
    st.secrets["EMAIL"],
    st.secrets["API_TOKEN"],
    st.secrets.get("JIRA_URL", "https://delfia.atlassian.net"),
)

# Campos a buscar no Jira
FIELDS = (
    "summary,customfield_14954,customfield_14829,customfield_14825,"
    "customfield_12374,customfield_12271,customfield_11993,customfield_11994,"
    "customfield_11948,customfield_12036,status"
)

# JQLs
JQL_PEND   = 'project = FSA AND status = "AGENDAMENTO"'
JQL_AGEND  = 'project = FSA AND status = "AGENDADO"'
JQL_TEC    = 'project = FSA AND status = "TEC-CAMPO"'


# ── Caching p/ reduzir delay (TTL=60s) ─────────────────────────────────────
@st.cache_data(ttl=60, show_spinner=False)
def fetch_issues_cached(jql: str):
    return jira.buscar_chamados(jql, FIELDS)

@st.cache_data(ttl=60, show_spinner=False)
def agrupar_por_loja_cached(issues: list):
    return jira.agrupar_chamados(issues)


# Botão de atualizar agora → limpa cache + rerun
col_refresh1, col_refresh2 = st.columns([1, 5])
with col_refresh1:
    if st.button("🔄 Atualizar agora"):
        st.cache_data.clear()
        st.experimental_rerun()
with col_refresh2:
    st.caption("Dica: o painel usa cache de 60s para reduzir o delay e evitar refresh total a cada clique.")

st.markdown("---")

# ── Busca (cache) ──────────────────────────────────────────────────────────
pendentes_raw = fetch_issues_cached(JQL_PEND)
agendados_raw = fetch_issues_cached(JQL_AGEND)
tec_raw       = fetch_issues_cached(JQL_TEC)

agrup_pend  = agrupar_por_loja_cached(pendentes_raw)
agrup_agend = agrupar_por_loja_cached(agendados_raw)
agrup_tec   = agrupar_por_loja_cached(tec_raw)

# ── Tabs ───────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs(["PENDENTES", "AGENDADOS", "TEC-CAMPO", "KANBAN (arrastar & soltar)"])

# ====== helper bloco por loja ======
def bloco_por_loja(status_nome: str, loja: str, detalhes: list):
    # cabeçalho “badge”
    if status_nome == "pendentes":
        st.markdown(badge("PENDENTE", "pending"), unsafe_allow_html=True)
    elif status_nome == "agendados":
        st.markdown(badge("AGENDADO", "scheduled"), unsafe_allow_html=True)
    else:
        st.markdown(badge("TEC‑CAMPO", "tec"), unsafe_allow_html=True)

    st.code(gerar_mensagem_whatsapp(loja, detalhes), language="text")


# ====== Tab PENDENTES ======
with tab1:
    st.subheader(f"Chamados PENDENTES ({sum(len(v) for v in agrup_pend.values())})")
    if not pendentes_raw:
        st.info("Nenhum chamado em AGENDAMENTO.")
    else:
        for loja, dets in sorted(agrup_pend.items()):
            with st.expander(f"{loja} — {len(dets)} chamado(s)"):
                bloco_por_loja("pendentes", loja, dets)


# ====== Tab AGENDADOS ======
with tab2:
    st.subheader(f"Chamados AGENDADOS ({sum(len(v) for v in agrup_agend.values())})")
    if not agendados_raw:
        st.info("Nenhum chamado em AGENDADO.")
    else:
        # agrupados por data de agendamento (somente para título)
        grupos_por_data = defaultdict(lambda: defaultdict(list))
        for i in agendados_raw:
            f = i["fields"]
            loja = f.get("customfield_14954", {}).get("value", "Loja Desconhecida")
            raw  = f.get("customfield_12036")
            data_str = "Sem data"
            if raw:
                try:
                    # 2025-08-11T18:00:00.000-0300 -> 11/08/2025
                    data_str = raw[:10]
                    y, m, d = data_str.split("-")
                    data_str = f"{d}/{m}/{y}"
                except Exception:
                    pass
            grupos_por_data[data_str][loja].append(i)

        for data_str, lojas in sorted(grupos_por_data.items()):
            total = sum(len(v) for v in lojas.values())
            st.subheader(f"{data_str} — {total} chamado(s)")
            for loja, iss in sorted(lojas.items()):
                detalhes = agrupar_por_loja_cached(iss)[loja]
                with st.expander(f"{loja} — {len(iss)} chamado(s)"):
                    bloco_por_loja("agendados", loja, detalhes)


# ====== Tab TEC‑CAMPO ======
with tab3:
    st.subheader(f"Chamados TEC‑CAMPO ({sum(len(v) for v in agrup_tec.values())})")
    if not tec_raw:
        st.info("Nenhum chamado em TEC‑CAMPO.")
    else:
        for loja, dets in sorted(agrup_tec.items()):
            with st.expander(f"{loja} — {len(dets)} chamado(s)"):
                bloco_por_loja("tec", loja, dets)


# ====== Tab KANBAN (arrastar & soltar) ======
with tab4:
    st.subheader("Kanban por Loja (arraste os FSAs entre colunas para transicionar)")
    st.caption("Dica: arraste; ao finalizar, clique em **Aplicar mudanças**.")

    # listas de strings “FSA-XXXX | Loja”
    def _fmt_items(issues):
        out = []
        for i in issues:
            f = i["fields"]
            loja = f.get("customfield_14954", {}).get("value", "--")
            out.append(f"{i['key']} | {loja}")
        return out

    col1_items = _fmt_items(pendentes_raw)
    col2_items = _fmt_items(agendados_raw)
    col3_items = _fmt_items(tec_raw)

    cols = st.columns(3)
    with cols[0]:
        st.markdown(badge("AGENDAMENTO", "pending"), unsafe_allow_html=True)
    with cols[1]:
        st.markdown(badge("AGENDADO", "scheduled"), unsafe_allow_html=True)
    with cols[2]:
        st.markdown(badge("TEC‑CAMPO", "tec"), unsafe_allow_html=True)

    # streamlit-sortables 0.3.1 → assinatura simples
    result = sort_items(
        [col1_items, col2_items, col3_items],
        index=[0, 1, 2],
        direction="vertical",
        styles={
            "container": {"background": "#0B0F14", "minHeight": "220px", "borderRadius": "10px"},
            "item": {"background": "#121821", "border": "1px solid #223047", "padding": "8px 10px",
                     "borderRadius": "8px", "margin": "6px 8px", "color": "#E6F0FF", "fontSize": "14px"},
            "ghost": {"opacity": 0.3},
        },
        key="kanban"
    )

    new_col1, new_col2, new_col3 = result

    def _just_keys(lst):
        # "FSA-123 | Loja" -> "FSA-123"
        return {x.split("|", 1)[0].strip() for x in lst}

    moved_to_agend  = _just_keys(new_col2) - _just_keys(col2_items)
    moved_to_tec    = _just_keys(new_col3) - _just_keys(col3_items)

    if moved_to_agend or moved_to_tec:
        with st.expander("⚙️ Aplicar mudanças"):
            st.write("→ **AGENDADO**:", ", ".join(sorted(moved_to_agend)) or "—")
            st.write("→ **TEC‑CAMPO**:", ", ".join(sorted(moved_to_tec)) or "—")
            if st.button("Aplicar agora"):
                applied = 0
                # a) mover para AGENDADO
                for k in moved_to_agend:
                    trans = jira.get_transitions(k)
                    agid = next((t["id"] for t in trans if "agend" in t["name"].lower()), None)
                    if agid and jira.transicionar_status(k, agid).status_code == 204:
                        applied += 1
                # b) mover para TEC‑CAMPO
                for k in moved_to_tec:
                    trans = jira.get_transitions(k)
                    tcid = next((t["id"] for t in trans if "tec-campo" in t.get("to", {}).get("name", "").lower()), None)
                    if tcid and jira.transicionar_status(k, tcid).status_code == 204:
                        applied += 1
                st.success(f"Transições aplicadas: {applied}")
                st.toast("Atualizando lista...", icon="✅")
                st.cache_data.clear()
                st.experimental_rerun()

st.markdown("---")
st.caption("Cache: 60s • Evita recarregar a página inteira a cada ação • Use 'Atualizar agora' para forçar.")

