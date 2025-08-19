import os
from collections import defaultdict
from datetime import datetime
import pytz
import streamlit as st

from utils.jira_api import JiraAPI
from utils.messages import (
    gerar_mensagem_whatsapp,
    encontrar_duplicados,
    ISO_DESKTOP_URL,
    ISO_PDV_URL,
    RAT_URL,
)

# —————————————————— CONFIG ——————————————————
st.set_page_config(page_title="Painel Field Service", layout="wide", page_icon="🛠️")

# Campos que buscamos no Jira (ajuste se necessário)
FIELDS = [
    "status",
    "customfield_14954",  # Loja (option.value)
    "customfield_14829",  # PDV
    "customfield_14825",  # Ativo (option.value)
    "customfield_12374",  # Problema
    "customfield_12271",  # Endereço
    "customfield_11948",  # Estado (option.value)
    "customfield_11993",  # CEP
    "customfield_11994",  # Cidade
    "customfield_12036",  # Data agendada
]

# JQLs simples por status
JQLS = {
    "agendamento": 'project = FSA AND status = "AGENDAMENTO"',
    "agendado": 'project = FSA AND status = "AGENDADO"',
    "tec": 'project = FSA AND status = "TEC-CAMPO"',
}

# —————————————————— SECRETS / CONEXÃO ——————————————————
def get_jira_credentials():
    # Preferir secrets (permanente)
    if "jira" in st.secrets:
        sec = st.secrets["jira"]
        return sec.get("url"), sec.get("email"), sec.get("token")
    # Fallback: variáveis de ambiente (opcional)
    env = os.environ
    if all(k in env for k in ("JIRA_URL", "JIRA_EMAIL", "JIRA_TOKEN")):
        return env["JIRA_URL"], env["JIRA_EMAIL"], env["JIRA_TOKEN"]
    # Sem nada -> avisa com instruções
    st.error(
        "Credenciais do Jira não encontradas em `st.secrets['jira']`.\n\n"
        "Adicione no *App secrets* do Streamlit Cloud (ou `secrets.toml` local):\n\n"
        "```toml\n[jira]\nurl = \"https://seu-dominio.atlassian.net\"\nemail = \"seu-email@dominio\"\ntoken = \"seu_api_token\"\n```\n"
    )
    st.stop()


@st.cache_data(ttl=120, show_spinner=False)
def carregar():
    url, email, token = get_jira_credentials()
    cli = JiraAPI(url=url, email=email, token=token)
    # Busca
    agendamento_raw = cli.buscar_chamados(JQLS["agendamento"], FIELDS, max_results=250)
    agendado_raw = cli.buscar_chamados(JQLS["agendado"], FIELDS, max_results=250)
    tec_raw = cli.buscar_chamados(JQLS["tec"], FIELDS, max_results=250)

    # Normaliza
    agendamento = [cli.normalizar(i) for i in agendamento_raw]
    agendado = [cli.normalizar(i) for i in agendado_raw]
    tec = [cli.normalizar(i) for i in tec_raw]

    return {
        "agendamento": agendamento,
        "agendado": agendado,
        "tec": tec,
    }


# —————————————————— UI ——————————————————
st.title("Painel Field Service")

with st.sidebar:
    st.subheader("Credenciais")
    url, email, token = get_jira_credentials()
    st.caption("Lendo de `st.secrets['jira']`.")
    st.code(f"url={url}\nemail={email}", language="toml")
    st.markdown("---")
    st.markdown("**Links padrão**")
    st.write(f"ISO Desktop: {ISO_DESKTOP_URL}")
    st.write(f"ISO PDV: {ISO_PDV_URL}")
    st.write(f"RAT: {RAT_URL}")

# Carregar dados
data = carregar()

def agrupar_por_data_e_loja(chamados: list[dict]) -> dict[str, dict[str, list[dict]]]:
    """
    -> { YYYY-MM-DD : { loja : [chamados...] } }
    Data preferida: fields.customfield_12036 (data_agendada).
    Se não tiver, usa a data atual só para não perder o grupo.
    """
    tz = pytz.timezone("America/Sao_Paulo")
    hoje = datetime.now(tz).strftime("%Y-%m-%d")

    agrup: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for ch in chamados:
        d = ch.get("data_agendada")
        if isinstance(d, str) and len(d) >= 10:
            key_date = d[:10]
        else:
            key_date = hoje
        loja = str(ch.get("loja", "Loja"))
        agrup[key_date][loja].append(ch)
    return agrup


def render_coluna(titulo: str, chamados: list[dict]):
    st.subheader(titulo)

    # Duplicados e Spare
    dup_set = encontrar_duplicados(chamados)

    agrup = agrupar_por_data_e_loja(chamados)
    for data_dia in sorted(agrup.keys()):
        grupos_loja = agrup[data_dia]
        total = sum(len(v) for v in grupos_loja.values())
        with st.expander(f"{datetime.strptime(data_dia, '%Y-%m-%d').strftime('%d/%m/%Y')} — {total} chamado(s)", expanded=False):
            for loja in sorted(grupos_loja.keys(), key=lambda x: (len(x), x)):
                dets = grupos_loja[loja]

                # badges
                qtd_spare = sum(1 for d in dets if d.get("has_spare"))
                qtd_dup = sum(1 for d in dets if d.get("dup_key") in dup_set)
                badges = []
                if qtd_spare:
                    badges.append(f"🧩 {qtd_spare} c/ Spare")
                if qtd_dup:
                    badges.append(f"⚠️ {qtd_dup} duplicado(s)")
                badge_txt = (" — " + " | ".join(badges)) if badges else ""

                st.markdown(f"**{loja}** — {len(dets)} chamado(s){badge_txt}")

                # Lista resumida
                for d in dets:
                    flags = []
                    if d.get("has_spare"):
                        flags.append("🧩 Spare")
                    if d.get("dup_key") in dup_set:
                        flags.append("⚠️ Duplicado")
                    flags_txt = f" ({', '.join(flags)})" if flags else ""
                    st.write(f"- {d['key']} | PDV {d['pdv']} | ATIVO {d['ativo']}{flags_txt}")

                # Mensagem “WhatsApp”
                st.code(gerar_mensagem_whatsapp(loja, dets), language="text")


# —————————————————— ABAS ——————————————————
tab1, tab2, tab3 = st.tabs(["AGENDAMENTO", "AGENDADO", "TEC-CAMPO"])

with tab1:
    render_coluna("Chamados AGENDAMENTO", data["agendamento"])

with tab2:
    render_coluna("Chamados AGENDADO", data["agendado"])

with tab3:
    render_coluna("Chamados TEC-CAMPO", data["tec"])

st.caption(f"Atualizado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
