import streamlit as st
from streamlit_autorefresh import st_autorefresh
import requests
from requests.auth import HTTPBasicAuth
from datetime import datetime
from collections import defaultdict
import os

# ❗ PRIMEEEEIRO COMANDO
st.set_page_config(page_title="Chamados em Agendamento", layout="wide")

# --- Autenticação via Streamlit Secrets ---
EMAIL = st.secrets["EMAIL"]
API_TOKEN = st.secrets["API_TOKEN"]
JIRA_URL = "https://delfia.atlassian.net"
AUTH = HTTPBasicAuth(EMAIL, API_TOKEN)
HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json"
}

# --- Atualiza automaticamente a cada 60 segundos ---
st_autorefresh(interval=60 * 1000, key="auto_refresh")

# --- Função para buscar chamados em AGENDAMENTO ---
def buscar_chamados_agendamento():
    query = {
        'jql': 'project = FSA AND status = AGENDAMENTO',
        'maxResults': 100,
        'fields': 'summary,customfield_14954,customfield_14829,customfield_14825,customfield_12374,customfield_12271,customfield_11993,customfield_11994,customfield_11948'
    }
    res = requests.get(f"{JIRA_URL}/rest/api/3/search", headers=HEADERS, auth=AUTH, params=query)

    if res.status_code != 200:
        st.error(f"❌ Erro ao buscar chamados: {res.status_code} - {res.text}")
        return []

    return res.json()["issues"]

# --- Função para agrupar por loja ---
def agrupar_por_loja(chamados):
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
    return agrupado

# --- Função para gerar mensagem no formato desejado ---
def exibir_mensagens(lojas):
    for loja, dados in lojas.items():
        chamados = dados["chamados"]
        if len(chamados) == 1:
            ch = chamados[0]
            print(f"""*{ch['key']}*
*Loja* {loja}
*PDV:* {ch['pdv']}
*ATIVO:* {ch['ativo']}
*Problema:* {ch['problema']}
*Endereço:* {dados['endereco']}
*Estado:* {dados['estado']}
*CEP:* {dados['cep']}
*Cidade:* {dados['cidade']}""")
        else:
            for ch in chamados:
                print(f"""*{ch['key']}*
*Loja* {loja}
*PDV:* {ch['pdv']}
*ATIVO:* {ch['ativo']}
*Problema:* {ch['problema']}
******""")
            print(f"""*Endereço:* {dados['endereco']}
*Estado:* {dados['estado']}
*CEP:* {dados['cep']}
*Cidade:* {dados['cidade']}""")
        )
        return "\n\n".join(blocos)

# --- Interface visual ---
st.title("📡 Chamados em Agendamento")
st.caption("Visualização em tempo real")

chamados = buscar_chamados_agendamento()
if not chamados:
    st.warning("Nenhum chamado encontrado no momento.")
else:
    agrupados = agrupar_por_loja(chamados)
    st.success(f"{len(chamados)} chamados encontrados. Agrupados por {len(agrupados)} loja(s).")

    for loja, lista_chamados in agrupados.items():
        with st.expander(f"Loja {loja} - {len(lista_chamados)} chamado(s)", expanded=True):
            mensagem = gerar_mensagem(loja, lista_chamados)
            st.code(mensagem, language="text")

st.markdown("---")
st.caption(f"🕒 Última atualização automática: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
