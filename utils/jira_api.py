"""Abstrações de acesso à API do Jira usadas pelo app Streamlit."""
from __future__ import annotations

import base64
import json
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests
import streamlit as st
from requests.auth import HTTPBasicAuth

DEFAULT_STATUS = "--"


class JiraAPI:
    """Cliente HTTP enxuto para chamadas REST do Jira."""

    def __init__(
        self,
        email: str,
        api_token: str,
        jira_url: str,
        use_ex_api: bool = False,
        cloud_id: Optional[str] = None,
    ) -> None:
        self.email = email.strip()
        self.api_token = api_token.strip()
        self.jira_url = jira_url.rstrip("/")
        self.use_ex_api = use_ex_api
        self.cloud_id = cloud_id

        self.auth = HTTPBasicAuth(self.email, self.api_token)
        self.hdr_json = {"Accept": "application/json", "Content-Type": "application/json"}
        self.hdr_accept = {"Accept": "application/json"}

        self.last_status: Optional[int] = None
        self.last_error: Optional[Any] = None
        self.last_url: Optional[str] = None
        self.last_params: Optional[Any] = None
        self.last_count: Optional[int] = None
        self.last_method: Optional[str] = None

    # -----------------------------------------------------------
    # Utilidades internas
    # -----------------------------------------------------------
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

    def _set_debug(
        self,
        url: str,
        params: Any,
        status: int,
        error: Any,
        count: int,
        method: str,
    ) -> None:
        self.last_url = url
        self.last_params = params
        self.last_status = status
        self.last_error = error
        self.last_count = count
        self.last_method = method

    def _req(
        self,
        method: str,
        url: str,
        *,
        json_body: Any = None,
        params: Optional[Dict[str, Any]] = None,
        json_content: bool = True,
    ) -> requests.Response:
        if self.use_ex_api:
            return requests.request(
                method,
                url,
                headers=self._auth_headers(json_content=json_content),
                data=json.dumps(json_body) if json_body is not None else None,
                params=params,
            )
        return requests.request(
            method,
            url,
            headers=self.hdr_json if json_content else self.hdr_accept,
            auth=self.auth,
            json=json_body if json_body is not None else None,
            params=params,
        )

    # -----------------------------------------------------------
    # Endpoints principais
    # -----------------------------------------------------------
    def buscar_chamados_enhanced(
        self,
        jql: str,
        fields: str | List[str],
        page_size: int = 100,
        reconcile: bool = False,
    ) -> Tuple[List[dict], Dict[str, Any]]:
        """Executa o endpoint POST /search/jql com suporte a paginação."""

        url = f"{self._base()}/search/jql"
        if isinstance(fields, str):
            fields_list = [f.strip() for f in fields.split(",") if f.strip()]
        else:
            fields_list = list(fields or [])

        expand: List[str] = []
        cleaned_fields: List[str] = []
        for campo in fields_list:
            if campo.lower() == "changelog":
                expand.append("changelog")
            else:
                cleaned_fields.append(campo)
        fields_list = cleaned_fields

        issues: List[dict] = []
        next_page_token: Optional[str] = None
        last_resp: Dict[str, Any] = {}

        while True:
            body: Dict[str, Any] = {
                "jql": jql,
                "maxResults": int(page_size),
                "fields": fields_list,
            }
            if expand:
                body["expand"] = expand
            if reconcile:
                body["reconcileIssues"] = []
            if next_page_token:
                body["nextPageToken"] = next_page_token

            try:
                resp = self._req("POST", url, json_body=body)
                if resp.status_code != 200:
                    err = _safe_json(resp)
                    self._set_debug(url, body, resp.status_code, err, 0, "POST")
                    return [], {
                        "url": url,
                        "params": body,
                        "status": resp.status_code,
                        "error": err,
                        "count": 0,
                        "method": "POST",
                    }

                data = resp.json()
                batch = data.get("issues", [])
                issues.extend(batch)
                next_page_token = data.get("nextPageToken")
                last_resp = {"url": url, "params": body, "status": 200, "count": len(batch), "method": "POST"}

                if not next_page_token:
                    break
            except requests.RequestException as exc:
                self._set_debug(url, body, -1, str(exc), 0, "POST")
                return [], {
                    "url": url,
                    "params": body,
                    "status": -1,
                    "error": str(exc),
                    "count": 0,
                    "method": "POST",
                }

        self._set_debug(url, last_resp.get("params"), last_resp.get("status", 200), None, len(issues), "POST")
        return issues, {"url": url, "status": 200, "count": len(issues), "method": "POST"}

    def agrupar_chamados(self, issues: List[dict]) -> Dict[str, List[Dict[str, Any]]]:
        """Agrupa os chamados por loja, extraindo campos utilizados pelo app."""

        def _extrair_loja(valor: Any) -> Tuple[str, str]:
            codigo: Optional[str] = None
            nome: Optional[str] = None

            def _registrar_codigo(possivel: Optional[str]) -> None:
                nonlocal codigo
                if possivel and str(possivel).strip():
                    codigo = codigo or str(possivel).strip()

            def _registrar_nome(possivel: Optional[str]) -> None:
                nonlocal nome
                if possivel and str(possivel).strip():
                    nome = nome or str(possivel).strip()

            if isinstance(valor, dict):
                for chave in ("value", "id", "key", "code", "codigo", "stringValue"):
                    _registrar_codigo(valor.get(chave))
                for chave in ("label", "name", "displayName", "text", "descricao"):
                    _registrar_nome(valor.get(chave))
                for nested_key in ("child", "children", "parent", "values", "options", "childrenValues"):
                    nested = valor.get(nested_key)
                    if nested:
                        codigo_nested, nome_nested = _extrair_loja(nested)
                        _registrar_codigo(codigo_nested)
                        _registrar_nome(nome_nested)
            elif isinstance(valor, list):
                for item in valor:
                    codigo_nested, nome_nested = _extrair_loja(item)
                    _registrar_codigo(codigo_nested)
                    _registrar_nome(nome_nested)
                    if codigo and nome:
                        break
            elif isinstance(valor, str):
                texto = valor.strip()
                if texto:
                    if " - " in texto:
                        possivel_codigo, possivel_nome = texto.split(" - ", 1)
                        _registrar_codigo(possivel_codigo)
                        _registrar_nome(possivel_nome)
                    else:
                        _registrar_codigo(texto)
                        _registrar_nome(texto)

            codigo_final = (codigo or nome or "Loja Desconhecida").strip()
            nome_final = (nome or codigo_final).strip()
            return codigo_final, nome_final

        def _extrair_status(fields: Dict[str, Any]) -> str:
            status_info = fields.get("status")
            if isinstance(status_info, dict):
                nome = status_info.get("name")
            elif isinstance(status_info, str):
                nome = status_info
            else:
                nome = None
            return (nome or DEFAULT_STATUS).strip()

        def _extrair_opcao(valor: Any) -> str:
            if isinstance(valor, dict):
                return (
                    str(
                        valor.get("value")
                        or valor.get("label")
                        or valor.get("name")
                        or valor.get("displayName")
                        or "--"
                    )
                    .strip()
                    or "--"
                )
            if isinstance(valor, list):
                return ", ".join(
                    str(item.get("value") if isinstance(item, dict) else item)
                    for item in valor
                    if item
                ) or "--"
            if valor is None:
                return "--"
            return str(valor).strip() or "--"

        agrupado: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

        for issue in issues:
            fields = issue.get("fields", {}) or {}
            loja_codigo, loja_nome = _extrair_loja(fields.get("customfield_14954"))

            agrupado[loja_codigo].append(
                {
                    "key": issue.get("key"),
                    "status": _extrair_status(fields),
                    "resumo": fields.get("summary", "--"),
                    "pdv": fields.get("customfield_14829", "--"),
                    "ativo": _extrair_opcao(fields.get("customfield_14825")),
                    "problema": fields.get("customfield_12374", "--"),
                    "endereco": fields.get("customfield_12271", "--"),
                    "estado": _extrair_opcao(fields.get("customfield_11948")),
                    "cep": fields.get("customfield_11993", "--"),
                    "cidade": fields.get("customfield_11994", "--"),
                    "data_agendada": fields.get("customfield_12036"),
                    "created": fields.get("created"),
                    "loja": loja_nome,
                    "loja_codigo": loja_codigo,
                    "historico_alerta": analisar_historico(issue),
                }
            )

        return dict(agrupado)

    def atualizar_campo_issue(self, issue_key: str, fields: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self._base()}/issue/{issue_key}"
        payload = {"fields": fields}

        try:
            resp = self._req("PUT", url, json_body=payload)
        except requests.RequestException as exc:  # pragma: no cover
            raise RuntimeError(f"Erro ao atualizar issue {issue_key}: {exc}") from exc

        if resp.status_code not in {200, 204}:
            conteudo = _safe_json(resp)
            raise RuntimeError(
                f"Falha ao atualizar issue {issue_key}: {resp.status_code} - {conteudo}"
            )

        if resp.content:
            try:
                return resp.json()
            except ValueError:  # pragma: no cover
                return {"raw": resp.text}
        return {}

    def get_transitions(self, issue_key: str) -> List[dict]:
        url = f"{self._base()}/issue/{issue_key}/transitions"
        try:
            resp = self._req("GET", url, json_content=False)
            if resp.status_code == 200:
                return resp.json().get("transitions", [])
        except requests.RequestException:
            pass
        return []

    def transicionar_status(
        self, issue_key: str, transition_id: str, fields: Optional[Dict[str, Any]] = None
    ) -> requests.Response:
        url = f"{self._base()}/issue/{issue_key}/transitions"
        payload: Dict[str, Any] = {"transition": {"id": str(transition_id)}}
        if fields:
            payload["fields"] = fields
        return self._req("POST", url, json_body=payload)


