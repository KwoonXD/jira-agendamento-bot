import streamlit as st
from streamlit_autorefresh import st_autorefresh
from datetime import datetime
from collections import defaultdict

from utils.jira_api import JiraAPI
from utils.messages import gerar_mensagem, verificar_duplicidade

# ── Configuração da página e auto‐refresh (90s) ──
st.set_page_config(page_title="Painel Field Service", layout="wide")
st_autorefresh(interval=90_000, key="auto_refresh")

# ── Histórico de undo ──
if "history" not in st.session_state:
    st.session_state.history = []

# ── Inicializa JiraAPI ──
jira = JiraAPI(
    st.secrets["EMAIL"],
    st.secrets["API_TOKEN"],
    "https://delfia.atlassian.net"
)

# ── Quais campos puxar da API ──
FIELDS = (
    "summary,customfield_14954,customfield_14829,customfield_14825,"
    "customfield_12374,customfield_12271,customfield_11993,"
    "customfield_11994,customfield_11948,customfield_12036,customfield_12279"
)

# ── 1) Carrega PENDENTES e agrupa por loja ──
pendentes_raw = jira.buscar_chamados("project = FSA AND status = AGENDAMENTO", FIELDS)
agrup_pend    = jira.agrupar_chamados(pendentes_raw)

# ── 2) Carrega AGENDADOS e agrupa por data → loja → lista de issues ──
agendados_raw = jira.buscar_chamados('project = FSA AND status = AGENDADO', FIELDS)
grouped_sched = defaultdict(lambda: defaultdict(list))
for issue in agendados_raw:
    f    = issue["fields"]
    loja = f.get("customfield_14954", {}).get("value", "Loja Desconhecida")
    raw  = f.get("customfield_12036")
    data_str = (
        datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S.%f%z")
                .strftime("%d/%m/%Y")
        if raw else "Não definida"
    )
    grouped_sched[data_str][loja].append(issue)

# ── 3) Raw por loja (pendentes+agendados) para transições em massa ──
raw_by_loja = defaultdict(list)
for i in pendentes_raw + agendados_raw:
    loja = i["fields"].get("customfield_14954",{}).get("value","Loja Desconhecida")
    raw_by_loja[loja].append(i)

