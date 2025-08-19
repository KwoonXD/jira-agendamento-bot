# streamlit_app.py
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, date, time
from typing import Any, Dict, List, Tuple

import streamlit as st
import requests

from utils.jira_api import JiraAPI, JiraConfig
from utils.messages import gerar_mensagem, verificar_duplicidade, is_desktop

# ==========================
# Config & Constantes
# ==========================
st.set_page_config(page_title="Painel Field Service", layout="wide")

FIELDS = (
    "key,status,summary,"
    "customfield_14954,"   # Loja (Dropdown)
    "customfield_14829,"   # PDV
    "customfield_14825,"   # Ativo (Dropdown)
    "customfield_12374,"   # Problema
    "customfield_12271,"   # Endereço
    "customfield_11948,"   # Estado (Dropdown)
    "customfield_11993,"   # CEP
    "customfield_11994,"   # Cidade
    "customfield_12036,"   # Data agendada
    "customfield_12279"    # Dados do Técnico (ADF)
)

JQL = {
    "PENDENTE": 'project = FSA AND status = "AGENDAMENTO"',
    "AGENDADO": 'project = FSA AND status = "AGENDADO"',
    "TEC-CAMPO": 'project = FSA AND status = "TEC-CAMPO"',
}

# Links padrão
ISO_DESKTOP_URL = "https://drive.google.com/file/d/1GQ64blQmysK3rbM0s0Xlot89bDNAbj5L/view?usp=drive_link"
ISO_PDV_URL     = "https://drive.google.com/file/d/1vxfHUDlT3kDdMaN0HroA5Nm9_OxasTaf/view?usp=drive_link"
RAT_URL         = "https://drive.google.com/file/d/1_SG1RofIjoJLgwWYs0ya0fKlmVd74Lhn/view?usp=sharing"


# ==========================
# Helpers
# ==========================
def jira_client() -> JiraAPI:
    cfg = JiraConfig(
        email=st.secrets["jira"]["email"],
        api_token=st.secrets["jira"]["api_token"],
        url=st.secrets["jira"]["url"],
        timeout=25,
    )
    return JiraAPI(cfg)


def fmt_iso(d: date, t: time) -> str:
    return datetime.combine(d, t).strftime("%Y-%m-%dT%H:%M:%S.000-0300")


def lojas_de(*agrup_dicts: Dict[str, Any]) -> List[str]:
    s = set()
    for g in agrup_dicts:
        s.update(g.keys())
    return sorted(s)


def obrigatorios_levar(detalhes: List[Dict[str, Any]]) -> str:
    precisa_iso_desktop = any(is_desktop(d.get("ativo"), d.get("pdv")) for d in detalhes)
    if precisa_iso_desktop:
        return f"[ISO Desktop]({ISO_DESKTOP_URL})"
    return f"[ISO PDV]({ISO_PDV_URL})"


# ==========================
# Cache de dados
# ==========================
@st.cache_data(ttl=120, show_spinner=True)
def carregar() -> Dict[str, Any]:
    cli = jira_client()
    pend_raw = cli.buscar_chamados(JQL["PENDENTE"], FIELDS)
    agnd_raw = cli.buscar_chamados(JQL["AGENDADO"], FIELDS)
    tec_raw  = cli.buscar_chamados(JQL["TEC-CAMPO"], FIELDS)
    return {
        "raw": {"PENDENTE": pend_raw, "AGENDADO": agnd_raw, "TEC-CAMPO": tec_raw},
        "grp": {
            "PENDENTE": cli.agrupar_chamados(pend_raw),
            "AGENDADO": cli.agrupar_chamados(agnd_raw),
            "TEC-CAMPO": cli.agrupar_chamados(tec_raw),
        },
    }


# ==========================
# Safe load
# ==========================
try:
    data = carregar()
except requests.HTTPError as e:
    st.error("Não foi possível consultar a API do Jira. Verifique URL / email / token.")
    with st.expander("Detalhes do erro"):
        st.exception(e)
    st.stop()
except Exception as e:
    st.error("Erro inesperado ao carregar dados.")
    with st.expander("Detalhes do erro"):
        st.exception(e)
    st.stop()

grp_pend = data["grp"]["PENDENTE"]
grp_agnd = data["grp"]["AGENDADO"]
grp_tec  = data["grp"]["TEC-CAMPO"]


