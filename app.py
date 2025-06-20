import streamlit as st
from streamlit_autorefresh import st_autorefresh
from datetime import datetime
from collections import defaultdict
import pandas as pd
import calendar

# ── AUTENTICAÇÃO SIMPLES ─────────────────────────────────────────────────────
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

# ── CONFIGURAÇÃO DA PÁGINA E AUTO-REFRESH ─────────────────────────────────────
st.set_page_config(page_title="Painel Field Service", layout="wide")
st_autorefresh(interval=90_000, key="auto_refresh")

# ── SIDEBAR: LOGOUT / REFRESH / UNDO / TRANSIÇÃO ──────────────────────────────
with st.sidebar:
    # Logout
    if st.button("🔓 Sair"):
        st.session_state.authenticated = False
        st.experimental_rerun()  # aqui ok que está fora do form/login

    # Refresh manual
    if st.button("🔄 Atualizar"):
        pass  # o st_autorefresh já cuidará de recarregar

    st.markdown("---")
    # Desfazer última ação
    st.header("↩️ Desfazer última ação")
    if st.button("Desfazer"):
        history = st.session_state.get("history", [])
        if history:
            from utils.jira_api import JiraAPI
            jira = JiraAPI(st.secrets["EMAIL"], st.secrets["API_TOKEN"], "https://delfia.atlassian.net")
            act = history.pop()
            for key, prev in zip(act["keys"], act["prev_fields"]):
                jira.transicionar_status(key, None, fields=prev)
            st.success("Ação desfeita")
        else:
            st.info("Nenhuma ação para desfazer")

    st.markdown("---")
    # Transição de Chamados
    st.header("▶️ Transição de Chamados")
    from utils.jira_api import JiraAPI
    jira = JiraAPI(st.secrets["EMAIL"], st.secrets["API_TOKEN"], "https://delfia.atlassian.net")

    FIELDS_SIMPLE = "summary,customfield_14954,customfield_12036"
    pendentes = jira.buscar_chamados("project = FSA AND status = AGENDAMENTO", FIELDS_SIMPLE)
    agendados = jira.buscar_chamados('project = FSA AND status = AGENDADO', FIELDS_SIMPLE)

    raw_by_store = defaultdict(list)
    for i in pendentes + agendados:
        loja = i["fields"].get("customfield_14954",{}).get("value","—")
        raw_by_store[loja].append(i)

    loja_sel = st.selectbox("Loja:", ["—"] + sorted(raw_by_store.keys()))
    if loja_sel != "—":
        keys = [i["key"] for i in raw_by_store[loja_sel]]
        sel  = st.multiselect("Selecionar FSAs:", keys)
        if sel:
            trans = jira.get_transitions(sel[0])
            opts  = {t["name"]: t["id"] for t in trans}
            choice = st.selectbox("Transição:", ["—"] + list(opts.keys()))

            extra = {}
            if choice.lower().startswith("agend"):
                data = st.date_input("Data do Agendamento")
                hora = st.time_input("Hora do Agendamento")
                tec  = st.text_input("Dados do Técnico")
                iso = datetime.combine(data, hora).strftime("%Y-%m-%dT%H:%M:%S.000-0300")
                extra["customfield_12036"] = iso
                if tec:
                    extra["customfield_12279"] = {
                        "type":"doc","version":1,
                        "content":[{"type":"paragraph","content":[{"type":"text","text":tec}]}]
                    }

            if st.button("Aplicar"):
                prev_fields = []
                for k in sel:
                    issue = jira.buscar_chamados(f'issue = {k}', FIELDS_SIMPLE)[0]
                    prev_fields.append(issue["fields"])
                    jira.transicionar_status(k, opts[choice], fields=extra or None)
                st.session_state.history = st.session_state.get("history", [])
                st.session_state.history.append({"keys":sel, "prev_fields":prev_fields})
                st.success(f"{len(sel)} FSAs movidos → {choice}")

# ── IMPORTS DO PAINEL E BUSCAS ────────────────────────────────────────────────
from utils.messages import gerar_mensagem, verificar_duplicidade
from collections import defaultdict

FIELDS_FULL = (
    "summary,customfield_14954,customfield_14829,customfield_14825,"
    "customfield_12374,customfield_12271,customfield_11993,"
    "customfield_11994,customfield_11948,customfield_12036"
)
pendentes = jira.buscar_chamados("project = FSA AND status = AGENDAMENTO", FIELDS_FULL)
agendados = jira.buscar_chamados('project = FSA AND status = AGENDADO', FIELDS_FULL)

# agrupa pendentes
agrup_pend = jira.agrupar_chamados(pendentes)

# agrupa agendados por data → loja
grouped = defaultdict(lambda: defaultdict(list))
for issue in agendados:
    f    = issue["fields"]
    loja = f.get("customfield_14954",{}).get("value","Loja")
    raw  = f.get("customfield_12036","")
    date = datetime.strptime(raw,"%Y-%m-%dT%H:%M:%S.%f%z").strftime("%d/%m/%Y") if raw else "Não definida"
    grouped[date][loja].append(issue)

