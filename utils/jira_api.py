import requests
from requests.auth import HTTPBasicAuth
from collections import defaultdict


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
