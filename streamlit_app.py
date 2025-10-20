import streamlit as st; st.set_page_config(page_title="🤖 Agenda Field Service", page_icon="🤖", layout="wide")
import pandas as pd
from collections import defaultdict
from typing import Any, Dict, List, Optional

try:
    from utils import jira_api as jira  # type: ignore
    from utils.messages import gerar_mensagem
except Exception as exc:  # pragma: no cover - fallback para depurações locais
    raise RuntimeError("Não foi possível importar módulos utilitários") from exc


DEFAULT_TECNICO = getattr(jira, "DEFAULT_TECNICO", "Sem técnico definido")
DEFAULT_STATUS = getattr(jira, "DEFAULT_STATUS", "--")

CAMPOS_JIRA: List[str] = [
    "responsavel",
    "assignee",
    "status",
    "summary",
    "customfield_14829",
    "customfield_14825",
    "customfield_12374",
    "customfield_12271",
    "customfield_11948",
    "customfield_11993",
    "customfield_11994",
    "customfield_12036",
    "customfield_14954",
    "created",
]


@st.cache_data(ttl=600, hash_funcs={jira.JiraAPI: lambda _: "jira_api_client"})
def carregar_chamados(cliente: "jira.JiraAPI", jql: str) -> List[Dict[str, Any]]:
    issues, _ = cliente.buscar_chamados_enhanced(jql, fields=CAMPOS_JIRA)
    return issues


