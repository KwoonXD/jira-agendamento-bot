import streamlit as st
from streamlit_autorefresh import st_autorefresh
from datetime import datetime
from collections import defaultdict

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

# ── CONFIG E AUTO-REFRESH ──────────────────────────────────────────────────────
st.set_page_config(page_title="Painel Field Service", layout="wide")
st_autorefresh(interval=90_000, key="auto_refresh")  # 1m30s

# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    if st.button("🔓 Sair"):
        st.session_state.authenticated = False
        st.experimental_rerun()

    if st.button("🔄 Atualizar"):
        pass

    st.markdown("---")
    st.header("↩️ Desfazer última ação")
    if st.button("Desfazer"):
        history = st.session_state.get("history", [])
        if history:
            jira = JiraAPI(st.secrets["EMAIL"], st.secrets["API_TOKEN"], "https://delfia.atlassian.net")
            act = history.pop()
            for key, prev in zip(act["keys"], act["prev_fields"]):
                jira.transicionar_status(key, None, fields=prev)
            st.success("Última ação desfeita")
        else:
            st.info("Nada a desfazer")

    st.markdown("---")
    st.header("▶️ Transição de Chamados")
    jira = JiraAPI(st.secrets["EMAIL"], st.secrets["API_TOKEN"], "https://delfia.atlassian.net")
    F = "summary,customfield_14954,customfield_12036"
    pend = jira.buscar_chamados("project = FSA AND status = AGENDAMENTO", F)
    age  = jira.buscar_chamados('project = FSA AND status = AGENDADO', F)

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
                    old = jira.buscar_chamados(f'issue = {k}', F)[0]["fields"]
                    prevs.append(old)
                    jira.transicionar_status(k, opts[choice], fields=extra or None)
                st.session_state.history = st.session_state.get("history",[])
                st.session_state.history.append({"keys":sel,"prev_fields":prevs})
                st.success(f"{len(sel)} FSAs movidos → {choice}")

# ── BUSCAS PRINCIPAIS ─────────────────────────────────────────────────────────
jira = JiraAPI(st.secrets["EMAIL"], st.secrets["API_TOKEN"], "https://delfia.atlassian.net")
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
    date = (datetime.strptime(raw,"%Y-%m-%dT%H:%M:%S.%f%z").strftime("%d/%m/%Y")
            if raw else "Não definida")
    grouped[date][loja].append(i)

# ── LAYOUT: DUAS COLUNAS ───────────────────────────────────────────────────────
st.title("📱 Painel Field Service")
col1, col2 = st.columns(2)

# Coluna 1: PENDENTES
with col1:
    st.header("⏳ Chamados PENDENTES de Agendamento")
    if not pendentes:
        st.warning("Nenhum pendente.")
    else:
        for loja, lst in agrup_pend.items():
            with st.expander(f"{loja} — {len(lst)} FSAs"):
                st.code(gerar_mensagem(loja, lst), language="text")

# Coluna 2: AGENDADOS
with col2:
    st.header("📋 Chamados AGENDADOS")
    if not agendados:
        st.info("Nenhum agendado.")
    else:
        for date, stores in sorted(grouped.items()):
            total = sum(len(v) for v in stores.values())
            st.subheader(f"{date} — {total} FSAs")
            for loja, lst in stores.items():
                det = jira.agrupar_chamados(lst)[loja]
                dup = [d["key"] for d in det if (d["pdv"],d["ativo"]) in verificar_duplicidade(det)]
                spare = jira.buscar_chamados(
                    f'project = FSA AND status = "Aguardando Spare" AND "Codigo da Loja[Dropdown]" = {loja}',
                    FIELDS_FULL
                )
                spk = [x["key"] for x in spare]
                tags=[]
                if spk: tags.append("Spare: "+", ".join(spk))
                if dup: tags.append("Dup: "+", ".join(dup))
                tag_str = f" [{' • '.join(tags)}]" if tags else ""
                with st.expander(f"{loja} — {len(lst)} FSAs{tag_str}"):
                    st.markdown("**FSAs:** " + ", ".join(d["key"] for d in det))
                    st.code(gerar_mensagem(loja, det), language="text")

st.markdown("---")
st.caption(f"Última atualização: {datetime.now():%d/%m/%Y %H:%M:%S}")
