import streamlit as st
from streamlit_autorefresh import st_autorefresh
from datetime import datetime
from collections import defaultdict
import pandas as pd
import calendar

from utils.jira_api import JiraAPI
from utils.messages import gerar_mensagem, verificar_duplicidade

# ── Configuração da página e auto‐refresh (90s) ──
st.set_page_config(page_title="Painel Field Service", layout="wide")
st_autorefresh(interval=90_000, key="auto_refresh")

# ── Inicializa JiraAPI ──
jira = JiraAPI(
    st.secrets["EMAIL"],
    st.secrets["API_TOKEN"],
    "https://delfia.atlassian.net"
)

# ── Campos para busca ──
FIELDS = (
    "summary,customfield_14954,customfield_14829,customfield_14825,"
    "customfield_12374,customfield_12271,customfield_11993,"
    "customfield_11994,customfield_11948,customfield_12036"
)

# ── Busca pendentes e agendados ──
pendentes_raw = jira.buscar_chamados("project = FSA AND status = AGENDAMENTO", FIELDS)
agendados_raw = jira.buscar_chamados('project = FSA AND status = AGENDADO', FIELDS)

# ── Agrupa pendentes por loja ──
agrup_pend = jira.agrupar_chamados(pendentes_raw)

# ── Agrupa agendados por data e loja para a lista ──
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

# ── Sidebar vazio (mantém espaço para Ações futuras) ──
with st.sidebar:
    st.header("Ações")
    st.info("Use as abas para ver Lista ou Calendário")

# ── Abas: Lista e Calendário ──
tab_lista, tab_cal = st.tabs(["📋 Lista", "📆 Calendário"])

with tab_lista:
    st.header("📱 Painel Field Service — Lista")
    col1, col2 = st.columns(2)

    # Pendentes
    with col1:
        st.subheader("⏳ Chamados PENDENTES de Agendamento")
        if not pendentes_raw:
            st.warning("Nenhum chamado em AGENDAMENTO.")
        else:
            for loja, issues in agrup_pend.items():
                with st.expander(f"{loja} — {len(issues)} chamado(s)", expanded=False):
                    st.code(gerar_mensagem(loja, issues), language="text")

    # Agendados
    with col2:
        st.subheader("📋 Chamados AGENDADOS")
        if not agendados_raw:
            st.info("Nenhum chamado em AGENDADO.")
        else:
            for date, stores in sorted(grouped_sched.items()):
                total = sum(len(v) for v in stores.values())
                st.markdown(f"**{date} — {total} chamado(s)**")
                for loja, issues in sorted(stores.items()):
                    detalhes = jira.agrupar_chamados(issues)[loja]
                    # tags de duplicidade e spare
                    dup = verificar_duplicidade(detalhes)
                    dup_keys   = [d["key"] for d in detalhes if (d["pdv"], d["ativo"]) in dup]
                    spare_raw  = jira.buscar_chamados(
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

with tab_cal:
    st.header("📆 Calendário Mensal de Agendamentos")

    # monta DataFrame somente com dia
    rows = []
    for issue in agendados_raw:
        raw = issue["fields"].get("customfield_12036")
        if not raw:
            continue
        dt = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S.%f%z")
        rows.append({"data": dt.date(), "key": issue["key"]})

    if not rows:
        st.info("Nenhum agendamento com data definida.")
    else:
        df = pd.DataFrame(rows)
        # Data atual
        hoje = datetime.now()
        ano, mes = hoje.year, hoje.month

        cal = calendar.Calendar(firstweekday=6)  # domingo=6
        html = '<table style="border-collapse:collapse;width:100%;">'
        # cabeçalho dos dias
        html += '<tr>' + ''.join(
            f'<th style="padding:4px;border:1px solid #444;background:#333;color:#fff">{d}</th>'
            for d in ["Dom","Seg","Ter","Qua","Qui","Sex","Sáb"]
        ) + '</tr>'

        # percorre as semanas do mês
        for week in cal.monthdayscalendar(ano, mes):
            html += "<tr>"
            for day in week:
                if day == 0:
                    # célula vazia
                    html += '<td style="padding:12px;border:1px solid #444;background:#222;"></td>'
                else:
                    cont = df[df["data"] == datetime(ano, mes, day).date()].shape[0]
                    # cor conforme quantidade
                    color = "#28a745" if cont > 0 else "#333"
                    html += (
                        f'<td style="vertical-align:top;padding:8px;border:1px solid #444;">'
                        f'<div style="font-size:14px;color:#ccc">{day}</div>'
                        f'<div style="background:{color};color:#fff;margin-top:4px;'
                        f'padding:2px;border-radius:2px;text-align:center;">'
                        f'{cont} chamado(s)</div>'
                        '</td>'
                    )
            html += "</tr>"

        html += "</table>"
        st.markdown(f"### {calendar.month_name[mes]} {ano}", unsafe_allow_html=True)
        st.markdown(html, unsafe_allow_html=True)

# ── Rodapé ──
st.markdown("---")
st.caption(f"Última atualização: {datetime.now():%d/%m/%Y %H:%M:%S}")
