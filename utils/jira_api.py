# utils/jira_api.py
from __future__ import annotations

import requests
from requests.auth import HTTPBasicAuth
from typing import Dict, Any, List


class JiraAPI:
    """
    Cliente simplificado do Jira Cloud (API v3).
    Inicialize com url, email e token; chame search_issues(jql).
    """

    DEFAULT_FIELDS = ",".join([
        "key",
        "summary",
        "status",
        "created",
        # Ajuste os customfields conforme seu Jira:
        "customfield_14954",  # Loja (option/value)
        "customfield_14829",  # PDV
        "customfield_14825",  # ATIVO (option/value)
        "customfield_12374",  # Problema
        "customfield_12271",  # Endereço
        "customfield_11948",  # Estado (option/value)
        "customfield_11993",  # CEP
        "customfield_11994",  # Cidade
        "customfield_12036",  # Data agendada (datetime)
    ])

    def __init__(self, url: str, email: str, token: str):
        self.base = url.rstrip("/")
        self.auth = HTTPBasicAuth(email, token)
        self.headers = {"Accept": "application/json"}

    def _get(self, path: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
        url = f"{self.base}{path}"
        r = requests.get(url, headers=self.headers, auth=self.auth, params=params, timeout=25)
        r.raise_for_status()
        return r.json()

    def search_raw(self, jql: str, fields: str | None = None, max_results: int = 200) -> List[Dict[str, Any]]:
        params = {
            "jql": jql,
            "maxResults": max_results,
            "fields": fields or self.DEFAULT_FIELDS,
        }
        data = self._get("/rest/api/3/search", params=params)
        return data.get("issues", [])

    def search_issues(self, jql: str, fields: str | None = None, max_results: int = 200) -> List[Dict[str, Any]]:
        issues = self.search_raw(jql, fields, max_results)
        return [self._normalize(i) for i in issues]

    @staticmethod
    def _opt(o: Any, key: str = "value", default: str = "--") -> str:
        if isinstance(o, dict):
            v = o.get(key)
            if v:
                return str(v)
        return default

    def _normalize(self, issue: Dict[str, Any]) -> Dict[str, Any]:
        f = issue.get("fields", {}) or {}

        return {
            "key": issue.get("key", "--"),
            "status": (f.get("status", {}) or {}).get("name", "--"),
            "created": f.get("created"),
            "loja": self._opt(f.get("customfield_14954")),
            "pdv": f.get("customfield_14829"),
            "ativo": self._opt(f.get("customfield_14825")),
            "problema": f.get("customfield_12374") or "--",
            "endereco": f.get("customfield_12271") or "--",
            "estado": self._opt(f.get("customfield_11948")),
            "cep": f.get("customfield_11993") or "--",
            "cidade": f.get("customfield_11994") or "--",
            "data_agendada": f.get("customfield_12036"),
        }
