# streamlit_app.py
import io
import csv
import streamlit as st
from streamlit_autorefresh import st_autorefresh
from datetime import datetime
from collections import defaultdict

from utils.jira_api import JiraAPI
from utils.messages import gerar_mensagem, verificar_duplicidade


# ─────────────────────────────
# Config geral
# ─────────────────────────────
st.set_page_config(
    page_title="Painel Field Service",
    layout="wide",
    initial_sidebar_state="expanded",
)
st_autorefresh(interval=90_000, key="auto_refresh")  # 90s

if "history" not in st.session_state:
    st.session_state.history = []


# ─────────────────────────────
# Secrets e cliente Jira
# ─────────────────────────────
EMAIL = st.secrets.get("EMAIL", "")
API_TOKEN = st.secrets.get("API_TOKEN", "")
CLOUD_ID = st.secrets.get("CLOUD_ID")
USE_EX_API = str(st.secrets.get("USE_EX_API", "true")).lower() == "true"

if not EMAIL or not API_TOKEN:
    st.error("⚠️ Configure `EMAIL` e `API_TOKEN` em `.streamlit/secrets.toml`.")
    st.stop()
if USE_EX_API and not CLOUD_ID:
    st.error("⚠️ `USE_EX_API=true`, mas faltou `CLOUD_ID` em secrets.")
    st.stop()

jira = JiraAPI(
    EMAIL,
    API_TOKEN,
    "https://delfia.atlassian.net",
    use_ex_api=USE_EX_API,
    cloud_id=CLOUD_ID,
)

who, dbg_who = jira.whoami()
if not who:
    st.error(
        "❌ Falha de autenticação no Jira.\n\n"
        f"- URL: `{dbg_who.get('url')}`\n"
        f"- Status: `{dbg_who.get('status')}`\n"
        f"- Erro: `{dbg_who.get('error')}`"
    )
    st.stop()


# ─────────────────────────────
# Campos e JQLs
# ─────────────────────────────
FIELDS = (
    "summary,customfield_14954,customfield_14829,customfield_14825,"
    "customfield_12374,customfield_12271,customfield_11993,"
    "customfield_11994,customfield_11948,customfield_12036,customfield_12279,"
    "status"
)

JQL_PEND = 'project = FSA AND status = "AGENDAMENTO" ORDER BY updated DESC'
JQL_AG   = 'project = FSA AND status = "Agendado" ORDER BY updated DESC'

# IDs confirmados
STATUS_ID_AGENDAMENTO = 11499
STATUS_ID_AGENDADO    = 11481
STATUS_ID_TEC_CAMPO   = 11500
JQL_COMBINADA = (
    f"project = FSA AND status in ({STATUS_ID_AGENDAMENTO},"
    f"{STATUS_ID_AGENDADO},{STATUS_ID_TEC_CAMPO})"
)


# ─────────────────────────────
# Busca (Enhanced JQL com paginação)
# ─────────────────────────────
pendentes_raw, dbg_pend = jira.buscar_chamados_enhanced(JQL_PEND, FIELDS, page_size=150)
agendados_raw, dbg_ag   = jira.buscar_chamados_enhanced(JQL_AG,   FIELDS, page_size=150)
combo_raw,     dbg_combo = jira.buscar_chamados_enhanced(JQL_COMBINADA, FIELDS, page_size=300)

# Agrupamentos
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

# Para “desfazer” e fluxos em massa
raw_by_loja = defaultdict(list)
for i in pendentes_raw + agendados_raw:
    loja = i["fields"].get("customfield_14954", {}).get("value", "Loja Desconhecida")
    raw_by_loja[loja].append(i)


