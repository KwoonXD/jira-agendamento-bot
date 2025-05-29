import streamlit as st
from streamlit_autorefresh import st_autorefresh
import requests
from requests.auth import HTTPBasicAuth
from datetime import datetime, date, time
from collections import defaultdict
import json
import time as t

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
    params = {"jql": jql, "maxResults": 100, "fields": "summary,customfield_14954,customfield_14829,customfield_14825,customfield_12374,customfield_12271,customfield_11993,customfield_11994,customfield_11948,customfield_12036"}
    res = requests.get(f"{JIRA_URL}/rest/api/3/search", headers=HEADERS, auth=AUTH, params=params)
    return res.json().get("issues", []) if res.status_code == 200 else []

def gerar_mensagem(loja, chamados):
    blocos = []
    for ch in chamados:
        blocos.append(f"*{ch['key']}*\n*Loja:* {loja}\n*PDV:* {ch['pdv']}\n*ATIVO:* {ch['ativo']}\n*Problema:* {ch['problema']}\n*****")
    blocos.append(f"*Endereço:* {chamados[0]['endereco']}\n*Estado:* {chamados[0]['estado']}\n*CEP:* {chamados[0]['cep']}\n*Cidade:* {chamados[0]['cidade']}")
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

chamados = buscar_chamados("project = FSA AND status = AGENDAMENTO")

if not chamados:
    st.warning("Nenhum chamado em AGENDAMENTO encontrado no momento.")
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

    st.success(f"{len(chamados)} chamados em AGENDAMENTO encontrados.")

    for loja, lista in agrupado.items():
        with st.expander(f"Loja {loja} - {len(lista)} chamado(s) AGENDAMENTO", expanded=False):
            st.code(gerar_mensagem(loja, lista), language="text")

# --- Chamados em AGENDADO ---
chamados_agendados = buscar_chamados("project = FSA AND status = AGENDADO")

agrupado_agendado = defaultdict(list)
for issue in chamados_agendados:
    fields = issue["fields"]
    loja = fields.get("customfield_14954", {}).get("value", "Loja Desconhecida")
    data_agendada = fields.get("customfield_12036")
    agrupado_agendado[loja].append({
        "key": issue["key"],
        "pdv": fields.get("customfield_14829", "--"),
        "ativo": fields.get("customfield_14825", {}).get("value", "--"),
        "problema": fields.get("customfield_12374", "--"),
        "data": data_agendada,
    })

st.header("📋 Chamados AGENDADOS")
if not chamados_agendados:
    st.info("Nenhum chamado em AGENDADO.")
else:
    for loja, lista in agrupado_agendado.items():
        with st.expander(f"Loja {loja} - {len(lista)} chamado(s) AGENDADO", expanded=False):
            for ch in lista:
                data_formatada = "Data não informada"
                if ch["data"]:
                    try:
                        data_formatada = datetime.strptime(ch["data"][:16], "%Y-%m-%dT%H:%M").strftime("%d/%m/%Y %H:%M")
                    except:
                        data_formatada = ch["data"]
                st.markdown(
                    f"🔹 **{ch['key']}** | **PDV:** {ch['pdv']} | **Ativo:** {ch['ativo']}  \n"
                    f"📆 Agendado para: `{data_formatada}`  \n"
                    f"🛠️ *{ch['problema']}*"
                )

# --- Agendamento de chamados ---
st.header("📆 Agendar chamados de uma loja")

with st.form("agendamento_form"):
    loja_agendamento = st.selectbox("Selecione a loja para agendar chamados:", sorted(agrupado.keys()))
    data_agendamento = st.date_input("Data de Agendamento", value=date.today())
    hora_agendamento = st.time_input("Hora de Agendamento", value=time(datetime.now().hour, datetime.now().minute))
    tecnico_responsavel = st.text_input("Nome do Técnico Responsável")
    tem_tec_campo = st.checkbox("Já tem técnico em campo?")
    confirmar_agendamento = st.form_submit_button("📌 Agendar Chamados")

if confirmar_agendamento:
    if not tecnico_responsavel:
        st.warning("Por favor, preencha o nome do técnico responsável.")
    else:
        datetime_agendamento = f"{data_agendamento}T{hora_agendamento.strftime('%H:%M')}:00.000-0300"
        chamados_para_agendar = [ch for ch in agrupado[loja_agendamento]]
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
                transicionado = transicionar_status(ch['key'], 9)  # ID 9: Agendado
                if transicionado:
                    st.success(f"➡️ {ch['key']} movido para 'Agendado'.")
                    t.sleep(1.5)
                    if tem_tec_campo:
                        transicionado2 = transicionar_status(ch['key'], 10)  # ID 10: Tec Campo
                        if transicionado2:
                            st.success(f"🚚 {ch['key']} movido para 'Tec Campo'.")
                        else:
                            st.error(f"❌ Falha ao mover {ch['key']} para 'Tec Campo'.")
                else:
                    st.error(f"❌ Falha ao mover {ch['key']} para 'Agendado'.")
            else:
                st.error(f"❌ Falha ao agendar {ch['key']}: {res.status_code}")

# --- Rodapé ---
st.markdown("---")
st.caption(f"🕒 Última atualização automática: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
