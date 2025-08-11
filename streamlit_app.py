# -*- coding: utf-8 -*-
import json
from datetime import datetime
from collections import defaultdict
from itertools import chain

import streamlit as st

# ====== Drag & Drop (Kanban) ======
try:
    from streamlit_sortables import sort_items
    HAS_SORTABLES = True
except Exception:
    HAS_SORTABLES = False

from utils.jira_api import JiraAPI
from utils.messages import verificar_duplicidade

# ========= PAGE / THEME =========
st.set_page_config(page_title="Painel Field Service", layout="wide")

# CSS alinhado ao tema do config.toml
st.markdown("""
<style>
:root {
  --pill-bg:#141A22; --pill-muted:#10151d; --text:#E6EDF3; --muted:#9aa4b2;
  --yellow:#FFB454; --green:#2ECC71; --blue:#3AA0FF; --info:#728097;
}

.badge{display:inline-flex;align-items:center;gap:8px;background:#1a212c;
  color:#dbe3ea;font-size:12px;font-weight:700;border-radius:999px;padding:6px 10px;margin-left:8px;}
.badge .dot{width:10px;height:10px;border-radius:3px;display:inline-block;}
.badge.pending .dot{background:#FFB454;}
.badge.scheduled .dot{background:#2ECC71;}
.badge.tec .dot{background:#3AA0FF;}
.badge.info .dot{background:#728097;}

.group-title{display:flex;align-items:center;gap:10px;font-weight:700;font-size:16px;}
.codebox{background:#0B0F14;border:1px solid #1f2a39;border-radius:12px;padding:12px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono","Courier New", monospace;white-space:pre-wrap;line-height:1.35;}
.head-pill{background:#10151d;border:1px solid #2a3342;padding:10px 14px;border-radius:12px;}
.kicker{color:#9aa4b2;font-size:12px}
</style>
""", unsafe_allow_html=True)

# ========= LINKS =========
ISO_DESKTOP_URL = "https://drive.google.com/file/d/1GQ64blQmysK3rbM0s0Xlot89bDNAbj5L/view?usp=drive_link"
ISO_PDV_URL     = "https://drive.google.com/file/d/1vxfHUDlT3kDdMaN0HroA5Nm9_OxasTaf/view?usp=drive_link"
RAT_URL         = "https://drive.google.com/file/d/1_SG1RofIjoJLgwWYs0ya0fKlmVd74Lhn/view?usp=sharing"

# ========= HELPERS =========
def parse_dt(raw):
    if not raw: return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try: return datetime.strptime(raw, fmt)
        except Exception: pass
    return None

def is_desktop(pdv_val, ativo_val):
    try:
        if str(pdv_val).strip() == "300": return True
    except Exception: pass
    return "desktop" in str(ativo_val or "").lower()

def badge(label, kind="info"):
    return f'<span class="badge {kind}"><span class="dot"></span>{label}</span>'

def header_badges(qtd, qtd_pdv, qtd_desktop, tem_dup=False):
    items = [badge(f"{qtd_pdv} PDV", "info"), badge(f"{qtd_desktop} Desktop", "info")]
    if tem_dup: items.append(badge("Possíveis Duplicados", "pending"))
    return " ".join(items)

def format_whatsapp_block(loja, chs):
    lines=[]
    for ch in chs:
        pdv, ativo = ch.get("pdv","--"), ch.get("ativo","--")
        tipo = "Desktop" if is_desktop(pdv, ativo) else "PDV"
        problema = ch.get("problema","--")
        lines += [
            f"*{ch.get('key','--')}*",
            f"Loja: {loja}",
            f"Status: {ch.get('status','--')}",
            f"PDV: {pdv}",
            f"*ATIVO:* {ativo}",
            f"Tipo de atendimento: {tipo}",
            f"Problema: {problema}, Self Checkout?: Não",
            "***"
        ]
    if chs:
        a = chs[0]
        lines += [
            f"Endereço: {a.get('endereco','--')}",
            f"Estado: {a.get('estado','--')}",
            f"CEP: {a.get('cep','--')}",
            f"Cidade: {a.get('cidade','--')}",
        ]
        qtd_pdv = sum(1 for x in chs if not is_desktop(x.get('pdv'), x.get('ativo')))
        qtd_dsk = len(chs) - qtd_pdv
        iso_link = ISO_PDV_URL if qtd_pdv >= qtd_dsk else ISO_DESKTOP_URL
        lines += [
            f"ISO ({'PDV' if qtd_pdv >= qtd_dsk else 'Desktop'}): {iso_link}",
            "------",
            f"⚠️ *É OBRIGATÓRIO LEVAR:*",
            f"• RAT: {RAT_URL}"
        ]
    return "\n".join(lines)

