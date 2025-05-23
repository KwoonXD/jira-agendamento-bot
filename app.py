import streamlit as st
import requests
from requests.auth import HTTPBasicAuth
from collections import defaultdict
from datetime import datetime

# Autenticação
EMAIL = st.secrets["EMAIL"]
API_TOKEN = st.secrets["API_TOKEN"]
JIRA_URL = "https://delfia.atlassian.net"
AUTH = HTTPBasicAuth(EMAIL, API_TOKEN)
HEADERS = {"Accept": "application/json", "Content-Type": "application/json"}

# Função para buscar chamados
def buscar_chamados():
    query = {
        "jql": 'project = "FSA" AND status = "AGENDAMENTO"',
        "maxResults": 100,
        "fields": "customfield_14954,customfield_14829,customfield_14825,customfield_12374,customfield_12271,customfield_11948,customfield_11993,customfield_11994"
    }
    res = requests.get(f"{JIRA_URL}/rest/api/3/search", headers=HEADERS, auth=AUTH, params=query)
    if res.status_code != 200:
        st.error(f"Erro: {res.status_code} - {res.text}")
        return []
    return res.json()["issues"]

# Agrupar chamados por loja
def agrupar_por_loja(chamados):
    agrupado = defaultdict(list)
    for issue in chamados:
        f = issue["fields"]
        loja = f.get("customfield_14954", {}).get("value", "Sem loja")
        agrupado[loja].append({
            "key": issue["key"],
            "pdv": f.get("customfield_14829", "--"),
            "ativo": f.get("customfield_14825", {}).get("value", "--"),
            "problema": f.get("customfield_12374", "--"),
            "endereco": f.get("customfield_12271", "--"),
            "estado": f.get("customfield_11948", {}).get("value", "--"),
            "cep": f.get("customfield_11993", "--"),
            "cidade": f.get("customfield_11994", "--")
        })
    return agrupado

# Gerar texto formatado
def gerar_mensagem(loja, chamados):
    if len(chamados) == 1:
        ch = chamados[0]
        return f"""*{ch['key']}*
Loja {loja}
PDV: {ch['pdv']}
ATIVO: {ch['ativo']}
Problema: {ch['problema']}

Endereço: {ch['endereco']}
Estado: {ch['estado']}
CEP: {ch['cep']}
Cidade: {ch['cidade']}
"""
    else:
        blocos = "\n***\n".join([
            f"""{ch['key']}
Loja {loja}
PDV: {ch['pdv']}
ATIVO: {ch['ativo']}
Problema: {ch['problema']}""" for ch in chamados
        ])
        final = f"""Endereço: {chamados[0]['endereco']}
Estado: {chamados[0]['estado']}
CEP: {chamados[0]['cep']}
Cidade: {chamados[0]['cidade']}"""
        return blocos + "\n***\n" + final

# Interface do Streamlit
st.set_page_config(page_title="Painel de Chamados", layout="wide")
st.title("📡 Chamados em Agendamento")
st.caption("Visualização em tempo real")

if st.button("🔄 Atualizar Chamados"):
    issues = buscar_chamados()
    if not issues:
        st.warning("Nenhum chamado encontrado.")
    else:
        agrupados = agrupar_por_loja(issues)
        st.success(f"{len(issues)} chamados encontrados.")
        for loja, chamados in agrupados.items():
            with st.expander(f"Loja {loja} - {len(chamados)} chamado(s)", expanded=True):
                st.code(gerar_mensagem(loja, chamados), language="text")

st.caption(f"⏰ Atualizado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
