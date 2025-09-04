import base64
import json
import requests
from requests.auth import HTTPBasicAuth
from collections import defaultdict
from typing import Tuple, Dict, Any, Optional


class JiraAPI:
    """
    Suporta dois modos:
      • Domínio: https://<site>.atlassian.net/rest/api/3/...
      • EX API : https://api.atlassian.com/ex/jira/{cloudId}/rest/api/3/...
    Para token fine-grained, use EX API (use_ex_api=True).
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
        self.hdr_json = {"Accept": "application/json", "Content-Type": "application/json"}
        self.hdr_accept = {"Accept": "application/json"}

        # debug da última chamada
        self.last_status = None
        self.last_error = None
        self.last_url = None
        self.last_params = None
        self.last_count = None
        self.last_method = None

    # ---------- helpers ----------
    def _base(self) -> str:
        if self.use_ex_api:
            if not self.cloud_id:
                raise ValueError("cloud_id é obrigatório quando use_ex_api=True")
            return f"https://api.atlassian.com/ex/jira/{self.cloud_id}/rest/api/3"
        return f"{self.jira_url}/rest/api/3"

    def _auth_headers(self, json_content: bool = False) -> Dict[str, str]:
        """
        Para EX API enviamos Authorization manualmente.
        """
        if not self.use_ex_api:
            return self.hdr_json if json_content else self.hdr_accept
        basic = f"{self.email}:{self.api_token}".encode("utf-8")
        base = {
            "Authorization": "Basic " + base64.b64encode(basic).decode("ascii"),
            "Accept": "application/json",
        }
        if json_content:
            base["Content-Type"] = "application/json"
        return base

    def _set_debug(self, url: str, params: Any, status: int, error: Any, count: int, method: str):
        self.last_url = url
        self.last_params = params
        self.last_status = status
        self.last_error = error
        self.last_count = count
        self.last_method = method

    # ---------- diagnóstico ----------
    def whoami(self) -> Tuple[Dict[str, Any] | None, Dict[str, Any]]:
        url = f"{self._base()}/myself"
        try:
            if self.use_ex_api:
                r = requests.get(url, headers=self._auth_headers(json_content=False))
            else:
                r = requests.get(url, headers=self.hdr_accept, auth=self.auth)
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
        """
        Busca issues via JQL.
        Tenta GET /search; se vier 410/405, refaz via POST /search com body JSON.
        """
        url = f"{self._base()}/search"
        params_get = {"jql": jql, "maxResults": 100, "fields": fields}

        # 1) GET
        try:
            if self.use_ex_api:
                r = requests.get(url, headers=self._auth_headers(json_content=False), params=params_get)
            else:
                r = requests.get(url, headers=self.hdr_accept, auth=self.auth, params=params_get)
            if r.status_code == 200:
                issues = r.json().get("issues", [])
                self._set_debug(url, {"method": "GET", **params_get}, 200, None, len(issues), "GET")
                return issues, {"url": url, "params": params_get, "status": 200, "count": len(issues)}
            # se for “Gone”/“Method Not Allowed”, tenta POST
            if r.status_code in (405, 410):
                # cai para o POST
                pass
            else:
                err = _safe_json(r)
                self._set_debug(url, {"method": "GET", **params_get}, r.status_code, err, 0, "GET")
                return [], {"url": url, "params": params_get, "status": r.status_code, "error": err, "count": 0}
        except requests.RequestException as e:
            # vai tentar POST também
            pass

        # 2) POST
        body_post = {"jql": jql, "maxResults": 100, "fields": fields.split(",")}
        try:
            if self.use_ex_api:
                r = requests.post(url, headers=self._auth_headers(json_content=True), data=json.dumps(body_post))
            else:
                r = requests.post(url, headers=self.hdr_json, auth=self.auth, json=body_post)
            if r.status_code == 200:
                issues = r.json().get("issues", [])
                self._set_debug(url, {"method": "POST", **body_post}, 200, None, len(issues), "POST")
                return issues, {"url": url, "params": body_post, "status": 200, "count": len(issues)}
            err = _safe_json(r)
            self._set_debug(url, {"method": "POST", **body_post}, r.status_code, err, 0, "POST")
            return [], {"url": url, "params": body_post, "status": r.status_code, "error": err, "count": 0}
        except requests.RequestException as e:
            self._set_debug(url, {"method": "POST", **body_post}, -1, str(e), 0, "POST")
            return [], {"url": url, "params": body_post, "status": -1, "error": str(e), "count": 0}

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
                r = requests.get(url, headers=self._auth_headers(json_content=False))
            else:
                r = requests.get(url, headers=self.hdr_accept, auth=self.auth)
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
                r = requests.get(url, headers=self._auth_headers(json_content=False), params=params)
            else:
                r = requests.get(url, headers=self.hdr_accept, auth=self.auth, params=params)
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
            return requests.post(url, headers=self._auth_headers(json_content=True), data=json.dumps(payload))
        else:
            return requests.post(url, headers=self.hdr_json, auth=self.auth, json=payload)


def _safe_json(r: requests.Response):
    try:
        return r.json()
    except Exception:
        return r.text
