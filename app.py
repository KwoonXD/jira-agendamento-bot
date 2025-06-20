import streamlit as st
from streamlit_autorefresh import st_autorefresh
from datetime import datetime, timedelta
from collections import defaultdict
import pandas as pd
import calendar
import plotly.express as px

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
    "customfield_11994,customfield_11948,customfield_12036"
)

# ── 1) Carrega PENDENTES e agrupa por loja ──
pendentes_raw = jira.buscar_chamados("project = FSA AND status = AGENDAMENTO", FIELDS)
agrup_pend    = jira.agrupar_chamados(pendentes_raw)

# ── 2) Carrega AGENDADOS e agrupa por data → loja → lista de issues ──
agendados_raw = jira.buscar_chamados('project = FSA AND status = AGENDADO', FIELDS)
grouped_sched = defaultdict(lambda: defaultdict(list))
for issue in agendados_raw:
    f    = issue["fields"]
    loja = f.get("customfield_14954", {}).get("value", "Loja Desconhecida")
    raw  = f.get("customfield_12036")
    data_str = (
        datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S.%f%z")
                .strftime("%d/%m/%Y")
        if raw else "Não definida"
    )
    grouped_sched[data_str][loja].append(issue)

# ── 3) Prepara linhas para o calendário mensal ──
rows = []
stores = []
for issue in agendados_raw:
    raw = issue["fields"].get("customfield_12036")
    if not raw:
        continue
    dt    = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S.%f%z")
    loja  = issue["fields"].get("customfield_14954", {}).get("value", "Loja Desconhecida")
    rows.append({"data": dt.date(), "key": issue["key"], "loja": loja})
    stores.append(loja)

df_cal = pd.DataFrame(rows)
unique_stores = sorted(set(stores))

# ── Gera um mapa de cores para cada loja ──
palette = px.colors.qualitative.Plotly
color_map = {loja: palette[i % len(palette)] for i, loja in enumerate(unique_stores)}

# ── Sidebar (espaço para ações futuras) ──
with st.sidebar:
    st.header("Ações")
    st.info("Use as abas para ver Lista ou Calendário")

# ── Abas: Lista e Calendário ──
tab_lista, tab_cal = st.tabs(["📋 Lista", "📆 Calendário"])

# ── Aba de Lista ──
with tab_lista:
    st.header("📱 Painel Field Service — Lista")
    c1, c2 = st.columns(2)

    # Pendentes
    with c1:
        st.subheader("⏳ Chamados PENDENTES de Agendamento")
        if not pendentes_raw:
            st.warning("Nenhum chamado em AGENDAMENTO.")
        else:
            for loja, issues in agrup_pend.items():
                with st.expander(f"{loja} — {len(issues)} chamado(s)", expanded=False):
                    st.code(gerar_mensagem(loja, issues), language="text")

    # Agendados
    with c2:
        st.subheader("📋 Chamados AGENDADOS")
        if not agendados_raw:
            st.info("Nenhum chamado em AGENDADO.")
        else:
            for date, stores in sorted(grouped_sched.items()):
                total = sum(len(v) for v in stores.values())
                st.markdown(f"**{date} — {total} chamado(s)**")
                for loja, issues in sorted(stores.items()):
                    detalhes  = jira.agrupar_chamados(issues)[loja]
                    dup_keys  = [d["key"] for d in detalhes if (d["pdv"], d["ativo"]) in verificar_duplicidade(detalhes)]
                    spare_raw = jira.buscar_chamados(
                        f'project = FSA AND status = "Aguardando Spare" AND "Codigo da Loja[Dropdown]" = {loja}',
                        FIELDS
                    )
                    spare_keys = [i["key"] for i in spare_raw]
                    tags = []
                    if spare_keys: tags.append("Spare: " + ", ".join(spare_keys))
                    if dup_keys:   tags.append("Dup: "   + ", ".join(dup_keys))
                    tag_str = f" [{' • '.join(tags)}]" if tags else ""
                    with st.expander(f"{loja} — {len(issues)} chamado(s){tag_str}", expanded=False):
                        st.markdown("**FSAs:** " + ", ".join(d["key"] for d in detalhes))
                        st.code(gerar_mensagem(loja, detalhes), language="text")

# ── Aba de Calendário ──
with tab_cal:
    st.header("📆 Calendário Mensal de Agendamentos")

    if df_cal.empty:
        st.info("Nenhum agendamento com data definida.")
    else:
        # Escolha de mês e ano
        hoje = datetime.now()
        anos = sorted({d.year for d in df_cal["data"]})
        meses = list(range(1, 13))
        sel_ano  = st.selectbox("Ano:", anos, index=anos.index(hoje.year))
        sel_mes  = st.selectbox("Mês:", meses, index=hoje.month - 1)
        st.markdown(f"### {calendar.month_name[sel_mes]} {sel_ano}")

        # Filtra só o mês/ano selecionado
        df_mes = df_cal[df_cal["data"].apply(lambda d: d.year == sel_ano and d.month == sel_mes)]

        # Monta tabela HTML
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
                    data_atual = datetime(sel_ano, sel_mes, day).date()
                    subset = df_mes[df_mes["data"] == data_atual]
                    count  = len(subset)
                    # badge com tooltip
                    badge = (
                        f'<div title="FSAs: {", ".join(subset["key"])}" '
                        f'style="background:{"#28a745" if count>0 else "#444"};'
                        'color:#fff;padding:4px;border-radius:4px;text-align:center;">'
                        f'{count} chamado(s)</div>'
                    )
                    # mini‐barras por FSA
                    bars = "".join(
                        f'<span title="{row["key"]} ({row["loja"]})" '
                        f'style="background:{color_map[row["loja"]]};'
                        'display:inline-block;width:8px;height:8px;margin:1px;'
                        'border-radius:2px;"></span>'
                        for _, row in subset.iterrows()
                    )
                    html += (
                        f'<td style="vertical-align:top;padding:8px;border:1px solid #444;">'
                        f'<div style="font-size:14px;color:#ccc">{day}</div>'
                        f'{badge}<div style="margin-top:4px;">{bars or ""}</div>'
                        '</td>'
                    )
            html += "</tr>"
        html += "</table>"

        st.markdown(html, unsafe_allow_html=True)

        # Drill: seleção de dia para detalhes
        dias = sorted(df_mes["data"].unique())
        sel = st.selectbox("Ver detalhes do dia:", [d.strftime("%d/%m/%Y") for d in dias])
        if sel:
            dt_sel = datetime.strptime(sel, "%d/%m/%Y").date()
            issues_sel = [issue for issue in agendados_raw
                          if issue["fields"].get("customfield_12036") and
                             datetime.strptime(issue["fields"]["customfield_12036"], "%Y-%m-%dT%H:%M:%S.%f%z").date() == dt_sel]
            st.markdown(f"#### Chamados agendados em {sel}")
            detalhes = jira.agrupar_chamados(issues_sel)
            for loja, lst in detalhes.items():
                with st.expander(f"{loja} — {len(lst)} chamado(s)", expanded=True):
                    st.code(gerar_mensagem(loja, lst), language="text")

# ── Rodapé ──
st.markdown("---")
st.caption(f"Última atualização: {datetime.now():%d/%m/%Y %H:%M:%S}")
