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
        params = {"jql": jql, "maxResults": 100, "fields": fields}
        url = f"{self.jira_url}/rest/api/3/search"
        res = requests.get(url, headers=self.headers, auth=self.auth, params=params)
        if res.status_code == 200:
            return res.json().get("issues", [])
        return []

    def agrupar_chamados(self, issues: list) -> dict:
        agrup = defaultdict(list)
        for issue in issues:
            f = issue.get("fields", {})
            loja = f.get("customfield_14954", {}).get("value", "Loja Desconhecida")
            agrup[loja].append({
                "key": issue.get("key"),
                "status": f.get("status", {}).get("name", "--"),
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
        url = f"{self.jira_url}/rest/api/3/issue/{issue_key}/transitions"
        res = requests.get(url, headers=self.headers, auth=self.auth)
        if res.status_code == 200:
            return res.json().get("transitions", [])
        return []

    def transition_by_name(self, issue_key: str, transition_name: str, fields: dict = None):
        transitions = self.get_transitions(issue_key)
        for t in transitions:
            if t.get("name", "").lower() == transition_name.lower():
                return self.transicionar_status(issue_key, t["id"], fields)
        return None

    def get_issue(self, issue_key: str, fields: str = "status") -> dict:
        url = f"{self.jira_url}/rest/api/3/issue/{issue_key}"
        res = requests.get(url, headers=self.headers, auth=self.auth, params={"fields": fields})
        if res.status_code == 200:
            return res.json()
        return {}

    def transicionar_status(self, issue_key: str, transition_id: str, fields: dict = None) -> requests.Response:
        payload = {"transition": {"id": str(transition_id)}}
        if fields:
            payload["fields"] = fields
        url = f"{self.jira_url}/rest/api/3/issue/{issue_key}/transitions"
        res = requests.post(url, headers=self.headers, auth=self.auth, json=payload)
        return res

    def add_comment(self, issue_key: str, body: str):
        url = f"{self.jira_url}/rest/api/3/issue/{issue_key}/comment"
        payload = {"body": body}
        res = requests.post(url, headers=self.headers, auth=self.auth, json=payload)
        return res