# ── Sidebar: Desfazer e Transição ──
with st.sidebar:
    st.header("Ações")
    if st.button("↩️ Desfazer última ação"):
        if st.session_state.history:
            action = st.session_state.history.pop()
            reverted = 0
            for key in action["keys"]:
                trans = jira.get_transitions(key)
                rev_id = next(
                    (t["id"] for t in trans if t.get("to",{}).get("name")==action["from"]),
                    None
                )
                if rev_id and jira.transicionar_status(key, rev_id).status_code == 204:
                    reverted += 1
            st.success(f"Revertido: {reverted} FSAs → {action['from']}")
        else:
            st.info("Nenhuma ação para desfazer.")

    st.markdown("---")
    st.header("Transição de Chamados")

    # Seleciona loja
    lojas = sorted(set(agrup_pend) | set(grouped_sched[next(iter(grouped_sched))].keys()))
    loja_sel = st.selectbox("Selecione a loja:", ["—"] + lojas)

    if loja_sel != "—":
        # Checkbox de fluxo completo
        em_campo = st.checkbox("Técnico está em campo? (agendar + mover tudo)")

        if em_campo:
            st.markdown("**Dados de Agendamento**")
            data    = st.date_input("Data do Agendamento")
            hora    = st.time_input("Hora do Agendamento")
            tecnico = st.text_input("Dados dos Técnicos (Nome-CPF-RG-TEL)")

            # payload de agendamento
            dt_iso = datetime.combine(data, hora).strftime("%Y-%m-%dT%H:%M:%S.000-0300")
            extra_ag = {"customfield_12036": dt_iso}
            if tecnico:
                extra_ag["customfield_12279"] = {
                    "type":"doc","version":1,
                    "content":[{"type":"paragraph","content":[{"type":"text","text":tecnico}]}]
                }

            # chaves pend+age
            keys_pend  = [i["key"] for i in pendentes_raw  if i["fields"].get("customfield_14954",{}).get("value")==loja_sel]
            keys_sched = [i["key"] for i in agendados_raw if i["fields"].get("customfield_14954",{}).get("value")==loja_sel]
            all_keys   = keys_pend + keys_sched

            if st.button(f"Agendar e mover {len(all_keys)} FSAs → Tec-Campo"):
                errors=[]; moved=0
                # a) agendar pendentes
                for k in keys_pend:
                    trans = jira.get_transitions(k)
                    agid  = next((t["id"] for t in trans if "agend" in t["name"].lower()),None)
                    if agid:
                        r= jira.transicionar_status(k, agid, fields=extra_ag)
                        if r.status_code!=204: errors.append(f"{k}⏳{r.status_code}")
                # b) mover todos
                for k in all_keys:
                    trans = jira.get_transitions(k)
                    tcid = next((t["id"] for t in trans if "tec-campo" in t.get("to",{}).get("name","").lower()),None)
                    if tcid:
                        r= jira.transicionar_status(k, tcid)
                        if r.status_code==204: moved+=1
                        else: errors.append(f"{k}➡️{r.status_code}")
                if errors:
                    st.error("Erros:"); [st.code(e) for e in errors]
                else:
                    st.success(f"{len(all_keys)} FSAs agendados e movidos → Tec-Campo")
                    st.session_state.history.append({"keys":all_keys,"from":"AGENDADO"})
                    # exibe mensagens destacando novos
                    detail = jira.agrupar_chamados(raw_by_loja[loja_sel])[loja_sel]
                    novos   = [d for d in detail if d["key"] in keys_pend]
                    antigos= [d for d in detail if d["key"] in keys_sched]
                    st.markdown("### 🆕 Novos Agendados")
                    st.code(gerar_mensagem(loja_sel, novos),language="text")
                    if antigos:
                        st.markdown("### 📋 Já Agendados")
                        st.code(gerar_mensagem(loja_sel, antigos),language="text")

        else:
            # fluxo manual
            opts = [i["key"] for i in pendentes_raw if i["fields"].get("customfield_14954",{}).get("value")==loja_sel]
            opts+= [i["key"] for i in agendados_raw if i["fields"].get("customfield_14954",{}).get("value")==loja_sel]
            sel = st.multiselect("Selecione FSAs pend.+age.:",sorted(set(opts)))
            extra = {}; choice=None; trans_opts={}
            if sel:
                trans_opts={t["name"]:t["id"] for t in jira.get_transitions(sel[0])}
                choice=st.selectbox("Transição:",["—"]+list(trans_opts))
                if choice and "agend" in choice.lower():
                    st.markdown("**Dados de Agendamento**")
                    d=st.date_input("Data do Agendamento"); h=st.time_input("Hora do Agendamento")
                    tec=st.text_input("Dados dos Técnicos (Nome-CPF-RG-TEL)")
                    iso=datetime.combine(d,h).strftime("%Y-%m-%dT%H:%M:%S.000-0300")
                    extra["customfield_12036"]=iso
                    if tec:
                        extra["customfield_12279"]={
                            "type":"doc","version":1,
                            "content":[{"type":"paragraph","content":[{"type":"text","text":tec}]}]
                        }
            if st.button("Aplicar"):
                if not sel or choice in (None,"—"):
                    st.warning("Selecione FSAs e transição.")
                else:
                    prev=jira.get_issue(sel[0])["fields"]["status"]["name"]
                    errs=[]; mv=0
                    for k in sel:
                        r=jira.transicionar_status(k,trans_opts[choice],fields=extra or None)
                        if r.status_code==204: mv+=1
                        else: errs.append(f"{k}:{r.status_code}")
                    if errs:
                        st.error("Falhas:"); [st.code(e) for e in errs]
                    else:
                        st.success(f"{mv} FSAs movidos → {choice}")
                        st.session_state.history.append({"keys":sel,"from":prev})

