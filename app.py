import streamlit as st
from streamlit_autorefresh import st_autorefresh
from datetime import datetime
from collections import defaultdict
import pandas as pd
import calendar

from utils.jira_api import JiraAPI
from utils.messages import gerar_mensagem, verificar_duplicidade

# ── LOGIN SIMPLES ─────────────────────────────────────────────────────────────
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🔒 Login Necessário")
    user = st.text_input("Usuário")
    pwd  = st.text_input("Senha", type="password")
    if st.button("Entrar"):
        if user.strip() == "admwt" and pwd.strip() == "suporte#wt2025":
            st.session_state.authenticated = True
            st.success("Bem-vindo!")
        else:
            st.error("Credenciais inválidas")
    st.stop()

# ── CONFIGURAÇÃO DA PÁGINA & AUTO-REFRESH ─────────────────────────────────────
st.set_page_config(page_title="Painel Field Service", layout="wide")
st_autorefresh(interval=90_000, key="auto_refresh")  # 1m30s

# ── INSTÂNCIA JIRA ─────────────────────────────────────────────────────────────
jira = JiraAPI(st.secrets["EMAIL"], st.secrets["API_TOKEN"], "https://delfia.atlassian.net")

# ── SIDEBAR: LOGOUT, VISÃO, REFRESH, UNDO, TRANSIÇÕES ─────────────────────────
with st.sidebar:
    if st.button("🔓 Sair"):
        st.session_state.authenticated = False
        st.experimental_rerun()

    st.markdown("## 📊 Visão")
    view = st.radio("", ["Lista", "Calendário"])

    if st.button("🔄 Atualizar"):
        pass  # auto-refresh já cuida

    st.markdown("---")
    st.header("↩️ Desfazer última ação")
    if st.button("Desfazer"):
        history = st.session_state.get("history", [])
        if history:
            act = history.pop()
            for key, prev in zip(act["keys"], act["prev_fields"]):
                jira.transicionar_status(key, None, fields=prev)
            st.success("Última ação desfeita")
        else:
            st.info("Nada a desfazer")

    st.markdown("---")
    st.header("▶️ Transição de Chamados")
    F_SIMPLE = "summary,customfield_14954,customfield_12036,customfield_12279"
    pend = jira.buscar_chamados("project = FSA AND status = AGENDAMENTO", F_SIMPLE)
    age  = jira.buscar_chamados('project = FSA AND status = AGENDADO',    F_SIMPLE)

    by_store = defaultdict(list)
    for i in pend + age:
        loja = i["fields"].get("customfield_14954",{}).get("value","—")
        by_store[loja].append(i)

    loja_sel = st.selectbox("Loja:", ["—"] + sorted(by_store))
    if loja_sel != "—":
        keys = [i["key"] for i in by_store[loja_sel]]
        sel  = st.multiselect("FSAs:", keys)
        if sel:
            trans = jira.get_transitions(sel[0])
            opts  = {t["name"]: t["id"] for t in trans}
            choice = st.selectbox("Transição:", ["—"] + list(opts))
            extra = {}
            if choice.lower().startswith("agend"):
                dt = st.date_input("Data do Agendamento")
                tm = st.time_input("Hora do Agendamento")
                te = st.text_input("Técnico (Nome-CPF-RG-TEL)")
                iso = datetime.combine(dt, tm).strftime("%Y-%m-%dT%H:%M:%S.000-0300")
                extra["customfield_12036"] = iso
                if te:
                    extra["customfield_12279"] = {
                      "type":"doc","version":1,
                      "content":[{"type":"paragraph","content":[{"type":"text","text":te}]}]
                    }
            if st.button("Aplicar"):
                prevs = []
                for k in sel:
                    old = jira.buscar_chamados(f'issue = {k}', F_SIMPLE)[0]["fields"]
                    prevs.append(old)
                    jira.transicionar_status(k, opts[choice], fields=extra or None)
                st.session_state.history = st.session_state.get("history",[])
                st.session_state.history.append({"keys":sel,"prev_fields":prevs})
                st.success(f"{len(sel)} FSAs movidos → {choice}")

# ── BUSCA COMPLETA DE CHAMADOS ─────────────────────────────────────────────────
FIELDS_FULL = (
    "summary,customfield_14954,customfield_14829,customfield_14825,"
    "customfield_12374,customfield_12271,customfield_11993,"
    "customfield_11994,customfield_11948,customfield_12036"
)
pendentes = jira.buscar_chamados("project = FSA AND status = AGENDAMENTO", FIELDS_FULL)
agendados = jira.buscar_chamados('project = FSA AND status = AGENDADO',    FIELDS_FULL)

agrup_pend = jira.agrupar_chamados(pendentes)

grouped   = defaultdict(lambda: defaultdict(list))
for i in agendados:
    f    = i["fields"]
    loja = f.get("customfield_14954",{}).get("value","Loja")
    raw  = f.get("customfield_12036","")
    date = (datetime.strptime(raw,"%Y-%m-%dT%H:%M:%S.%f%z")
            .strftime("%d/%m/%Y") if raw else "Não definida")
    grouped[date][loja].append(i)

# ── PREPARA DADOS PARA CALENDÁRIO ───────────────────────────────────────────────
cal_rows = []
stores   = []
for i in agendados:
    raw = i["fields"].get("customfield_12036")
    if not raw: continue
    dt   = datetime.strptime(raw,"%Y-%m-%dT%H:%M:%S.%f%z")
    loja = i["fields"].get("customfield_14954",{}).get("value","Loja")
    cal_rows.append({"data":dt.date(),"key":i["key"],"loja":loja})
    stores.append(loja)