# ─────────────────────────────
# Sidebar – ações
# ─────────────────────────────
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

    lojas_pend = set(agrup_pend.keys())
    lojas_ag = set()
    for _, stores in grouped_sched.items():
        lojas_ag |= set(stores.keys())
    lojas_cat = ["—"] + sorted(lojas_pend | lojas_ag)

    loja_sel = st.selectbox("Selecione a loja:", lojas_cat, help="Usado nas ações em massa abaixo.")

    with st.expander("🛠️ Debug (Enhanced Search)"):
        st.json({
            "use_ex_api": USE_EX_API, "cloud_id": CLOUD_ID,
            "pendentes": {"count": len(pendentes_raw), **dbg_pend},
            "agendados": {"count": len(agendados_raw), **dbg_ag},
            "combo": {"count": len(combo_raw), **dbg_combo},
            "last_call": {
                "url": jira.last_url,
                "method": jira.last_method,
                "status": jira.last_status,
                "count": jira.last_count,
                "params": jira.last_params,
                "error": jira.last_error
            }
        })

    # Fluxo de transição
    if loja_sel != "—":
        st.markdown("### 🚚 Fluxo rápido")
        em_campo = st.checkbox("Técnico em campo? (agendar + mover tudo → Tec-Campo)")

        if em_campo:
            st.caption("Preencha os dados do agendamento:")
            data = st.date_input("Data")
            hora = st.time_input("Hora")
            tecnico = st.text_input("Técnicos (Nome-CPF-RG-TEL)")

            dt_iso = datetime.combine(data, hora).strftime("%Y-%m-%dT%H:%M:%S.000-0300")
            extra_ag = {"customfield_12036": dt_iso}
            if tecnico:
                extra_ag["customfield_12279"] = {
                    "type": "doc", "version": 1,
                    "content": [{"type": "paragraph", "content": [{"type": "text", "text": tecnico}]}],
                }

            keys_pend  = [i["key"] for i in pendentes_raw if i["fields"].get("customfield_14954", {}).get("value") == loja_sel]
            keys_sched = [i["key"] for i in agendados_raw  if i["fields"].get("customfield_14954", {}).get("value") == loja_sel]
            all_keys = keys_pend + keys_sched

            if st.button(f"Agendar e mover {len(all_keys)} FSAs → Tec-Campo"):
                errors, moved = [], 0

                # 1) Agendar pendentes
                for k in keys_pend:
                    trans = jira.get_transitions(k)
                    agid = next((t["id"] for t in trans if "agend" in t["name"].lower()), None)
                    if agid:
                        r = jira.transicionar_status(k, agid, fields=extra_ag)
                        if r.status_code != 204:
                            errors.append(f"{k}⏳{r.status_code}")

                # 2) Mover todos para Tec-Campo
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

        else:
            # fluxo manual
            opts = [
                i["key"] for i in pendentes_raw
                if i["fields"].get("customfield_14954", {}).get("value") == loja_sel
            ] + [
                i["key"] for i in agendados_raw
                if i["fields"].get("customfield_14954", {}).get("value") == loja_sel
            ]
            sel = st.multiselect("FSAs (pend.+agend.):", sorted(set(opts)))
            if sel:
                trans_opts = {t["name"]: t["id"] for t in jira.get_transitions(sel[0])}
                choice = st.selectbox("Transição:", ["—"] + list(trans_opts))
                extra = {}
                if choice and "agend" in choice.lower():
                    d = st.date_input("Data")
                    h = st.time_input("Hora")
                    tec = st.text_input("Técnicos (Nome-CPF-RG-TEL)")
                    iso = datetime.combine(d, h).strftime("%Y-%m-%dT%H:%M:%S.000-0300")
                    extra["customfield_12036"] = iso
                    if tec:
                        extra["customfield_12279"] = {
                            "type": "doc", "version": 1,
                            "content": [{"type": "paragraph", "content": [{"type": "text", "text": tec}]}],
                        }
                if st.button("Aplicar"):
                    if choice in (None, "—") or not sel:
                        st.warning("Selecione FSAs e transição.")
                    else:
                        prev = jira.get_issue(sel[0])["fields"]["status"]["name"]
                        errs, mv = [], 0
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


# ─────────────────────────────
# Cabeçalho + KPIs
# ─────────────────────────────
st.title("📱 Painel Field Service")

# KPIs (robusto mesmo se faltar status)
kpi = {"AGENDAMENTO": 0, "Agendado": 0, "TEC-CAMPO": 0}
for issue in combo_raw:
    fields = issue.get("fields") or {}
    status_name = (fields.get("status") or {}).get("name")
    if status_name in kpi:
        kpi[status_name] += 1

colk1, colk2, colk3, colk4 = st.columns(4)
colk1.metric("⏳ AGENDAMENTO", kpi["AGENDAMENTO"])
colk2.metric("📋 Agendado",   kpi["Agendado"])
colk3.metric("🧰 TEC-CAMPO",  kpi["TEC-CAMPO"])

# Contagem por loja/cidade/UF para destaques
contagem_por_loja = {}
for issue in combo_raw:
    f = issue.get("fields", {})
    loja = (f.get("customfield_14954") or {}).get("value") or "Loja Desconhecida"
    cidade = f.get("customfield_11994") or ""
    uf = (f.get("customfield_11948") or {}).get("value") or ""
    if loja not in contagem_por_loja:
        contagem_por_loja[loja] = {"cidade": cidade, "uf": uf, "qtd": 0}
    contagem_por_loja[loja]["qtd"] += 1
    if not contagem_por_loja[loja]["cidade"] and cidade:
        contagem_por_loja[loja]["cidade"] = cidade
    if not contagem_por_loja[loja]["uf"] and uf:
        contagem_por_loja[loja]["uf"] = uf