def _safe_json(resp: requests.Response):
    try:
        return resp.json()
    except Exception:
        return resp.text


@st.cache_resource(show_spinner=False)
def conectar_jira() -> "JiraAPI":
    """Cria (ou reutiliza) uma instância de :class:`JiraAPI` com base no ``st.secrets``."""

    raiz = st.secrets
    config = raiz.get("JIRA") if isinstance(raiz.get("JIRA"), dict) else {}

    def _buscar_chave(chaves: List[str]) -> Optional[str]:
        for chave in chaves:
            if chave in config and config[chave]:
                return str(config[chave])
            if chave in raiz and raiz[chave]:
                return str(raiz[chave])
        return None

    email = _buscar_chave(["email", "EMAIL", "jira_email", "JIRA_EMAIL", "username", "USERNAME", "user", "USER"])
    token = _buscar_chave(["token", "TOKEN", "api_token", "API_TOKEN", "password", "PASSWORD", "jira_token", "JIRA_TOKEN"])
    url = _buscar_chave(["url", "URL", "jira_url", "JIRA_URL", "server", "SERVER", "server_url", "SERVER_URL", "base_url", "BASE_URL", "host", "HOST"])
    use_ex_api_raw = _buscar_chave(["use_ex_api", "USE_EX_API"])
    cloud_id = _buscar_chave(["cloud_id", "CLOUD_ID"])

    if not email or not token or not url:
        raise RuntimeError("Credenciais do Jira ausentes em st.secrets (email/token/url)")

    use_ex_api = str(use_ex_api_raw).lower() in {"1", "true", "yes", "on"} if use_ex_api_raw is not None else False
    return JiraAPI(email=email, api_token=token, jira_url=url, use_ex_api=use_ex_api, cloud_id=cloud_id)


