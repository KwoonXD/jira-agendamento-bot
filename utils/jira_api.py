import requests
from requests.auth import HTTPBasicAuth

class JiraAPI:
    """
    API enxuta para buscar issues do Jira Cloud (REST v3).

    Você passa: email, api_token e base_url, e usa:
      - buscar_chamados(jql, fields)
      - normalizar(issue) -> dict pronto p/ tela/mensagem
    """
    def __init__(self, email: str, api_token: str, jira_url: str):
        self.base = jira_url.rstrip("/")
        self.auth = HTTPBasicAuth(email, api_token)
        self.headers = {"Accept": "application/json"}

    def _get(self, path: str, params: dict | None = None) -> dict:
        url = f"{self.base}{path}"
        r = requests.get(url, auth=self.auth, headers=self.headers, params=params, timeout=30)
        r.raise_for_status()
        return r.json()

    def buscar_chamados(self, jql: str, fields: str, max_results: int = 200) -> list[dict]:
        params = {"jql": jql, "fields": fields, "maxResults": max_results}
        data = self._get("/rest/api/3/search", params=params)
        return data.get("issues", [])

    # --------- Normalização (ajuste seus customfields aqui) ------------------
    # Troque estes IDs se necessário. Estão coerentes com seu histórico.
    CF_LOJA        = "customfield_14954"  # -> option.value
    CF_PDV         = "customfield_14829"  # -> texto/num
    CF_ATIVO       = "customfield_14825"  # -> option.value
    CF_PROBLEMA    = "customfield_12374"  # -> texto
    CF_ENDERECO    = "customfield_12271"  # -> texto
    CF_UF          = "customfield_11948"  # -> option.value
    CF_CEP         = "customfield_11993"  # -> texto
    CF_CIDADE      = "customfield_11994"  # -> texto
    CF_DATA_AG     = "customfield_12036"  # -> string ISO com timezone

    def normalizar(self, issue: dict) -> dict:
        f = issue.get("fields", {})
        def opt(d, key):
            val = f.get(key)
            if isinstance(val, dict):
                return val.get("value") or val.get("name")
            return val

        def status_name():
            s = f.get("status") or {}
            return s.get("name", "--")

        return {
            "key": issue.get("key"),
            "status": status_name(),
            "loja": (opt(self, self.CF_LOJA) if isinstance(self, dict) else opt(f, self.CF_LOJA)) or "--",
            "pdv": (f.get(self.CF_PDV) if isinstance(self, str) else f.get(self.CF_PDV, "--")) or "--",
            "ativo": (opt(f, self.CF_ATIVO) or "--"),
            "problema": (f.get(self.CF_PROBLEMA) or "--"),
            "endereco": (f.get(self.CF_ENDERECO) or "--"),
            "estado": (opt(f, self.CF_UF) or "--"),
            "cep": (f.get(self.CF_CEP) or "--"),
            "cidade": (f.get(self.CF_CIDADE) or "--"),
            "data_agendada": f.get(self.CF_DATA_AG),  # string ISO; formatamos depois
        }
