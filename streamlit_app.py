# streamlit_app.py
import streamlit as st
from streamlit_autorefresh import st_autorefresh
from datetime import datetime
from collections import defaultdict

from utils.jira_api import JiraAPI
from utils.messages import gerar_mensagem, verificar_duplicidade


# ── Config & Auto-refresh (90s) ──
st.set_page_config(page_title="Painel Field Service", layout="wide")
st_autorefresh(interval=90_000, key="auto_refresh")

# ── Histórico de undo ──
if "history" not in st.session_state:
    st.session_state.history = []

# ── Secrets ──
EMAIL = st.secrets.get("EMAIL", "")
API_TOKEN = st.secrets.get("API_TOKEN", "")
CLOUD_ID = st.secrets.get("CLOUD_ID")
USE_EX_API = str(st.secrets.get("USE_EX_API", "true")).lower() == "true"

if not EMAIL or not API_TOKEN:
    st.error("⚠️ Configure `EMAIL` e `API_TOKEN` em .streamlit/secrets.toml")
    st.stop()
if USE_EX_API and not CLOUD_ID:
    st.error("⚠️ `USE_EX_API=true`, mas faltou `CLOUD_ID` em secrets.toml")
    st.stop()

# ── JiraAPI ──
jira = JiraAPI(
    EMAIL,
    API_TOKEN,
    "https://delfia.atlassian.net",
    use_ex_api=USE_EX_API,
    cloud_id=CLOUD_ID,
)

# ── Auth check ──
who, dbg_who = jira.whoami()
if not who:
    st.error(
        "❌ Falha de autenticação no Jira.\n\n"
        f"- URL: `{dbg_who.get('url')}`\n"
        f"- Status: `{dbg_who.get('status')}`\n"
        f"- Erro: `{dbg_who.get('error')}`\n"
    )
    st.stop()

# ── Campos ──
FIELDS = (
    "summary,customfield_14954,customfield_14829,customfield_14825,"
    "customfield_12374,customfield_12271,customfield_11993,"
    "customfield_11994,customfield_11948,customfield_12036,customfield_12279"
)

# ── JQLs principais ──
JQL_PEND = 'project = FSA AND status = "AGENDAMENTO" ORDER BY updated DESC'
JQL_AG   = 'project = FSA AND status = "Agendado" ORDER BY updated DESC'

# ── Diagnóstico rápido (opcional) ──
dbg_parse_pend = jira.parse_jql(JQL_PEND)
dbg_count_pend = jira.count_jql(JQL_PEND)
dbg_parse_ag   = jira.parse_jql(JQL_AG)
dbg_count_ag   = jira.count_jql(JQL_AG)

# ── Busca ENHANCED (com paginação) ──
pendentes_raw, dbg_pend = jira.buscar_chamados_enhanced(JQL_PEND, FIELDS, page_size=100)
agendados_raw, dbg_ag   = jira.buscar_chamados_enhanced(JQL_AG,   FIELDS, page_size=100)

# ── Busca combinada para contagem por loja (AGENDAMENTO + Agendado + TEC-CAMPO via IDs) ──
# IDs confirmados: AGENDAMENTO=11499, Agendado=11481, TEC-CAMPO=11500
JQL_COMBINADA = 'project = FSA AND status in (11499,11481,11500)'
combo_raw, dbg_combo = jira.buscar_chamados_enhanced(JQL_COMBINADA, FIELDS, page_size=200)

# ── Agrupamentos para as colunas principais ──
agrup_pend = jira.agrupar_chamados(pendentes_raw)

grouped_sched = defaultdict(lambda: defaultdict(list))
for issue in agendados_raw:
    f = issue["fields"]
    loja = f.get("customfield_14954", {}).get("value", "Loja Desconhecida")
    raw_dt = f.get("customfield_12036")
    data_str = (
        datetime.strptime(raw_dt, "%Y-%m-%dT%H:%M:%S.%f%z").strftime("%d/%m/%Y")
        if raw_dt else "Não definida"
    )
    grouped_sched[data_str][loja].append(issue)

raw_by_loja = defaultdict(list)
for i in pendentes_raw + agendados_raw:
    loja = i["fields"].get("customfield_14954", {}).get("value", "Loja Desconhecida")
    raw_by_loja[loja].append(i)

