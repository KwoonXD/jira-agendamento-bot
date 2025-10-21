from __future__ import annotations
import base64
from collections import defaultdict

import requests
from requests.auth import HTTPBasicAuth
DEFAULT_STATUS = "--"

    """Cliente HTTP enxuto para chamadas REST do Jira."""
    def __init__(
        email: str,
        jira_url: str,
        cloud_id: Optional[str] = None,
        self.email = email.strip()
        self.jira_url = jira_url.rstrip("/")
        self.cloud_id = cloud_id
        self.auth = HTTPBasicAuth(self.email, self.api_token)
        self.hdr_accept = {"Accept": "application/json"}
        self.last_status: Optional[int] = None
        self.last_url: Optional[str] = None
        self.last_count: Optional[int] = None
    # -----------------------------------------------------------
    # -----------------------------------------------------------
        if self.use_ex_api:
                raise ValueError("cloud_id é obrigatório quando use_ex_api=True")
        return f"{self.jira_url}/rest/api/3"
    def _auth_headers(self, json_content: bool = False) -> Dict[str, str]:
        if not self.use_ex_api:

        base = {
            "Accept": "application/json",
        if json_content:
        return base
    def _set_debug(
        url: str,
        status: int,
        count: int,
    ) -> None:
        self.last_params = params
        self.last_error = error
        self.last_method = method
    def _req(
        method: str,
        *,
        params: Optional[Dict[str, Any]] = None,
    ) -> requests.Response:
            return requests.request(
                url,
                data=json.dumps(json_body) if json_body is not None else None,
            )
            method,
            headers=self.hdr_json if json_content else self.hdr_accept,
            json=json_body if json_body is not None else None,
        )
    # -----------------------------------------------------------
    # -----------------------------------------------------------
        self,
        fields: str | List[str],
        reconcile: bool = False,
        """Executa o endpoint POST /search/jql com suporte a paginação."""

        # ``/search/jql``. Para manter compatibilidade ampla utilizamos o
        url = f"{self._base()}/search"
            fields_list = [f.strip() for f in fields.split(",") if f.strip()]
            fields_list = list(fields or [])
        expand: List[str] = []
        cleaned_fields: List[str] = []
        for campo in fields_list:
                expand.append("changelog")
                cleaned_fields.append(campo)

        next_page_token: Optional[str] = None

            body: Dict[str, Any] = {
                "maxResults": int(page_size),
            }
            if cleaned_fields:
                body["fields"] = cleaned_fields
            if expand:
                body["expand"] = expand
                body["reconcileIssues"] = []
                body["nextPageToken"] = next_page_token
            try:
                if resp.status_code != 200:
                    self._set_debug(url, body, resp.status_code, err, 0, "POST")
                        "url": url,
                        "status": resp.status_code,
                        "count": 0,
                    }
                data = resp.json()
                issues.extend(batch)
                last_resp = {"url": url, "params": body, "status": 200, "count": len(batch), "method": "POST"}
                if not next_page_token:
            except requests.RequestException as exc:
                return [], {
                    "params": body,
                    "error": str(exc),
                    "method": "POST",

        return issues, {"url": url, "status": 200, "count": len(issues), "method": "POST"}
    def agrupar_chamados(self, issues: List[dict]) -> Dict[str, List[Dict[str, Any]]]:

            codigo: Optional[str] = None

                nonlocal codigo
                    codigo = codigo or str(possivel).strip()
            def _registrar_nome(possivel: Optional[str]) -> None:
                if possivel and str(possivel).strip():

                for chave in ("value", "id", "key", "code", "codigo", "stringValue"):
                for chave in ("label", "name", "displayName", "text", "descricao"):
                for nested_key in ("child", "children", "parent", "values", "options", "childrenValues"):
                    if nested:
                        _registrar_codigo(codigo_nested)
            elif isinstance(valor, list):
                    codigo_nested, nome_nested = _extrair_loja(item)
                    _registrar_nome(nome_nested)
                        break
                texto = valor.strip()
                    if " - " in texto:
                        _registrar_codigo(possivel_codigo)
                    else:
                        _registrar_nome(texto)
            codigo_final = (codigo or nome or "Loja Desconhecida").strip()
            return codigo_final, nome_final
        def _extrair_status(fields: Dict[str, Any]) -> str:
            if isinstance(status_info, dict):
            elif isinstance(status_info, str):
            else:
            return (nome or DEFAULT_STATUS).strip()
        def _extrair_opcao(valor: Any) -> str:
                return (
                        valor.get("value")
                        or valor.get("name")
                        or "--"
                    .strip()
                )
                return ", ".join(
                    for item in valor
                ) or "--"
                return "--"


            fields = issue.get("fields", {}) or {}
            historico_info = analisar_historico(issue)

                {
                    "status": _extrair_status(fields),
                    "pdv": fields.get("customfield_14829", "--"),
                    "problema": fields.get("customfield_12374", "--"),
                    "estado": _extrair_opcao(fields.get("customfield_11948")),
                    "cidade": fields.get("customfield_11994", "--"),
                    "created": fields.get("created"),
                    "loja_codigo": loja_codigo,
                    "dias_no_status": historico_info.get("dias_no_status"),
                }


        url = f"{self._base()}/issue/{issue_key}"

            resp = self._req("PUT", url, json_body=payload)
            raise RuntimeError(f"Erro ao atualizar issue {issue_key}: {exc}") from exc
        if resp.status_code not in {200, 204}:
            raise RuntimeError(
            )
        if resp.content:
                return resp.json()
                return {"raw": resp.text}

        url = f"{self._base()}/issue/{issue_key}/transitions"
            resp = self._req("GET", url, json_content=False)
                return resp.json().get("transitions", [])
            pass

        self, issue_key: str, transition_id: str, fields: Optional[Dict[str, Any]] = None
        url = f"{self._base()}/issue/{issue_key}/transitions"
        if fields:
        return self._req("POST", url, json_body=payload)

    try:
    except Exception:

@st.cache_resource(show_spinner=False)
    """Cria (ou reutiliza) uma instância de :class:`JiraAPI` com base no ``st.secrets``."""
    raiz = st.secrets

        for chave in chaves:
                return str(config[chave])
                return str(raiz[chave])

    token = _buscar_chave(["token", "TOKEN", "api_token", "API_TOKEN", "password", "PASSWORD", "jira_token", "JIRA_TOKEN"])
    use_ex_api_raw = _buscar_chave(["use_ex_api", "USE_EX_API"])

        raise RuntimeError("Credenciais do Jira ausentes em st.secrets (email/token/url)")
    use_ex_api = str(use_ex_api_raw).lower() in {"1", "true", "yes", "on"} if use_ex_api_raw is not None else False

def get_lista_status(chamados_brutos: List[dict]) -> List[str]:

    possui_sem_status = False
    for issue in chamados_brutos:
        status_info = fields.get("status")
            nome = status_info.get("name")
            nome = status_info
            nome = None
            status.add(nome)
            possui_sem_status = True
    if possui_sem_status:


def atualizar_agendamento(cliente: JiraAPI, issue_key: str, nova_data: str) -> Dict[str, Any]:

        raise ValueError("issue_key é obrigatório")
        raise ValueError("nova_data é obrigatória")

def transicionar_chamados(cliente: JiraAPI, chaves: List[str], nome_status_destino: str) -> Dict[str, Any]:

    sucesso = 0

        try:
        except Exception as exc:  # pragma: no cover
            continue
        transition_id: Optional[str] = None
            if str(trans.get("name")).strip().lower() == nome_status_destino.strip().lower():
                break
        if not transition_id:
            continue
        try:
            if resp.status_code in {200, 204}:
            else:
                    {
                        "erro": f"Status HTTP {resp.status_code}",
                    }
        except requests.RequestException as exc:  # pragma: no cover


def atualizar_agendamento_lote(cliente: JiraAPI, chaves: List[str], nova_data: str) -> Dict[str, Any]:

        raise ValueError("nova_data é obrigatória")
    total = len(chaves)
    falhas: List[Dict[str, Any]] = []
    for chave in chaves:
            cliente.atualizar_campo_issue(chave, {"customfield_12036": str(nova_data)})
        except Exception as exc:  # pragma: no cover


def analisar_historico(issue: Dict[str, Any]) -> Dict[str, Any]:

    histories = changelog.get("histories") or []
    if not histories:

        "Resolvido",
        "Fechado",
        "Encerrado",
        "Closed",
        "Done",

        ((issue.get("fields", {}) or {}).get("status", {}) or {}).get("name")
        else (issue.get("fields", {}) or {}).get("status")
    current_status = str(current_status or "").strip()
    histories_sorted = sorted(
        key=lambda item: item.get("created") or "",

    entrada_status_atual: Optional[pd.Timestamp] = None
    for history in histories_sorted:
        dt = pd.to_datetime(created, utc=True, errors="coerce")
            if str(item.get("field")).lower() != "status":
            origem = (item.get("fromString") or "").strip()
            if origem and destino and origem in final_status and destino not in final_status:
            if current_status and destino and destino.lower() == current_status.lower():
                    entrada_status_atual = dt
    if entrada_status_atual is None:
        entrada_status_atual = pd.to_datetime(created, utc=True, errors="coerce")
    dias_no_status: Optional[int] = None
        agora = pd.Timestamp.now(tz="UTC")

    if reaberto:
    if dias_no_status is not None and dias_no_status > 10:

