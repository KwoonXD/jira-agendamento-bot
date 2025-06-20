import streamlit as st

# ── BLOCO DE AUTENTICAÇÃO SIMPLES ────────────────────────────────────────
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🔒 Login Necessário")
    user = st.text_input("Usuário")
    pwd  = st.text_input("Senha", type="password")
    if st.button("Entrar"):
        if user == "admwt" and pwd == "suporte#wt2025":
            st.session_state.authenticated = True
            st.experimental_rerun()
        else:
            st.error("Usuário ou senha incorretos")
    st.stop()  # impede que o resto do app carregue

# ── FIM DO BLOCO DE AUTENTICAÇÃO ────────────────────────────────────────


# ── A PARTIR DAQUI, O APP JÁ ESTÁ AUTENTICADO ────────────────────────────

# exemplo de logout:
if st.sidebar.button("🔓 Sair"):
    st.session_state.authenticated = False
    st.experimental_rerun()

# ---- O restante do seu código abaixo permanece inalterado ----

from streamlit_autorefresh import st_autorefresh
from datetime import datetime, timedelta
from collections import defaultdict
import pandas as pd
import calendar

from utils.jira_api import JiraAPI
from utils.messages import gerar_mensagem, verificar_duplicidade

# ── Configuração da página e auto‐refresh (90s) ──
st.set_page_config(page_title="Painel Field Service", layout="wide")
st_autorefresh(interval=90_000, key="auto_refresh")

# ── Histórico de undo ──
if "history" not in st.session_state:
    st.session_state.history = []

# ── Inicializa JiraAPI ──
jira = JiraAPI(
    st.secrets["EMAIL"],
    st.secrets["API_TOKEN"],
    "https://delfia.atlassian.net"
)

# ── Quais campos puxar da API ──
FIELDS = (
    "summary,customfield_14954,customfield_14829,customfield_14825,"
    "customfield_12374,customfield_12271,customfield_11993,"
    "customfield_11994,customfield_11948,customfield_12036,customfield_12279"
)

# ── 1) Carrega PENDENTES e agrupa por loja ──
pendentes_raw = jira.buscar_chamados("project = FSA AND status = AGENDAMENTO", FIELDS)
agrup_pend    = jira.agrupar_chamados(pendentes_raw)

# ── 2) Carrega AGENDADOS e agrupa por data → loja ──
agendados_raw = jira.buscar_chamados('project = FSA AND status = AGENDADO', FIELDS)
grouped_sched = defaultdict(lambda: defaultdict(list))
for issue in agendados_raw:
    f    = issue["fields"]
    loja = f.get("customfield_14954",{}).get("value","Loja Desconhecida")
    raw  = f.get("customfield_12036","")
    date = (
        datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S.%f%z")
                .strftime("%d/%m/%Y")
        if raw else "Não definida"
    )
    grouped_sched[date][loja].append(issue)

# ── 3) Prepara df_cal para calendário mensal ──
rows=[]
for issue in agendados_raw:
    raw = issue["fields"].get("customfield_12036")
    if not raw: continue
    dt = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S.%f%z")
    loja = issue["fields"].get("customfield_14954",{}).get("value","Loja Desconhecida")
    rows.append({"data": dt.date(), "key": issue["key"], "loja": loja})
df_cal = pd.DataFrame(rows)

# ── Sidebar: Desfazer e Transição ──
with st.sidebar:
    st.header("Ações")
    if st.button("↩️ Desfazer última ação"):
        if st.session_state.history:
            act = st.session_state.history.pop()
            for key, prev in zip(act["keys"], act["prev_fields"]):
                jira.transicionar_status(key, None, fields=prev)
            st.success("Undo realizado")
        else:
            st.info("Nada a desfazer.")

    st.markdown("---")
    st.header("Transição de Chamados")
    lojas = sorted(set(agrup_pend) | set(grouped_sched.keys()))
    loja_sel = st.selectbox("Loja:", ["—"] + lojas)
    if loja_sel != "—":
        em_campo = st.checkbox("Técnico em campo? (agendar+mover tudo)")
        if em_campo or st.checkbox("Agendar avulso"):
            data = st.date_input("Data Agendamento")
            hora = st.time_input("Hora Agendamento")
            tecnico = st.text_input("Dados Técnico")
            dt_iso = datetime.combine(data,hora).strftime("%Y-%m-%dT%H:%M:%S.000-0300")
            extra = {"customfield_12036": dt_iso}
            if tecnico:
                extra["customfield_12279"] = {
                    "type":"doc","version":1,
                    "content":[{"type":"paragraph","content":[{"type":"text","text":tecnico}]}]
                }
        keys_pend  = [i["key"] for i in pendentes_raw  if i["fields"].get("customfield_14954",{}).get("value")==loja_sel]
        keys_sched = [i["key"] for i in agendados_raw if i["fields"].get("customfield_14954",{}).get("value")==loja_sel]
        all_keys   = keys_pend + keys_sched
        if st.button("Aplicar Transição"):
            prev_fields=[]
            for k in all_keys:
                prev_raw = jira.buscar_chamados(f"key={k}",FIELDS)[0]["fields"]
                prev_fields.append({"customfield_12036": prev_raw.get("customfield_12036","")})
                if k in keys_pend:
                    trans = jira.get_transitions(k)
                    agid = next((t["id"] for t in trans if "agend" in t["name"].lower()),None)
                    if agid: jira.transicionar_status(k,agid,fields=extra)
                trans = jira.get_transitions(k)
                tcid  = next((t["id"] for t in trans if "tec-campo" in t.get("to",{}).get("name","").lower()),None)
                if tcid: jira.transicionar_status(k,tcid)
            st.session_state.history.append({"keys":all_keys,"prev_fields":prev_fields})
            st.success(f"{len(all_keys)} FSAs processadas.")

