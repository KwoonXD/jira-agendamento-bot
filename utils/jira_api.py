# utils/jira_api.py
from __future__ import annotations

import requests
from requests.auth import HTTPBasicAuth
from typing import Dict, List


FIELDS = ",".join([
    "status",
    "created",
    "customfield_14954",  # Loja (cascading value / option)
    "customfield_14829",  # PDV
    "customfield_14825",  # Ativo (option)
    "customfield_12374",  # Problema
    "customfield_12271",  # Endereço
    "customfield_11948",  # Estado (option)
    "customfield_11993",  # CEP
    "customfield_11994",  # Cidade
    "customfield_12036",  # Data agendada (datetime)
])

JQLS = {
    "agendamento": 'project = FSA AND status = "AGENDAMENTO"',
    "agendado":    'project = FSA AND status = "AGENDADO"',
    "tec":         'project = FSA AND status = "TEC-CAMPO"',
}


class JiraAPI:
    """Cliente simples para Jira Cloud API v3."""

    def __init__(self, email: str, api_token: str, base_url: str):
        self.email = email
        self.api_token = api_token
        self.base_url = base_url.rstrip("/")
        self._auth = HTTPBasicAuth(email, api_token)
        self._headers = {"Accept": "application/json"}

    def _get(self, path: str, params: Dict = None) -> dict:
        url = f"{self.base_url}{path}"
        r = requests.get(url, headers=self._headers, auth=self._auth, params=params or {}, timeout=20)
        r.raise_for_status()
        return r.json()

    # -------- Public ---------------------------------------------------------

    def buscar_chamados(self, jql: str, fields: str = FIELDS, max_results: int = 200) -> List[dict]:
        params = {"jql": jql, "fields": fields, "maxResults": max_results}
        data = self._get("/rest/api/3/search", params=params)
        return data.get("issues", [])

    @staticmethod
    def normalizar_issue(issue: dict) -> dict:
        f = issue.get("fields", {})
        loja = (f.get("customfield_14954") or {}).get("value") or "Loja Desconhecida"
        estado = (f.get("customfield_11948") or {}).get("value") or "--"
        ativo = (f.get("customfield_14825") or {}).get("value") or "--"

        return {
            "key": issue.get("key", "--"),
            "status": (f.get("status") or {}).get("name") or "--",
            "created": f.get("created"),             # ISO8601
            "loja": loja,
            "pdv": str(f.get("customfield_14829") or "--"),
            "ativo": str(ativo),
            "problema": str(f.get("customfield_12374") or "--"),
            "endereco": str(f.get("customfield_12271") or "--"),
            "estado": str(estado),
            "cep": str(f.get("customfield_11993") or "--"),
            "cidade": str(f.get("customfield_11994") or "--"),
            "data_agendada": f.get("customfield_12036"),  # ISO8601
        }
