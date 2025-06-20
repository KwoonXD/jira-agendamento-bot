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
        return agrupado
            def get_transitions(self, issue_key):
        """Retorna lista de transições disponíveis para um chamado."""
        res = requests.get(
            f"{self.jira_url}/rest/api/3/issue/{issue_key}/transitions",
            headers=self.headers,
            auth=self.auth
        )
        if res.status_code == 200:
            return res.json().get("transitions", [])
        return []

    def transicionar_status(self, issue_key, transition_id):
        """Executa a transição de status no Jira."""
        res = requests.post(
            f"{self.jira_url}/rest/api/3/issue/{issue_key}/transitions",
            headers=self.headers,
            auth=self.auth,
            json={"transition": {"id": str(transition_id)}}
        )
        return res.status_code == 204