# ── Main ──
st.title("📱 Painel Field Service")
col1,col2=st.columns(2)

with col1:
    st.header("⏳ Chamados PENDENTES de Agendamento")
    if not pendentes_raw:
        st.warning("Nenhum chamado em AGENDAMENTO.")
    else:
        for loja,iss in agrup_pend.items():
            with st.expander(f"{loja} — {len(iss)} chamado(s)",expanded=False):
                st.code(gerar_mensagem(loja,iss),language="text")

with col2:
    st.header("📋 Chamados AGENDADOS")
    if not agendados_raw:
        st.info("Nenhum chamado em AGENDADO.")
    else:
        for date, stores in sorted(grouped_sched.items()):
            total=sum(len(v) for v in stores.values())
            st.subheader(f"{date} — {total} chamado(s)")
            for loja,iss in sorted(stores.items()):
                detalhes=jira.agrupar_chamados(iss)[loja]
                dup_keys=[d["key"] for d in detalhes if (d["pdv"],d["ativo"]) in verificar_duplicidade(detalhes)]
                spare_raw=jira.buscar_chamados(
                    f'project = FSA AND status = "Aguardando Spare" AND "Codigo da Loja[Dropdown]" = {loja}',
                    FIELDS
                )
                spare_keys=[i["key"] for i in spare_raw]
                tags=[]
                if spare_keys: tags.append("Spare: "+", ".join(spare_keys))
                if dup_keys:   tags.append("Dup: "+", ".join(dup_keys))
                tag_str=f" [{' • '.join(tags)}]" if tags else ""
                with st.expander(f"{loja} — {len(iss)} chamado(s){tag_str}",expanded=False):
                    st.markdown("**FSAs:** "+", ".join(d["key"] for d in detalhes))
                    st.code(gerar_mensagem(loja,detalhes),language="text")

st.markdown("---")
st.caption(f"Última atualização: {datetime.now():%d/%m/%Y %H:%M:%S}")

export_utils.py
import pandas as pd
from fpdf import FPDF

def chamados_to_csv(chamados, filename="chamados_exportados.csv"):
    df = pd.DataFrame(chamados)
    df.to_csv(filename, index=False)
    return filename

def chamados_to_pdf(chamados, filename="chamados_exportados.pdf"):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    for chamado in chamados:
        pdf.multi_cell(0, 10,
            f"Chamado: {chamado['key']}\n"
            f"Loja: {chamado['loja']}\n"
            f"PDV: {chamado['pdv']}\n"
            f"Ativo: {chamado['ativo']}\n"
            f"Problema: {chamado['problema']}\n"
            f"Data Agendada: {chamado['data_agendada']}\n"
            f"Endereço: {chamado['endereco']}\n"
            f"Cidade: {chamado['cidade']} - {chamado['estado']} (CEP: {chamado['cep']})\n"
            "--------------------------------------------"
        )

    pdf.output(filename)
    return filename
jira_api.py
import requests
from requests.auth import HTTPBasicAuth

