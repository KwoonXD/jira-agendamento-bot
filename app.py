import streamlit as st
from streamlit_autorefresh import st_autorefresh
import requests
from requests.auth import HTTPBasicAuth
from datetime import datetime, date, time
from collections import defaultdict
import json

# --- Configurações e autenticação ---
st.set_page_config(page_title="Chamados em Agendamento", layout="wide")
st_autorefresh(interval=60 * 1000, key="auto_refresh")

EMAIL = st.secrets["EMAIL"]
API_TOKEN = st.secrets["API_TOKEN"]
JIRA_URL = "https://delfia.atlassian.net"
AUTH = HTTPBasicAuth(EMAIL, API_TOKEN)
HEADERS = {"Accept": "application/json", "Content-Type": "application/json"}

# --- Funções reutilizáveis ---
def buscar_chamados(jql):
    params = {"jql": jql, "maxResults": 100, "fields": "summary,customfield_14954,customfield_14829,customfield_14825,customfield_12374,customfield_12271,customfield_11993,customfield_11994,customfield_11948"}
    res = requests.get(f"{JIRA_URL}/rest/api/3/search", headers=HEADERS, auth=AUTH, params=params)
    return res.json().get("issues", []) if res.status_code == 200 else []

def gerar_mensagem(loja, chamados):
    blocos = []
    for ch in chamados:
        blocos.append(f"*{ch['key']}*\n*Loja* {loja}\n*PDV:* {ch['pdv']}\n*ATIVO:* {ch['ativo']}\n*Problema:* {ch['problema']}\n*****")
    blocos.append(f"*Endereço:* {chamados[0]['endereco']}\n*Estado:* {chamados[0]['estado']}\n*CEP:* {chamados[0]['cep']}\n*Cidade:* {chamados[0]['cidade']}")
    return "\n".join(blocos)

# --- Página principal ---
st.title("📡 Chamados em Agendamento")

chamados = buscar_chamados("project = FSA AND status = AGENDAMENTO")

if not chamados:
    st.warning("Nenhum chamado encontrado no momento.")
else:
    agrupado = defaultdict(list)
    for issue in chamados:
        fields = issue["fields"]
        loja = fields.get("customfield_14954", {}).get("value", "Loja Desconhecida")
        agrupado[loja].append({
            "key": issue["key"],
            "pdv": fields.get("customfield_14829", "--"),
            "ativo": fields.get("customfield_14825", {}).get("value", "--"),
            "problema": fields.get("customfield_12374", "--"),
            "endereco": fields.get("customfield_12271", "--"),
            "estado": fields.get("customfield_11948", {}).get("value", "--"),
            "cep": fields.get("customfield_11993", "--"),
            "cidade": fields.get("customfield_11994", "--")
        })

    st.success(f"{len(chamados)} chamados encontrados.")

    for loja, lista in agrupado.items():
        with st.expander(f"Loja {loja} - {len(lista)} chamado(s)", expanded=False):
            st.code(gerar_mensagem(loja, lista), language="text")

st.markdown("---")
st.caption(f"🕒 Última atualização automática: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")

# --- Seção extra: Atualizar chamados TEC-CAMPO ---
st.header("🔧 Atualizar chamados TEC-CAMPO por loja")

with st.form("atualizar_form"):
    loja_input = st.text_input("Digite o código da loja (ex: L005, L024, Loja 5030):")

    col1, col2, col3 = st.columns(3)
    with col1:
        data_inicio = st.date_input("Data Início", value=date.today())
        hora_inicio = st.time_input("Hora Início", value=datetime.now().time())
    with col2:
        data_fim = st.date_input("Data Fim", value=date.today())
        hora_fim = st.time_input("Hora Fim", value=datetime.now().time())
    with col3:
        data_agendamento = st.date_input("Data de Agendamento", value=date.today())
        hora_agendamento = st.time_input("Hora Agendamento", value=datetime.now().time())

    datetime_inicio = f"{data_inicio}T{hora_inicio.strftime('%H:%M:%S')}.000-0300"
    datetime_fim = f"{data_fim}T{hora_fim.strftime('%H:%M:%S')}.000-0300"
    datetime_agendamento = f"{data_agendamento}T{hora_agendamento.strftime('%H:%M:%S')}.000-0300"

    custo_visita = st.number_input("Custo da Visita (padrão: 120.0)", value=120.0)
    num_visita = st.number_input("Número de Visita", value=1)
    confirmar = st.form_submit_button("🔁 Buscar e Preparar Atualização")

if confirmar and loja_input:
    if loja_input.upper().startswith("LOJA"):
        loja_term = loja_input.upper()
    else:
        numero = loja_input.replace("L", "").zfill(3)
        loja_term = f"L{numero}"

    jql = f'project = FSA AND status = "TEC-CAMPO" AND text ~ "{loja_term}"'
    tec_chamados = buscar_chamados(jql)

    encontrados = []
    for ch in tec_chamados:
        loja_real = ch["fields"].get("customfield_14954", {}).get("value", "")
        if loja_real == loja_term or loja_real.upper() == loja_input.upper():
            encontrados.append(ch)

    if not encontrados:
        st.warning("Nenhum chamado TEC-CAMPO encontrado para essa loja.")
    else:
        st.info(f"{len(encontrados)} chamados encontrados para a loja {loja_input}.")
        edicoes = {}
        for ch in encontrados:
            with st.expander(f"Chamado {ch['key']}", expanded=True):
                valor_individual = st.number_input(f"Custo específico para {ch['key']}", value=custo_visita, key=ch['key'])
                edicoes[ch['key']] = valor_individual

        if st.button("✅ Confirmar e Atualizar Todos"):
            for ch in encontrados:
                payload = {
                    "fields": {
                        "customfield_10702": datetime_inicio,
                        "customfield_10703": datetime_fim,
                        "customfield_12036": datetime_agendamento,
                        "customfield_12413": edicoes[ch['key']],
                        "customfield_12657": num_visita,
                        "customfield_11958": edicoes[ch['key']]
                    }
                }
                res = requests.put(f"{JIRA_URL}/rest/api/3/issue/{ch['key']}", headers=HEADERS, auth=AUTH, data=json.dumps(payload))
                if res.status_code == 204:
                    st.success(f"✅ {ch['key']} atualizado com sucesso.")
                else:
                    st.error(f"❌ Erro ao atualizar {ch['key']}: {res.status_code}")