# ==========================
# Sidebar — Filtros + Lote
# ==========================
with st.sidebar:
    st.header("Filtros")
    todas_lojas = lojas_de(grp_pend, grp_agnd, grp_tec)
    lojas_sel = st.multiselect("Lojas", todas_lojas)
    chave_like = st.text_input("Filtrar por FSA (ex: FSA-123)")

    st.markdown("---")
    st.header("Transição em lote")

    destino = st.selectbox("Mover para:", ["—", "AGENDAMENTO", "AGENDADO", "TEC-CAMPO"])

    # monta lista de chaves com filtro global aplicado
    def listar_chaves_filtradas() -> List[str]:
        out: List[str] = []
        for g in (grp_pend, grp_agnd, grp_tec):
            for loja, itens in g.items():
                if lojas_sel and loja not in lojas_sel:  # filtra por loja se selecionado
                    continue
                for d in itens:
                    k = d.get("key", "")
                    if chave_like and chave_like.lower() not in k.lower():
                        continue
                    out.append(k)
        return sorted(set(out))

    chaves_opcoes = listar_chaves_filtradas()
    chaves_sel = st.multiselect("FSAs", chaves_opcoes, placeholder="Selecione um ou mais...")

    extra_fields: Dict[str, Any] = {}
    if destino == "AGENDADO":
        st.markdown("**Agendamento (obrigatório para mover a AGENDADO)**")
        d = st.date_input("Data", value=date.today())
        h = st.time_input("Hora", value=time(9, 0))
        tec = st.text_input("Dados do Técnico (Nome-CPF-RG-TEL)")

        if d and h:
            extra_fields["customfield_12036"] = fmt_iso(d, h)
        if tec:
            extra_fields["customfield_12279"] = {
                "type": "doc",
                "version": 1,
                "content": [{"type": "paragraph", "content": [{"type": "text", "text": tec}]}],
            }

    if st.button("Aplicar", type="primary", use_container_width=True):
        if not chaves_sel or destino == "—":
            st.warning("Selecione FSAs e o status de destino.")
        elif destino == "AGENDADO" and ("customfield_12036" not in extra_fields or "customfield_12279" not in extra_fields):
            st.warning("Para mover a AGENDADO, preencha Data/Hora e Dados do Técnico.")
        else:
            cli = jira_client()
            ok = 0
            falhas: List[str] = []
            for k in chaves_sel:
                try:
                    trans = cli.get_transitions(k)
                    tgt = next(
                        (
                            t["id"]
                            for t in trans
                            if destino.lower() in (t.get("to", {}).get("name", "").lower())
                            or destino.lower() in t.get("name", "").lower()
                        ),
                        None,
                    )
                    if not tgt:
                        falhas.append(f"{k}: transição '{destino}' indisponível")
                        continue
                    r = cli.transicionar_status(k, tgt, fields=(extra_fields or None))
                    if r.status_code == 204:
                        ok += 1
                    else:
                        falhas.append(f"{k}: HTTP {r.status_code}")
                except Exception as e:
                    falhas.append(f"{k}: {e}")

            if ok:
                st.success(f"{ok} chamado(s) atualizado(s).")
                st.cache_data.clear()
                st.rerun()
            if falhas:
                st.error("Falhas:")
                for f in falhas[:30]:
                    st.code(f)


# ==========================
# Funções de renderização
# ==========================
def aplicar_filtros(itens: List[Dict[str, Any]], loja: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if lojas_sel and loja not in lojas_sel:
        return out
    for d in itens:
        k = d.get("key", "")
        if chave_like and chave_like.lower() not in k.lower():
            continue
        out.append(d)
    return out


def titulo_expander(loja: str, itens: List[Dict[str, Any]]) -> str:
    qtd = len(itens)
    qtd_desktop = sum(1 for d in itens if is_desktop(d.get("ativo"), d.get("pdv")))
    return f"{loja} — {qtd} chamado(s) ({qtd_desktop} Desktop)"


def bloco_loja(loja: str, itens: List[Dict[str, Any]]) -> None:
    if not itens:
        return
    # chaves
    st.markdown("**FSAs:** " + ", ".join(d.get("key", "--") for d in itens))

    # mensagem (sem status/tipo)
    st.code(gerar_mensagem(loja, itens), language="text")

    # duplicidades
    dups = verificar_duplicidade(itens)
    if dups:
        st.info("Possíveis duplicidades (PDV, ATIVO): " + ", ".join(str(x) for x in sorted(dups)))

    # obrigatório levar (ISO) + RAT
    st.markdown("**Obrigatório levar:** " + obrigatorios_levar(itens))
    st.markdown("**RAT:** " + f"[Modelo]({RAT_URL})")


# ==========================
# UI — Abas
# ==========================
tab1, tab2, tab3 = st.tabs(["Pendentes", "Agendados", "Tec‑Campo"])

with tab1:
    st.subheader("Chamados em AGENDAMENTO")
    if not grp_pend:
        st.warning("Nenhum chamado em AGENDAMENTO.")
    else:
        for loja, itens in sorted(grp_pend.items()):
            itens_f = aplicar_filtros(itens, loja)
            if not itens_f:
                continue
            with st.expander(titulo_expander(loja, itens_f), expanded=False):
                bloco_loja(loja, itens_f)

with tab2:
    st.subheader("Chamados AGENDADOS (agrupados por data)")
    raw = data["raw"]["AGENDADO"]
    if not raw:
        st.info("Nenhum chamado em AGENDADO.")
    else:
        grouped: Dict[str, Dict[str, List[Dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
        for issue in raw:
            f = issue.get("fields", {}) or {}
            loja = (f.get("customfield_14954") or {}).get("value") or "Loja Desconhecida"
            raw_dt = f.get("customfield_12036")
            if raw_dt:
                dt = None
                for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
                    try:
                        dt = datetime.strptime(raw_dt, fmt)
                        break
                    except Exception:
                        pass
                data_str = dt.strftime("%d/%m/%Y") if dt else "Sem data"
            else:
                data_str = "Sem data"
            grouped[data_str][loja].append(issue)

        for data_str, lojas in sorted(grouped.items()):
            total = sum(len(v) for v in lojas.values())
            st.markdown(f"### {data_str} — {total} chamado(s)")
            for loja, issues in sorted(lojas.items()):
                detalhes = jira_client().agrupar_chamados(issues)[loja]
                detalhes_f = aplicar_filtros(detalhes, loja)
                if not detalhes_f:
                    continue
                with st.expander(titulo_expander(loja, detalhes_f), expanded=False):
                    bloco_loja(loja, detalhes_f)

with tab3:
    st.subheader("Chamados em TEC‑CAMPO")
    if not grp_tec:
        st.info("Nenhum chamado em TEC‑CAMPO.")
    else:
        for loja, itens in sorted(grp_tec.items()):
            itens_f = aplicar_filtros(itens, loja)
            if not itens_f:
                continue
            with st.expander(titulo_expander(loja, itens_f), expanded=False):
                bloco_loja(loja, itens_f)

st.markdown("---")
st.caption(f"Última atualização: {datetime.now():%d/%m/%Y %H:%M:%S}")
