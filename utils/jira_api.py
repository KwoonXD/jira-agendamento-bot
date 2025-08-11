import requests
from requests.auth import HTTPBasicAuth
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

_DEFAULT_TIMEOUT = (4, 12)  # (connect, read) segundos

class _TimeoutSession(requests.Session):
    """Requests Session que aplica timeout por padrão."""
    def __init__(self, timeout=_DEFAULT_TIMEOUT):
        super().__init__()
        self._timeout = timeout

    def request(self, *args, **kwargs):
        kwargs.setdefault("timeout", self._timeout)
        return super().request(*args, **kwargs)

class JiraAPI:
    def __init__(self, email: str, api_token: str, jira_url: str):
        self.email = email
        self.api_token = api_token
        self.jira_url = jira_url.rstrip('/')

        # Sessão com pool + retry idempotente (GET)
        self.session = _TimeoutSession()
        retry = Retry(
            total=3,
            backoff_factor=0.6,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=["GET", "POST"]
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=20, pool_maxsize=50)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

        self.auth = HTTPBasicAuth(self.email, self.api_token)
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    # ---------- BUSCAS ----------
    def buscar_chamados(self, jql: str, fields: str) -> list:
        params = {"jql": jql, "maxResults": 200, "fields": fields}
        url = f"{self.jira_url}/rest/api/3/search"
        res = self.session.get(url, headers=self.headers, auth=self.auth, params=params)
        if res.status_code == 200:
            return res.json().get("issues", [])
        return []

    # ---------- TRANSIÇÕES ----------
    def get_transitions(self, issue_key: str) -> list:
        url = f"{self.jira_url}/rest/api/3/issue/{issue_key}/transitions"
        res = self.session.get(url, headers=self.headers, auth=self.auth)
        if res.status_code == 200:
            return res.json().get("transitions", [])
        return []

    def get_issue(self, issue_key: str) -> dict:
        url = f"{self.jira_url}/rest/api/3/issue/{issue_key}"
        res = self.session.get(url, headers=self.headers, auth=self.auth, params={"fields": "status"})
        if res.status_code == 200:
            return res.json()
        return {}

    def transicionar_status(self, issue_key: str, transition_id: str, fields: dict = None) -> requests.Response:
        payload = {"transition": {"id": str(transition_id)}}
        if fields:
            payload["fields"] = fields
        url = f"{self.jira_url}/rest/api/3/issue/{issue_key}/transitions"
        return self.session.post(url, headers=self.headers, auth=self.auth, json=payload)
