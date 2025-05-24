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
        blocos.append(f"*{ch['key']}*\n*Loja:* {loja}\n*PDV:* {ch['pdv']}\n*ATIVO:* {ch['ativo']}\n*Problema:* {ch['problema']}\n*****")
    blocos.append(f"*Endereço:* {chamados[0]['endereco']}\n*Estado:* {chamados[0]['estado']}\n*CEP:* {chamados[0]['cep']}\n*Cidade:* {chamados[0]['cidade']}")
    return "\n".join(blocos)

def obter_transicoes(issue_key):
    url = f"{JIRA_URL}/rest/api/3/issue/{issue_key}/transitions"
    res = requests.get(url, headers=HEADERS, auth=AUTH)
    if res.status_code == 200:
        return res.json().get("transitions", [])
    return []

def obter_id_transicao(issue_key, nome_transicao):
    transicoes = obter_transicoes(issue_key)
    for t in transicoes:
        if t["name"].lower() == nome_transicao.lower():
            return t["id"]
    return None

def transicionar_status(issue_key, nome_transicao):
    id_transicao = obter_id_transicao(issue_key, nome_transicao)
    if not id_transicao:
        return False
    url = f"{JIRA_URL}/rest/api/3/issue/{issue_key}/transitions"
    payload = {"transition": {"id": str(id_transicao)}}
    res = requests.post(url, headers=HEADERS, auth=AUTH, json=payload)
    return res.status_code == 204

# --- Página principal ---
st.title("📱 Chamados em Agendamento")

chamados = buscar_chamados("project = FSA AND status = AGENDAMENTO")

if not chamados:
    st.warning("Nenhum chamado encontrado no momento.")
    agrupado = {}
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

# --- Agendamento de chamados ---
st.header("📆 Agendar chamados de uma loja")

with st.form("agendamento_form"):
    if agrupado:
        loja_agendamento = st.selectbox("Selecione a loja para agendar chamados:", sorted(agrupado.keys()))
        data_agendamento = st.date_input("Data de Agendamento", value=date.today())
        hora_agendamento = st.time_input("Hora de Agendamento", value=time(datetime.now().hour, datetime.now().minute))
        tecnico_responsavel = st.text_input("Nome do Técnico Responsável")
        com_tec_em_campo = st.checkbox("Já há técnico em campo nesta loja?")
        confirmar_agendamento = st.form_submit_button("📌 Agendar Chamados")

if "confirmar_agendamento" in locals() and confirmar_agendamento:
    if not tecnico_responsavel:
        st.warning("Por favor, preencha o nome do técnico responsável.")
    else:
        datetime_agendamento = f"{data_agendamento}T{hora_agendamento.strftime('%H:%M')}:00.000-0300"
        chamados_para_agendar = agrupado.get(loja_agendamento, [])
        for ch in chamados_para_agendar:
            payload = {
                "fields": {
                    "customfield_12036": datetime_agendamento,
                    "customfield_12279": {
                        "type": "doc",
                        "version": 1,
                        "content": [
                            {"type": "paragraph", "content": [{"type": "text", "text": tecnico_responsavel}]}
                        ]
                    }
                }
            }
            res = requests.put(f"{JIRA_URL}/rest/api/3/issue/{ch['key']}", headers=HEADERS, auth=AUTH, data=json.dumps(payload))
            if res.status_code == 204:
                st.success(f"✅ {ch['key']} agendado com sucesso.")
                transicionado = transicionar_status(ch['key'], "Agendado")
                if com_tec_em_campo:
                    transicionado &= transicionar_status(ch['key'], "TEC-CAMPO")
                if transicionado:
                    st.success(f"🔄 {ch['key']} transicionado com sucesso.")
                else:
                    st.warning(f"⚠️ {ch['key']} agendado, mas não foi possível transicionar status.")
            else:
                st.error(f"❌ Falha ao agendar {ch['key']}: {res.status_code}")
