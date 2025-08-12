import requests
from requests.auth import HTTPBasicAuth


class JiraAPI:
    def __init__(self, email: str, api_token: str, jira_url: str):
        self.email = email
        self.api_token = api_token
        self.jira_url = jira_url.rstrip("/")
        self.auth = HTTPBasicAuth(self.email, self.api_token)
        self.headers = {"Accept": "application/json", "Content-Type": "application/json"}

    # ---------- leitura ----------
    def buscar_chamados(self, jql: str, fields: str, max_results: int = 200) -> list:
        url = f"{self.jira_url}/rest/api/3/search"
        params = {"jql": jql, "fields": fields, "maxResults": max_results}
        r = requests.get(url, headers=self.headers, auth=self.auth, params=params, timeout=30)
        r.raise_for_status()
        return r.json().get("issues", [])

    def get_issue(self, issue_key: str, fields: str = "status") -> dict:
        url = f"{self.jira_url}/rest/api/3/issue/{issue_key}"
        r = requests.get(url, headers=self.headers, auth=self.auth, params={"fields": fields}, timeout=30)
        r.raise_for_status()
        return r.json()

    def get_transitions(self, issue_key: str) -> list:
        url = f"{self.jira_url}/rest/api/3/issue/{issue_key}/transitions"
        r = requests.get(url, headers=self.headers, auth=self.auth, timeout=30)
        r.raise_for_status()
        return r.json().get("transitions", [])

    # ---------- escrita ----------
    def transicionar_status(self, issue_key: str, transition_id: str, fields: dict | None = None):
        url = f"{self.jira_url}/rest/api/3/issue/{issue_key}/transitions"
        payload = {"transition": {"id": str(transition_id)}}
        if fields:
            payload["fields"] = fields
        r = requests.post(url, headers=self.headers, auth=self.auth, json=payload, timeout=30)
        r.raise_for_status()
        return r

    def add_comment(self, issue_key: str, body: str):
        url = f"{self.jira_url}/rest/api/3/issue/{issue_key}/comment"
        r = requests.post(url, headers=self.headers, auth=self.auth, json={"body": body}, timeout=30)
        r.raise_for_status()
        return r

    # ---------- helpers de transformação ----------
    def agrupar_chamados(self, issues: list) -> dict:
        """
        retorno:
        { loja: [ {key, loja, pdv, ativo, problema, endereco, estado, cep, cidade,
                   selfchk, data_agendada, status}, ... ] }
        """
        from collections import defaultdict

        agrup = defaultdict(list)
        for it in issues:
            f = it.get("fields", {})
            loja = f.get("customfield_14954", {}).get("value", "Loja Desconhecida")  # Código da Loja[Dropdown]
            agrup[loja].append(
                {
                    "key": it.get("key"),
                    "loja": loja,
                    "pdv": str(f.get("customfield_14829", "") or ""),
                    "ativo": (f.get("customfield_14825", {}) or {}).get("value", "") or "",
                    "problema": f.get("customfield_12374", "") or "",
                    "endereco": f.get("customfield_12271", "") or "",
                    "estado": (f.get("customfield_11948", {}) or {}).get("value", "") or "",
                    "cep": f.get("customfield_11993", "") or "",
                    "cidade": f.get("customfield_11994", "") or "",
                    "selfchk": f.get("customfield_12279", None),  # campo rich text do técnico
                    "data_agendada": f.get("customfield_12036", None),
                    "status": (f.get("status", {}) or {}).get("name", ""),
                }
            )
        return agrup
