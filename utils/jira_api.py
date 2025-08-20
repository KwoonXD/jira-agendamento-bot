import base64
import requests
from requests.auth import HTTPBasicAuth
from collections import defaultdict
from typing import Tuple, Dict, Any, List, Optional


class JiraAPI:
    """
    Suporta dois modos:
      • Domínio: https://<site>.atlassian.net/rest/api/3/...
      • EX API : https://api.atlassian.com/ex/jira/{cloudId}/rest/api/3/...
    Para token fine‑grained, use EX API (use_ex_api=True).
    """

    def __init__(
        self,
        email: str,
        api_token: str,
        jira_url: str,
        use_ex_api: bool = False,
        cloud_id: Optional[str] = None
    ):
        self.email = email.strip()
        self.api_token = api_token.strip()
        self.jira_url = jira_url.rstrip("/")
        self.use_ex_api = use_ex_api
        self.cloud_id = cloud_id

        self.auth = HTTPBasicAuth(self.email, self.api_token)
        self.headers = {"Accept": "application/json", "Content-Type": "application/json"}

        # debug da última chamada
        self.last_status = None
        self.last_error = None
        self.last_url = None
        self.last_params = None
        self.last_count = None

    # ---------- helpers ----------
    def _base(self) -> str:
        if self.use_ex_api:
            if not self.cloud_id:
                raise ValueError("cloud_id é obrigatório quando use_ex_api=True")
            return f"https://api.atlassian.com/ex/jira/{self.cloud_id}/rest/api/3"
        return f"{self.jira_url}/rest/api/3"

    def _auth_headers(self) -> Dict[str, str]:
        if not self.use_ex_api:
            return {}
        basic = f"{self.email}:{self.api_token}".encode("utf-8")
        return {
            "Authorization": "Basic " + base64.b64encode(basic).decode("ascii"),
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _set_debug(self, url: str, params: Dict[str, Any], status: int, error: Any, count: int):
        self.last_url = url
        self.last_params = params
        self.last_status = status
        self.last_error = error
        self.last_count = count

    # ---------- diagnóstico ----------
    def whoami(self) -> Tuple[Dict[str, Any] | None, Dict[str, Any]]:
        url = f"{self._base()}/myself"
        hdr = self._auth_headers() or self.headers
        try:
            if self.use_ex_api:
                r = requests.get(url, headers=hdr)
            else:
                r = requests.get(url, headers=self.headers, auth=self.auth)
            dbg = {"url": url, "status": r.status_code}
            if r.status_code == 200:
                return r.json(), dbg
            try:
                dbg["error"] = r.json()
            except Exception:
                dbg["error"] = r.text
            return None, dbg
        except requests.RequestException as e:
            return None, {"url": url, "status": -1, "error": str(e)}

    def tenant_info(self) -> Tuple[Dict[str, Any] | None, Dict[str, Any]]:
        url = f"{self.jira_url}/_edge/tenant_info"
        try:
            r = requests.get(url, timeout=10)
            dbg = {"url": url, "status": r.status_code}
            if r.status_code == 200:
                return r.json(), dbg
            dbg["error"] = r.text
            return None, dbg
        except requests.RequestException as e:
            return None, {"url": url, "status": -1, "error": str(e)}

    # ---------- Core ----------
    def buscar_chamados(self, jql: str, fields: str) -> Tuple[list, Dict[str, Any]]:
        params = {"jql": jql, "maxResults": 100, "fields": fields}
        url = f"{self._base()}/search"
        debug = {"url": url, "params": params.copy(), "status": None, "error": None, "count": None}

        try:
            if self.use_ex_api:
                r = requests.get(url, headers=self._auth_headers(), params=params)
            else:
                r = requests.get(url, headers=self.headers, auth=self.auth, params=params)
            status = r.status_code
            if status == 200:
                issues = r.json().get("issues", [])
                debug.update({"status": status, "count": len(issues)})
                self._set_debug(url, params, status, None, len(issues))
                return issues, debug
            else:
                try:
                    err = r.json()
                except Exception:
                    err = r.text
                debug.update({"status": status, "error": err, "count": 0})
                self._set_debug(url, params, status, err, 0)
                return [], debug
        except requests.RequestException as e:
            debug.update({"status": -1, "error": str(e), "count": 0})
            self._set_debug(url, params, -1, str(e), 0)
            return [], debug

    def agrupar_chamados(self, issues: list) -> dict:
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
                "data_agendada": f.get("customfield_12036"),
            })
        return agrup

    def get_transitions(self, issue_key: str) -> list:
        url = f"{self._base()}/issue/{issue_key}/transitions"
        try:
            if self.use_ex_api:
                r = requests.get(url, headers=self._auth_headers())
            else:
                r = requests.get(url, headers=self.headers, auth=self.auth)
            if r.status_code == 200:
                return r.json().get("transitions", [])
        except requests.RequestException:
            pass
        return []

    def get_issue(self, issue_key: str) -> dict:
        url = f"{self._base()}/issue/{issue_key}"
        params = {"fields": "status"}
        try:
            if self.use_ex_api:
                r = requests.get(url, headers=self._auth_headers(), params=params)
            else:
                r = requests.get(url, headers=self.headers, auth=self.auth, params=params)
            if r.status_code == 200:
                return r.json()
        except requests.RequestException:
            pass
        return {}

    def transicionar_status(self, issue_key: str, transition_id: str, fields: dict = None) -> requests.Response:
        url = f"{self._base()}/issue/{issue_key}/transitions"
        payload = {"transition": {"id": str(transition_id)}}
        if fields:
            payload["fields"] = fields
        if self.use_ex_api:
            return requests.post(url, headers=self._auth_headers(), json=payload)
        else:
            return requests.post(url, headers=self.headers, auth=self.auth, json=payload)