def get_lista_status(chamados_brutos: List[dict]) -> List[str]:
    """Retorna a lista de status distintos presentes nas issues informadas."""

    status: set[str] = set()
    possui_sem_status = False

    for issue in chamados_brutos:
        fields = issue.get("fields", {}) or {}
        status_info = fields.get("status")
        if isinstance(status_info, dict):
            nome = status_info.get("name")
        elif isinstance(status_info, str):
            nome = status_info
        else:
            nome = None
        if nome:
            status.add(nome)
        else:
            possui_sem_status = True

    if possui_sem_status:
        status.add(DEFAULT_STATUS)

    return sorted(status)


def atualizar_agendamento(cliente: JiraAPI, issue_key: str, nova_data: str) -> Dict[str, Any]:
    """Atualiza o campo customfield_12036 de uma issue."""

    if not issue_key:
        raise ValueError("issue_key é obrigatório")
    if not nova_data:
        raise ValueError("nova_data é obrigatória")
    return cliente.atualizar_campo_issue(issue_key, {"customfield_12036": str(nova_data)})


def transicionar_chamados(cliente: JiraAPI, chaves: List[str], nome_status_destino: str) -> Dict[str, Any]:
    """Move os chamados para o status informado, quando a transição estiver disponível."""

    total = len(chaves)
    sucesso = 0
    falhas: List[Dict[str, Any]] = []

    for chave in chaves:
        try:
            transitions = cliente.get_transitions(chave)
        except Exception as exc:  # pragma: no cover
            falhas.append({"key": chave, "erro": str(exc)})
            continue

        transition_id: Optional[str] = None
        for trans in transitions:
            if str(trans.get("name")).strip().lower() == nome_status_destino.strip().lower():
                transition_id = str(trans.get("id"))
                break

        if not transition_id:
            falhas.append({"key": chave, "erro": "Transição não encontrada"})
            continue

        try:
            resp = cliente.transicionar_status(chave, transition_id)
            if resp.status_code in {200, 204}:
                sucesso += 1
            else:
                falhas.append(
                    {
                        "key": chave,
                        "erro": f"Status HTTP {resp.status_code}",
                        "detalhe": _safe_json(resp),
                    }
                )
        except requests.RequestException as exc:  # pragma: no cover
            falhas.append({"key": chave, "erro": str(exc)})

    return {"total": total, "sucesso": sucesso, "falhas": falhas, "destino": nome_status_destino}


