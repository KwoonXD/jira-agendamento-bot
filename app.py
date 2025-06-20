import streamlit as st
from streamlit_autorefresh import st_autorefresh
from datetime import datetime
from collections import defaultdict
import pandas as pd
import calendar

# ── BLOCO DE AUTENTICAÇÃO SIMPLES ─────────────────────────────────────────────
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

# botão de logout
if st.sidebar.button("🔓 Sair"):
    st.session_state.authenticated = False
    # ao logout, apenas recarregamos para mostrar tela de login
    st.experimental_rerun()
# ── FIM DA AUTENTICAÇÃO ───────────────────────────────────────────────────────


# ── IMPORTS DO SEU PAINEL ─────────────────────────────────────────────────────
from utils.jira_api import JiraAPI
from utils.messages import gerar_mensagem, verificar_duplicidade

# ── CONFIGS GERAIS ────────────────────────────────────────────────────────────
st.set_page_config(page_title="Painel Field Service", layout="wide")
st_autorefresh(interval=90_000, key="auto_refresh")  # 90s automático

if "history" not in st.session_state:
    st.session_state.history = []

jira = JiraAPI(
    st.secrets["EMAIL"],
    st.secrets["API_TOKEN"],
    "https://delfia.atlassian.net"
)

FIELDS = (
    "summary,customfield_14954,customfield_14829,customfield_14825,"
    "customfield_12374,customfield_12271,customfield_11993,"
    "customfield_11994,customfield_11948,customfield_12036,customfield_12279"
)


# ── 1) PENDENTES de AGENDAMENTO ───────────────────────────────────────────────
pendentes = jira.buscar_chamados("project = FSA AND status = AGENDAMENTO", FIELDS)
agrup_pend = jira.agrupar_chamados(pendentes)


# ── 2) CHAMADOS AGENDADOS ──────────────────────────────────────────────────────
agendados = jira.buscar_chamados('project = FSA AND status = AGENDADO', FIELDS)
grouped = defaultdict(lambda: defaultdict(list))
for issue in agendados:
    f     = issue["fields"]
    loja  = f.get("customfield_14954", {}).get("value", "Loja Desconhecida")
    raw   = f.get("customfield_12036", "")
    date  = (
        datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S.%f%z")
                .strftime("%d/%m/%Y")
        if raw else "Não definida"
    )
    grouped[date][loja].append(issue)


# ── 3) DADOS DO CALENDÁRIO ────────────────────────────────────────────────────
cal_rows = []
for issue in agendados:
    raw = issue["fields"].get("customfield_12036")
    if not raw:
        continue
    dt = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S.%f%z")
    loja = issue["fields"].get("customfield_14954", {}).get("value", "Loja Desconhecida")
    cal_rows.append({"data": dt.date(), "key": issue["key"], "loja": loja})
df_cal = pd.DataFrame(cal_rows)


# ── SIDEBAR: DESFAZER ─────────────────────────────────────────────────────────
with st.sidebar:
    st.header("🔄 Ações")
    if st.button("↩️ Desfazer última ação"):
        if st.session_state.history:
            act = st.session_state.history.pop()
            for key, prev in zip(act["keys"], act["prev_fields"]):
                jira.transicionar_status(key, None, fields=prev)
            st.success("Última ação desfeita")
        else:
            st.info("Nada a desfazer.")


# ── ABAS: LISTA e CALENDÁRIO ─────────────────────────────────────────────────
tab1, tab2 = st.tabs(["📋 Lista", "📆 Calendário"])

# --- Aba Lista ---
with tab1:
    st.title("📱 Painel Field Service — Lista")

    col1, col2 = st.columns(2)
    # Pendentes
    with col1:
        st.subheader("⏳ Chamados PENDENTES de Agendamento")
        if not pendentes:
            st.warning("Nenhum pendente no momento.")
        else:
            for loja, lst in agrup_pend.items():
                with st.expander(f"{loja} — {len(lst)} FSAs", expanded=False):
                    st.code(gerar_mensagem(loja, lst), language="text")

    # Agendados
    with col2:
        st.subheader("📋 Chamados AGENDADOS")
        if not agendados:
            st.info("Nenhum agendado no momento.")
        else:
            for date, stores in sorted(grouped.items()):
                total = sum(len(v) for v in stores.values())
                st.markdown(f"**{date} — {total} FSAs**")
                for loja, lst in sorted(stores.items()):
                    detalhes = jira.agrupar_chamados(lst)[loja]
                    dup_keys = [d["key"] for d in detalhes if (d["pdv"], d["ativo"]) in verificar_duplicidade(detalhes)]
                    spare_raw = jira.buscar_chamados(
                        f'project = FSA AND status = "Aguardando Spare" AND "Codigo da Loja[Dropdown]" = {loja}',
                        FIELDS
                    )
                    spare_keys = [i["key"] for i in spare_raw]
                    tags = []
                    if spare_keys:
                        tags.append("Spare: " + ", ".join(spare_keys))
                    if dup_keys:
                        tags.append("Dup: " + ", ".join(dup_keys))
                    tag_str = f" [{' • '.join(tags)}]" if tags else ""
                    with st.expander(f"{loja} — {len(lst)} FSAs{tag_str}", expanded=False):
                        st.markdown("**FSAs:** " + ", ".join(d["key"] for d in detalhes))
                        st.code(gerar_mensagem(loja, detalhes), language="text")

# --- Aba Calendário ---
with tab2:
    st.title("📆 Calendário Mensal de Agendamentos")
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
        html = '<table style="border-collapse:collapse;width:100%;">'
        html += '<tr>' + ''.join(
            f'<th style="padding:4px;border:1px solid #444;background:#333;color:#fff">{d}</th>'
            for d in ["Dom","Seg","Ter","Qua","Qui","Sex","Sáb"]
        ) + '</tr>'

        for week in cal.monthdayscalendar(sel_ano, sel_mes):
            html += "<tr>"
            for day in week:
                if day == 0:
                    html += '<td style="padding:12px;border:1px solid #444;background:#222;"></td>'
                else:
                    date_now = datetime(sel_ano, sel_mes, day).date()
                    subset = df_mes[df_mes["data"] == date_now]
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
                        'background:#888;border-radius:2px;"></span>'
                        for _, r in subset.iterrows()
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
        sel_dia = st.selectbox("Ver detalhes do dia:", [d.strftime("%d/%m/%Y") for d in dias])
        if sel_dia:
            dt_sel = datetime.strptime(sel_dia, "%d/%m/%Y").date()
            filtrados = [
                i for i in agendados
                if i["fields"].get("customfield_12036") and
                   datetime.strptime(i["fields"]["customfield_12036"], "%Y-%m-%dT%H:%M:%S.%f%z").date() == dt_sel
            ]
            st.markdown(f"#### Chamados em {sel_dia}")
            detalhados = jira.agrupar_chamados(filtrados)
            for loja, lst in detalhados.items():
                with st.expander(f"{loja} — {len(lst)} FSAs", expanded=True):
                    st.code(gerar_mensagem(loja, lst), language="text")

# ── RODAPÉ ───────────────────────────────────────────────────────────────────
st.markdown("---")
st.caption(f"Última atualização: {datetime.now():%d/%m/%Y %H:%M:%S}")
