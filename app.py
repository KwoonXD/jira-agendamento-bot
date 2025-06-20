import streamlit as st
from streamlit_autorefresh import st_autorefresh
import requests
from requests.auth import HTTPBasicAuth
from datetime import datetime
from collections import defaultdict

# ── CONFIGURAÇÃO ───────────────────────────────────────────────────────────────
st.set_page_config("Painel Field Service", layout="wide")
# auto‐refresh a cada 90 segundos:
st_autorefresh(interval=90_000, key="auto_refresh")

# ── SECRETS ────────────────────────────────────────────────────────────────────
EMAIL     = st.secrets["EMAIL"]
API_TOKEN = st.secrets["API_TOKEN"]
JIRA_URL  = "https://delfia.atlassian.net"
AUTH      = HTTPBasicAuth(EMAIL, API_TOKEN)
HEADERS   = {"Accept": "application/json", "Content-Type": "application/json"}

# ── CLASSE DE ACESSO AO JIRA ────────────────────────────────────────────────────
class JiraAPI:
    def __init__(self, base_url, auth, headers):
        self.base = base_url
        self.auth = auth
        self.headers = headers

    def search(self, jql, fields, maxResults=100):
        params = {"jql": jql, "fields": fields, "maxResults": maxResults}
        res = requests.get(f"{self.base}/rest/api/3/search",
                           headers=self.headers, auth=self.auth, params=params)
        res.raise_for_status()
        return res.json().get("issues", [])

    def transitions(self, issue_key):
        res = requests.get(f"{self.base}/rest/api/3/issue/{issue_key}/transitions",
                           headers=self.headers, auth=self.auth)
        res.raise_for_status()
        return res.json().get("transitions", [])

    def do_transition(self, issue_key, transition_id, fields_update=None):
        payload = {"transition": {"id": str(transition_id)}}
        if fields_update:
            payload["fields"] = fields_update
        res = requests.post(f"{self.base}/rest/api/3/issue/{issue_key}/transitions",
                            headers=self.headers, auth=self.auth, json=payload)
        return res.status_code == 204

# ── FUNÇÕES DE FORMATAÇÃO E LÓGICA ──────────────────────────────────────────────
def gerar_mensagem(loja, chamados):
    linhas = []
    for ch in chamados:
        data_raw = ch.get("data_agendada", "")
        try:
            data_fmt = datetime.strptime(data_raw, "%Y-%m-%dT%H:%M:%S.%f%z") \
                         .strftime("%d/%m/%Y %H:%M")
        except:
            data_fmt = "--"
        linhas.append(
            f"*{ch.get('key','--')}*\n"
            f"*Loja:* {loja}\n"
            f"*PDV:* {ch.get('pdv','--')}\n"
            f"*Ativo:* {ch.get('ativo','--')}\n"
            f"*Problema:* {ch.get('problema','--')}\n"
            f"*Data Agendada:* {data_fmt}\n"
            f"*****\n"
            f"*Endereço:* {ch.get('endereco','--')}\n"
            f"*Estado:* {ch.get('estado','--')}\n"
            f"*CEP:* {ch.get('cep','--')}\n"
            f"*Cidade:* {ch.get('cidade','--')}"
        )
    return "\n\n".join(linhas)

def detectar_duplicidade(chamados):
    seen = {}
    dup = set()
    for c in chamados:
        key = (c.get("pdv"), c.get("ativo"))
        if key in seen:
            dup.add(key)
        else:
            seen[key] = True
    return dup

def agrupar_por_loja(issues, fields):
    agr = defaultdict(list)
    for issue in issues:
        f = issue["fields"]
        loja = f.get("customfield_14954", {}).get("value","Loja?") 
        agr[loja].append({
            "key": issue["key"],
            "pdv": f.get("customfield_14829","--"),
            "ativo": f.get("customfield_14825",{}).get("value","--"),
            "problema": f.get("customfield_12374","--"),
            "endereco": f.get("customfield_12271","--"),
            "estado": f.get("customfield_11948",{}).get("value","--"),
            "cep": f.get("customfield_11993","--"),
            "cidade": f.get("customfield_11994","--"),
            "data_agendada": f.get("customfield_12036","")
        })
    return agr

# ── INICIALIZA API E CONSTANTES ─────────────────────────────────────────────────
FIELDS = (
    "summary,customfield_14954,customfield_14829,customfield_14825,"
    "customfield_12374,customfield_12271,customfield_11993,"
    "customfield_11994,customfield_11948,customfield_12036"
)
jira = JiraAPI(JIRA_URL, AUTH, HEADERS)

# ── ESTADO DE “UNDO” ────────────────────────────────────────────────────────────
if "history" not in st.session_state:
    st.session_state.history = []

# ── SIDEBAR ─────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.button("🔄 Atualizar página")
    if st.button("↩️ Desfazer última ação"):
        if st.session_state.history:
            act = st.session_state.history.pop()
            rev_count = 0
            for key in act["keys"]:
                transs = jira.transitions(key)
                rev = next((t["id"] for t in transs if t["to"]["name"]==act["from"]), None)
                if rev and jira.do_transition(key, rev):
                    rev_count += 1
            st.success(f"Revertido: {rev_count} chamados → {act['from']}")
        else:
            st.info("Nada a desfazer.")

    st.markdown("---")
    st.header("Transição de Chamados")
    loja_sel = st.selectbox("Loja:", ["Todas"] + list(
        agrupar_por_loja(jira.search('project=FSA AND status=AGENDADO', FIELDS)).keys()
    ))
    todos = []
    # pendentes
    pend = jira.search("project=FSA AND status=AGENDAMENTO", FIELDS)
    grp_pend = agrupar_por_loja(pend, FIELDS)
    # agendados
    agd = jira.search("project=FSA AND status=AGENDADO", FIELDS)
    grp_agd = agrupar_por_loja(agd, FIELDS)

    # monta lista de keys
    for loja, lst in grp_pend.items():
        if loja_sel=="Todas" or loja_sel==loja:
            todos += [c["key"] for c in lst]
    for loja, lst in grp_agd.items():
        if loja_sel=="Todas" or loja_sel==loja:
            todos += [c["key"] for c in lst]

    sel = st.multiselect("FSAs (pend.+agend.):", sorted(set(todos)))
    trans_ops = {}
    if sel:
        # carrega transições do primeiro selecionado
        trans_ops = {t["name"]:t["id"] for t in jira.transitions(sel[0])}
    choice = st.selectbox("Transição:", ["—"]+list(trans_ops.keys()))
    # campos extras para “Agendado”
    if choice=="Agendado":
        dt = st.date_input("Data do Agendamento")
        tm = st.time_input("Hora do Agendamento")
        tec= st.text_input("Dados Técnicos (Nome-CPF-RG-TEL)")
    advanced = st.checkbox("Técnico está em campo? (agendar + mover tudo)")

    if st.button("Aplicar Transição") and sel and choice!="—":
        prev_status = jira.transitions(sel[0])
        prev_name   = next((t["from"]["name"] for t in prev_status), "")
        # preenche campos se for “Agendado”:
        fields_up = {}
        if choice=="Agendado":
            # monta timestamp no formato ISO Jira:
            iso = dt.strftime("%Y-%m-%d") + "T" + tm.strftime("%H:%M") + ":00.000-0300"
            fields_up = {
                "customfield_12036": iso,
                "customfield_12279": { "value": tec }
            }
        moved = 0
        for k in sel:
            # 1) se advanced, e tipo pendente, primeiro agendar:
            if advanced:
                jira.do_transition(k, trans_ops["Agendado"], fields_up)
                # em seguida mover para Tec-Campo
                jira.do_transition(k, trans_ops.get("Tec-Campo"), None)
                moved += 1
            else:
                jira.do_transition(k, trans_ops[choice], fields_up or None)
                moved += 1
        # salva no histórico
        st.session_state.history.append({"keys": sel, "from": prev_name})
        st.success(f"{moved} FSAs movidos → {choice}")

# ── PÁGINA PRINCIPAL ───────────────────────────────────────────────────────────
st.title("📱 Painel Field Service")
c1, c2 = st.columns(2)

with c1:
    st.header("⏳ Chamados PENDENTES de Agendamento")
    pendentes = jira.search("project=FSA AND status=AGENDAMENTO", FIELDS)
    if not pendentes:
        st.warning("Nenhum chamado em AGENDAMENTO.")
    else:
        for loja, lst in agrupar_por_loja(pendentes, FIELDS).items():
            with st.expander(f"{loja} — {len(lst)} chamados"):
                st.code(gerar_mensagem(loja, lst), language="text")

with c2:
    st.header("📋 Chamados AGENDADOS")
    agds = jira.search("project=FSA AND status=AGENDADO", FIELDS)
    # agrupa por data depois por loja
    por_data = defaultdict(lambda: defaultdict(list))
    for issue in agds:
        f = issue["fields"]
        raw = f.get("customfield_12036","")
        date = "--"
        try:
            date = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S.%f%z").strftime("%d/%m/%Y")
        except: pass
        loja = f.get("customfield_14954",{}).get("value","Loja?")
        por_data[date][loja].append({
            "key": issue["key"],
            "pdv": f.get("customfield_14829","--"),
            "ativo": f.get("customfield_14825",{}).get("value","--"),
            "problema": f.get("customfield_12374","--"),
            "endereco": f.get("customfield_12271","--"),
            "estado": f.get("customfield_11948",{}).get("value","--"),
            "cep": f.get("customfield_11993","--"),
            "cidade": f.get("customfield_11994","--"),
            "data_agendada": raw
        })
    if not agds:
        st.info("Nenhum chamado agendado.")
    else:
        for date, lojas in por_data.items():
            total = sum(len(v) for v in lojas.values())
            st.subheader(f"{date} — {total} chamados")
            for loja, lst in lojas.items():
                with st.expander(f"{loja} — {len(lst)} chamados"):
                    dup = detectar_duplicidade(lst)
                    spare = jira.search(
                        f'project=FSA AND status="Aguardando Spare" AND "Codigo da Loja[Dropdown]"={loja}',
                        FIELDS
                    )
                    tags = []
                    if dup:
                        fs = [c["key"] for c in lst if (c["pdv"],c["ativo"]) in dup]
                        tags.append("Dup: "+", ".join(fs))
                    if spare:
                        tags.append("Spare: "+", ".join(i["key"] for i in spare))
                    if tags:
                        st.markdown("⚠️ " + " • ".join(tags))
                    st.code(gerar_mensagem(loja, lst), language="text")

st.markdown("---")
st.caption(f"Última atualização: {datetime.now():%d/%m/%Y %H:%M:%S}")