def atualizar_agendamento_lote(cliente: JiraAPI, chaves: List[str], nova_data: str) -> Dict[str, Any]:
    """Atualiza o campo de agendamento de todas as issues informadas."""

    if not nova_data:
        raise ValueError("nova_data é obrigatória")

    total = len(chaves)
    sucesso = 0
    falhas: List[Dict[str, Any]] = []

    for chave in chaves:
        try:
            cliente.atualizar_campo_issue(chave, {"customfield_12036": str(nova_data)})
            sucesso += 1
        except Exception as exc:  # pragma: no cover
            falhas.append({"key": chave, "erro": str(exc)})

    return {"total": total, "sucesso": sucesso, "falhas": falhas, "data": nova_data}


def analisar_historico(issue: Dict[str, Any]) -> str:
    """Analisa o changelog para sinalizar reaberturas ou paradas prolongadas."""

    changelog = issue.get("changelog") or {}
    histories = changelog.get("histories") or []

    if not histories:
        return ""

    final_status = {
        "Resolvido",
        "Resolvida",
        "Fechado",
        "Fechada",
        "Encerrado",
        "Encerrada",
        "Closed",
        "Resolved",
        "Done",
    }

    reaberto = False
    ultima_transicao_dt: Optional[pd.Timestamp] = None

    for history in histories:
        created = history.get("created")
        dt = pd.to_datetime(created, utc=True, errors="coerce")
        for item in history.get("items", []) or []:
            if str(item.get("field")).lower() != "status":
                continue
            origem = (item.get("fromString") or "").strip()
            destino = (item.get("toString") or "").strip()
            if origem and destino and origem in final_status and destino not in final_status:
                reaberto = True
            if dt is not None and not pd.isna(dt):
                if ultima_transicao_dt is None or dt > ultima_transicao_dt:
                    ultima_transicao_dt = dt

    alertas: List[str] = []
    if reaberto:
        alertas.append("🔄 Reaberto")

    if ultima_transicao_dt is not None and not pd.isna(ultima_transicao_dt):
        agora = pd.Timestamp.now(tz="UTC")
        dias = (agora - ultima_transicao_dt).days
        if dias > 10:
            alertas.append("⏳ Parado")

    return " ".join(alertas)