threshold_default = 2
destaques_raw = [
    {"Loja": loja, "Cidade": data["cidade"], "UF": data["uf"], "Chamados": data["qtd"]}
    for loja, data in contagem_por_loja.items()
    if data["qtd"] >= threshold_default
]
colk4.metric("🏷️ Lojas com 2+", len(destaques_raw))

st.markdown("")


# ─────────────────────────────
# Seção: Lojas com N+ chamados (colapsável)
# ─────────────────────────────
with st.expander(
    f"🏷️ Lojas com 2+ chamados (AGENDAMENTO • Agendado • TEC-CAMPO) — {len(destaques_raw)} loja(s)",
    expanded=False
):
    c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
    threshold = c1.number_input("Mín. chamados", min_value=2, max_value=50, value=threshold_default, step=1)
    order_opt = c2.selectbox("Ordenar por", ["Chamados ↓", "Loja ↑", "Cidade ↑"])
    uf_filter = c3.text_input("Filtrar UF (ex.: SP)", value="")
    busca_loja = c4.text_input("Buscar loja/cidade", value="", placeholder="Digite parte do nome...")

    destaques = [
        row for row in (
            {"Loja": loja, "Cidade": data["cidade"], "UF": data["uf"], "Chamados": data["qtd"]}
            for loja, data in contagem_por_loja.items()
            if data["qtd"] >= threshold
        )
        if (not uf_filter or (row["UF"] or "").upper() == uf_filter.strip().upper())
        and (not busca_loja or busca_loja.lower() in (row["Loja"] or "").lower()
             or busca_loja.lower() in (row["Cidade"] or "").lower())
    ]

    if order_opt == "Chamados ↓":
        destaques.sort(key=lambda x: (-x["Chamados"], x["Loja"]))
    elif order_opt == "Loja ↑":
        destaques.sort(key=lambda x: (x["Loja"], -x["Chamados"]))
    else:
        destaques.sort(key=lambda x: (x["Cidade"] or "", x["Loja"]))

    st.caption(f"{len(destaques)} loja(s) encontradas após filtros.")
    st.dataframe(destaques, use_container_width=True, hide_index=True)

    if destaques:
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=["Loja", "Cidade", "UF", "Chamados"])
        writer.writeheader()
        writer.writerows(destaques)
        st.download_button(
            "⬇️ Baixar CSV",
            data=output.getvalue().encode("utf-8"),
            file_name=f"lojas_destaque_{threshold}+_{datetime.now():%Y%m%d_%H%M%S}.csv",
            mime="text/csv"
        )
    else:
        st.info("Nenhuma loja atende aos filtros no momento.")


# ─────────────────────────────
# Abas: Pendentes | Agendados
# ─────────────────────────────
tab1, tab2 = st.tabs(["⏳ Pendentes de Agendamento", "📋 Agendados"])

with tab1:
    filtro_loja_pend = st.text_input("🔎 Filtrar por loja (código ou cidade) — Pendentes", "")
    if not pendentes_raw:
        st.warning("Nenhum chamado em **AGENDAMENTO**.")
    else:
        for loja, iss in sorted(jira.agrupar_chamados(pendentes_raw).items()):
            if filtro_loja_pend:
                if filtro_loja_pend.lower() not in loja.lower():
                    cidades = {x.get("cidade", "") for x in iss}
                    if not any(filtro_loja_pend.lower() in (c or "").lower() for c in cidades):
                        continue
            with st.expander(f"{loja} — {len(iss)} chamado(s)", expanded=False):
                st.code(gerar_mensagem(loja, iss), language="text")

with tab2:
    filtro_loja_ag = st.text_input("🔎 Filtrar por loja (código ou cidade) — Agendados", "")
    if not agendados_raw:
        st.info("Nenhum chamado em **Agendado**.")
    else:
        for date, stores in sorted(grouped_sched.items()):
            total = sum(len(v) for v in stores.values())
            st.subheader(f"{date} — {total} chamado(s)")
            for loja, iss in sorted(stores.items()):
                if filtro_loja_ag and filtro_loja_ag.lower() not in loja.lower():
                    cidades = { (x.get("fields", {}) or {}).get("customfield_11994") for x in iss }
                    if not any(filtro_loja_ag.lower() in (c or "").lower() for c in cidades):
                        continue

                detalhes = jira.agrupar_chamados(iss)[loja]
                dup_keys = [d["key"] for d in detalhes
                            if (d["pdv"], d["ativo"]) in verificar_duplicidade(detalhes)]

                spare_raw, _ = jira.buscar_chamados_enhanced(
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


# Rodapé
st.markdown("---")
st.caption(f"Última atualização: {datetime.now():%d/%m/%Y %H:%M:%S}")