df_cal = pd.DataFrame(cal_rows)
unique_lojas = sorted(set(stores))
palette = px.colors.qualitative.Plotly
color_map = {l: palette[i%len(palette)] for i,l in enumerate(unique_lojas)}

# ── RENDERIZAÇÃO PRINCIPAL ─────────────────────────────────────────────────────
st.title("📱 Painel Field Service")

if view == "Lista":
    col1, col2 = st.columns(2)

    # PENDENTES
    with col1:
        st.header("⏳ Pendentes de Agendamento")
        if not pendentes:
            st.warning("Nenhum pendente.")
        else:
            for loja, lst in agrup_pend.items():
                with st.expander(f"{loja} — {len(lst)} FSAs"):
                    st.code(gerar_mensagem(loja, lst), language="text")

    # AGENDADOS
    with col2:
        st.header("📋 Chamados AGENDADOS")
        if not agendados:
            st.info("Nenhum agendado.")
        else:
            for date, stores in sorted(grouped.items()):
                total = sum(len(v) for v in stores.values())
                st.subheader(f"{date} — {total} FSAs")
                for loja, lst in stores.items():
                    det   = jira.agrupar_chamados(lst)[loja]
                    dup   = [d["key"] for d in det
                             if (d["pdv"],d["ativo"]) in verificar_duplicidade(det)]
                    spare = jira.buscar_chamados(
                        f'project = FSA AND status = "Aguardando Spare" '
                        f'AND "Codigo da Loja[Dropdown]" = {loja}',
                        FIELDS_FULL
                    )
                    spk = [x["key"] for x in spare]
                    tags=[]
                    if spk: tags.append("Spare: "+", ".join(spk))
                    if dup: tags.append("Dup: "+", ".join(dup))
                    tag_str = f" [{' • '.join(tags)}]" if tags else ""
                    with st.expander(f"{loja} — {len(lst)} FSAs{tag_str}"):
                        st.markdown("**FSAs:** "+", ".join(d["key"] for d in det))
                        st.code(gerar_mensagem(loja, det), language="text")

elif view == "Calendário":
    st.header("📆 Calendário Mensal de Agendamentos")
    if df_cal.empty:
        st.info("Nenhum agendamento definido.")
    else:
        hoje  = datetime.now()
        anos  = sorted({d.year for d in df_cal["data"]})
        meses = list(range(1,13))
        sel_ano = st.selectbox("Ano:", anos, index=anos.index(hoje.year))
        sel_mes = st.selectbox("Mês:", meses, index=hoje.month-1)
        st.markdown(f"### {calendar.month_name[sel_mes]} {sel_ano}")

        df_mes = df_cal[df_cal["data"].apply(lambda d:d.year==sel_ano and d.month==sel_mes)]
        cal = calendar.Calendar(firstweekday=6)

        # Gera tabela HTML com contagem e barras
        html = "<table style='border-collapse:collapse;width:100%'>"
        html += "<tr>" + "".join(
            f"<th style='border:1px solid #444;padding:4px;"
            f"background:#333;color:#fff'>{d}</th>"
            for d in ["Dom","Seg","Ter","Qua","Qui","Sex","Sáb"]
        ) + "</tr>"

        for week in cal.monthdayscalendar(sel_ano,sel_mes):
            html += "<tr>"
            for day in week:
                if day==0:
                    html += ("<td style='border:1px solid #444;"
                             "padding:12px;background:#222'></td>")
                else:
                    data_atual = datetime(sel_ano,sel_mes,day).date()
                    subset = df_mes[df_mes["data"]==data_atual]
                    cnt = len(subset)

                    color = "#28a745" if cnt>0 else "#444"
                    badge = (
                        f"<div title='FSAs: {', '.join(subset['key'])}' "
                        f"style='background:{color};color:#fff;"
                        "padding:4px;border-radius:4px;text-align:center;'>"
                        f"{cnt} FSAs</div>"
                    )
                    bars = "".join(
                        f"<span title='{r['key']} ({r['loja']})' "
                        f"style='display:inline-block;width:8px;"
                        f"height:8px;margin:1px;background:{color_map[r['loja']]};"
                        "border-radius:2px;'></span>"
                        for _,r in subset.iterrows()
                    )

                    html += (
                        "<td style='border:1px solid #444;padding:8px;"
                        "vertical-align:top;'>"
                        f"<div style='font-size:14px;color:#ccc'>{day}</div>"
                        f"{badge}<div style='margin-top:4px'>{bars}</div>"
                        "</td>"
                    )
            html += "</tr>"
        html += "</table>"
        st.markdown(html, unsafe_allow_html=True)

        dias = sorted(df_mes["data"].unique())
        sel = st.selectbox("Ver detalhes do dia:", [d.strftime("%d/%m/%Y") for d in dias])
        if sel:
            dt_sel = datetime.strptime(sel,"%d/%m/%Y").date()
            issues_sel = [
                i for i in agendados
                if i["fields"].get("customfield_12036")
                and datetime.strptime(
                    i["fields"]["customfield_12036"], "%Y-%m-%dT%H:%M:%S.%f%z"
                ).date() == dt_sel
            ]
            st.markdown(f"#### Chamados em {sel}")
            dets = jira.agrupar_chamados(issues_sel)
            for loja,lst in dets.items():
                with st.expander(f"{loja} — {len(lst)} FSAs"):
                    st.code(gerar_mensagem(loja,lst), language="text")

st.markdown("---")
st.caption(f"Última atualização: {datetime.now():%d/%m/%Y %H:%M:%S}")
