import requests
from requests.auth import HTTPBasicAuth

class JiraAPI:
    def __init__(self, email: str, api_token: str, base_url: str):
        self.email = email
        self.api_token = api_token
        self.base_url = base_url.rstrip("/")
        self._auth = HTTPBasicAuth(email, api_token)
        self._headers = {"Accept": "application/json"}

    def _get(self, path: str, params=None) -> dict:
        url = f"{self.base_url}{path}"
        r = requests.get(url, headers=self._headers, auth=self._auth, params=params or {}, timeout=20)
        r.raise_for_status()
        return r.json()

    def whoami(self):
        return self._get("/rest/api/3/myself")

    def buscar_chamados(self, jql: str, fields: str, max_results=200):
        params = {"jql": jql, "fields": fields, "maxResults": max_results}
        data = self._get("/rest/api/3/search", params=params)
        return data.get("issues", [])

    @staticmethod
    def normalizar(issue: dict) -> dict:
        f = issue.get("fields", {})
        loja = (f.get("customfield_14954") or {}).get("value") or "Loja Desconhecida"
        estado = (f.get("customfield_11948") or {}).get("value") or "--"
        ativo = (f.get("customfield_14825") or {}).get("value") or "--"
        return {
            "key": issue.get("key", "--"),
            "status": (f.get("status") or {}).get("name") or "--",
            "created": f.get("created"),
            "loja": loja,
            "pdv": str(f.get("customfield_14829") or "--"),
            "ativo": str(ativo),
            "problema": str(f.get("customfield_12374") or "--"),
            "endereco": str(f.get("customfield_12271") or "--"),
            "estado": str(estado),
            "cep": str(f.get("customfield_11993") or "--"),
            "cidade": str(f.get("customfield_11994") or "--"),
            "data_agendada": f.get("customfield_12036"),
        }
