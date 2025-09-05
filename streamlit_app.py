# streamlit_app.py
import io
import csv
import time
import requests
from datetime import datetime, timedelta, timezone
from collections import defaultdict

import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

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

# estado para filtros/presets
if "filters" not in st.session_state:
    st.session_state.filters = {
        "threshold": 2,          # destaque N+
        "uf": "",                # filtro UF
        "q": "",                 # busca loja/cidade (destaques)
        "days": 14,              # janela do gráfico
        "statuses": ["AGENDAMENTO", "Agendado", "TEC-CAMPO"],  # visão geral
    }
if "presets" not in st.session_state:
    st.session_state.presets = {}   # nome -> dict de filtros


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
    "status,created,resolutiondate,updated"
)

JQL_PEND = 'project = FSA AND status = "AGENDAMENTO" ORDER BY updated DESC'
JQL_AG   = 'project = FSA AND status = "Agendado" ORDER BY updated DESC'
JQL_TC   = 'project = FSA AND status = "TEC-CAMPO" ORDER BY updated DESC'

# IDs confirmados (para visão combinada)
STATUS_ID_AGENDAMENTO = 11499
STATUS_ID_AGENDADO    = 11481
STATUS_ID_TEC_CAMPO   = 11500
JQL_COMBINADA = (
    f"project = FSA AND status in ({STATUS_ID_AGENDAMENTO},"
    f"{STATUS_ID_AGENDADO},{STATUS_ID_TEC_CAMPO})"
)

# JQL para resolvidos (para gráfico de tendência)
# IDs/nomes conhecidos: Encerrado (11498), Resolvido (10702)
JQL_RESOLVIDOS_BASE = (
    'project = FSA AND status in (11498, 10702, "Encerrado", "Resolvido") '
    'AND resolutiondate >= "{from_iso}" AND resolutiondate <= "{to_iso}"'
)


# ─────────────────────────────
# Funções auxiliares
# ─────────────────────────────
def parse_dt(dt_str: str):
    if not dt_str:
        return None
    try:
        return datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%S.%f%z").astimezone(timezone.utc)
    except Exception:
        try:
            return datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%S%z").astimezone(timezone.utc)
        except Exception:
            return None

def loja_from_issue(issue):
    f = issue.get("fields", {})
    return (f.get("customfield_14954") or {}).get("value") or "Loja Desconhecida"

def cidade_from_issue(issue):
    return (issue.get("fields", {}) or {}).get("customfield_11994") or ""

def uf_from_issue(issue):
    return ((issue.get("fields", {}) or {}).get("customfield_11948") or {}).get("value") or ""

def cep_from_issue(issue):
    return (issue.get("fields", {}) or {}).get("customfield_11993") or ""

def endereco_from_issue(issue):
    return (issue.get("fields", {}) or {}).get("customfield_12271") or ""

def updated_from_issue(issue):
    return parse_dt((issue.get("fields", {}) or {}).get("updated"))

def created_from_issue(issue):
    return parse_dt((issue.get("fields", {}) or {}).get("created"))

def resolutiondate_from_issue(issue):
    return parse_dt((issue.get("fields", {}) or {}).get("resolutiondate"))

def is_loja_critica(loja_data):
    """Critério de alerta: >=5 chamados OU (sem atualização há 7+ dias)."""
    qtd = loja_data.get("qtd", 0)
    last_upd = loja_data.get("last_updated")
    stale = False
    if last_upd:
        stale = (datetime.now(timezone.utc) - last_upd) > timedelta(days=7)
    return (qtd >= 5) or stale


# ─────────────────────────────
# Buscas (Enhanced JQL com paginação)
# ─────────────────────────────
pendentes_raw, dbg_pend = jira.buscar_chamados_enhanced(JQL_PEND, FIELDS, page_size=200)
agendados_raw, dbg_ag   = jira.buscar_chamados_enhanced(JQL_AG,   FIELDS, page_size=200)
tec_raw,      dbg_tc    = jira.buscar_chamados_enhanced(JQL_TC,   FIELDS, page_size=300)
combo_raw,    dbg_combo = jira.buscar_chamados_enhanced(JQL_COMBINADA, FIELDS, page_size=600)

# janela de dias para tendência
days_window = int(st.session_state.filters["days"])
to_dt = datetime.now(timezone.utc)
from_dt = to_dt - timedelta(days=days_window)