# ── Abas: Lista e Calendário ──
tab1, tab2 = st.tabs(["📋 Lista","📆 Calendário"])

with tab1:
    st.header("Pendentes")
    if not pendentes_raw:
        st.warning("Nenhum pendente.")
    else:
        for loja, lst in agrup_pend.items():
            with st.expander(f"{loja} — {len(lst)} FSAs", expanded=False):
                st.code(gerar_mensagem(loja, lst), language="text")

    st.header("Agendados")
    if not agendados_raw:
        st.info("Nenhum agendado.")
    else:
        for date, stores in sorted(grouped_sched.items()):
            total = sum(len(v) for v in stores.values())
            st.markdown(f"**{date} — {total} FSAs**")
            for loja, lst in sorted(stores.items()):
                det = jira.agrupar_chamados(lst)[loja]
                dup = verificar_duplicidade(det)
                dupk = [d["key"] for d in det if (d["pdv"],d["ativo"]) in dup]
                spare = jira.buscar_chamados(
                    f'project = FSA AND status="Aguardando Spare" '
                    f'AND "Codigo da Loja[Dropdown]" = {loja}', FIELDS
                )
                spk = [i["key"] for i in spare]
                tags=[]
                if spk: tags.append("Spare: "+", ".join(spk))
                if dupk: tags.append("Dup: "+", ".join(dupk))
                tag_str = f" [{' • '.join(tags)}]" if tags else ""
                with st.expander(f"{loja} — {len(lst)} FSAs{tag_str}", expanded=False):
                    st.markdown("**FSAs:** " + ", ".join(d["key"] for d in det))
                    st.code(gerar_mensagem(loja, det), language="text")

with tab2:
    st.header("Calendário")
    if df_cal.empty:
        st.info("Nenhum agendamento definido.")
    else:
        hoje = datetime.now()
        anos = sorted({d.year for d in df_cal["data"]})
        meses = list(range(1,13))
        sel_ano = st.selectbox("Ano:", anos, index=anos.index(hoje.year))
        sel_mes = st.selectbox("Mês:", meses, index=hoje.month-1)
        st.markdown(f"### {calendar.month_name[sel_mes]} {sel_ano}")

        df_mes = df_cal[df_cal["data"].apply(lambda d: d.year==sel_ano and d.month==sel_mes)]
        cal = calendar.Calendar(firstweekday=6)
        html = '<table style="border-collapse:collapse;width:100%;">'
        html += '<tr>' + ''.join(
            f'<th style="padding:4px;border:1px solid #444;background:#333;color:#fff">{d}</th>'
            for d in ["Dom","Seg","Ter","Qua","Qui","Sex","Sáb"]
        ) + '</tr>'
        for week in cal.monthdayscalendar(sel_ano, sel_mes):
            html += "<tr>"
            for day in week:
                if day==0:
                    html += '<td style="padding:12px;border:1px solid #444;background:#222;"></td>'
                else:
                    date = datetime(sel_ano,sel_mes,day).date()
                    subset = df_mes[df_mes["data"]==date]
                    cnt = len(subset)
                    badge = (
                        f'<div title="FSAs: {", ".join(subset["key"])}" '
                        f'style="background:{"#28a745" if cnt>0 else "#444"};'
                        'color:#fff;padding:4px;border-radius:4px;text-align:center;">'
                        f'{cnt} FSAs</div>'
                    )
                    bars = "".join(
                        f'<span title="{r["key"]} ({r["loja"]})" '
                        'style="display:inline-block;width:8px;height:8px;margin:1px;'
                        f'background:#888;border-radius:2px;"></span>'
                        for _,r in subset.iterrows()
                    )
                    html += (
                        f'<td style="vertical-align:top;padding:8px;border:1px solid #444;">'
                        f'<div style="font-size:14px;color:#ccc">{day}</div>'
                        f'{badge}<div style="margin-top:4px;">{bars}</div></td>'
                    )
            html += "</tr>"
        html += "</table>"
        st.markdown(html, unsafe_allow_html=True)

        dias = sorted(df_mes["data"].unique())
        sel = st.selectbox("Ver detalhes do dia:", [d.strftime("%d/%m/%Y") for d in dias])
        if sel:
            dt_sel = datetime.strptime(sel, "%d/%m/%Y").date()