def _deduplicar_chamados(*listas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    vistos: Dict[str, Dict[str, Any]] = {}
    for lista in listas:
        for issue in lista:
            chave = issue.get("key")
            if chave and chave not in vistos:
                vistos[chave] = issue
            elif not chave:
                # Mantém itens sem chave única usando ``id`` ou ``self`` como fallback.
                marcador = issue.get("id") or issue.get("self")
                if marcador and marcador not in vistos:
                    vistos[marcador] = issue
    return list(vistos.values())


def _flatten_por_loja(agrupados: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    chamados: List[Dict[str, Any]] = []
    for lista in agrupados.values():
        chamados.extend(lista)
    return chamados


def montar_dataframe_chamados(chamados: List[Dict[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(chamados)
    if df.empty:
        return df

    df = df.drop(columns=["tecnico_account_id"], errors="ignore")

    colunas_prioritarias = [
        "key",
        "status",
        "loja_codigo",
        "loja",
        "pdv",
        "ativo",
        "problema",
        "data_agendada",
        "tecnico",
        "created",
    ]
    existentes = [col for col in colunas_prioritarias if col in df.columns]
    restantes = [col for col in df.columns if col not in existentes]
    df = df[existentes + restantes]

    if "data_agendada" in df.columns:
        df["data_agendada"] = pd.to_datetime(df["data_agendada"], errors="coerce").dt.strftime("%Y-%m-%d")
    if "created" in df.columns:
        df["created"] = pd.to_datetime(df["created"], errors="coerce").dt.strftime("%Y-%m-%d %H:%M")
    return df


def _obter_responsavel(fields: Dict[str, Any]) -> Optional[Any]:
    for chave in ("responsavel", "assignee"):
        responsavel = fields.get(chave)
        if responsavel:
            return responsavel
    return None


def _esta_sem_responsavel(issue: Dict[str, Any]) -> bool:
    fields = issue.get("fields", {}) or {}
    responsavel = _obter_responsavel(fields)

    if not responsavel:
        return True

    if isinstance(responsavel, dict):
        return not any(
            responsavel.get(campo)
            for campo in ("accountId", "displayName", "name", "emailAddress")
        )

    return False


def _obter_status_issue(issue: Dict[str, Any]) -> str:
    fields = issue.get("fields", {}) or {}
    status_info = fields.get("status")
    if isinstance(status_info, dict):
        nome = status_info.get("name")
    elif isinstance(status_info, str):
        nome = status_info
    else:
        nome = None
    return (nome or DEFAULT_STATUS).strip()


def _exibir_lojas(
    cliente: "jira.JiraAPI",
    issues: List[Dict[str, Any]],
    spare_keys: set[str],
) -> None:
    if not issues:
        st.info("Nenhum chamado encontrado com os filtros selecionados.")
        return

    agrupados = cliente.agrupar_chamados(issues)

    for loja_codigo in sorted(agrupados.keys(), key=str.casefold):
        chamados_loja = agrupados[loja_codigo]
        if not chamados_loja:
            continue

        loja_nome = chamados_loja[0].get("loja")
        descricao_loja = loja_nome or loja_codigo
        if loja_nome and loja_nome != loja_codigo:
            descricao_loja = f"{loja_codigo} — {loja_nome}"

        aguardando_spare = [
            chamado for chamado in chamados_loja if chamado.get("key") in spare_keys
        ]

        header = f"{descricao_loja} ({len(chamados_loja)})"
        with st.expander(header, expanded=False):
            if aguardando_spare:
                lista_keys = ", ".join(
                    str(ch.get("key")) for ch in aguardando_spare if ch.get("key")
                )
                st.warning(
                    f"Chamados aguardando Spare: {lista_keys}", icon="⚠️"
                )

            titulo_mensagem = (
                f"{loja_codigo} — {loja_nome}"
                if loja_nome and loja_nome != loja_codigo
                else (loja_nome or loja_codigo)
            )
            mensagem = gerar_mensagem(titulo_mensagem, chamados_loja)
            st.code(mensagem, language="markdown")

            df_loja = montar_dataframe_chamados(chamados_loja)
            if df_loja.empty:
                st.info("Sem dados tabulares para esta loja.")
            else:
                st.dataframe(df_loja, use_container_width=True)


def _renderizar_nao_atribuidos(
    cliente: "jira.JiraAPI",
    chamados: List[Dict[str, Any]],
    mapa_tecnicos: Dict[str, Any],
) -> None:
    if not chamados:
        st.success("Todos os chamados estão atribuídos no momento.")
        return

    normalizados = _flatten_por_loja(cliente.agrupar_chamados(chamados))
    opcoes_tecnicos = list(mapa_tecnicos.keys())
    indice_padrao = 1 if len(opcoes_tecnicos) > 1 else 0

    for chamado in sorted(normalizados, key=lambda c: c.get("created") or ""):
        chave = chamado.get("key") or "--"
        loja_nome = chamado.get("loja")
        loja_codigo = chamado.get("loja_codigo") or loja_nome
        descricao_loja = loja_codigo or loja_nome or "--"
        if loja_nome and loja_codigo and loja_nome != loja_codigo:
            descricao_loja = f"{loja_codigo} — {loja_nome}"
        col_info, col_select, col_botao = st.columns([4, 3, 1])

        col_info.markdown(
            f"**{chave}** — {chamado.get('resumo', '--')}  \n"
            f"Loja: {descricao_loja}  \n"
            f"Status: {chamado.get('status', DEFAULT_STATUS)}"
        )

        selecionado = col_select.selectbox(
            "Técnico",
            opcoes_tecnicos,
            index=indice_padrao,
            key=f"select_tecnico_{chave}",
        )

        if col_botao.button("Atribuir", key=f"atribuir_{chave}"):
            account_id = mapa_tecnicos.get(selecionado)
            with st.status("Atribuindo chamado...", expanded=True) as status_box:
                try:
                    jira.atribuir_tecnico(cliente, chave, account_id)
                    status_box.update(
                        label="Chamado atribuído com sucesso!",
                        state="complete",
                        expanded=False,
                    )
                    st.toast(f"Chamado {chave} atribuído!", icon="✅")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as erro:  # pragma: no cover - feedback ao usuário
                    status_box.update(label=f"Erro ao atribuir: {erro}", state="error")


def _renderizar_atribuidos(
    cliente: "jira.JiraAPI",
    chamados: List[Dict[str, Any]],
) -> None:
    if not chamados:
        st.info("Não há chamados atribuídos nas consultas carregadas.")
        return

    agrupados = cliente.agrupar_chamados(chamados)
    normalizados = _flatten_por_loja(agrupados)

    por_tecnico: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for chamado in normalizados:
        tecnico = chamado.get("tecnico") or DEFAULT_TECNICO
        por_tecnico[tecnico].append(chamado)

    for tecnico in sorted(por_tecnico.keys(), key=str.casefold):
        chamados_tecnico = por_tecnico[tecnico]
        with st.expander(f"{tecnico} ({len(chamados_tecnico)})", expanded=False):
            df_tecnico = montar_dataframe_chamados(chamados_tecnico)
            if df_tecnico.empty:
                st.info("Sem dados para exibir.")
            else:
                st.dataframe(df_tecnico, use_container_width=True)


def main() -> None:
    st.sidebar.title("Configurações")

    cliente = jira.conectar_jira()

    jql_pendentes_default = st.secrets.get(
        "JQL_PENDENTES",
        "project = FSA AND status = \"Pendente\" ORDER BY updated DESC",
    )
    jql_agendados_default = st.secrets.get(
        "JQL_AGENDADOS",
        "project = FSA AND status = \"Agendado\" ORDER BY updated DESC",
    )
    jql_teccampo_default = st.secrets.get(
        "JQL_TEC_CAMPO",
        "project = FSA AND status = \"Tec-Campo\" ORDER BY updated DESC",
    )
    jql_spare_default = st.secrets.get(
        "JQL_SPARE",
        "project = FSA AND \"Aguardando Spare\" = \"Sim\" ORDER BY updated DESC",
    )

    with st.sidebar.expander("Consultas JQL", expanded=False):
        jql_pendentes = st.text_area(
            "Pendentes",
            jql_pendentes_default,
            key="jql_pendentes",
            height=120,
        )
        jql_agendados = st.text_area(
            "Agendados",
            jql_agendados_default,
            key="jql_agendados",
            height=120,
        )
        jql_teccampo = st.text_area(
            "Tec-Campo",
            jql_teccampo_default,
            key="jql_teccampo",
            height=120,
        )
        jql_spare = st.text_area(
            "Spare",
            jql_spare_default,
            key="jql_spare",
            height=120,
        )

    if st.sidebar.button("Limpar Cache e Recarregar"):
        st.cache_data.clear()
        st.cache_resource.clear()
        st.rerun()

    chamados_pendentes = carregar_chamados(cliente, jql_pendentes)
    chamados_agendados = carregar_chamados(cliente, jql_agendados)
    chamados_teccampo = carregar_chamados(cliente, jql_teccampo)
    chamados_spare = carregar_chamados(cliente, jql_spare)

    spare_keys = {issue.get("key") for issue in chamados_spare if issue.get("key")}
    todos_abertos = _deduplicar_chamados(
        chamados_pendentes, chamados_agendados, chamados_teccampo
    )

    tab_loja, tab_tecnico = st.tabs(
        ["Visão por Loja (Despacho)", "Visão por Técnico (Gestão)"]
    )

    with tab_loja:
        st.subheader("Despacho por Loja")

        status_disponiveis = jira.get_lista_status(todos_abertos)
        if status_disponiveis:
            status_selecionados = st.multiselect(
                "Filtrar por Status",
                status_disponiveis,
                default=status_disponiveis,
                key="filtro_status_loja",
            )
            if status_selecionados:
                chamados_filtrados = [
                    issue
                    for issue in todos_abertos
                    if _obter_status_issue(issue) in status_selecionados
                ]
            else:
                chamados_filtrados = []
        else:
            st.info("Nenhum status encontrado nas consultas carregadas.")
            chamados_filtrados = todos_abertos

        _exibir_lojas(cliente, chamados_filtrados, spare_keys)

    with tab_tecnico:
        st.subheader("Gestão por Técnico")

        if not todos_abertos:
            st.info("Nenhum chamado aberto nas consultas carregadas.")
            return

        mapa_tecnicos = jira.get_lista_tecnicos(todos_abertos)

        aba_nao_atr, aba_atr = st.tabs(["Não Atribuídos", "Atribuídos"])

        with aba_nao_atr:
            nao_atribuidos = [
                issue for issue in todos_abertos if _esta_sem_responsavel(issue)
            ]
            _renderizar_nao_atribuidos(cliente, nao_atribuidos, mapa_tecnicos)

        with aba_atr:
            atribuidos = [
                issue for issue in todos_abertos if not _esta_sem_responsavel(issue)
            ]
            _renderizar_atribuidos(cliente, atribuidos)


if __name__ == "__main__":
    main()
