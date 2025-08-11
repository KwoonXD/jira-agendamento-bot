    # --- Operacional extra ---

    def add_comment(self, issue_key: str, body: str):
        url = f"{self.jira_url}/rest/api/3/issue/{issue_key}/comment"
        payload = {"body": body}
        return requests.post(url, headers=self.headers, auth=self.auth, json=payload)

    def set_assignee(self, issue_key: str, account_id: str = None, email: str = None):
        """
        Atribui issue. Recomendado usar accountId.
        Se passar email, Jira Cloud precisa que você habilite 'user picker by email'.
        """
        url = f"{self.jira_url}/rest/api/3/issue/{issue_key}/assignee"
        if account_id:
            payload = {"accountId": account_id}
        elif email:
            payload = {"emailAddress": email}
        else:
            payload = {"accountId": None}  # desatribuir
        return requests.put(url, headers=self.headers, auth=self.auth, json=payload)

    def transition_by_name(self, issue_key: str, to_name_contains: str, fields: dict | None = None):
        """Procura a transição pelo nome de destino (contains, case-insensitive) e executa."""
        trans = self.get_transitions(issue_key)
        target = next((t for t in trans if to_name_contains.lower() in t.get("to", {}).get("name", "").lower()), None)
        if not target:
            return None
        return self.transicionar_status(issue_key, target["id"], fields=fields)
