import os
from datetime import datetime, time
from collections import defaultdict
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from utils.jira_api import JiraAPI
from utils.messages import (
    gerar_mensagem,
    verificar_duplicidade,
    ISO_DESKTOP_URL,
    ISO_PDV_URL,
    RAT_URL,
)

# ──────────────────────────────────────────────────────────────────────────────
# Config Página + Auto-Refresh (90s)
# ──────────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Painel Field Service", layout="wide")
st_autorefresh(interval=90_000, key="auto_refresh")

# Histórico para desfazer (opcional)
if "history" not in st.session_state:
    st.session_state.history = []

# ──────────────────────────────────────────────────────────────────────────────
# Ler credenciais Jira com fallback (secrets → env)
# ──────────────────────────────────────────────────────────────────────────────
def _read_secret(name: str, env: str, default: str = None):
    try:
        return st.secrets[name]
    except Exception:
        return os.getenv(env, default)

EMAIL    = _read_secret("EMAIL",    "JIRA_EMAIL",    "")
API_TOKEN= _read_secret("API_TOKEN","JIRA_API_TOKEN","")
JIRA_URL = _read_secret("JIRA_URL", "JIRA_URL",      "https://delfia.atlassian.net")

if not (EMAIL and API_TOKEN and JIRA_URL):
    st.error("🔐 Credenciais do Jira ausentes. Configure EMAIL, API_TOKEN e JIRA_URL nos Secrets ou variáveis de ambiente.")
    st.stop()

jira = JiraAPI(EMAIL, API_TOKEN, JIRA_URL)

# ──────────────────────────────────────────────────────────────────────────────
# Campos a buscar no Jira
# ──────────────────────────────────────────────────────────────────────────────
FIELDS = (
    "summary,status,customfield_14954,customfield_14829,customfield_14825,"
    "customfield_12374,customfield_12271,customfield_11993,customfield_11994,"
    "customfield_11948,customfield_12036,customfield_12279"
)

JQLS = {
    "pend": 'project = FSA AND status = AGENDAMENTO',
    "agnd": 'project = FSA AND status = AGENDADO',
    "tec":  'project = FSA AND status in (TEC-CAMPO)'
}

# ──────────────────────────────────────────────────────────────────────────────
# Helpers de parsing
# ──────────────────────────────────────────────────────────────────────────────
def parse_dt(raw: str) -> str:
    if not raw:
        return "Não definida"
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(raw, fmt).strftime("%d/%m/%Y %H:%M")
        except Exception:
            pass
    return str(raw)

def is_desktop(ch: dict) -> bool:
    """Desktop se: PDV >= 300 ou ativo contém 'desktop' (case-insensitive)."""
    try:
        pdv = str(ch.get("pdv", "")).strip()
        num = int(pdv) if pdv.isdigit() else -1
    except Exception:
        num = -1
    ativo = str(ch.get("ativo", "")).lower()
    return (num >= 300) or ("desktop" in ativo)

# ──────────────────────────────────────────────────────────────────────────────
# Cache de dados para reduzir delay
# ──────────────────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=True, ttl=60)
def carregar():
    pend = jira.buscar_chamados(JQLS["pend"], FIELDS)
    agnd = jira.buscar_chamados(JQLS["agnd"], FIELDS)
    tec  = jira.buscar_chamados(JQLS["tec"],  FIELDS)
    return {"pend": pend, "agnd": agnd, "tec": tec}

# ──────────────────────────────────────────────────────────────────────────────
# Agrupar utilitário
# ──────────────────────────────────────────────────────────────────────────────
def agrupar_por_loja(issues: list) -> dict:
    # Reusa o método para padronizar estrutura (com status, pdv, etc.)
    return jira.agrupar_chamados(issues)

def agendados_por_data_loja(issues: list) -> dict:
    by_date = defaultdict(lambda: defaultdict(list))
    for issue in issues:
        f = issue.get("fields", {})
        loja = f.get("customfield_14954", {}).get("value", "Loja Desconhecida")
        data = parse_dt(f.get("customfield_12036"))
        by_date[data][loja].append(issue)
    return by_date

