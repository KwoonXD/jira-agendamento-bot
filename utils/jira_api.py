import requests
from requests.auth import HTTPBasicAuth
from collections import defaultdict

class JiraAPI:
    def __init__(self, email, api_token, jira_url):
        self.auth = HTTPBasicAuth(email, api_token)
        self.headers = {"Accept": "application/json", "Content-Type": "application/json"}
        self.jira_url = jira_url

    def buscar_chamados(self, jql, fields):
        params = {
            "jql": jql,
            "maxResults": 100,
            "fields": fields
        }
        res = requests.get(f"{self.jira_url}/rest/api/3/search", headers=self.headers, auth=self.auth, params=params)
        return res.json().get("issues", []) if res.status_code == 200 else []

   def agrupar_chamados(self, chamados):
    agrupado = defaultdict(list)
    for issue in chamados:
        fields = issue["fields"]
        loja = fields.get("customfield_14954", {}).get("value", "Loja Desconhecida")
        ativo = fields.get("customfield_14825", {}).get("value", "--")
        problema = fields.get("customfield_12374", "--")
        pdv = fields.get("customfield_14829", "--")

        agrupado[loja].append({
            "key": issue["key"],
            "pdv": pdv,
            "ativo": ativo,
            "problema": problema,
            "endereco": fields.get("customfield_12271", "--"),
            "estado": fields.get("customfield_11948", {}).get("value", "--"),
            "cep": fields.get("customfield_11993", "--"),
            "cidade": fields.get("customfield_11994", "--"),
            "data_agendada": fields.get("customfield_12036", "")
        })
    return agrupado

