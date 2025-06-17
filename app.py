import streamlit as st
from streamlit_autorefresh import st_autorefresh
import requests
from requests.auth import HTTPBasicAuth
from datetime import datetime
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
    params = {
        "jql": jql,
        "maxResults": 100,
        "fields": "summary,customfield_14954,customfield_14829,customfield_14825,customfield_12374,customfield_12271,customfield_11993,customfield_11994,customfield_11948,customfield_12036"
    }
    res = requests.get(f"{JIRA_URL}/rest/api/3/search", headers=HEADERS, auth=AUTH, params=params)
    return res.json().get("issues", []) if res.status_code == 200 else []

def gerar_mensagem(loja, chamados):
    blocos = []
    for ch in chamados:
        data_agendada = ch.get('data_agendada')
        data_formatada = datetime.strptime(data_agendada, "%Y-%m-%dT%H:%M:%S.%f%z").strftime('%d/%m/%Y %H:%M') if data_agendada else '--'
        blocos.append(
            f"*{ch['key']}*\n"
            f"*Loja:* {loja}\n"
            f"*PDV:* {ch['pdv']}\n"
            f"*ATIVO:* {ch['ativo']}\n"
            f"*Problema:* {ch['problema']}\n"
            f"*Data Agendada:* {data_formatada}\n*****"
        )
    blocos.append(
        f"*Endereço:* {chamados[0]['endereco']}\n"
        f"*Estado:* {chamados[0]['estado']}\n"
        f"*CEP:* {chamados[0]['cep']}\n"
        f"*Cidade:* {chamados[0]['cidade']}"
    )
    return "\n".join(blocos)

def transicionar_status(issue_key, id_transicao):
    res = requests.post(
        f"{JIRA_URL}/rest/api/3/issue/{issue_key}/transitions",
        headers=HEADERS,
        auth=AUTH,
        json={"transition": {"id": str(id_transicao)}}
    )
    return res.status_code == 204

# --- Página principal ---
st.title("📱 Chamados em Agendamento")

# --- Chamados em AGENDAMENTO ---
st.header("⏳ Chamados PENDENTES de Agendamento")
chamados = buscar_chamados("project = FSA AND status = AGENDAMENTO")

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
        "cidade": fields.get("customfield_11994", "--"),
        "data_agendada": fields.get("customfield_12036", "")
    })

if not chamados:
    st.warning("Nenhum chamado em AGENDAMENTO encontrado no momento.")
else:
    st.success(f"{len(chamados)} chamados em AGENDAMENTO encontrados.")
    for loja, lista in agrupado.items():
        with st.expander(f"Loja {loja} - {len(lista)} chamado(s) AGENDAMENTO", expanded=False):
            st.code(gerar_mensagem(loja, lista), language="text")

# --- Chamados em AGENDADO ---
st.header("📋 Chamados AGENDADOS")
chamados_agendados = buscar_chamados("project = FSA AND status = AGENDADO")

agrupado_agendado = defaultdict(list)
for issue in chamados_agendados:
    fields = issue["fields"]
    loja = fields.get("customfield_14954", {}).get("value", "Loja Desconhecida")
    agrupado_agendado[loja].append({
        "key": issue["key"],
        "pdv": fields.get("customfield_14829", "--"),
        "ativo": fields.get("customfield_14825", {}).get("value", "--"),
        "problema": fields.get("customfield_12374", "--"),
        "endereco": fields.get("customfield_12271", "--"),
        "estado": fields.get("customfield_11948", {}).get("value", "--"),
        "cep": fields.get("customfield_11993", "--"),
        "cidade": fields.get("customfield_11994", "--"),
        "data_agendada": fields.get("customfield_12036", "")
    })

if not agrupado_agendado:
    st.info("Nenhum chamado em AGENDADO encontrado.")
else:
    for loja, lista in agrupado_agendado.items():
        com_spare = buscar_chamados(f'project = FSA AND status = "Aguardando Spare" AND "Codigo da Loja[Dropdown]" = {loja}')
        if com_spare:
            aviso = f"⚠️ {len(com_spare)} chamado(s) em Aguardando Spare para esta loja: {', '.join(c['key'] for c in com_spare)}"
        else:
            aviso = "✅ Sem chamados em Aguardando Spare para esta loja."

        with st.expander(f"Loja {loja} - {len(lista)} chamado(s) AGENDADO", expanded=False):
            st.code(gerar_mensagem(loja, lista), language="text")
            st.markdown(aviso)

# --- Rodapé ---
st.markdown("---")
st.caption(f"🕒 Última atualização automática: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
