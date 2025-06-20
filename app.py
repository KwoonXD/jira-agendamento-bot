import streamlit as st
from streamlit_autorefresh import st_autorefresh
from datetime import datetime
from collections import defaultdict
import pandas as pd
import calendar

# ── AUTENTICAÇÃO SIMPLES ──────────────────────────────────────────────────────
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🔒 Login Necessário")
    user = st.text_input("Usuário")
    pwd  = st.text_input("Senha", type="password")
    if st.button("Entrar"):
        if user == "admwt" and pwd == "suporte#wt2025":
            st.session_state.authenticated = True
        else:
            st.error("Usuário ou senha incorretos")
    st.stop()

# ── SIDEBAR: LOGOUT / REFRESH / UNDO ──────────────────────────────────────────
with st.sidebar:
    if st.button("🔓 Sair"):
        st.session_state.authenticated = False
        st.experimental_rerun()
    if st.button("🔄 Atualizar"):
        st.experimental_rerun()
    st.markdown("---")
    st.header("↩️ Desfazer")
    if st.button("Desfazer última ação"):
        history = st.session_state.get("history", [])
        if history:
            act = history.pop()
            from utils.jira_api import JiraAPI
            jira = JiraAPI(st.secrets["EMAIL"], st.secrets["API_TOKEN"], "https://delfia.atlassian.net")
            for key, prev in zip(act["keys"], act["prev_fields"]):
                jira.transicionar_status(key, None, fields=prev)
            st.success("Última ação desfeita")
        else:
            st.info("Nada a desfazer.")

# ── IMPORTS DO PAINEL ─────────────────────────────────────────────────────────
from utils.jira_api import JiraAPI
from utils.messages import gerar_mensagem, verificar_duplicidade

# ── CONFIGURAÇÕES GERAIS ─────────────────────────────────────────────────────
st.set_page_config(page_title="Painel Field Service", layout="wide")
st_autorefresh(interval=90_000, key="auto_refresh")

if "history" not in st.session_state:
    st.session_state.history = []

jira = JiraAPI(st.secrets["EMAIL"], st.secrets["API_TOKEN"], "https://delfia.atlassian.net")

FIELDS = (
    "summary,customfield_14954,customfield_14829,customfield_14825,"
    "customfield_12374,customfield_12271,customfield_11993,"
    "customfield_11994,customfield_11948,customfield_12036,customfield_12279"
)

# ── 1) CHAMA PENDENTES ────────────────────────────────────────────────────────
pendentes = jira.buscar_chamados("project = FSA AND status = AGENDAMENTO", FIELDS)
agrup_pend = jira.agrupar_chamados(pendentes)

# ── 2) CHAMA AGENDADOS ───────────────────────────────────────────────────────
agendados = jira.buscar_chamados('project = FSA AND status = AGENDADO', FIELDS)
grouped = defaultdict(lambda: defaultdict(list))
for issue in agendados:
    f    = issue["fields"]
    loja = f.get("customfield_14954", {}).get("value", "Loja Desconhecida")
    raw  = f.get("customfield_12036", "")
    date = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S.%f%z").strftime("%d/%m/%Y") if raw else "Não definida"
    grouped[date][loja].append(issue)

# ── 3) DATAFRAME PARA CALENDÁRIO ─────────────────────────────────────────────
cal_rows = []
for issue in agendados:
    raw = issue["fields"].get("customfield_12036")
    if not raw:
        continue
    dt = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S.%f%z")
    loja = issue["fields"].get("customfield_14954", {}).get("value", "Loja Desconhecida")
    cal_rows.append({"data": dt.date(), "key": issue["key"], "loja": loja})
df_cal = pd.DataFrame(cal_rows)

# ── TABS: LISTA vs CALENDÁRIO ────────────────────────────────────────────────
tab1, tab2 = st.tabs(["📋 Lista", "📆 Calendário"])

