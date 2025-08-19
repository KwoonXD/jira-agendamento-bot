# streamlit_app.py
import streamlit as st
from streamlit_autorefresh import st_autorefresh
from datetime import datetime
from collections import defaultdict

from utils.jira_api import JiraAPI
from utils.messages import gerar_mensagem, verificar_duplicidade

# ──────────────────────────────────────────────────────────────────────────────
# Configuração básica
# ──────────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Painel Field Service", layout="wide")
st_autorefresh(interval=90_000, key="auto_refresh")

# CSS leve para polir a UI (pílulas, cartões e tipografia)
st.markdown(
    """
    <style>
      .pill {
        display:inline-block; padding:4px 10px; border-radius:999px;
        font-weight:600; font-size:12px; margin-left:8px; white-space:nowrap;
      }
      .pill-pend    {background:#FFB84D22; color:#FFB84D;}
      .pill-sched   {background:#2ECC7022; color:#2ECC70;}
      .pill-tec     {background:#3498DB22; color:#3498DB;}
      .caps { letter-spacing: .04em; font-weight:700; font-size:.85rem; opacity:.8 }

      .small-muted { color:#999; font-size:12px}

      .card {
        background: #111418;
        border: 1px solid #202632;
        border-radius: 12px;
        padding: 14px 16px;
      }

      .expander > div > div { padding-top:0!important; }
      .metric-row { display:flex; gap:10px; align-items:center; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ──────────────────────────────────────────────────────────────────────────────
# Helpers visuais
# ──────────────────────────────────────────────────────────────────────────────
def _title_with_pill(title: str, pill_txt: str = "", pill_kind: str = "") -> str:
    pill = f'<span class="pill pill-{pill_kind}">{pill_txt}</span>' if pill_txt else ""
    return f"<div class='metric-row'><h3 style='margin:0'>{title}</h3>{pill}</div>"

def _expander_title(loja: str, qtd: int, tags=None) -> str:
    meta = []
    if tags:
        meta.append(" • ".join(tags))
    right = f"{qtd} chamado(s)" + (f" — {' | '.join(meta)}" if meta else "")
    return f"<b>{loja}</b> <span class='small-muted'>— {right}</span>"

def _date_title(dt_str: str, total: int) -> str:
    return f"<h4 style='margin:.25rem 0 .5rem 0'>{dt_str} <span class='small-muted'>— {total} chamado(s)</span></h4>"

# ──────────────────────────────────────────────────────────────────────────────
# Estado (desfazer)
# ──────────────────────────────────────────────────────────────────────────────
if "history" not in st.session_state:
    st.session_state.history = []

# ──────────────────────────────────────────────────────────────────────────────
# Jira API
# ──────────────────────────────────────────────────────────────────────────────
jira = JiraAPI(
    st.secrets["EMAIL"],
    st.secrets["API_TOKEN"],
    "https://delfia.atlassian.net",
)

FIELDS = (
    "summary,customfield_14954,customfield_14829,customfield_14825,"
    "customfield_12374,customfield_12271,customfield_11993,"
    "customfield_11994,customfield_11948,customfield_12036,customfield_12279"
)

# ──────────────────────────────────────────────────────────────────────────────
# Busca de dados
# ──────────────────────────────────────────────────────────────────────────────
pendentes_raw = jira.buscar_chamados('project = FSA AND status = "AGENDAMENTO"', FIELDS)
agrup_pend    = jira.agrupar_chamados(pendentes_raw)

agendados_raw = jira.buscar_chamados('project = FSA AND status = "AGENDADO"', FIELDS)
grouped_sched = defaultdict(lambda: defaultdict(list))
for issue in agendados_raw:
    f    = issue["fields"]
    loja = f.get("customfield_14954", {}).get("value", "Loja Desconhecida")
    raw  = f.get("customfield_12036")
    data_str = (
        datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S.%f%z").strftime("%d/%m/%Y")
        if raw else "Sem data"
    )
    grouped_sched[data_str][loja].append(issue)

raw_by_loja = defaultdict(list)
for i in pendentes_raw + agendados_raw:
    loja = i["fields"].get("customfield_14954",{}).get("value","Loja Desconhecida")
    raw_by_loja[loja].append(i)

# ──────────────────────────────────────────────────────────────────────────────
# Sidebar: ações & transições
# ──────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("#### Ações")
    if st.button("↩️ Desfazer última ação"):
        if st.session_state.history:
            action = st.session_state.history.pop()
            reverted = 0
            for key in action["keys"]:
                trans = jira.get_transitions(key)
                rev_id = next(
                    (t["id"] for t in trans if t.get("to",{}).get("name")==action["from"]),
                    None
                )
                if rev_id and jira.transicionar_status(key, rev_id).status_code == 204:
                    reverted += 1
            st.success(f"Revertido: {reverted} FSAs → {action['from']}")
        else:
            st.info("Nenhuma ação para desfazer.")

    st.markdown("---")
    st.markdown('<span class="caps">TRANSIÇÃO DE CHAMADOS</span>', unsafe_allow_html=True)

    lojas_pend = set(agrup_pend)
    lojas_age  = set()
    if grouped_sched:
        for stores in grouped_sched.values():
            lojas_age |= set(stores)
    lojas = sorted(lojas_pend | lojas_age)

    loja_sel = st.selectbox("Loja", ["—"] + lojas)
    if loja_sel != "—":
        em_campo = st.checkbox("Técnico em campo? (agendar + mover tudo)")

        if em_campo:
            st.markdown('<span class="caps">DADOS DE AGENDAMENTO</span>', unsafe_allow_html=True)
            data    = st.date_input("Data")
            hora    = st.time_input("Hora")
            tecnico = st.text_input("Técnicos (Nome-CPF-RG-TEL)")

            dt_iso = datetime.combine(data, hora).strftime("%Y-%m-%dT%H:%M:%S.000-0300")
            extra_ag = {"customfield_12036": dt_iso}
            if tecnico:
                extra_ag["customfield_12279"] = {
                    "type":"doc","version":1,
                    "content":[{"type":"paragraph","content":[{"type":"text","text":tecnico}]}]
                }

            keys_pend  = [i["key"] for i in pendentes_raw  if i["fields"].get("customfield_14954",{}).get("value")==loja_sel]
            keys_sched = [i["key"] for i in agendados_raw if i["fields"].get("customfield_14954",{}).get("value")==loja_sel]
            all_keys   = keys_pend + keys_sched

            if st.button(f"Agendar e mover {len(all_keys)} FSAs → TEC-CAMPO"):
                errors=[]; moved=0
                # a) agendar pendentes
                for k in keys_pend:
                    trans = jira.get_transitions(k)
                    agid  = next((t["id"] for t in trans if "agend" in t["name"].lower()),None)
                    if agid:
                        r= jira.transicionar_status(k, agid, fields=extra_ag)
                        if r.status_code!=204: errors.append(f"{k} ⏳ {r.status_code}")
                # b) mover todos
                for k in all_keys:
                    trans = jira.get_transitions(k)
                    tcid = next((t["id"] for t in trans if "tec-campo" in t.get("to",{}).get("name","").lower()),None)
                    if tcid:
                        r= jira.transicionar_status(k, tcid)
                        if r.status_code==204: moved+=1
                        else: errors.append(f"{k} ➡️ {r.status_code}")

                if errors:
                    st.error("Ocorreram erros:")
                    for e in errors: st.code(e)
                else:
                    st.success(f"{len(all_keys)} FSAs agendados e movidos → TEC-CAMPO")
                    st.session_state.history.append({"keys":all_keys,"from":"AGENDADO"})

                    detalhes_por_loja = jira.agrupar_chamados(raw_by_loja[loja_sel])[loja_sel]
                    novos   = [d for d in detalhes_por_loja if d["key"] in keys_pend]
                    antigos = [d for d in detalhes_por_loja if d["key"] in keys_sched]

                    if novos:
                        st.markdown(_title_with_pill("🆕 Novos Agendados", "AGENDADO", "sched"), unsafe_allow_html=True)
                        st.code(gerar_mensagem(loja_sel, novos), language="text")

                    if antigos:
                        st.markdown(_title_with_pill("📋 Já Agendados"), unsafe_allow_html=True)
                        st.code(gerar_mensagem(loja_sel, antigos), language="text")

        else:
            opts = [i["key"] for i in pendentes_raw if i["fields"].get("customfield_14954",{}).get("value")==loja_sel]
            opts+= [i["key"] for i in agendados_raw if i["fields"].get("customfield_14954",{}).get("value")==loja_sel]
            sel = st.multiselect("Selecionar FSAs:", sorted(set(opts)))

            extra = {}; choice=None; trans_opts={}
            if sel:
                trans_opts={t["name"]:t["id"] for t in jira.get_transitions(sel[0])}
                choice=st.selectbox("Transição",["—"]+list(trans_opts))
                if choice and "agend" in choice.lower():
                    st.markdown('<span class="caps">DADOS DE AGENDAMENTO</span>', unsafe_allow_html=True)
                    d=st.date_input("Data"); h=st.time_input("Hora")
                    tec=st.text_input("Técnicos (Nome-CPF-RG-TEL)")
                    iso=datetime.combine(d,h).strftime("%Y-%m-%dT%H:%M:%S.000-0300")
                    extra["customfield_12036"]=iso
                    if tec:
                        extra["customfield_12279"]={
                            "type":"doc","version":1,
                            "content":[{"type":"paragraph","content":[{"type":"text","text":tec}]}]
                        }

            if st.button("Aplicar"):
                if not sel or choice in (None,"—"):
                    st.warning("Selecione FSAs e uma transição.")
                else:
                    prev=jira.get_issue(sel[0])["fields"]["status"]["name"]
                    errs=[]; mv=0
                    for k in sel:
                        r=jira.transicionar_status(k,trans_opts[choice],fields=extra or None)
                        if r.status_code==204: mv+=1
                        else: errs.append(f"{k}:{r.status_code}")
                    if errs:
                        st.error("Falhas:")
                        for e in errs: st.code(e)
                    else:
                        st.success(f"{mv} FSAs movidos → {choice}")
                        st.session_state.history.append({"keys":sel,"from":prev})

# ──────────────────────────────────────────────────────────────────────────────
# Conteúdo principal
# ──────────────────────────────────────────────────────────────────────────────
st.markdown(_title_with_pill("Painel Field Service"), unsafe_allow_html=True)
col1,col2=st.columns(2, gap="large")

# PENDENTES
with col1:
    st.markdown(_title_with_pill("⏳ PENDENTES", "AGENDAMENTO", "pend"), unsafe_allow_html=True)
    if not pendentes_raw:
        st.info("Nenhum chamado em AGENDAMENTO.")
    else:
        for loja,iss in sorted(agrup_pend.items(), key=lambda x: x[0]):
            with st.expander(_expander_title(loja, len(iss)), expanded=False):
                st.code(gerar_mensagem(loja,iss), language="text")

# AGENDADOS
with col2:
    st.markdown(_title_with_pill("📋 AGENDADOS", "AGENDADO", "sched"), unsafe_allow_html=True)
    if not agendados_raw:
        st.info("Nenhum chamado em AGENDADO.")
    else:
        for date, stores in sorted(grouped_sched.items()):
            total=sum(len(v) for v in stores.values())
            st.markdown(_date_title(date, total), unsafe_allow_html=True)

            for loja,iss in sorted(stores.items()):
                detalhes=jira.agrupar_chamados(iss)[loja]

                duplicate_pairs = verificar_duplicidade(detalhes)
                dup_keys = [d["key"] for d in detalhes if (d["pdv"],d["ativo"]) in duplicate_pairs]

                spare_raw=jira.buscar_chamados(
                    f'project = FSA AND status = "Aguardando Spare" AND "Codigo da Loja[Dropdown]" = {loja}',
                    FIELDS
                )
                spare_keys=[i["key"] for i in spare_raw]

                tags=[]
                if spare_keys: tags.append("Spare: "+", ".join(spare_keys))
                if dup_keys:   tags.append("Dup: "+", ".join(dup_keys))

                with st.expander(_expander_title(loja, len(iss), tags=tags), expanded=False):
                    st.markdown("**FSAs:** " + ", ".join(d["key"] for d in detalhes))
                    st.code(gerar_mensagem(loja,detalhes), language="text")

st.markdown("---")
st.caption(f"Última atualização: {datetime.now():%d/%m/%Y %H:%M:%S}")
