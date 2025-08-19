# streamlit_app.py
import sys
from datetime import datetime, date, time
from collections import defaultdict
from typing import List, Dict, Any, Tuple, Iterable

import streamlit as st
import requests

from utils.jira_api import JiraAPI

# ─────────────────────────────────────────────────────────────
# Config da página
# ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="Painel Field Service", layout="wide")

# Banner e tema leve
st.markdown(
    """
    <style>
      .status-badge{padding:2px 8px;border-radius:999px;font-weight:600}
      .b-pend{background:#ffc10722;color:#b38700;border:1px solid #ffc10766}
      .b-agnd{background:#0dcaf022;color:#0b7285;border:1px solid #0dcaf066}
      .b-tec{background:#20c99722;color:#116b5c;border:1px solid #20c99766}
      .mono{font-family: ui-monospace, Menlo, Consolas, "Liberation Mono", monospace}
      .small{font-size:12px;opacity:.8}
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("📱 Painel Field Service")


# ─────────────────────────────────────────────────────────────
# Utilidades
# ─────────────────────────────────────────────────────────────
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
    "customfield_12279"    # Dados dos Técnicos (campo rich-text)
)

JQL = {
    "PENDENTE": 'project = FSA AND status = "AGENDAMENTO"',
    "AGENDADO": 'project = FSA AND status = "AGENDADO"',
    "TEC-CAMPO": 'project = FSA AND status = "TEC-CAMPO"',
}

def _jira() -> JiraAPI:
    return JiraAPI(
        email=st.secrets["jira"]["email"],
        api_token=st.secrets["jira"]["api_token"],
        jira_url=st.secrets["jira"]["url"],
        timeout=25,
    )

def _fmt_dt_iso(d: date, t: time) -> str:
    # Ajuste fuso se quiser (aqui -03:00 fixo)
    return datetime.combine(d, t).strftime("%Y-%m-%dT%H:%M:%S.000-0300")

def _is_desktop(ativo: str, pdv: str) -> bool:
    # Regras usadas anteriormente: PDV 300+ é Desktop, ou se "Desktop" aparece no Ativo
    try:
        if pdv and str(pdv).strip().isdigit() and int(str(pdv).strip()) >= 300:
            return True
    except Exception:
        pass
    return isinstance(ativo, str) and ("desktop" in ativo.lower())

def _gerar_mensagem(loja: str, chamados: List[Dict[str, Any]]) -> str:
    """
    Mensagem compacta por loja (para WhatsApp/Teams).
    NÃO inclui tipo de atendimento nem status (pedido recente).
    ISO fica na sessão de “Obrigatório levar” — fora desta mensagem.
    """
    blocos = []
    ref_end = None
    for ch in chamados:
        lin = [
            f"*{ch.get('key','--')}*",
            f"Loja: {loja}",
            f"PDV: {ch.get('pdv','--')}",
            f"*ATIVO: {ch.get('ativo','--')}*",
            f"Problema: {ch.get('problema','--')}",
            "***"
        ]
        blocos.append("\n".join(lin))
        # endereço de referência
        if any(ch.get(k) for k in ("endereco","estado","cep","cidade")):
            ref_end = ch

    if ref_end:
        blocos.append(
            "\n".join([
                f"Endereço: {ref_end.get('endereco','--')}",
                f"Estado: {ref_end.get('estado','--')}",
                f"CEP: {ref_end.get('cep','--')}",
                f"Cidade: {ref_end.get('cidade','--')}",
            ])
        )

    return "\n\n".join(blocos)

@st.cache_data(ttl=120, show_spinner=False)
def _carregar() -> Dict[str, Any]:
    """Carrega issues por status, já agrupadas por loja."""
    cli = _jira()
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


# ─────────────────────────────────────────────────────────────
# Carga de dados com tratamento de erro
# ─────────────────────────────────────────────────────────────
try:
    data = _carregar()
except requests.HTTPError as e:
    st.error("❌ Falha ao consultar a API do Jira. Verifique URL, email e token.")
    with st.expander("Detalhes da exceção"):
        st.exception(e)
    st.stop()
except Exception as e:
    st.error("❌ Erro inesperado ao carregar dados.")
    with st.expander("Detalhes da exceção"):
        st.exception(e)
    st.stop()


# ─────────────────────────────────────────────────────────────
# Sidebar — Filtros Globais + Ações em Lote
# ─────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("🔎 Filtros")
    # Colete todas as lojas dos três grupos
    lojas_all = set(data["grp"]["PENDENTE"].keys()) | set(data["grp"]["AGENDADO"].keys()) | set(data["grp"]["TEC-CAMPO"].keys())
    lojas_sel = st.multiselect("Lojas", sorted(lojas_all))
    chave_like = st.text_input("Filtrar por FSA (ex: FSA-123)")

    st.markdown("---")
    st.header("⚡ Transição em Lote")

    alvo = st.selectbox("Mover para status:", ["—", "AGENDAMENTO", "AGENDADO", "TEC-CAMPO"])
    st.caption("Selecione abaixo os FSAs (de qualquer aba); se destino for **AGENDADO**, data/hora e técnico são obrigatórios.")

    # Colete lista de chaves conforme filtro global
    def _lista_chaves_filtradas() -> List[str]:
        res = []
        for status_nome in ("PENDENTE", "AGENDADO", "TEC-CAMPO"):
            for loja, itens in data["grp"][status_nome].items():
                if lojas_sel and loja not in lojas_sel:
                    continue
                for d in itens:
                    if chave_like and chave_like.lower() not in d["key"].lower():
                        continue
                    res.append(d["key"])
        return sorted(res)

    opts = _lista_chaves_filtradas()
    sel_keys = st.multiselect("FSAs selecionados", opts, placeholder="Escolha um ou mais FSAs...")

    extra_fields = {}
    if alvo == "AGENDADO":
        st.markdown("**Dados de Agendamento (obrigatórios)**")
        d = st.date_input("Data", value=date.today())
        h = st.time_input("Hora", value=time(9, 0))
        tec = st.text_input("Dados dos Técnicos (Nome-CPF-RG-TEL)")
        if d and h:
            extra_fields["customfield_12036"] = _fmt_dt_iso(d, h)
        if tec:
            # campo rich-text (Atlassian Document Format)
            extra_fields["customfield_12279"] = {
                "type": "doc", "version": 1,
                "content": [{"type": "paragraph", "content": [{"type": "text", "text": tec}]}]
            }

    btn = st.button("Aplicar transição em lote", type="primary", use_container_width=True)

    if btn:
        if not sel_keys or alvo == "—":
            st.warning("Selecione ao menos um FSA e um **status destino**.")
        elif alvo == "AGENDADO" and ("customfield_12036" not in extra_fields or "customfield_12279" not in extra_fields):
            st.warning("Para mover a **AGENDADO**, preencha **Data/Hora** e **Dados do Técnico**.")
        else:
            cli = _jira()
            ok = 0
            falhas = []
            for k in sel_keys:
                try:
                    transitions = cli.get_transitions(k)
                    # Procura por nome do destino (no 'to') ou pelo nome da transição contendo o termo
                    tgt_id = next(
                        (
                            t["id"] for t in transitions
                            if alvo.lower() in (t.get("to", {}).get("name", "").lower())
                            or alvo.lower() in t.get("name", "").lower()
                        ),
                        None
                    )
                    if not tgt_id:
                        falhas.append(f"{k}: transição '{alvo}' indisponível")
                        continue
                    r = cli.transicionar_status(k, tgt_id, fields=(extra_fields or None))
                    if r.status_code == 204:
                        ok += 1
                    else:
                        falhas.append(f"{k}: HTTP {r.status_code}")
                except Exception as e:
                    falhas.append(f"{k}: {e}")

            if ok:
                st.success(f"✅ {ok} chamado(s) atualizado(s).")
                st.cache_data.clear()
                st.rerun()
            if falhas:
                st.error("Falhas:")
                for f in falhas[:20]:
                    st.code(f)


# ─────────────────────────────────────────────────────────────
# Helpers de renderização
# ─────────────────────────────────────────────────────────────
def _aplicar_filtros(lista: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for d in lista:
        if lojas_sel:
            # 'loja' não vem dentro do d, então filtramos na montagem
            pass
        if chave_like and chave_like.lower() not in d["key"].lower():
            continue
        out.append(d)
    return out

def _header_status(txt: str, cls: str) -> None:
    st.markdown(f'<span class="status-badge {cls}">{txt}</span>', unsafe_allow_html=True)

def _expander_titulo(loja: str, itens: List[Dict[str, Any]]) -> str:
    qtd = len(itens)
    qtd_pdv = sum(1 for d in itens if _is_desktop(d.get("ativo",""), str(d.get("pdv",""))))
    return f"{loja} — {qtd} chamado(s) ({qtd_pdv} Desktop)"


def _bloco_loja(loja: str, itens: List[Dict[str, Any]]) -> None:
    """Expansor por loja: mostra chaves, mensagem pronta e 'Obrigatório levar' com ISO conforme regra."""
    detalhes = list(itens)  # já filtrados por loja no loop do tab
    # Linha com as chaves
    st.markdown("**FSAs:** " + ", ".join(d.get("key","--") for d in detalhes))

    # Mensagem compacta (sem status/tipo)
    st.code(_gerar_mensagem(loja, detalhes), language="text")

    # Bloco 'Obrigatório levar'
    # ISO: se houver qualquer Desktop dentro do grupo, exibe link de ISO Desktop
    precisa_iso_desktop = any(_is_desktop(d.get("ativo",""), str(d.get("pdv",""))) for d in detalhes)

    # Links — personalize os URLs conforme já usa
    ISO_DESKTOP_URL = "https://drive.google.com/file/d/1GQ64blQmysK3rbM0s0Xlot89bDNAbj5L/view?usp=drive_link"
    ISO_PDV_URL     = "https://drive.google.com/file/d/1vxfHUDlT3kDdMaN0HroA5Nm9_OxasTaf/view?usp=drive_link"
    RAT_URL         = "https://drive.google.com/file/d/1_SG1RofIjoJLgwWYs0ya0fKlmVd74Lhn/view?usp=sharing"

    obrigatorios = []
    if precisa_iso_desktop:
        obrigatorios.append(f"[ISO Desktop]({ISO_DESKTOP_URL})")
    else:
        obrigatorios.append(f"[ISO PDV]({ISO_PDV_URL})")

    st.markdown("**🧰 É obrigatório levar:** " + " • ".join(obrigatorios))
    st.markdown("**📄 RAT:** " + f"[Baixar modelo]({RAT_URL})")


# ─────────────────────────────────────────────────────────────
# Abas
# ─────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["⏳ Pendentes", "📋 Agendados", "🧰 Tec‑Campo"])

# ——— PENDENTES
with tab1:
    _header_status("AGENDAMENTO", "b-pend")
    grp = data["grp"]["PENDENTE"]
    if not grp:
        st.warning("Nenhum chamado em AGENDAMENTO.")
    else:
        for loja, itens in sorted(grp.items()):
            if lojas_sel and loja not in lojas_sel:
                continue
            itens_f = _aplicar_filtros(itens)
            if not itens_f:
                continue
            with st.expander(_expander_titulo(loja, itens_f), expanded=False):
                _bloco_loja(loja, itens_f)

# ——— AGENDADOS
with tab2:
    _header_status("AGENDADO", "b-agnd")
    # Agrupar por data (dd/mm/aaaa) → loja
    raw = data["raw"]["AGENDADO"]
    grouped = defaultdict(lambda: defaultdict(list))
    for issue in raw:
        f = issue.get("fields", {})
        loja = (f.get("customfield_14954") or {}).get("value") or "Loja Desconhecida"
        raw_dt = f.get("customfield_12036")
        if raw_dt:
            try:
                dt = datetime.strptime(raw_dt, "%Y-%m-%dT%H:%M:%S.%f%z")
            except Exception:
                try:
                    dt = datetime.strptime(raw_dt, "%Y-%m-%dT%H:%M:%S%z")
                except Exception:
                    dt = None
            data_str = dt.strftime("%d/%m/%Y") if dt else "Sem data"
        else:
            data_str = "Sem data"
        grouped[data_str][loja].append(issue)

    if not raw:
        st.info("Nenhum chamado em AGENDADO.")
    else:
        for data_str, lojas in sorted(grouped.items()):
            total = sum(len(v) for v in lojas.values())
            st.subheader(f"{data_str} — {total} chamado(s)")
            for loja, iss in sorted(lojas.items()):
                if lojas_sel and loja not in lojas_sel:
                    continue
                # Converter para o formato do agrupar_chamados
                detalhes = _jira().agrupar_chamados(iss)[loja]
                detalhes_f = _aplicar_filtros(detalhes)
                if not detalhes_f:
                    continue
                with st.expander(_expander_titulo(loja, detalhes_f), expanded=False):
                    _bloco_loja(loja, detalhes_f)

# ——— TEC-CAMPO
with tab3:
    _header_status("TEC‑CAMPO", "b-tec")
    grp = data["grp"]["TEC-CAMPO"]
    if not grp:
        st.info("Nenhum chamado em TEC‑CAMPO.")
    else:
        for loja, itens in sorted(grp.items()):
            if lojas_sel and loja not in lojas_sel:
                continue
            itens_f = _aplicar_filtros(itens)
            if not itens_f:
                continue
            with st.expander(_expander_titulo(loja, itens_f), expanded=False):
                _bloco_loja(loja, itens_f)

st.markdown("---")
st.caption(f"Última atualização: {datetime.now():%d/%m/%Y %H:%M:%S}")