# resolvidos (para gráfico)
jql_res = JQL_RESOLVIDOS_BASE.format(
    from_iso=from_dt.strftime("%Y-%m-%d %H:%M"),
    to_iso=to_dt.strftime("%Y-%m-%d %H:%M")
)
resolvidos_raw, dbg_res = jira.buscar_chamados_enhanced(jql_res, FIELDS, page_size=600)

# Agrupamentos existentes
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

agrup_tec = jira.agrupar_chamados(tec_raw)

# Para “desfazer” e fluxos em massa
raw_by_loja = defaultdict(list)
for i in pendentes_raw + agendados_raw + tec_raw:
    raw_by_loja[loja_from_issue(i)].append(i)


# ─────────────────────────────
# Construções para visão geral / destaques
# ─────────────────────────────
# KPIs (robustos mesmo se faltar status)
kpi = {"AGENDAMENTO": 0, "Agendado": 0, "TEC-CAMPO": 0}
for issue in combo_raw:
    fields = issue.get("fields") or {}
    status_name = (fields.get("status") or {}).get("name")
    if status_name in kpi:
        kpi[status_name] += 1

# Contagem, cidade/UF e última atualização por loja (para destaques e alertas)
contagem_por_loja = {}
for issue in combo_raw:
    loja = loja_from_issue(issue)
    cidade = cidade_from_issue(issue)
    uf = uf_from_issue(issue)
    upd = updated_from_issue(issue)

    if loja not in contagem_por_loja:
        contagem_por_loja[loja] = {
            "cidade": cidade, "uf": uf, "qtd": 0, "last_updated": upd,
            "endereco": endereco_from_issue(issue), "cep": cep_from_issue(issue)
        }
    contagem_por_loja[loja]["qtd"] += 1
    if cidade and not contagem_por_loja[loja]["cidade"]:
        contagem_por_loja[loja]["cidade"] = cidade
    if uf and not contagem_por_loja[loja]["uf"]:
        contagem_por_loja[loja]["uf"] = uf
    if upd and (contagem_por_loja[loja]["last_updated"] is None or upd > contagem_por_loja[loja]["last_updated"]):
        contagem_por_loja[loja]["last_updated"] = upd
    # se algum issue tiver endereço/cep melhor, mantém
    if not contagem_por_loja[loja]["endereco"] and endereco_from_issue(issue):
        contagem_por_loja[loja]["endereco"] = endereco_from_issue(issue)
    if not contagem_por_loja[loja]["cep"] and cep_from_issue(issue):
        contagem_por_loja[loja]["cep"] = cep_from_issue(issue)

# Base para Top 5
top_list = sorted(
    [
        {
            "loja": loja,
            "cidade": data["cidade"],
            "uf": data["uf"],
            "qtd": data["qtd"],
            "last_updated": data["last_updated"],
            "critica": is_loja_critica(data),
        }
        for loja, data in contagem_por_loja.items()
    ],
    key=lambda x: (-x["qtd"], x["loja"])
)[:5]


