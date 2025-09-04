import base64
import json
import requests
from requests.auth import HTTPBasicAuth
from collections import defaultdict
from typing import Tuple, Dict, Any, Optional, List


class JiraAPI:
    """
    Dois modos:
      • Domínio: https://<site>.atlassian.net/rest/api/3/...
      • EX API : https://api.atlassian.com/ex/jira/{cloudId}/rest/api/3/...

    Para token fine-grained, use EX API (use_ex_api=True) + cloud_id.
    Endpoints usados:
      - POST /rest/api/3/jql/parse                 (valida JQL)
      - POST /rest/api/3/search/approximate-count  (conta issues)
      - POST /rest/api/3/search/jql                (enhanced search - busca issues)
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

        # debug última chamada
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

    def _req(self, method: str, url: str, *, json_body: Any = None, params: Dict[str, Any] = None, json_content=True):
        if self.use_ex_api:
            return requests.request(method, url, headers=self._auth_headers(json_content=json_content),
                                    data=(json.dumps(json_body) if json_body is not None else None),
                                    params=params)
        else:
            return requests.request(method, url, headers=(self.hdr_json if json_content else self.hdr_accept),
                                    auth=self.auth,
                                    json=(json_body if json_body is not None else None),
                                    params=params)

    # ---------- diagnóstico ----------
    def whoami(self) -> Tuple[Dict[str, Any] | None, Dict[str, Any]]:
        url = f"{self._base()}/myself"
        try:
            r = self._req("GET", url, json_content=False)
            dbg = {"url": url, "status": r.status_code}
            if r.status_code == 200:
                return r.json(), dbg
            dbg["error"] = _safe_json(r)
            return None, dbg
        except requests.RequestException as e:
            return None, {"url": url, "status": -1, "error": str(e)}

    # ---------- status helpers ----------
    def list_all_statuses(self):
        """GET /status — lista status globais."""
        url = f"{self._base()}/status"
        try:
            r = self._req("GET", url, json_content=False)
            return r.status_code, (r.json() if r.status_code == 200 else _safe_json(r))
        except Exception as e:
            return -1, str(e)

    def list_project_statuses(self, project_key: str):
        """
        GET /project/{projectKey}/statuses — lista status por tipo de issue no projeto.
        """
        url = f"{self._base()}/project/{project_key}/statuses"
        try:
            r = self._req("GET", url, json_content=False)
            return r.status_code, (r.json() if r.status_code == 200 else _safe_json(r))
        except Exception as e:
            return -1, str(e)

    # ---------- JQL helpers ----------
    def parse_jql(self, jql: str) -> Dict[str, Any]:
        """POST /jql/parse — valida JQL e retorna erros detalhados (STRICT)."""
        url = f"{self._base()}/jql/parse"
        body = {"queries": [jql], "validation": "STRICT"}
        try:
            r = self._req("POST", url, json_body=body)
            out = {"url": url, "status": r.status_code}
            if r.status_code == 200:
                out["result"] = r.json()
            else:
                out["error"] = _safe_json(r)
            return out
        except requests.RequestException as e:
            return {"url": url, "status": -1, "error": str(e)}

    def count_jql(self, jql: str) -> Dict[str, Any]:
        """POST /search/approximate-count — conta issues para a JQL."""
        url = f"{self._base()}/search/approximate-count"
        body = {"jql": jql}
        try:
            r = self._req("POST", url, json_body=body)
            out = {"url": url, "status": r.status_code}
            if r.status_code == 200:
                out["count"] = r.json().get("count", 0)
            else:
                out["error"] = _safe_json(r)
            return out
        except requests.RequestException as e:
            return {"url": url, "status": -1, "error": str(e)}

    # ---------- busca principal ----------
    def buscar_chamados(self, jql: str, fields: str, start_at: int = 0, max_results: int = 100) -> Tuple[List[dict], Dict[str, Any]]:
        """
        EX API: POST /search/jql (enhanced)
        Domínio: GET /search (legado)
        """
        base = self._base()
        fields_list = [f.strip() for f in fields.split(",") if f.strip()]

        if self.use_ex_api:
            url = f"{base}/search/jql"
            body = {
                "jql": jql,
                "startAt": start_at,
                "maxResults": max_results,
                "fields": fields_list
            }
            try:
                r = self._req("POST", url, json_body=body)
                if r.status_code == 200:
                    issues = r.json().get("issues", [])
                    self._set_debug(url, {"method": "POST", **body}, 200, None, len(issues), "POST")
                    return issues, {"url": url, "params": body, "status": 200, "count": len(issues), "method": "POST"}
                err = _safe_json(r)
                self._set_debug(url, {"method": "POST", **body}, r.status_code, err, 0, "POST")
                return [], {"url": url, "params": body, "status": r.status_code, "error": err, "count": 0, "method": "POST"}
            except requests.RequestException as e:
                self._set_debug(url, {"method": "POST", **body}, -1, str(e), 0, "POST")
                return [], {"url": url, "params": body, "status": -1, "error": str(e), "count": 0, "method": "POST"}

        # caminho tradicional (domínio)
        url = f"{base}/search"
        params_get = {"jql": jql, "maxResults": max_results, "startAt": start_at, "fields": ",".join(fields_list)}
        try:
            r = self._req("GET", url, params=params_get, json_content=False)
            if r.status_code == 200:
                issues = r.json().get("issues", [])
                self._set_debug(url, {"method": "GET", **params_get}, 200, None, len(issues), "GET")
                return issues, {"url": url, "params": params_get, "status": 200, "count": len(issues), "method": "GET"}
            err = _safe_json(r)
            self._set_debug(url, {"method": "GET", **params_get}, r.status_code, err, 0, "GET")
            return [], {"url": url, "params": params_get, "status": r.status_code, "error": err, "count": 0, "method": "GET"}
        except requests.RequestException as e:
            self._set_debug(url, {"method": "GET", **params_get}, -1, str(e), 0, "GET")
            return [], {"url": url, "params": params_get, "status": -1, "error": str(e), "count": 0, "method": "GET"}

    # ---------- helpers do painel ----------
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
            r = self._req("GET", url, json_content=False)
            if r.status_code == 200:
                return r.json().get("transitions", [])
        except requests.RequestException:
            pass
        return []

    def get_issue(self, issue_key: str) -> dict:
        url = f"{self._base()}/issue/{issue_key}"
        params = {"fields": "status"}
        try:
            r = self._req("GET", url, params=params, json_content=False)
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
        return self._req("POST", url, json_body=payload)


def _safe_json(r: requests.Response):
    try:
        return r.json()
    except Exception:
        return r.text