def agrupar_por_loja(issues):
    agrup=defaultdict(list)
    for issue in issues:
        f=issue.get("fields",{})
        loja=f.get("customfield_14954",{}).get("value","Loja Desconhecida")
        agrup[loja].append({
            "key": issue.get("key"),
            "status": f.get("status",{}).get("name","--"),
            "pdv": f.get("customfield_14829","--"),
            "ativo": f.get("customfield_14825",{}).get("value","--"),
            "problema": f.get("customfield_12374","--"),
            "endereco": f.get("customfield_12271","--"),
            "estado": f.get("customfield_11948",{}).get("value","--"),
            "cep": f.get("customfield_11993","--"),
            "cidade": f.get("customfield_11994","--"),
            "data_agendada": f.get("customfield_12036")
        })
    return agrup

def group_title_with_badge(base, status_name):
    cls={"AGENDAMENTO":"pending","AGENDADO":"scheduled","TEC-CAMPO":"tec"}.get(status_name.upper(),"info")
    return f'<div class="group-title"><span>{base}</span>{badge(status_name,cls)}</div>'

def count_pdv_desktop(dets):
    qtd_pdv = sum(1 for d in dets if not is_desktop(d.get("pdv"), d.get("ativo")))
    return qtd_pdv, len(dets)-qtd_pdv

# ========= JIRA / CACHE =========
jira = JiraAPI(st.secrets["EMAIL"], st.secrets["API_TOKEN"], "https://delfia.atlassian.net")

FIELDS = (
    "summary,status,customfield_14954,customfield_14829,customfield_14825,"
    "customfield_12374,customfield_12271,customfield_11993,"
    "customfield_11994,customfield_11948,customfield_12036,customfield_12279"
)

@st.cache_data(ttl=45, show_spinner=False)
def buscar_cached(jql: str, fields: str):
    return jira.buscar_chamados(jql, fields)

def refresh():
    buscar_cached.clear()
    st.session_state["last_pull"] = datetime.now()
    st.rerun()

JQLS = {
    "pend":  'project = FSA AND status = "AGENDAMENTO"',
    "agend": 'project = FSA AND status = "AGENDADO"',
    "tec":   'project = FSA AND status = "TEC-CAMPO"'
}

# ========= SIDEBAR (form minimiza rerun) =========
with st.sidebar:
    st.header("Ações")
    if st.button("🔄 Atualizar agora"): refresh()
    st.caption("Cache: 45s. Evita bater no Jira a cada interação.")

    st.markdown("---")
    st.header("Filtros")
    with st.form("form_filtros"):
        filtro_txt = st.text_input("Filtro global", value=st.session_state.get("flt",""))
        loja_escolhida = st.text_input("Filtrar por Loja", value=st.session_state.get("loja",""))
        if st.form_submit_button("Aplicar filtros"):
            st.session_state["flt"] = filtro_txt
            st.session_state["loja"] = loja_escolhida
            st.rerun()

# ========= FETCH (único ponto de rede) =========
with st.spinner("Carregando dados do Jira..."):
    pend_raw = buscar_cached(JQLS["pend"], FIELDS)
    agnd_raw = buscar_cached(JQLS["agend"], FIELDS)
    tec_raw  = buscar_cached(JQLS["tec"], FIELDS)

pend = agrupar_por_loja(pend_raw)
agnd = agrupar_por_loja(agnd_raw)
tec  = agrupar_por_loja(tec_raw)

# ========= HEADER =========
st.markdown(
    f"""<div class="head-pill">
        <strong>📱 Painel Field Service</strong>
        {badge("PENDENTE","pending")}{badge("AGENDADO","scheduled")}{badge("TEC-CAMPO","tec")}
        <span class="kicker">Último pull: {st.session_state.get('last_pull', datetime.now()):%d/%m %H:%M:%S}</span>
    </div>""",
    unsafe_allow_html=True
)

tab1, tab2, tab3, tab4 = st.tabs(["PENDENTES", "AGENDADOS", "TEC-CAMPO", "KANBAN"])

# ========= RENDER FRAGMENTOS (evita rerender desnecessário) =========
@st.fragment  # streamlit>=1.28
def render_lista_por_loja(status_nome, agrup):
    if not agrup:
        st.info(f"Nenhum chamado em {status_nome}.")
        return
    def get_data_str(it):
        dt = parse_dt(it.get("data_agendada"))
        return dt.strftime("%d/%m/%Y") if dt else "Sem Data"

    # PENDENTES: sem data
    if status_nome == "AGENDAMENTO":
        for loja in sorted(agrup):
            det = agrup[loja]
            if st.session_state.get("loja") and st.session_state["loja"] not in str(loja): continue
            if st.session_state.get("flt"):
                det = [d for d in det if st.session_state["flt"].lower() in json.dumps(d, ensure_ascii=False).lower()]
            qtd_pdv,qtd_dsk = count_pdv_desktop(det)
            header = group_title_with_badge(f"{loja} — {len(det)} chamado(s)", "PENDENTE")
            with st.expander(f"{loja} — {len(det)} chamado(s)", expanded=False):
                st.markdown(header, unsafe_allow_html=True)
                st.caption(header_badges(len(det), qtd_pdv, qtd_dsk))
                st.markdown(f"<div class='codebox'>{format_whatsapp_block(loja, det)}</div>", unsafe_allow_html=True)
        return

    # AGENDADO / TEC‑CAMPO: por data
    grouped = defaultdict(lambda: defaultdict(list))
    for loja, items in agrup.items():
        for it in items:
            grouped[get_data_str(it)][loja].append(it)

    for data_str, lojas in sorted(grouped.items()):
        total = sum(len(v) for v in lojas.values())
        st.subheader(f"{data_str} — {total} chamado(s)")
        for loja in sorted(lojas):
            det = lojas[loja]
            if st.session_state.get("loja") and st.session_state["loja"] not in str(loja): continue
            if st.session_state.get("flt"):
                det = [d for d in det if st.session_state["flt"].lower() in json.dumps(d, ensure_ascii=False).lower()]
            qtd_pdv,qtd_dsk = count_pdv_desktop(det)
            header = group_title_with_badge(f"{loja} — {len(det)} chamado(s)", status_nome)
            with st.expander(f"{loja} — {len(det)} chamado(s)", expanded=False):
                st.markdown(header, unsafe_allow_html=True)
                dup_keys=[d["key"] for d in det if (d["pdv"], d["ativo"]) in verificar_duplicidade(det)]
                st.caption(header_badges(len(det), qtd_pdv, qtd_dsk, tem_dup=bool(dup_keys)))
                st.markdown(f"**FSAs:** {', '.join(d['key'] for d in det)}")
                st.markdown(f"<div class='codebox'>{format_whatsapp_block(loja, det)}</div>", unsafe_allow_html=True)

with tab1: render_lista_por_loja("AGENDAMENTO", pend)
with tab2: render_lista_por_loja("AGENDADO", agnd)
with tab3: render_lista_por_loja("TEC-CAMPO", tec)

with tab4:
    if not HAS_SORTABLES:
        st.error("Instale: streamlit-sortables==0.3.1")
    else:
        def items_from(agrup):
           return [f"{d['key']} | {loja}" for loja, dets in agrup.items() for d in dets]


        col1_items, col2_items, col3_items = items_from(pend), items_from(agnd), items_from(tec)
        cols = st.columns(3)
        with cols[0]: st.markdown(badge("AGENDAMENTO","pending"), unsafe_allow_html=True)
        with cols[1]: st.markdown(badge("AGENDADO","scheduled"), unsafe_allow_html=True)
        with cols[2]: st.markdown(badge("TEC-CAMPO","tec"), unsafe_allow_html=True)

        result = sort_items(
            [col1_items, col2_items, col3_items],
            multi_containers=True, direction="vertical", use_drag_handle=True,
            styles={"container":{"background":"#0B0F14","minHeight":"260px","padding":"6px"},
                    "ghost":{"opacity":0.2}},
            key="kanban-v1"
        )

        if st.button("Aplicar mudanças"):
            transition_targets={0:"AGENDAMENTO",1:"AGENDADO",2:"TEC-CAMPO"}
            moved=0
            for col_idx, cards in enumerate(result):
                alvo=transition_targets[col_idx]
                for card in cards:
                    key=card.split("|")[0].strip()
                    trans=jira.get_transitions(key)
                    tid=next((t["id"] for t in trans if t.get("to",{}).get("name","").upper()==alvo),None)
                    if tid and jira.transicionar_status(key, tid).status_code==204:
                        moved+=1
            st.success(f"Transições aplicadas: {moved}")
            refresh()

st.markdown("---")
st.caption(f"Última atualização: {datetime.now():%d/%m/%Y %H:%M:%S}")