with tab1:
    st.title("📱 Field Service — Lista")

    col1, col2 = st.columns(2)
    # PENDENTES
    with col1:
        st.subheader("⏳ Pendentes de Agendamento")
        if not pendentes:
            st.warning("Nenhum chamado PENDENTE.")
        else:
            for loja, lst in agrup_pend.items():
                with st.expander(f"{loja} — {len(lst)} FSAs"):
                    st.code(gerar_mensagem(loja, lst), language="text")

    # AGENDADOS
    with col2:
        st.subheader("📋 Chamados Agendados")
        if not agendados:
            st.info("Nenhum chamado AGENDADO.")
        else:
            for date, stores in sorted(grouped.items()):
                total = sum(len(v) for v in stores.values())
                st.markdown(f"**{date} — {total} FSAs**")
                for loja, lst in sorted(stores.items()):
                    det = jira.agrupar_chamados(lst)[loja]
                    dupk = [d["key"] for d in det if (d["pdv"], d["ativo"]) in verificar_duplicidade(det)]
                    spare = jira.buscar_chamados(
                        f'project = FSA AND status = "Aguardando Spare" AND "Codigo da Loja[Dropdown]" = {loja}',
                        FIELDS
                    )
                    spk = [i["key"] for i in spare]
                    tags = []
                    if spk:
                        tags.append("Spare: " + ", ".join(spk))
                    if dupk:
                        tags.append("Dup: " + ", ".join(dupk))
                    tag_str = f" [{' • '.join(tags)}]" if tags else ""
                    with st.expander(f"{loja} — {len(lst)} FSAs{tag_str}"):
                        st.markdown("**FSAs:** " + ", ".join(d["key"] for d in det))
                        st.code(gerar_mensagem(loja, det), language="text")

with tab2:
    st.title("📆 Calendário Mensal")
    if df_cal.empty:
        st.info("Nenhum agendamento com data definida.")
    else:
        hoje = datetime.now()
        anos = sorted({d.year for d in df_cal["data"]})
        meses = list(range(1, 13))
        sel_ano = st.selectbox("Ano:", anos, index=anos.index(hoje.year))
        sel_mes = st.selectbox("Mês:", meses, index=hoje.month - 1)
        st.markdown(f"### {calendar.month_name[sel_mes]} {sel_ano}")

        df_mes = df_cal[df_cal["data"].apply(lambda d: d.year == sel_ano and d.month == sel_mes)]
        cal = calendar.Calendar(firstweekday=6)
        html = "<table style='width:100%;border-collapse:collapse'>"
        html += "<tr>" + "".join(
            f"<th style='border:1px solid #444;padding:4px;background:#333;color:#fff'>{d}</th>"
            for d in ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"]
        ) + "</tr>"

        for week in cal.monthdayscalendar(sel_ano, sel_mes):
            html += "<tr>"
            for day in week:
                if day == 0:
                    html += "<td style='border:1px solid #444;padding:12px;background:#222'></td>"
                else:
                    dt = datetime(sel_ano, sel_mes, day).date()
                    subset = df_mes[df_mes["data"] == dt]
                    cnt = len(subset)
                    badge = (
                        f"<div title='FSAs: {', '.join(subset['key'])}' "
                        f"style='background:{'#28a745' if cnt>0 else '#444'};"
                        "color:#fff;padding:4px;border-radius:4px;text-align:center'>"
                        f"{cnt} FSAs</div>"
                    )
                    bars = "".join(
                        "<span style='display:inline-block;width:8px;height:8px;margin:1px;"
                        "background:#888;border-radius:2px'"
                        f"title='{r['key']} ({r['loja']})'></span>"
                        for _, r in subset.iterrows()
                    )
                    html += (
                        f"<td style='border:1px solid #444;padding:8px;vertical-align:top'>"
                        f"<div style='font-size:14px;color:#ccc'>{day}</div>"
                        f"{badge}<div style='margin-top:4px'>{bars}</div></td>"
                    )
            html += "</tr>"
        html += "</table>"
        st.markdown(html, unsafe_allow_html=True)

        dias = sorted(df_mes["data"].unique())
        sel = st.selectbox("Ver detalhes do dia:", [d.strftime("%d/%m/%Y") for d in dias])
        if sel:
            dt_sel = datetime.strptime(sel, "%d/%m/%Y").date()
            sel_issues = [
                i for i in agendados
                if i["fields"].get("customfield_12036") and
                   datetime.strptime(i["fields"]["customfield_12036"], "%Y-%m-%dT%H:%M:%S.%f%z").date() == dt_sel
            ]
            st.markdown(f"#### Chamados em {sel}")
            dets = jira.agrupar_chamados(sel_issues)
            for loja, lst in dets.items():
                with st.expander(f"{loja} — {len(lst)} FSAs"):
                    st.code(gerar_mensagem(loja, lst), language="text")

# ── RODAPÉ ───────────────────────────────────────────────────────────────────
st.markdown("---")
st.caption(f"Última atualização: {datetime.now():%d/%m/%Y %H:%M:%S}")