# ── Sidebar ──
with st.sidebar:
    st.header("Ações")
    if st.button("↩️ Desfazer última ação"):
        if st.session_state.history:
            action = st.session_state.history.pop()
            reverted = 0
            for key in action["keys"]:
                trans = jira.get_transitions(key)
                rev_id = next((t["id"] for t in trans if t.get("to", {}).get("name") == action["from"]), None)
                if rev_id and jira.transicionar_status(key, rev_id).status_code == 204:
                    reverted += 1
            st.success(f"Revertido: {reverted} FSAs → {action['from']}")
        else:
            st.info("Nenhuma ação para desfazer.")

    st.markdown("---")
    st.header("Transição de Chamados")

    # Lojas (robusto mesmo sem agendados)
    lojas_pend = set(agrup_pend.keys())
    lojas_ag = set()
    for _, stores in grouped_sched.items():
        lojas_ag |= set(stores.keys())
    todas_as_lojas = ["—"] + sorted(lojas_pend | lojas_ag)

    loja_sel = st.selectbox("Selecione a loja:", todas_as_lojas)

    with st.expander("🛠️ Debug (Enhanced Search)", expanded=False):
        st.json({
            "use_ex_api": USE_EX_API,
            "cloud_id": CLOUD_ID,
            "whoami_status": dbg_who.get("status"),
            "parse_pend": dbg_parse_pend,
            "count_pend": dbg_count_pend,
            "pendentes": dbg_pend,
            "parse_ag": dbg_parse_ag,
            "count_ag": dbg_count_ag,
            "agendados": dbg_ag,
            "combo": dbg_combo,
            "last_call": {
                "url": jira.last_url,
                "method": jira.last_method,
                "status": jira.last_status,
                "count": jira.last_count,
                "params": jira.last_params,
                "error": jira.last_error
            }
        })

    if loja_sel != "—":
        em_campo = st.checkbox("Técnico está em campo? (agendar + mover tudo)")

        if em_campo:
            st.markdown("**Dados de Agendamento**")
            data = st.date_input("Data do Agendamento")
            hora = st.time_input("Hora do Agendamento")
            tecnico = st.text_input("Dados dos Técnicos (Nome-CPF-RG-TEL)")

            dt_iso = datetime.combine(data, hora).strftime("%Y-%m-%dT%H:%M:%S.000-0300")
            extra_ag = {"customfield_12036": dt_iso}
            if tecnico:
                extra_ag["customfield_12279"] = {
                    "type": "doc",
                    "version": 1,
                    "content": [{"type": "paragraph", "content": [{"type": "text", "text": tecnico}]}],
                }

            keys_pend  = [i["key"] for i in pendentes_raw if i["fields"].get("customfield_14954", {}).get("value") == loja_sel]
            keys_sched = [i["key"] for i in agendados_raw  if i["fields"].get("customfield_14954", {}).get("value") == loja_sel]
            all_keys = keys_pend + keys_sched

            if st.button(f"Agendar e mover {len(all_keys)} FSAs → Tec-Campo"):
                errors = []
                moved = 0

                # a) agendar pendentes
                for k in keys_pend:
                    trans = jira.get_transitions(k)
                    agid = next((t["id"] for t in trans if "agend" in t["name"].lower()), None)
                    if agid:
                        r = jira.transicionar_status(k, agid, fields=extra_ag)
                        if r.status_code != 204:
                            errors.append(f"{k}⏳{r.status_code}")

                # b) mover todos para Tec-Campo
                for k in all_keys:
                    trans = jira.get_transitions(k)
                    tcid = next((t["id"] for t in trans if "tec-campo" in t.get("to", {}).get("name", "").lower()), None)
                    if tcid:
                        r = jira.transicionar_status(k, tcid)
                        if r.status_code == 204:
                            moved += 1
                        else:
                            errors.append(f"{k}➡️{r.status_code}")

                if errors:
                    st.error("Erros:")
                    [st.code(e) for e in errors]
                else:
                    st.success(f"{len(all_keys)} FSAs agendados e movidos → Tec-Campo")
                    st.session_state.history.append({"keys": all_keys, "from": "AGENDADO"})

                    detail = jira.agrupar_chamados(raw_by_loja[loja_sel])[loja_sel]
                    novos = [d for d in detail if d["key"] in keys_pend]
                    antigos = [d for d in detail if d["key"] in keys_sched]
                    st.markdown("### 🆕 Novos Agendados")
                    st.code(gerar_mensagem(loja_sel, novos), language="text")
                    if antigos:
                        st.markdown("### 📋 Já Agendados")
                        st.code(gerar_mensagem(loja_sel, antigos), language="text")

        else:
            # fluxo manual
            opts = [
                i["key"] for i in pendentes_raw
                if i["fields"].get("customfield_14954", {}).get("value") == loja_sel
            ] + [
                i["key"] for i in agendados_raw
                if i["fields"].get("customfield_14954", {}).get("value") == loja_sel
            ]
            sel = st.multiselect("Selecione FSAs pend.+age.:", sorted(set(opts)))
            extra = {}
            choice = None
            trans_opts = {}
            if sel:
                trans_opts = {t["name"]: t["id"] for t in jira.get_transitions(sel[0])}
                choice = st.selectbox("Transição:", ["—"] + list(trans_opts))
                if choice and "agend" in choice.lower():
                    st.markdown("**Dados de Agendamento**")
                    d = st.date_input("Data do Agendamento")
                    h = st.time_input("Hora do Agendamento")
                    tec = st.text_input("Dados dos Técnicos (Nome-CPF-RG-TEL)")
                    iso = datetime.combine(d, h).strftime("%Y-%m-%dT%H:%M:%S.000-0300")
                    extra["customfield_12036"] = iso
                    if tec:
                        extra["customfield_12279"] = {
                            "type": "doc",
                            "version": 1,
                            "content": [{"type": "paragraph", "content": [{"type": "text", "text": tec}]}],
                        }

            if st.button("Aplicar"):
                if not sel or choice in (None, "—"):
                    st.warning("Selecione FSAs e transição.")
                else:
                    prev = jira.get_issue(sel[0])["fields"]["status"]["name"]
                    errs = []
                    mv = 0
                    for k in sel:
                        r = jira.transicionar_status(k, trans_opts[choice], fields=extra or None)
                        if r.status_code == 204:
                            mv += 1
                        else:
                            errs.append(f"{k}:{r.status_code}")
                    if errs:
                        st.error("Falhas:")
                        [st.code(e) for e in errs]
                    else:
                        st.success(f"{mv} FSAs movidos → {choice}")
                        st.session_state.history.append({"keys": sel, "from": prev})

