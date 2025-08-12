# utils/jira_api.py
import requests
from requests.auth import HTTPBasicAuth
from collections import defaultdict


class JiraAPI:
    def __init__(self, email: str, api_token: str, jira_url: str):
        self.email = email
        self.api_token = api_token
        self.jira_url = jira_url.rstrip("/")
        self.auth = HTTPBasicAuth(self.email, self.api_token)
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    # ===== basic REST =====
    def buscar_chamados(self, jql: str, fields: str) -> list:
        params = {"jql": jql, "maxResults": 200, "fields": fields}
        url = f"{self.jira_url}/rest/api/3/search"
        res = requests.get(url, headers=self.headers, auth=self.auth, params=params, timeout=30)
        if res.status_code == 200:
            return res.json().get("issues", [])
        return []

    def get_transitions(self, issue_key: str) -> list:
        url = f"{self.jira_url}/rest/api/3/issue/{issue_key}/transitions"
        res = requests.get(url, headers=self.headers, auth=self.auth, timeout=30)
        if res.status_code == 200:
            return res.json().get("transitions", [])
        return []

    def get_issue(self, issue_key: str) -> dict:
        url = f"{self.jira_url}/rest/api/3/issue/{issue_key}"
        res = requests.get(url, headers=self.headers, auth=self.auth, params={"fields": "status"}, timeout=30)
        return res.json() if res.status_code == 200 else {}

    def transicionar_status(self, issue_key: str, transition_id: str, fields: dict = None):
        payload = {"transition": {"id": str(transition_id)}}
        if fields:
            payload["fields"] = fields
        url = f"{self.jira_url}/rest/api/3/issue/{issue_key}/transitions"
        return requests.post(url, headers=self.headers, auth=self.auth, json=payload, timeout=30)

    # ===== helper para o app =====
    def agrupar_chamados(self, issues: list) -> dict:
        """
        Retorna { loja: [ {key,status,pdv,ativo,problema,endereco,estado,cep,cidade}, ... ] }
        Mapeia os customfields usados no app.
        """
        agrup = defaultdict(list)
        for issue in issues:
            f = issue.get("fields", {})
            loja = f.get("customfield_14954", {}) .get("value", "Loja Desconhecida")
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
                # data_agendada existe, mas não exibimos no corpo do chamado:
                "data_agendada": f.get("customfield_12036"),
            })
        return agrup