# ──────────────────────────────────────────────────────────────────────────────
# UI: Barra lateral (Desfazer e Transições em Lote)
# ──────────────────────────────────────────────────────────────────────────────
def sidebar_transicoes(pendentes_raw, agendados_raw):
    with st.sidebar:
        st.header("Ações")
        # Desfazer
        if st.button("↩️ Desfazer última ação"):
            if st.session_state.history:
                action = st.session_state.history.pop()
                reverted = 0
                for key in action["keys"]:
                    trans = jira.get_transitions(key)
                    rev_id = next(
                        (t["id"] for t in trans if t.get("to", {}).get("name") == action["from"]),
                        None
                    )
                    if rev_id and jira.transicionar_status(key, rev_id).status_code == 204:
                        reverted += 1
                st.success(f"Revertido: {reverted} FSAs → {action['from']}")
                st.cache_data.clear()
            else:
                st.info("Nenhuma ação para desfazer.")

        st.markdown("---")
        st.header("Transição em Lote")
        # Escolher loja
        lojas = sorted(
            set(jira.agrupar_chamados(pendentes_raw).keys())
            | set(jira.agrupar_chamados(agendados_raw).keys())
        )
        loja_sel = st.selectbox("Loja:", ["—"] + lojas)
        if loja_sel == "—":
            return

        # Coleta chaves por loja
        keys_pend = [i["key"] for i in pendentes_raw if i["fields"].get("customfield_14954", {}).get("value") == loja_sel]
        keys_agnd = [i["key"] for i in agendados_raw if i["fields"].get("customfield_14954", {}).get("value") == loja_sel]
        all_keys  = sorted(set(keys_pend + keys_agnd))

        # Agendamento rápido (obrigatórios)
        st.subheader("Agendamento Rápido")
        data = st.date_input("Data")
        hora = st.time_input("Hora", value=time(9, 0))
        tecnico = st.text_input("Dados do Técnico (Nome-CPF-RG-TEL)")
        sem_tecnico = st.checkbox("Sem técnico (atribuir Técnico Fictício e apenas agendar)")

        if st.button(f"Agendar e mover {len(all_keys)} FSAs → Tec‑Campo"):
            if (not data or not hora):
                st.warning("Informe data e hora.")
                return
            # payload
            dt_iso = datetime.combine(data, hora).strftime("%Y-%m-%dT%H:%M:%S.000-0300")
            extra_ag = {"customfield_12036": dt_iso}
            if tecnico:
                extra_ag["customfield_12279"] = {
                    "type": "doc", "version": 1,
                    "content": [{"type": "paragraph", "content": [{"type": "text", "text": tecnico}]}]
                }

            erros = []
            # 1) Agendar pendentes
            for k in keys_pend:
                trans = jira.get_transitions(k)
                agid = next((t["id"] for t in trans if "agend" in t["name"].lower()), None)
                if agid:
                    r = jira.transicionar_status(k, agid, fields=extra_ag)
                    if r.status_code != 204:
                        erros.append(f"{k}⏳{r.status_code}")

            # 2) Atribuição (técnico real ou fictício) – se desejar marcar no campo rich text
            if sem_tecnico and not tecnico:
                # escreve “Sem técnico — Fictício” no campo de técnico
                extra_attr = {
                    "customfield_12279": {
                        "type": "doc", "version": 1,
                        "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Técnico Fictício (Sem técnico)"}]}]
                    }
                }
                for k in all_keys:
                    r = jira.transicionar_status(k, None, fields=extra_attr)  # só atualiza campos
                    # Ignora status_code != 204 pois alguns projetos exigem transition id para update (sem transição). Sem erro crítico.

            # 3) Mover todos para Tec‑Campo
            moved = 0
            for k in all_keys:
                trans = jira.get_transitions(k)
                tcid = next((t["id"] for t in trans if "tec-campo" in t.get("to", {}).get("name", "").lower()), None)
                if tcid:
                    r = jira.transicionar_status(k, tcid)
                    if r.status_code == 204:
                        moved += 1
                    else:
                        erros.append(f"{k}➡️{r.status_code}")

            if erros:
                st.error("Erros:"); [st.code(e) for e in erros]
            else:
                st.success(f"{len(all_keys)} FSAs agendados e movidos → Tec‑Campo")
                st.session_state.history.append({"keys": all_keys, "from": "AGENDADO"})
                st.cache_data.clear()

