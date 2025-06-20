import streamlit as st
from streamlit_autorefresh import st_autorefresh
from datetime import datetime
from collections import defaultdict

from utils.jira_api import JiraAPI
from utils.messages import gerar_mensagem, verificar_duplicidade

# ── Configuração da página e auto‐refresh (90s) ──
st.set_page_config(page_title="Painel Field Service", layout="wide")
st_autorefresh(interval=90_000, key="auto_refresh")

# ── Histórico de undo ──
if "history" not in st.session_state:
    st.session_state.history = []

# ── Instancia JiraAPI ──
jira = JiraAPI(
    st.secrets["EMAIL"],
    st.secrets["API_TOKEN"],
    "https://delfia.atlassian.net"
)

# ── Campos completos ──
FIELDS_FULL = (
    "summary,customfield_14954,customfield_14829,customfield_14825,"
    "customfield_12374,customfield_12271,customfield_11993,"
    "customfield_11994,customfield_11948,customfield_12036,customfield_12279"
)

# ── Sidebar ──
with st.sidebar:
    st.header("🔄 Ações")
    if st.button("↻ Atualizar agora"):
        st.experimental_rerun()

    st.markdown("---")
    st.header("↩️ Desfazer última ação")
    if st.button("Desfazer"):
        if st.session_state.history:
            action = st.session_state.history.pop()
            reverted = 0
            for key, prev_fields in zip(action["keys"], action["prev_fields"]):
                # apenas reenvia os campos anteriores
                jira.transicionar_status(key, None, fields=prev_fields)
                reverted += 1
            st.success(f"Revertido: {reverted} FSAs")
        else:
            st.info("Nada para desfazer.")

    st.markdown("---")
    st.header("▶️ Transição em Massa")
    # Recarrega pendentes e agendados completos
    pend_full = jira.buscar_chamados("project = FSA AND status = AGENDAMENTO", FIELDS_FULL)
    age_full  = jira.buscar_chamados('project = FSA AND status = AGENDADO',    FIELDS_FULL)

    by_store = defaultdict(list)
    for issue in pend_full + age_full:
        loja = issue["fields"].get("customfield_14954", {}).get("value", "—")
        by_store[loja].append(issue)

    loja_sel = st.selectbox("Loja:", ["—"] + sorted(by_store.keys()))
    if loja_sel != "—":
        keys = [i["key"] for i in by_store[loja_sel]]
        sel  = st.multiselect("Selecionar FSAs:", keys)
        if sel:
            trans = jira.get_transitions(sel[0])
            opts  = {t["name"]: t["id"] for t in trans}
            choice = st.selectbox("Transição:", ["—"] + list(opts.keys()))
            extra = {}
            if choice.lower().startswith("agend"):
                st.markdown("**Dados de Agendamento**")
                d = st.date_input("Data do Agendamento")
                h = st.time_input("Hora do Agendamento")
                t = st.text_input("Dados do Técnico (Nome-CPF-RG-TEL)")
                iso = datetime.combine(d, h).strftime("%Y-%m-%dT%H:%M:%S.000-0300")
                extra["customfield_12036"] = iso
                if t:
                    extra["customfield_12279"] = {
                        "type":"doc","version":1,
                        "content":[{"type":"paragraph","content":[{"type":"text","text":t}]}]
                    }
            if choice != "—" and st.button("Aplicar Transição"):
                prev_fields = []
                for k in sel:
                    # pega campos antes da transição para undo
                    old = jira.buscar_chamados(f'issue={k}', FIELDS_FULL)[0]["fields"]
                    prev_fields.append(old)
                    jira.transicionar_status(k, opts[choice], fields=extra or None)
                st.session_state.history.append({
                    "keys": sel,
                    "prev_fields": prev_fields
                })
                st.success(f"{len(sel)} FSAs movidos → {choice}")

# ── Busca e agrupamento ──
pendentes = jira.buscar_chamados("project = FSA AND status = AGENDAMENTO", FIELDS_FULL)
agendados = jira.buscar_chamados('project = FSA AND status = AGENDADO',    FIELDS_FULL)

agrup_pend = jira.agrupar_chamados(pendentes)

grouped = defaultdict(lambda: defaultdict(list))
for issue in agendados:
    f = issue["fields"]
    loja = f.get("customfield_14954", {}).get("value", "Loja Desconhecida")
    raw = f.get("customfield_12036")
    date = (datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S.%f%z").strftime("%d/%m/%Y")
            if raw else "Não definida")
    grouped[date][loja].append(issue)

# ── Layout principal ──
st.title("📱 Painel Field Service")
col1, col2 = st.columns(2)

# Coluna de Pendentes
with col1:
    st.header("⏳ Chamados PENDENTES de Agendamento")
    if not pendentes:
        st.warning("Nenhum pendente.")
    else:
        for loja, lst in agrup_pend.items():
            with st.expander(f"{loja} — {len(lst)} FSAs", expanded=False):
                st.code(gerar_mensagem(loja, lst), language="text")

# Coluna de Agendados
with col2:
    st.header("📋 Chamados AGENDADOS")
    if not agendados:
        st.info("Nenhum agendado.")
    else:
        for date, stores in sorted(grouped.items()):
            total = sum(len(v) for v in stores.values())
            st.subheader(f"{date} — {total} FSAs")
            for loja, lst in sorted(stores.items()):
                det  = jira.agrupar_chamados(lst)[loja]
                dup = [d["key"] for d in det if (d["pdv"], d["ativo"]) in verificar_duplicidade(det)]
                spare = jira.buscar_chamados(
                    f'project = FSA AND status = "Aguardando Spare" '
                    f'AND "Codigo da Loja[Dropdown]" = {loja}',
                    FIELDS_FULL
                )
                spk = [i["key"] for i in spare]
                tags = []
                if spk: tags.append("Spare: " + ", ".join(spk))
                if dup: tags.append("Dup: "   + ", ".join(dup))
                tag_str = f" [{' • '.join(tags)}]" if tags else ""
                with st.expander(f"{loja} — {len(lst)} FSAs{tag_str}", expanded=False):
                    st.markdown("**FSAs:** " + ", ".join(d["key"] for d in det))
                    st.code(gerar_mensagem(loja, det), language="text")

# ── Rodapé ──
st.markdown("---")
st.caption(f"Última atualização: {datetime.now():%d/%m/%Y %H:%M:%S}")