class JiraAPI:
    def __init__(self, email: str, api_token: str, jira_url: str):
        self.email = email
        self.api_token = api_token
        self.jira_url = jira_url.rstrip('/')
        self.auth = HTTPBasicAuth(self.email, self.api_token)
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

    def buscar_chamados(self, jql: str, fields: str) -> list:
        """
        Busca issues via JQL e retorna lista de issues.
        """
        params = {
            "jql": jql,
            "maxResults": 100,
            "fields": fields
        }
        url = f"{self.jira_url}/rest/api/3/search"
        res = requests.get(url, headers=self.headers, auth=self.auth, params=params)
        if res.status_code == 200:
            return res.json().get("issues", [])
        return []

    def agrupar_chamados(self, issues: list) -> dict:
        """
        Agrupa issues por customfield_14954 (loja) e retorna dict:
        { loja_value: [ {key, pdv, ativo, problema, endereco, estado, cep, cidade, data_agendada}, ... ] }
        """
        from collections import defaultdict
        agrup = defaultdict(list)
        for issue in issues:
            f = issue.get("fields", {})
            loja = f.get("customfield_14954", {}).get("value", "Loja Desconhecida")
            agrup[loja].append({
                "key": issue.get("key"),
                "pdv": f.get("customfield_14829", "--"),
                "ativo": f.get("customfield_14825", {}).get("value", "--"),
                "problema": f.get("customfield_12374", "--"),
                "endereco": f.get("customfield_12271", "--"),
                "estado": f.get("customfield_11948", {}).get("value", "--"),
                "cep": f.get("customfield_11993", "--"),
                "cidade": f.get("customfield_11994", "--"),
                "data_agendada": f.get("customfield_12036")
            })
        return agrup

    def get_transitions(self, issue_key: str) -> list:
        """
        Retorna lista de transições disponíveis para a issue.
        """
        url = f"{self.jira_url}/rest/api/3/issue/{issue_key}/transitions"
        res = requests.get(url, headers=self.headers, auth=self.auth)
        if res.status_code == 200:
            return res.json().get("transitions", [])
        return []

    def get_issue(self, issue_key: str) -> dict:
        """
        Retorna JSON completo da issue (ou pelo menos os campos necessários como status).
        """
        url = f"{self.jira_url}/rest/api/3/issue/{issue_key}"
        # busca só o campo status para history
        res = requests.get(url, headers=self.headers, auth=self.auth, params={"fields": "status"})
        if res.status_code == 200:
            return res.json()
        return {}

    def transicionar_status(self, issue_key: str, transition_id: str, fields: dict = None) -> requests.Response:
        """
        Executa transição de status. Se campos forem fornecidos, inclui no payload.
        Retorna o objeto Response para inspeção de status/erro.
        """
        payload = {"transition": {"id": str(transition_id)}}
        if fields:
            payload["fields"] = fields
        url = f"{self.jira_url}/rest/api/3/issue/{issue_key}/transitions"
        res = requests.post(url, headers=self.headers, auth=self.auth, json=payload)
        return res
messages.py
# utils/messages.py

from datetime import datetime

def gerar_mensagem(loja, chamados):
    """
    Gera uma mensagem para um grupo de chamados da mesma loja,
    listando cada FSA sem data agendada e, ao final, exibindo
    uma única vez o bloco de endereço.
    """
    blocos = []
    endereco_info = None  # Será preenchido com a tupla (end,estado,cep,cidade)

    for ch in chamados:
        # cabeçalho de cada FSA
        linhas = [
            f"*{ch['key']}*",
            f"Loja: {loja}",
            f"PDV: {ch.get('pdv','--')}",
            f"*ATIVO: {ch.get('ativo','--')}*",
            f"Problema: {ch.get('problema','--')}",
            "***"
        ]
        blocos.append("\n".join(linhas))

        # armazena endereço (último sobrescreve, mas todos pendentes têm o mesmo)
        endereco_info = (
            ch.get('endereco','--'),
            ch.get('estado','--'),
            ch.get('cep','--'),
            ch.get('cidade','--')
        )

    # após listar todos, adiciona o bloco de endereço apenas uma vez
    if endereco_info:
        blocos.append(
            "\n".join([
                f"Endereço: {endereco_info[0]}",
                f"Estado: {endereco_info[1]}",
                f"CEP: {endereco_info[2]}",
                f"Cidade: {endereco_info[3]}"
            ])
        )

    # une todos os blocos com linha em branco dupla
    return "\n\n".join(blocos)


def verificar_duplicidade(chamados):
    """
    Retorna um set de tuplas (pdv, ativo) que aparecem mais de uma vez,
    para sinalizar duplicidade.
    """
    seen = {}
    duplicates = set()
    for ch in chamados:
        key = (ch.get("pdv"), ch.get("ativo"))
        if key in seen:
            duplicates.add(key)
        else:
            seen[key] = True
    return duplicates
