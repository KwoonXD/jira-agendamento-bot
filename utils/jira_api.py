import requests
from requests.auth import HTTPBasicAuth


class JiraAPI:
    """
    Cliente mínimo para Jira Cloud (API v3).
    """
    def __init__(self, url: str, email: str, token: str):
        self.url = url.rstrip("/")
        self.auth = HTTPBasicAuth(email, token)
        self.headers = {"Accept": "application/json"}

    # ———— baixo nível ————
    def _get(self, path: str, params: dict | None = None) -> dict:
        resp = requests.get(
            f"{self.url}{path}",
            headers=self.headers,
            auth=self.auth,
            params=params,
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json()

    # ———— alto nível ————
    def buscar_chamados(self, jql: str, fields: list[str], max_results: int = 200) -> list[dict]:
        data = self._get(
            "/rest/api/3/search",
            params={
                "jql": jql,
                "fields": ",".join(fields),
                "maxResults": max_results,
            },
        )
        return data.get("issues", [])

    def normalizar(self, issue: dict) -> dict:
        """
        Converte a issue crua numa estrutura plana e resiliente.
        Ajuste os customfield_* conforme o seu Jira.
        """
        f = issue.get("fields", {}) or {}

        def _val(path, default="--"):
            cur = f
            for p in path.split("."):
                cur = (cur or {}).get(p)
            return cur if (cur is not None and cur != "") else default

        # Campos customizados (troque se precisar)
        loja = _val("customfield_14954.value", "Loja")
        pdv = _val("customfield_14829", "--")
        ativo = _val("customfield_14825.value", "--")
        problema = _val("customfield_12374", "--")
        endereco = _val("customfield_12271", "--")
        estado = _val("customfield_11948.value", "--")
        cep = _val("customfield_11993", "--")
        cidade = _val("customfield_11994", "--")
        dataag = f.get("customfield_12036")  # ISO 8601 ou None

        # Heurísticas
        has_spare = any(s in (str(problema).upper() + " " + str(ativo).upper())
                        for s in ("SPARE", "PEÇA", "PECA", "PEÇAS"))
        # chave de duplicidade
        dup_key = (str(pdv).strip(), str(ativo).strip())

        return {
            "key": issue.get("key"),
            "status": (f.get("status") or {}).get("name", "--"),
            "loja": loja,
            "pdv": pdv,
            "ativo": ativo,
            "problema": problema,
            "endereco": endereco,
            "estado": estado,
            "cep": cep,
            "cidade": cidade,
            "data_agendada": dataag,
            "has_spare": bool(has_spare),
            "dup_key": dup_key,
        }
