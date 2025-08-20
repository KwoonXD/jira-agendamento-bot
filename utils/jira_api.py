import requests
from requests.auth import HTTPBasicAuth
from collections import defaultdict
from typing import Tuple, Dict, Any, List


class JiraAPI:
    """
    Wrapper para Jira Cloud API v3 com utilitários de diagnóstico.
    """

    def __init__(self, email: str, api_token: str, jira_url: str):
        self.email = email
        self.api_token = api_token
        self.jira_url = jira_url.rstrip("/")
        self.auth = HTTPBasicAuth(self.email, self.api_token)
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        # último snapshot (rápido)
        self.last_status = None
        self.last_error = None
        self.last_url = None
        self.last_params = None
        self.last_count = None

    # ------------------------
    # Helpers de diagnóstico
    # ------------------------
    def whoami(self) -> Tuple[Dict[str, Any] | None, Dict[str, Any]]:
        """
        Confere o usuário autenticado.
        Retorna (payload|None, debug).
        """
        url = f"{self.jira_url}/rest/api/3/myself"
        dbg = {"url": url}
        try:
            r = requests.get(url, headers=self.headers, auth=self.auth)
            dbg["status"] = r.status_code
            if r.status_code == 200:
                return r.json(), dbg
            try:
                dbg["error"] = r.json()
            except Exception:
                dbg["error"] = r.text
            return None, dbg
        except requests.RequestException as e:
            dbg["status"] = -1
            dbg["error"] = str(e)
            return None, dbg

    def listar_projetos(self, max_results: int = 50) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Lista projetos visíveis ao usuário/token.
        Retorna (lista, debug).
        """
        url = f"{self.jira_url}/rest/api/3/project/search"
        params = {"maxResults": max_results}
        dbg = {"url": url, "params": params}
        try:
            r = requests.get(url, headers=self.headers, auth=self.auth, params=params)
            dbg["status"] = r.status_code
            if r.status_code == 200:
                data = r.json() or {}
                values = data.get("values", [])
                dbg["count"] = len(values)
                return values, dbg
            try:
                dbg["error"] = r.json()
            except Exception:
                dbg["error"] = r.text
            return [], dbg
        except requests.RequestException as e:
            dbg["status"] = -1
            dbg["error"] = str(e)
            return [], dbg

    # ------------------------
    # Core
    # ------------------------
    def _set_debug(self, url: str, params: Dict[str, Any], status: int, error: Any, count: int):
        self.last_url = url
        self.last_params = params
        self.last_status = status
        self.last_error = error
        self.last_count = count

    def buscar_chamados(self, jql: str, fields: str) -> Tuple[list, Dict[str, Any]]:
        """
        Executa search JQL e retorna (issues, debug_snapshot).
        """
        params = {"jql": jql, "maxResults": 100, "fields": fields}
        url = f"{self.jira_url}/rest/api/3/search"

        debug_snapshot: Dict[str, Any] = {
            "url": url,
            "params": params.copy(),
            "status": None,
            "error": None,
            "count": None,
        }

        try:
            res = requests.get(url, headers=self.headers, auth=self.auth, params=params)
            status = res.status_code
            if status == 200:
                issues = res.json().get("issues", [])
                count = len(issues)
                debug_snapshot.update({"status": status, "count": count})
                self._set_debug(url, params, status, None, count)
                return issues, debug_snapshot
            else:
                try:
                    err = res.json()
                except Exception:
                    err = res.text
                debug_snapshot.update({"status": status, "error": err, "count": 0})
                self._set_debug(url, params, status, err, 0)
                return [], debug_snapshot
        except requests.RequestException as e:
            debug_snapshot.update({"status": -1, "error": str(e), "count": 0})
            self._set_debug(url, params, -1, str(e), 0)
            return [], debug_snapshot

    def agrupar_chamados(self, issues: list) -> dict:
        """
        Agrupa issues por customfield_14954 (loja).
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
                "data_agendada": f.get("customfield_12036"),
            })
        return agrup

    def get_transitions(self, issue_key: str) -> list:
        url = f"{self.jira_url}/rest/api/3/issue/{issue_key}/transitions"
        res = requests.get(url, headers=self.headers, auth=self.auth)
        if res.status_code == 200:
            return res.json().get("transitions", [])
        return []

    def get_issue(self, issue_key: str) -> dict:
        url = f"{self.jira_url}/rest/api/3/issue/{issue_key}"
        res = requests.get(url, headers=self.headers, auth=self.auth, params={"fields": "status"})
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
