import streamlit as st
from streamlit_autorefresh import st_autorefresh
import requests
from requests.auth import HTTPBasicAuth
from datetime import datetime
from collections import defaultdict
import json
import streamlit.components.v1 as components

# Configurações iniciais
st.set_page_config(page_title="Chamados em Agendamento", layout="wide")
st_autorefresh(interval=60 * 1000, key="auto_refresh")  # Atualiza a cada 60s

# Permissão para notificações
components.html("""
    <script>
        function solicitarPermissao() {
            if (Notification.permission !== "granted") {
                Notification.requestPermission().then(function(permission) {
                    if (permission === "granted") {
                        alert("Permissão concedida para notificações.");
                    }
                });
            } else {
                alert("Notificações já estão permitidas.");
            }
        }

        const botao = document.createElement("button");
        botao.innerText = "🔔 Ativar Notificações";
        botao.style.fontSize = "16px";
        botao.style.padding = "10px 20px";
        botao.onclick = solicitarPermissao;
        document.body.prepend(botao);
    </script>
""", height=0)

# Autenticação
EMAIL = st.secrets["EMAIL"]
API_TOKEN = st.secrets["API_TOKEN"]
JIRA_URL = "https://delfia.atlassian.net"
AUTH = HTTPBasicAuth(EMAIL, API_TOKEN)
HEADERS = {"Accept": "application/json", "Content-Type": "application/json"}

# Funções
@st.cache_resource(show_spinner=False)
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

# Estado para notificação
if "ultimos_chamados" not in st.session_state:
    st.session_state.ultimos_chamados = []

# Página principal
st.title("📡 Chamados em Agendamento")

chamados = buscar_chamados("project = FSA AND status = AGENDAMENTO")
novos_chamados = [c for c in chamados if c["key"] not in st.session_state.ultimos_chamados]

# Notifica se houver novos
if novos_chamados:
    st.markdown(f"<script>if (Notification.permission === 'granted') new Notification('🔔 {len(novos_chamados)} novo(s) chamado(s) em AGENDAMENTO!');</script>", unsafe_allow_html=True)

st.session_state.ultimos_chamados = [c["key"] for c in chamados]  # Atualiza histórico

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

# Você ainda pode manter a seção de atualização TEC-CAMPO abaixo, se desejar