# ─────────────────────────────
# Sidebar – ações e debug
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
    lojas_tc = set(agrup_tec.keys())
    lojas_cat = ["—"] + sorted(lojas_pend | lojas_ag | lojas_tc)

    loja_sel = st.selectbox("Selecione a loja:", lojas_cat, help="Usado nas ações em massa abaixo.")

    with st.expander("🛠️ Debug (Enhanced Search)"):
        st.json({
            "use_ex_api": USE_EX_API, "cloud_id": CLOUD_ID,
            "pendentes": {"count": len(pendentes_raw), **dbg_pend},
            "agendados": {"count": len(agendados_raw), **dbg_ag},
            "tec_campo": {"count": len(tec_raw), **dbg_tc},
            "combo": {"count": len(combo_raw), **dbg_combo},
            "resolvidos": {"count": len(resolvidos_raw), **dbg_res},
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

            keys_pend  = [i["key"] for i in pendentes_raw if loja_from_issue(i) == loja_sel]
            keys_sched = [i["key"] for i in agendados_raw  if loja_from_issue(i) == loja_sel]
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
                i["key"] for i in pendentes_raw if loja_from_issue(i) == loja_sel
            ] + [
                i["key"] for i in agendados_raw if loja_from_issue(i) == loja_sel
            ] + [
                i["key"] for i in tec_raw if loja_from_issue(i) == loja_sel
            ]
            sel = st.multiselect("FSAs (pend.+agend.+tec-campo):", sorted(set(opts)))
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
# Título
# ─────────────────────────────
st.title("📱 Painel Field Service")


# ─────────────────────────────
# ABAS (ordem nova): 📋 Chamados | 📊 Visão Geral
# ─────────────────────────────
tab_details, tab_overview = st.tabs(["📋 Chamados", "📊 Visão Geral"])


# ============================
# 📋 Chamados (Detalhes)
# ============================
with tab_details:
    # ── SEÇÃO: Lojas com N+ chamados (colapsável) ──
    st.subheader("🏷️ Lojas com N+ chamados (AGENDAMENTO • Agendado • TEC-CAMPO)")
    with st.expander("Abrir/Fechar destaques", expanded=False):
        c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
        threshold = c1.number_input("Mín. chamados", min_value=2, max_value=50, value=int(st.session_state.filters["threshold"]), step=1)
        order_opt = c2.selectbox("Ordenar por", ["Chamados ↓", "Loja ↑", "Cidade ↑"])
        uf_filter = c3.text_input("Filtrar UF", value=st.session_state.filters["uf"])
        busca_loja = c4.text_input("Buscar loja/cidade", value=st.session_state.filters["q"], placeholder="Digite parte do nome...")

        st.session_state.filters.update({"threshold": int(threshold), "uf": uf_filter, "q": busca_loja})

        destaques = []
        for loja, data in contagem_por_loja.items():
            if data["qtd"] >= threshold:
                row = {
                    "Loja": loja,
                    "Cidade": data["cidade"],
                    "UF": data["uf"],
                    "Chamados": data["qtd"],
                    "Últ. atualização": data["last_updated"].astimezone(timezone.utc).strftime("%d/%m/%Y %H:%M") if data["last_updated"] else "—",
                    "⚠️": "🔴" if is_loja_critica(data) else "",
                }
                destaques.append(row)

        destaques = [
            r for r in destaques
            if (not uf_filter or (r["UF"] or "").upper() == uf_filter.strip().upper())
            and (not busca_loja or busca_loja.lower() in (r["Loja"] or "").lower()
                 or busca_loja.lower() in (r["Cidade"] or "").lower())
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
            writer = csv.DictWriter(output, fieldnames=["Loja", "Cidade", "UF", "Chamados", "Últ. atualização", "⚠️"])
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

    st.markdown("")

    # ── Sub-abas: Pendentes | Agendados | TEC-CAMPO ──
    tab1, tab2, tab3 = st.tabs(["⏳ Pendentes de Agendamento", "📋 Agendados", "🧰 TEC-CAMPO"])

    with tab1:
        filtro_loja_pend = st.text_input("🔎 Filtrar por loja (código ou cidade) — Pendentes", "")
        if not pendentes_raw:
            st.warning("Nenhum chamado em **AGENDAMENTO**.")
        else:
            for loja, iss in sorted(jira.agrupar_chamados(pendentes_raw).items()):
                data = contagem_por_loja.get(loja, {"qtd": len(iss), "last_updated": None})
                alerta = " 🔴" if is_loja_critica(data) else ""
                if filtro_loja_pend:
                    if filtro_loja_pend.lower() not in loja.lower():
                        cidades = {x.get("cidade", "") for x in iss}
                        if not any(filtro_loja_pend.lower() in (c or "").lower() for c in cidades):
                            continue
                with st.expander(f"{alerta} {loja} — {len(iss)} chamado(s)", expanded=False):
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
                    data = contagem_por_loja.get(loja, {"qtd": len(iss), "last_updated": None})
                    alerta = " 🔴" if is_loja_critica(data) else ""

                    if filtro_loja_ag and filtro_loja_ag.lower() not in loja.lower():
                        cidades = {(x.get("fields", {}) or {}).get("customfield_11994") for x in iss}
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

                    with st.expander(f"{alerta} {loja} — {len(iss)} chamado(s){tag_str}", expanded=False):
                        st.markdown("**FSAs:** " + ", ".join(d["key"] for d in detalhes))
                        st.code(gerar_mensagem(loja, detalhes), language="text")

    with tab3:  # TEC-CAMPO
        filtro_loja_tc = st.text_input("🔎 Filtrar por loja (código ou cidade) — TEC-CAMPO", "")
        if not tec_raw:
            st.info("Nenhum chamado em **TEC-CAMPO**.")
        else:
            for loja, iss in sorted(agrup_tec.items()):
                data = contagem_por_loja.get(loja, {"qtd": len(iss), "last_updated": None})
                alerta = " 🔴" if is_loja_critica(data) else ""
                if filtro_loja_tc:
                    if filtro_loja_tc.lower() not in loja.lower():
                        cidades = {x.get("cidade", "") for x in iss}
                        if not any(filtro_loja_tc.lower() in (c or "").lower() for c in cidades):
                            continue
                with st.expander(f"{alerta} {loja} — {len(iss)} chamado(s)", expanded=False):
                    st.code(gerar_mensagem(loja, iss), language="text")

    st.markdown("---")
    st.caption(f"Última atualização: {datetime.now():%d/%m/%Y %H:%M:%S}")


# ============================
# 📊 Visão Geral
# ============================
with tab_overview:
    # ── Presets de Filtros (favoritos) ──
    with st.expander("🔖 Favoritos / Filtros salvos"):
        c1, c2 = st.columns([2, 1])
        with c1:
            st.write("Ajustes rápidos do painel:")
            st.session_state.filters["threshold"] = st.number_input(
                "Mín. chamados p/ destaque", min_value=2, max_value=50, value=int(st.session_state.filters["threshold"]), step=1
            )
            st.session_state.filters["uf"] = st.text_input("Filtrar UF (ex.: SP)", value=st.session_state.filters["uf"])
            st.session_state.filters["q"] = st.text_input("Buscar loja/cidade (destaques)", value=st.session_state.filters["q"])
            st.session_state.filters["days"] = st.slider("Janela do gráfico (dias)", min_value=7, max_value=90, value=int(st.session_state.filters["days"]), step=1)
        with c2:
            preset_names = ["—"] + sorted(st.session_state.presets.keys())
            pick = st.selectbox("Carregar preset", preset_names, index=0)
            if pick != "—":
                if st.button("Carregar"):
                    st.session_state.filters.update(st.session_state.presets[pick])
                    st.success(f"Preset '{pick}' carregado.")
                    st.experimental_rerun()
                if st.button("Excluir"):
                    st.session_state.presets.pop(pick, None)
                    st.success(f"Preset '{pick}' excluído.")
            new_name = st.text_input("Salvar como…", "")
            if st.button("Salvar preset") and new_name.strip():
                st.session_state.presets[new_name.strip()] = dict(st.session_state.filters)
                st.success(f"Preset '{new_name.strip()}' salvo.")

    st.markdown("")

    # ── KPIs ──
    colk1, colk2, colk3, colk4 = st.columns(4)
    colk1.metric("⏳ AGENDAMENTO", kpi["AGENDAMENTO"])
    colk2.metric("📋 Agendado",   kpi["Agendado"])
    colk3.metric("🧰 TEC-CAMPO",  kpi["TEC-CAMPO"])
    colk4.metric("🏷️ Lojas com 2+", sum(1 for x in contagem_por_loja.values() if x["qtd"] >= 2))

    st.markdown("")

    # ── TOP 5 Lojas Críticas ──
    st.subheader("📌 Top 5 lojas mais críticas")
    tcols = st.columns(5) if top_list else []
    for idx, card in enumerate(top_list):
        with tcols[idx]:
            indicador = "🔴 " if card["critica"] else ""
            last_upd = card["last_updated"].astimezone(timezone.utc).strftime("%d/%m %H:%M") if card["last_updated"] else "—"
            st.metric(
                label=f"{indicador}{card['loja']} • {card['cidade']}-{card['uf']}",
                value=card["qtd"],
                delta=f"Últ. atualização: {last_upd}"
            )

    st.markdown("")

    # ── Gráfico de Tendência (Novos vs Resolvidos) ──
    st.subheader("📈 Tendência (últimos dias)")
    # base de datas
    all_days = pd.date_range(
        (datetime.now() - timedelta(days=int(st.session_state.filters["days"]))).date(),
        datetime.now().date(),
        freq="D"
    )

    # Novos: por created (usando combo_raw — aberto na janela)
    novos = [created_from_issue(i) for i in combo_raw]
    novos = [d for d in novos if d and (datetime.now(timezone.utc) - d) <= timedelta(days=int(st.session_state.filters["days"]))]
    df_novos = pd.Series(1, index=[d.date() for d in novos]).groupby(level=0).sum() if novos else pd.Series(dtype=int)

    # Resolvidos: por resolutiondate
    resd = [resolutiondate_from_issue(i) for i in resolvidos_raw]
    resd = [d for d in resd if d and (datetime.now(timezone.utc) - d) <= timedelta(days=int(st.session_state.filters["days"]))]
    df_res = pd.Series(1, index=[d.date() for d in resd]).groupby(level=0).sum() if resd else pd.Series(dtype=int)

    df = pd.DataFrame({
        "Novos": df_novos.reindex(all_days.date, fill_value=0),
        "Resolvidos": df_res.reindex(all_days.date, fill_value=0),
    }, index=[d.strftime("%d/%m") for d in all_days.date])

    st.line_chart(df, use_container_width=True)

    st.markdown("")

    # ── Heatmap: geocodificação automática via Jira (endereço/cep) ──
    st.subheader("🗺️ Heatmap de lojas (auto, via endereço/CEP do Jira)")

    @st.cache_data(ttl=60*60*24, show_spinner=False)
    def geocode_nominatim(q: str):
        """Geocodifica uma query textual via OSM Nominatim (cache 24h)."""
        url = "https://nominatim.openstreetmap.org/search"
        headers = {"User-Agent": "FieldServiceDashboard/1.0 (contact: ops@empresa.com)"}
        params = {"q": q, "format": "json", "limit": 1, "countrycodes": "br"}
        try:
            r = requests.get(url, headers=headers, params=params, timeout=10)
            if r.status_code == 200 and r.json():
                item = r.json()[0]
                return float(item["lat"]), float(item["lon"])
        except Exception:
            return None
        return None

    # Se preferir Google Geocoding, habilite aqui e adicione st.secrets["GOOGLE_MAPS_KEY"]
    # def geocode_google(q: str):
    #     key = st.secrets.get("GOOGLE_MAPS_KEY")
    #     if not key: return None
    #     url = "https://maps.googleapis.com/maps/api/geocode/json"
    #     params = {"address": q, "key": key, "region": "br"}
    #     try:
        #         r = requests.get(url, params=params, timeout=10)
        #         js = r.json()
        #         if js.get("status") == "OK":
        #             loc = js["results"][0]["geometry"]["location"]
        #             return loc["lat"], loc["lng"]
        #     except Exception:
        #         return None
        #     return None

    # Monta queries únicas por loja (endereço/cidade/UF/CEP)
    pontos = []
    lojas_unicas = []
    for loja, data in contagem_por_loja.items():
        end = (data.get("endereco") or "").strip()
        cid = (data.get("cidade") or "").strip()
        uf  = (data.get("uf") or "").strip()
        cep = (data.get("cep") or "").strip()
        if not any([end, cid, uf, cep]):
            continue
        q = ", ".join([x for x in [end, cid, uf] if x]) + (f", {cep}" if cep else "") + ", Brasil"
        lojas_unicas.append((loja, q, data["qtd"]))

    with st.expander("⚙️ Configurar geocodificação", expanded=False):
        st.caption("Usa Nominatim (OSM) com cache de 24h. Recomendado manter uso moderado.")
        max_geocode = st.slider("Máximo de lojas para geocodificar por execução", 10, 500, min(100, len(lojas_unicas)))
        pause = st.slider("Pausa entre chamadas (segundos)", 0.0, 2.0, 0.5, 0.1)
        run_geo = st.checkbox("Executar geocodificação agora", value=True)

    if run_geo and lojas_unicas:
        geocoded = 0
        for loja, query, peso in lojas_unicas[:max_geocode]:
            coords = geocode_nominatim(query)  # ou geocode_google(query)
            if coords:
                lat, lon = coords
                # repete ponto proporcional a qtd de chamados (efeito heat)
                pontos += [{"lat": lat, "lon": lon} for _ in range(max(1, int(peso)))]
            geocoded += 1
            if pause > 0:
                time.sleep(pause)

        if pontos:
            st.map(pd.DataFrame(pontos), use_container_width=True)
        else:
            st.info("Nenhuma loja geocodificada com sucesso nesta execução.")
        st.caption(f"Geocodificadas: {geocoded} / {len(lojas_unicas)} loja(s)")
    else:
        st.info("Ative “Executar geocodificação agora” para gerar o mapa.")

    st.markdown("---")
    st.caption(f"Última atualização: {datetime.now():%d/%m/%Y %H:%M:%S}")