# ──────────────────────────────────────────────────────────────────────────────
# UI: Bloco reutilizável por loja
# ──────────────────────────────────────────────────────────────────────────────
def bloco_por_loja(loja: str, detalhes: list):
    """
    detalhes: lista de dicts vindos de JiraAPI.agrupar_chamados (já normalizados).
    """
    # FSAs
    st.markdown("**FSAs:** " + ", ".join(d["key"] for d in detalhes))
    # Mensagem pronta p/ enviar (sem status/tipo; ISO aparece em Obrigatório levar; RAT no final)
    st.code(
        gerar_mensagem(
            loja,
            detalhes,
            iso_desktop=ISO_DESKTOP_URL,
            iso_pdv=ISO_PDV_URL,
            rat_url=RAT_URL,
            detect_desktop=is_desktop,
        ),
        language="text"
    )

# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────
st.title("📱 Painel Field Service")

# Carregar dados
try:
    data = carregar()
except Exception as e:
    st.error(f"Falha ao carregar dados do Jira: {e}")
    st.stop()

pendentes_raw = data["pend"]
agendados_raw = data["agnd"]
tec_raw       = data["tec"]

# Sidebar ações
sidebar_transicoes(pendentes_raw, agendados_raw)

# Tabs
tab1, tab2, tab3 = st.tabs(["⏳ Pendentes", "📋 Agendados", "🛠️ Tec‑Campo"])

# ── TAB 1: Pendentes
with tab1:
    st.subheader("Chamados PENDENTES de Agendamento")
    if not pendentes_raw:
        st.warning("Nenhum chamado em AGENDAMENTO.")
    else:
        agrup_pend = agrupar_por_loja(pendentes_raw)
        for loja, iss in sorted(agrup_pend.items()):
            with st.expander(f"{loja} — {len(iss)} chamado(s)", expanded=False):
                bloco_por_loja(loja, iss)

# ── TAB 2: Agendados
with tab2:
    st.subheader("Chamados AGENDADOS")
    if not agendados_raw:
        st.info("Nenhum chamado em AGENDADO.")
    else:
        grouped_sched = agendados_por_data_loja(agendados_raw)
        for date, stores in sorted(grouped_sched.items()):
            total = sum(len(v) for v in stores.values())
            st.markdown(f"### {date} — {total} chamado(s)")
            for loja, iss in sorted(stores.items()):
                # Normaliza os dicts da mesma forma do pendente
                detalhes = agrupar_por_loja(iss)[loja]
                # Marcação de duplicidades e spare
                dup_keys = [d["key"] for d in detalhes if (d["pdv"], d["ativo"]) in verificar_duplicidade(detalhes)]
                spare_raw = jira.buscar_chamados(
                    f'project = FSA AND status = "Aguardando Spare" AND "Codigo da Loja[Dropdown]" = {loja}', FIELDS
                )
                spare_keys = [i["key"] for i in spare_raw]
                tags = []
                if spare_keys: tags.append("Spare: " + ", ".join(spare_keys))
                if dup_keys:   tags.append("Dup: " + ", ".join(dup_keys))
                tag_str = f" [{' • '.join(tags)}]" if tags else ""
                with st.expander(f"{loja} — {len(iss)} chamado(s){tag_str}", expanded=False):
                    bloco_por_loja(loja, detalhes)

# ── TAB 3: Tec‑Campo
with tab3:
    st.subheader("Chamados TEC‑CAMPO")
    if not tec_raw:
        st.info("Nenhum chamado em TEC‑CAMPO.")
    else:
        agrup_tec = agrupar_por_loja(tec_raw)
        for loja, iss in sorted(agrup_tec.items()):
            with st.expander(f"{loja} — {len(iss)} chamado(s)", expanded=False):
                bloco_por_loja(loja, iss)

st.markdown("---")
st.caption(f"Última atualização: {datetime.now():%d/%m/%Y %H:%M:%S}")