# ── TÍTULO ──
st.title("📱 Painel Field Service")

# ── TÍTULO ──
st.title("📱 Painel Field Service")

# ── SEÇÃO DESTACADA (MINIMIZÁVEL): Lojas com 2+ chamados ──
# Monta a lista antes para conseguirmos mostrar a contagem no título do expander
contagem_por_loja = {}
for issue in combo_raw:
    f = issue.get("fields", {})
    loja = (f.get("customfield_14954") or {}).get("value") or "Loja Desconhecida"
    cidade = f.get("customfield_11994") or ""
    if loja not in contagem_por_loja:
        contagem_por_loja[loja] = {"cidade": cidade, "qtd": 0}
    contagem_por_loja[loja]["qtd"] += 1
    if not contagem_por_loja[loja]["cidade"] and cidade:
        contagem_por_loja[loja]["cidade"] = cidade

destaques = [
    {"Loja": loja, "Cidade": data["cidade"], "Chamados": data["qtd"]}
    for loja, data in contagem_por_loja.items()
    if data["qtd"] >= 2
]
destaques.sort(key=lambda x: (-x["Chamados"], x["Loja"]))

exp_title = f"🏷️ Lojas com 2+ chamados (AGENDAMENTO • Agendado • TEC-CAMPO) — {len(destaques)} loja(s)"

with st.expander(exp_title, expanded=False):
    if destaques:
        st.dataframe(
            destaques,
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("Nenhuma loja com 2 ou mais chamados nesse conjunto.")


# ── Colunas principais ──
col1, col2 = st.columns(2)

with col1:
    st.header("⏳ Chamados PENDENTES de Agendamento")
    if not pendentes_raw:
        st.warning("Nenhum chamado em AGENDAMENTO.")
    else:
        for loja, iss in sorted(jira.agrupar_chamados(pendentes_raw).items()):
            with st.expander(f"{loja} — {len(iss)} chamado(s)", expanded=False):
                st.code(gerar_mensagem(loja, iss), language="text")

with col2:
    st.header("📋 Chamados AGENDADOS")
    if not agendados_raw:
        st.info("Nenhum chamado em AGENDADO.")
    else:
        for date, stores in sorted(grouped_sched.items()):
            total = sum(len(v) for v in stores.values())
            st.subheader(f"{date} — {total} chamado(s)")
            for loja, iss in sorted(stores.items()):
                detalhes = jira.agrupar_chamados(iss)[loja]
                dup_keys = [
                    d["key"] for d in detalhes
                    if (d["pdv"], d["ativo"]) in verificar_duplicidade(detalhes)
                ]
                # Spare da mesma loja (opcional)
                spare_raw, _dbg = jira.buscar_chamados_enhanced(
                    f'project = FSA AND status = "Aguardando Spare" AND "Codigo da Loja[Dropdown]" = "{loja}"',
                    FIELDS, page_size=100
                )
                spare_keys = [i["key"] for i in spare_raw]
                tags = []
                if spare_keys: tags.append("Spare: " + ", ".join(spare_keys))
                if dup_keys:   tags.append("Dup: " + ", ".join(dup_keys))
                tag_str = f" [{' • '.join(tags)}]" if tags else ""
                with st.expander(f"{loja} — {len(iss)} chamado(s){tag_str}", expanded=False):
                    st.markdown("**FSAs:** " + ", ".join(d["key"] for d in detalhes))
                    st.code(gerar_mensagem(loja, detalhes), language="text")

st.markdown("---")
st.caption(f"Última atualização: {datetime.now():%d/%m/%Y %H:%M:%S}")
