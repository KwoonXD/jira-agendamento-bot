# utils/jira_api.py
import time
import requests
from typing import List, Dict, Any, Optional
from requests.auth import HTTPBasicAuth


class JiraAPI:
    def __init__(self, email: str, api_token: str, jira_url: str, timeout: int = 25):
        self.email = email
        self.api_token = api_token
        self.jira_url = jira_url.rstrip("/")
        self.auth = HTTPBasicAuth(self.email, self.api_token)
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        self.timeout = timeout

    # ------------------- requisição com retry/backoff -------------------
    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        max_retries: int = 3,
        backoff_base: float = 0.8,
    ) -> requests.Response:
        url = f"{self.jira_url}{path}"
        last_exc: Optional[Exception] = None
        r = None

        for attempt in range(1, max_retries + 1):
            try:
                r = requests.request(
                    method,
                    url,
                    headers=self.headers,
                    auth=self.auth,
                    timeout=self.timeout,
                    params=params,
                    json=json,
                )

                # rate limit
                if r.status_code == 429:
                    wait = float(r.headers.get("Retry-After", attempt * backoff_base))
                    time.sleep(wait)
                    continue

                if r.status_code >= 400:
                    try:
                        payload = r.json()
                    except Exception:
                        payload = r.text
                    msg = (
                        f"Jira API HTTP {r.status_code} [{method} {path}] "
                        f"params={params} json={json} payload={payload}"
                    )
                    r.raise_for_status()
                return r

            except requests.HTTPError as e:
                last_exc = e
                if r is not None and 400 <= r.status_code < 500 and r.status_code != 429:
                    break
                time.sleep(attempt * backoff_base)

            except requests.RequestException as e:
                last_exc = e
                time.sleep(attempt * backoff_base)

        raise requests.HTTPError(f"Falha ao chamar Jira após {max_retries} tentativas: {last_exc}")

    # ------------------- busca paginada -------------------
    def buscar_chamados(self, jql: str, fields: str, max_results: int = 1000) -> List[Dict[str, Any]]:
        path = "/rest/api/3/search"
        start_at = 0
        page_size = 100
        issues: List[Dict[str, Any]] = []

        while len(issues) < max_results:
            params = {
                "jql": jql,
                "startAt": start_at,
                "maxResults": min(page_size, max_results - len(issues)),
                "fields": fields,
            }
            r = self._request("GET", path, params=params)
            data = r.json()

            page_issues = data.get("issues", []) or []
            issues.extend(page_issues)

            if len(page_issues) == 0 or start_at + len(page_issues) >= data.get("total", 0):
                break
            start_at += len(page_issues)

        return issues

    # ------------------- agrupar por loja -------------------
    def agrupar_chamados(self, issues: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        from collections import defaultdict
        agrup = defaultdict(list)
        for issue in issues:
            f = issue.get("fields", {})
            loja = (f.get("customfield_14954") or {}).get("value") or "Loja Desconhecida"
            agrup[loja].append({
                "key": issue.get("key"),
                "status": (f.get("status") or {}).get("name", "--"),
                "pdv": f.get("customfield_14829", "--"),
                "ativo": (f.get("customfield_14825") or {}).get("value", "--"),
                "problema": f.get("customfield_12374", "--"),
                "endereco": f.get("customfield_12271", "--"),
                "estado": (f.get("customfield_11948") or {}).get("value", "--"),
                "cep": f.get("customfield_11993", "--"),
                "cidade": f.get("customfield_11994", "--"),
                "data_agendada": f.get("customfield_12036"),
            })
        return agrup

    # ------------------- transições -------------------
    def get_transitions(self, issue_key: str) -> List[Dict[str, Any]]:
        r = self._request("GET", f"/rest/api/3/issue/{issue_key}/transitions")
        return r.json().get("transitions", [])

    def get_issue(self, issue_key: str) -> Dict[str, Any]:
        r = self._request("GET", f"/rest/api/3/issue/{issue_key}", params={"fields": "status"})
        return r.json()

    def transicionar_status(self, issue_key: str, transition_id: str, fields: Optional[Dict[str, Any]] = None) -> requests.Response:
        payload = {"transition": {"id": str(transition_id)}}
        if fields:
            payload["fields"] = fields
        return self._request("POST", f"/rest/api/3/issue/{issue_key}/transitions", json=payload)