# prepara df para calendário
cal_rows = []
for issue in agendados:
    raw = issue["fields"].get("customfield_12036")
    if not raw: continue
    dt   = datetime.strptime(raw,"%Y-%m-%dT%H:%M:%S.%f%z")
    loja = issue["fields"].get("customfield_14954",{}).get("value","Loja")
    cal_rows.append({"data":dt.date(),"key":issue["key"],"loja":loja})
df_cal = pd.DataFrame(cal_rows)

# ── TABS: Lista / Calendário ─────────────────────────────────────────────────
tab1, tab2 = st.tabs(["📋 Lista","📆 Calendário"])

with tab1:
    st.header("📱 Chamados PENDENTES de Agendamento")
    if not pendentes:
        st.warning("Nenhum pendente.")
    else:
        for loja, lst in agrup_pend.items():
            with st.expander(f"{loja} — {len(lst)} FSAs"):
                st.code(gerar_mensagem(loja, lst), language="text")

    st.header("📋 Chamados AGENDADOS")
    if not agendados:
        st.info("Nenhum agendado.")
    else:
        for date, stores in sorted(grouped.items()):
            total = sum(len(v) for v in stores.values())
            st.subheader(f"{date} — {total} FSAs")
            for loja, lst in stores.items():
                det = jira.agrupar_chamados(lst)[loja]
                dupk = [d["key"] for d in det if (d["pdv"],d["ativo"]) in verificar_duplicidade(det)]
                spare = jira.buscar_chamados(
                    f'project = FSA AND status = "Aguardando Spare" AND "Codigo da Loja[Dropdown]" = {loja}',
                    FIELDS_FULL
                )
                spk = [i["key"] for i in spare]
                tags=[]
                if spk: tags.append("Spare: "+", ".join(spk))
                if dupk: tags.append("Dup: "+", ".join(dupk))
                tag_str = f" [{' • '.join(tags)}]" if tags else ""
                with st.expander(f"{loja} — {len(lst)} FSAs{tag_str}"):
                    st.markdown("**FSAs:** "+", ".join(d["key"] for d in det))
                    st.code(gerar_mensagem(loja, det), language="text")

with tab2:
    st.header("📆 Calendário Mensal")
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
        html="<table style='border-collapse:collapse;width:100%'>"
        html+="<tr>"+ "".join(
            f"<th style='border:1px solid #444;padding:4px;background:#333;color:#fff'>{d}</th>"
            for d in ["Dom","Seg","Ter","Qua","Qui","Sex","Sáb"]
        )+"</tr>"
        for week in cal.monthdayscalendar(sel_ano,sel_mes):
            html+="<tr>"
            for day in week:
                if day==0:
                    html+="<td style='border:1px solid #444;padding:12px;background:#222'></td>"
                else:
                    dt = datetime(sel_ano,sel_mes,day).date()
                    sub= df_mes[df_mes["data"]==dt]
                    cnt= len(sub)
                    badge = (
                        f"<div title='FSAs: {', '.join(sub['key'])}' "
                        f"style='background:{'#28a745' if cnt>0 else '#444'};"
                        "color:#fff;padding:4px;border-radius:4px;text-align:center'>"
                        f"{cnt} FSAs</div>"
                    )
                    bars="".join(
                        "<span style='display:inline-block;width:8px;height:8px;margin:1px;"
                        "background:#888;border-radius:2px' "
                        f"title='{r['key']} ({r['loja']})'></span>"
                        for _,r in sub.iterrows()
                    )
                    html+=(
                        f"<td style='border:1px solid #444;padding:8px;vertical-align:top'>"
                        f"<div style='font-size:14px;color:#ccc'>{day}</div>"
                        f"{badge}<div style='margin-top:4px'>{bars}</div></td>"
                    )
            html+="</tr>"
        html+="</table>"
        st.markdown(html, unsafe_allow_html=True)

        dias = sorted(df_mes["data"].unique())
        sel = st.selectbox("Ver detalhes do dia:", [d.strftime("%d/%m/%Y") for d in dias])
        if sel:
            dt_sel = datetime.strptime(sel,"%d/%m/%Y").date()
            sel_iss = [
                i for i in agendados
                if i["fields"].get("customfield_12036") and
                   datetime.strptime(i["fields"]["customfield_12036"],
                                     "%Y-%m-%dT%H:%M:%S.%f%z").date()==dt_sel
            ]
            st.markdown(f"#### Chamados em {sel}")
            dets = jira.agrupar_chamados(sel_iss)
            for loja,lst in dets.items():
                with st.expander(f"{loja} — {len(lst)} FSAs"):
                    st.code(gerar_mensagem(loja,lst),language="text")

st.markdown("---")
st.caption(f"Última atualização: {datetime.now():%d/%m/%Y %H:%M:%S}")
