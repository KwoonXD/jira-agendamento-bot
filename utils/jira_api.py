# utils/jira_api.py
import base64
import json
import streamlit as st
import requests
from requests.auth import HTTPBasicAuth
from collections import defaultdict
from typing import Tuple, Dict, Any, Optional, List


DEFAULT_TECNICO = "Sem técnico definido"
DEFAULT_STATUS = "--"


class JiraAPI:
    """
    Suporta dois modos:
      • Domínio: https://<site>.atlassian.net/rest/api/3/...
      • EX API : https://api.atlassian.com/ex/jira/{cloudId}/rest/api/3/...

    Para tokens fine-grained/OAuth, use EX API (use_ex_api=True) + cloud_id.
    Endpoints usados:
      - POST /rest/api/3/jql/parse
      - POST /rest/api/3/search/approximate-count
      - POST /rest/api/3/search/jql (enhanced search, com paginação via nextPageToken)
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

    # ---------- base & headers ----------
    def _base(self) -> str:
        if self.use_ex_api:
            if not self.cloud_id:
                raise ValueError("cloud_id é obrigatório quando use_ex_api=True")
            return f"https://api.atlassian.com/ex/jira/{self.cloud_id}/rest/api/3"
        return f"{self.jira_url}/rest/api/3"

    def _auth_headers(self, json_content: bool = False) -> Dict[str, str]:
        """Na EX API a autenticação é via header Basic manual."""
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

    def parse_jql(self, jql: str) -> Dict[str, Any]:
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

    # ---------- busca principal (ENHANCED) ----------
    def buscar_chamados_enhanced(self, jql: str, fields: str | List[str], page_size: int = 100, reconcile: bool = False) -> Tuple[List[dict], Dict[str, Any]]:
        """
        POST /search/jql com body JSON (jql, fields, maxResults) + paginação via nextPageToken.
        Retorna (issues, debug_dict)
        """
        base = self._base()
        url = f"{base}/search/jql"

        if isinstance(fields, str):
            fields_list = [f.strip() for f in fields.split(",") if f.strip()]
        else:
            fields_list = list(fields or [])

        issues: List[dict] = []
        next_page_token: Optional[str] = None
        last_resp = {}

        while True:
            body = {
                "jql": jql,
                "maxResults": int(page_size),
                "fields": fields_list
            }
            if reconcile:
                body["reconcileIssues"] = []
            if next_page_token:
                body["nextPageToken"] = next_page_token

            try:
                r = self._req("POST", url, json_body=body)
                if r.status_code != 200:
                    err = _safe_json(r)
                    self._set_debug(url, {"method": "POST", **body}, r.status_code, err, 0, "POST")
                    return [], {"url": url, "params": body, "status": r.status_code, "error": err, "count": 0, "method": "POST"}

                data = r.json()
                batch = data.get("issues", [])
                issues.extend(batch)
                next_page_token = data.get("nextPageToken")
                last_resp = {"url": url, "params": body, "status": 200, "count": len(batch), "method": "POST"}

                if not next_page_token:
                    break
            except requests.RequestException as e:
                self._set_debug(url, {"method": "POST", **body}, -1, str(e), 0, "POST")
                return [], {"url": url, "params": body, "status": -1, "error": str(e), "count": 0, "method": "POST"}

        self._set_debug(url, last_resp.get("params"), last_resp.get("status", 200), None, len(issues), "POST")
        return issues, {"url": url, "status": 200, "count": len(issues), "method": "POST"}

    # ---------- transições / leitura ----------
    def agrupar_chamados(self, issues: list) -> dict:
        """Agrupa os chamados por loja utilizando ``customfield_14954`` como chave."""

        def _extrair_loja(valor: Any) -> Tuple[str, str]:
            codigo: Optional[str] = None
            nome: Optional[str] = None

            if isinstance(valor, dict):
                codigo = valor.get("value") or valor.get("id") or valor.get("key") or valor.get("code")
                nome = valor.get("label") or valor.get("name") or valor.get("displayName")

                if not codigo and isinstance(valor.get("stringValue"), str):
                    codigo = valor["stringValue"].strip()

                for chave in ("child", "children", "parent"):
                    nested = valor.get(chave)
                    if nested is not None:
                        codigo_nested, nome_nested = _extrair_loja(nested)
                        codigo = codigo or codigo_nested
                        nome = nome or nome_nested

            elif isinstance(valor, list):
                for item in valor:
                    codigo_item, nome_item = _extrair_loja(item)
                    codigo = codigo or codigo_item
                    nome = nome or nome_item
                    if codigo and nome:
                        break

            elif isinstance(valor, str):
                texto = valor.strip()
                if texto:
                    if " - " in texto:
                        possivel_codigo, possivel_nome = texto.split(" - ", 1)
                        codigo = possivel_codigo.strip() or codigo
                        nome = possivel_nome.strip() or nome
                    else:
                        codigo = codigo or texto
                        nome = nome or texto

            codigo_padrao = (codigo or nome or "Loja Desconhecida").strip()
            nome_padrao = (nome or codigo_padrao).strip()
            return codigo_padrao, nome_padrao

        def _extrair_tecnico(fields: Dict[str, Any]) -> Tuple[str, Optional[str]]:
            for chave in ("responsavel", "assignee"):
                responsavel = fields.get(chave)
                if isinstance(responsavel, dict):
                    nome = (
                        responsavel.get("displayName")
                        or responsavel.get("name")
                        or responsavel.get("emailAddress")
                    )
                    if nome:
                        account_id = responsavel.get("accountId")
                        return str(nome).strip(), str(account_id).strip() if account_id else None
                elif isinstance(responsavel, str) and responsavel.strip():
                    return responsavel.strip(), None
            return DEFAULT_TECNICO, None

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
                return str(valor.get("value") or valor.get("label") or valor.get("name") or "--").strip() or "--"
            if isinstance(valor, list):
                return ", ".join(str(item.get("value") if isinstance(item, dict) else item) for item in valor if item) or "--"
            if valor is None:
                return "--"
            return str(valor).strip() or "--"

        agrupado: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

        for issue in issues:
            fields = issue.get("fields", {}) or {}

            loja_codigo, loja_nome = _extrair_loja(fields.get("customfield_14954"))
            tecnico_nome, tecnico_account = _extrair_tecnico(fields)
            status_nome = _extrair_status(fields)

            agrupado[loja_codigo].append(
                {
                    "key": issue.get("key"),
                    "status": status_nome,
                    "tecnico": tecnico_nome or DEFAULT_TECNICO,
                    "tecnico_account_id": tecnico_account,
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
                }
            )

        return dict(agrupado)

    def atualizar_campo_issue(self, issue_key: str, fields: Dict[str, Any]) -> Dict[str, Any]:
        """Atualiza campos de uma issue no Jira."""

        url = f"{self._base()}/issue/{issue_key}"
        payload = {"fields": fields}

        try:
            resp = self._req("PUT", url, json_body=payload)
        except requests.RequestException as exc:  # pragma: no cover - propagação
            raise RuntimeError(f"Erro ao atualizar issue {issue_key}: {exc}") from exc

        if resp.status_code not in {200, 204}:
            conteudo = _safe_json(resp)
            raise RuntimeError(
                f"Falha ao atualizar issue {issue_key}: {resp.status_code} - {conteudo}"
            )

        if resp.content:
            try:
                return resp.json()
            except ValueError:  # pragma: no cover - resposta sem JSON
                return {"raw": resp.text}

        return {}

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


@st.cache_resource(show_spinner=False)
def conectar_jira() -> "JiraAPI":
    """Retorna uma instância compartilhada de :class:`JiraAPI` usando ``st.secrets``."""

    def _buscar_chave(chaves: List[str]) -> Optional[str]:
        for chave in chaves:
            if isinstance(config, dict) and chave in config and config[chave]:
                return str(config[chave])
            if chave in raiz and raiz[chave]:
                return str(raiz[chave])
        return None

    raiz = st.secrets
    config_raw = raiz.get("JIRA")
    config = config_raw if isinstance(config_raw, dict) else {}

    email = _buscar_chave([
        "email",
        "EMAIL",
        "jira_email",
        "JIRA_EMAIL",
        "username",
        "USERNAME",
        "user",
        "USER",
    ])
    token = _buscar_chave([
        "token",
        "TOKEN",
        "api_token",
        "API_TOKEN",
        "password",
        "PASSWORD",
        "jira_token",
        "JIRA_TOKEN",
    ])
    url = _buscar_chave([
        "url",
        "URL",
        "jira_url",
        "JIRA_URL",
        "server",
        "SERVER",
        "server_url",
        "SERVER_URL",
        "base_url",
        "BASE_URL",
        "host",
        "HOST",
    ])
    use_ex_api_raw = _buscar_chave(["use_ex_api", "USE_EX_API"])
    cloud_id = _buscar_chave(["cloud_id", "CLOUD_ID"])

    if not email or not token or not url:
        raise RuntimeError("Credenciais do Jira ausentes em st.secrets (email/token/url)")

    use_ex_api = str(use_ex_api_raw).lower() in {"1", "true", "yes", "on"} if use_ex_api_raw is not None else False

    return JiraAPI(
        email=email,
        api_token=token,
        jira_url=url,
        use_ex_api=use_ex_api,
        cloud_id=cloud_id,
    )


def get_lista_tecnicos(chamados_brutos: List[dict]) -> Dict[str, Optional[str]]:
    """Retorna um dicionário ``displayName`` → ``accountId`` apenas para usuários válidos."""

    tecnicos: Dict[str, Optional[str]] = {"Ninguém": None}

    for issue in chamados_brutos:
        fields = issue.get("fields", {}) or {}
        for chave in ("responsavel", "assignee"):
            responsavel = fields.get(chave)
            if isinstance(responsavel, dict):
                nome = responsavel.get("displayName")
                account_id = responsavel.get("accountId")
                if nome and account_id:
                    nome_norm = str(nome).strip()
                    conta_norm = str(account_id).strip()
                    if nome_norm and conta_norm and nome_norm not in tecnicos:
                        tecnicos[nome_norm] = conta_norm
                break

    ordenados = {"Ninguém": None}
    for nome in sorted((n for n in tecnicos if n != "Ninguém"), key=str.casefold):
        ordenados[nome] = tecnicos[nome]
    return ordenados


def get_lista_status(chamados_brutos: List[dict]) -> List[str]:
    """Retorna a lista de status presentes nos chamados."""

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


def atualizar_agendamento(cliente: "JiraAPI", issue_key: str, nova_data: str) -> Dict[str, Any]:
    """Atualiza o campo de agendamento (`customfield_12036`) de uma issue."""

    if not isinstance(cliente, JiraAPI):
        raise TypeError("cliente deve ser uma instância de JiraAPI")

    if not issue_key:
        raise ValueError("issue_key é obrigatório")

    if not nova_data:
        raise ValueError("nova_data é obrigatória")

    return cliente.atualizar_campo_issue(issue_key, {"customfield_12036": str(nova_data)})


def atribuir_tecnico(cliente: "JiraAPI", issue_key: str, account_id: Optional[str]) -> Dict[str, Any]:
    """Atualiza o responsável (`assignee`) de uma issue."""

    if not isinstance(cliente, JiraAPI):
        raise TypeError("cliente deve ser uma instância de JiraAPI")

    if not issue_key:
        raise ValueError("issue_key é obrigatório")

    payload = {"assignee": {"accountId": account_id}} if account_id else {"assignee": None}
    return cliente.atualizar_campo_issue(issue_key, payload)
