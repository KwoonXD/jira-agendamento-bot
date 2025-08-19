# streamlit_app.py
from __future__ import annotations

import uuid
from datetime import datetime
from collections import defaultdict

import streamlit as st
from utils.jira_api import JiraAPI
from utils.messages import gerar_mensagem


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║ Config geral                                                             ║
# ╚══════════════════════════════════════════════════════════════════════════╝
st.set_page_config(page_title="Painel Field Service", layout="wide")

# CSS global para polir o visual (cards, badges, tipografia)
st.markdown(
    """
    <style>
      /* fonte e espaçamento */
      .block-container {padding-top: 1.2rem; padding-bottom: 2rem; max-width: 1250px;}
      h1, h2, h3, h4 { letter-spacing: 0.2px; }

      /* badge pill */
      .pill {
        display:inline-block; padding:4px 10px; border-radius:999px; font-weight:600; font-size:12px;
        border:1px solid rgba(255,255,255,0.08)
      }
      .pill-pend { background:#2B1A00; color:#FFC266; }
      .pill-agnd { background:#0D1F13; color:#74D680; }
      .pill-tec  { background:#0D1A26; color:#6FA8DC; }

      /* card */
      .card {
        border:1px solid rgba(255,255,255,.09);
        background:rgba(255,255,255,.02);
        border-radius:14px; padding:14px 16px; margin:10px 0 16px 0;
      }
      .card .muted {opacity:.7}
      .kpi {
        display:flex; gap:.75rem; align-items:center; font-size:12px; opacity:.85
      }
      .kpi b {font-size:13px;}
      .head-row {display:flex; gap:8px; align-items:center; justify-content:space-between;}
      .chip {
        display:inline-block; padding:2px 8px; border-radius:8px; background:#1D2530; color:#B9C2CF;
        border:1px solid rgba(255,255,255,.08); font-size:11px; margin-left:4px;
      }

      /* botão copiar */
      .copy-btn {
        font-size:12px; padding:6px 10px; border-radius:8px; border:1px solid rgba(255,255,255,.12);
        background:rgba(255,255,255,.03); cursor:pointer;
      }
      .copy-btn:hover { background:rgba(255,255,255,.06); }
      .sep {height:10px}
      details > summary { cursor: pointer; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ╔══════════════════════════════════════════════════════════════════════════╗
# ║ Definições e utilidades                                                  ║
# ╚══════════════════════════════════════════════════════════════════════════╝
JQLS = {
    "agendamento": 'project = FSA AND status = "AGENDAMENTO"',
    "agendado":    'project = FSA AND status = "AGENDADO"',
    "teccampo":    'project = FSA AND status = "TEC-CAMPO"',
}
FIELDS = ",".join([
    "status",
    "customfield_14954",  # loja
    "customfield_14829",  # PDV
    "customfield_14825",  # Ativo
    "customfield_12374",  # Problema
    "customfield_12271",  # Endereço
    "customfield_11948",  # Estado
    "customfield_11993",  # CEP
    "customfield_11994",  # Cidade
    "customfield_12036",  # Data agendada (ISO string)
])


@st.cache_data(ttl=120, show_spinner=False)
def carregar():
    cli = JiraAPI()
    me = cli.whoami()
    pend = JiraAPI.normalize(cli.search(JQLS["agendamento"], FIELDS))
    agnd = JiraAPI.normalize(cli.search(JQLS["agendado"], FIELDS))
    tec  = JiraAPI.normalize(cli.search(JQLS["teccampo"], FIELDS))
    return {"me": me, "agendamento": pend, "agendado": agnd, "teccampo": tec}


def agrupar_por_data(items: list[dict]) -> dict[str, list[dict]]:
    groups = defaultdict(list)
    for x in items:
        raw = x.get("data_agendada_raw")
        dt = raw[:10] if raw else datetime.now().strftime("%Y-%m-%d")
        groups[dt].append(x)
    # ordena por data
    return dict(sorted(groups.items(), key=lambda kv: kv[0]))


def agrupar_por_loja(items: list[dict]) -> dict[str, list[dict]]:
    g = defaultdict(list)
    for x in items:
        g[str(x.get("loja", "--"))].append(x)
    # ordena numericamente quando possível
    def keyf(k):
        try:
            return int(k)
        except Exception:
            return 10**9
    return dict(sorted(g.items(), key=lambda kv: keyf(kv[0])))


def pill(label: str) -> str:
    return {
        "AGENDAMENTO": "<span class='pill pill-pend'>PENDENTE</span>",
        "AGENDADO":    "<span class='pill pill-agnd'>AGENDADO</span>",
        "TEC-CAMPO":   "<span class='pill pill-tec'>TEC-CAMPO</span>",
    }[label]


def render_copy_button(text_to_copy: str, label: str = "Copiar mensagem"):
    """
    Injeta um botão HTML + JS para copiar para a área de transferência.
    """
    uid = f"copy_{uuid.uuid4().hex}"
    html = f"""
    <button class="copy-btn" onclick="
      navigator.clipboard.writeText(document.getElementById('{uid}').innerText);
      this.innerText='Copiado!';
      setTimeout(()=>this.innerText='{label}',1200);
    ">{label}</button>
    <pre id="{uid}" style="white-space: pre-wrap; display:none;">{text_to_copy}</pre>
    """
    st.markdown(html, unsafe_allow_html=True)


def contador_badges(pend: int, agnd: int, tec: int):
    c1, c2, c3, c4 = st.columns([1,1,1,6])
    c1.markdown(f"<span class='pill pill-pend'>PENDENTES: <b>{pend}</b></span>", unsafe_allow_html=True)
    c2.markdown(f"<span class='pill pill-agnd'>AGENDADOS: <b>{agnd}</b></span>", unsafe_allow_html=True)
    c3.markdown(f"<span class='pill pill-tec'>TEC-CAMPO: <b>{tec}</b></span>", unsafe_allow_html=True)
    with c4:
        if st.button("↻ Atualizar", use_container_width=False):
            st.cache_data.clear()
            st.rerun()


def aplica_filtros(lista: list[dict], termo: str, somente_spare: bool, somente_dup: bool) -> list[dict]:
    termo = (termo or "").strip().lower()
    if not (termo or somente_spare or somente_dup):
        return lista

    # checa duplicidade por (pdv, ativo)
    seen = set()
    dups = set()
    for c in lista:
        key = (str(c.get("pdv")), str(c.get("ativo")).strip().lower())
        if key in seen:
            dups.add(key)
        else:
            seen.add(key)

    out = []
    for c in lista:
        text = " ".join([
            str(c.get("key","")),
            str(c.get("loja","")),
            str(c.get("pdv","")),
            str(c.get("ativo","")),
            str(c.get("problema","")),
            str(c.get("cidade","")),
        ]).lower()

        is_spare = "spare" in str(c.get("ativo","")).lower()
        is_dup = (str(c.get("pdv")), str(c.get("ativo")).strip().lower()) in dups

        if termo and termo not in text:
            continue
        if somente_spare and not is_spare:
            continue
        if somente_dup and not is_dup:
            continue
        out.append(c)
    return out


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║ Cabeçalho                                                                ║
# ╚══════════════════════════════════════════════════════════════════════════╝
st.markdown("<h1>Painel Field Service</h1>", unsafe_allow_html=True)
try:
    data = carregar()
    st.caption(f"Conectado como **{data['me'].get('displayName','?')}** — {datetime.now():%d/%m/%Y %H:%M}")
except Exception as e:
    st.error(str(e))
    st.stop()

# KPIs de topo
contador_badges(len(data["agendamento"]), len(data["agendado"]), len(data["teccampo"]))

# Filtros globais
with st.expander("Filtros"):
    f1, f2, f3, f4 = st.columns([3,1.2,1.2,4])
    termo = f1.text_input("Busca global", placeholder="loja, PDV, ativo, problema, chave...")
    somente_spare = f2.toggle("Somente SPARE", value=False)
    somente_dup = f3.toggle("Somente duplicados", value=False)
    f4.caption("Dica: a busca combina vários campos e funciona em todas as abas.")

# ╔══════════════════════════════════════════════════════════════════════════╗
# ║ Abas                                                                     ║
# ╚══════════════════════════════════════════════════════════════════════════╝
tab1, tab2, tab3 = st.tabs(
    [f"AGENDAMENTO", f"AGENDADO", f"TEC-CAMPO"]
)

def desenhar_aba(nome: str, items: list[dict]):
    # Aplicar filtros globais
    items_f = aplica_filtros(items, termo, somente_spare, somente_dup)

    por_data = agrupar_por_data(items_f)
    total = sum(len(v) for v in por_data.values())
    st.markdown(f"<div class='kpi'><b>{total}</b> chamado(s) {pill(nome)}</div>", unsafe_allow_html=True)

    for dia, arr in por_data.items():
        leg_data = datetime.strptime(dia, "%Y-%m-%d").strftime("%d/%m/%Y")
        st.markdown(f"### {leg_data}  <span class='chip'> {len(arr)} chamados </span>", unsafe_allow_html=True)

        # Dentro de cada dia, agrupar por loja
        por_loja = agrupar_por_loja(arr)
        for loja, chamados in por_loja.items():
            msg = gerar_mensagem(loja, chamados)

            # Cabeçalho do card (loja e contagem)
            st.markdown(
                f"""
                <div class='card'>
                  <div class='head-row'>
                    <div style="font-weight:700;">Loja {loja}</div>
                    <div class='muted'>{len(chamados)} chamado(s)</div>
                  </div>
                """,
                unsafe_allow_html=True,
            )

            # botões (copiar) + conteúdo colapsável
            c_left, c_right = st.columns([6,1])
            with c_left:
                render_copy_button(msg, "Copiar mensagem")
                st.markdown("<div class='sep'></div>", unsafe_allow_html=True)
                with st.expander("Ver mensagem"):
                    st.code(msg, language="text")
            with c_right:
                # mini-Resumo de ativos (extra gostosinho)
                ativos = {}
                for c in chamados:
                    a = str(c.get("ativo","--")).upper()
                    ativos[a] = ativos.get(a, 0) + 1
                if ativos:
                    st.markdown("**Ativos**")
                    for k, v in sorted(ativos.items(), key=lambda x:-x[1]):
                        st.caption(f"- {k}: {v}")

            # fecha card
            st.markdown("</div>", unsafe_allow_html=True)

with tab1:
    desenhar_aba("AGENDAMENTO", data["agendamento"])
with tab2:
    desenhar_aba("AGENDADO", data["agendado"])
with tab3:
    desenhar_aba("TEC-CAMPO", data["teccampo"])

st.caption(f"Atualizado em {datetime.now():%d/%m/%Y %H:%M}")
