# utils/jira_api.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from collections import defaultdict

import requests
from requests.adapters import HTTPAdapter, Retry


@dataclass(frozen=True)
class JiraConfig:
    email: str
    api_token: str
    url: str
    timeout: int = 25


class JiraAPI:
    """
    Cliente simples e robusto para Jira Cloud v3.
    - Sessão com retry/backoff
    - Busca com paginação
    - Métodos utilitários para transições
    """

    def __init__(self, cfg: JiraConfig) -> None:
        self.cfg = cfg
        self.base = cfg.url.rstrip("/")
        self.session = requests.Session()
        self.session.auth = (cfg.email, cfg.api_token)
        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json",
        })
        retries = Retry(
            total=4,
            read=4,
            connect=4,
            backoff_factor=0.6,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET", "POST"]),
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retries))
        self.session.mount("http://", HTTPAdapter(max_retries=retries))

    # ------------- REST helpers -------------
    def _get(self, path: str, **params) -> Dict[str, Any]:
        r = self.session.get(f"{self.base}{path}", params=params, timeout=self.cfg.timeout)
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, json: Dict[str, Any]) -> requests.Response:
        r = self.session.post(f"{self.base}{path}", json=json, timeout=self.cfg.timeout)
        # para transição, Jira retorna 204 sem body
        if r.status_code >= 400:
            try:
                r.raise_for_status()
            except Exception:
                # deixa o chamador decidir (mantemos o Response)
                pass
        return r

    # ------------- Public API -------------
    def buscar_chamados(self, jql: str, fields: str, max_results: int = 1000) -> List[Dict[str, Any]]:
        """
        Faz paginação até 'max_results'. Retorna lista de issues (JSON bruto).
        """
        issues: List[Dict[str, Any]] = []
        start = 0
        page_size = 100

        while start < max_results:
            payload = self._get(
                "/rest/api/3/search",
                jql=jql,
                fields=fields,
                startAt=start,
                maxResults=min(page_size, max_results - start),
            )
            chunk = payload.get("issues", [])
            issues.extend(chunk)
            if len(chunk) < page_size:
                break
            start += page_size

        return issues

    def agrupar_chamados(self, issues: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Consolida o necessário por loja.
        Retorna: { loja: [ {key, status, pdv, ativo, problema, endereco, estado, cep, cidade, data_agendada}, ... ] }
        """
        agrup: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for issue in issues:
            f = issue.get("fields", {}) or {}
            loja = (f.get("customfield_14954") or {}).get("value") or "Loja Desconhecida"
            agrup[loja].append({
                "key": issue.get("key"),
                "status": (f.get("status") or {}).get("name"),
                "pdv": f.get("customfield_14829"),
                "ativo": (f.get("customfield_14825") or {}).get("value"),
                "problema": f.get("customfield_12374"),
                "endereco": f.get("customfield_12271"),
                "estado": (f.get("customfield_11948") or {}).get("value"),
                "cep": f.get("customfield_11993"),
                "cidade": f.get("customfield_11994"),
                "data_agendada": f.get("customfield_12036"),
            })
        return agrup

    def get_transitions(self, issue_key: str) -> List[Dict[str, Any]]:
        data = self._get(f"/rest/api/3/issue/{issue_key}/transitions")
        return data.get("transitions", []) or []

    def transicionar_status(self, issue_key: str, transition_id: str, fields: Optional[Dict[str, Any]] = None) -> requests.Response:
        payload: Dict[str, Any] = {"transition": {"id": str(transition_id)}}
        if fields:
            payload["fields"] = fields
        return self._post(f"/rest/api/3/issue/{issue_key}/transitions", json=payload)
