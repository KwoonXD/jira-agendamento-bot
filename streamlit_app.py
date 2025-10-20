import streamlit as st; st.set_page_config(page_title="🤖 Agenda Field Service", page_icon="🤖", layout="wide")
import pandas as pd
from datetime import datetime, date
from typing import Any, Dict, List

try:
    from utils import jira_api as jira  # type: ignore
except Exception as exc:  # pragma: no cover - fallback para depurações locais
    raise RuntimeError("Não foi possível importar utils.jira_api") from exc


def _parse_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%d/%m/%Y"):
            try:
                return datetime.strptime(value[: len(fmt)], fmt).date()
            except ValueError:
                continue
    return None


@st.cache_data(ttl=600, hash_funcs={jira.JiraAPI: lambda _: "jira_api_client"})
def carregar_chamados(cliente: "jira.JiraAPI", jql: str) -> List[Dict[str, Any]]:
    return jira.buscar_chamados_brutos(cliente, jql)


@st.cache_data(ttl=600)
def preparar_dados(chamados_brutos: List[Dict[str, Any]]) -> Dict[str, Any]:
    agrupados = jira.agrupar_chamados_por_tecnico(chamados_brutos)
    tecnicos = sorted(jira.get_lista_tecnicos(chamados_brutos))
    status = sorted(jira.get_lista_status(chamados_brutos))

    df = pd.DataFrame(chamados_brutos)
    if not df.empty:
        if "key" not in df.columns:
            if "issue_key" in df.columns:
                df["key"] = df["issue_key"]
            else:
                df["key"] = [registro.get("key") if isinstance(registro, dict) else None for registro in chamados_brutos]
        if "data_agendada" in df.columns:
            df["data_agendada"] = pd.to_datetime(df["data_agendada"], errors="coerce").dt.date
        else:
            df["data_agendada"] = None
        if "created" in df.columns:
            df["created"] = pd.to_datetime(df["created"], errors="coerce")
        if "tecnico" not in df.columns:
            df["tecnico"] = df.get("responsavel")
    else:
        df = pd.DataFrame(columns=["key", "status", "tecnico", "data_agendada", "created"])

    return {
        "agrupados": agrupados,
        "tecnicos": tecnicos,
        "status": status,
        "dataframe": df,
    }


def aplicar_filtros(df: pd.DataFrame, tecnico_sel: str, status_sel: List[str], data_ini: date | None, data_fim: date | None) -> pd.DataFrame:
    filtrado = df.copy()

    if status_sel and "status" in filtrado.columns:
        filtrado = filtrado[filtrado["status"].isin(status_sel)]
    if tecnico_sel and tecnico_sel != "Todos" and "tecnico" in filtrado.columns:
        filtrado = filtrado[filtrado["tecnico"] == tecnico_sel]
    if "data_agendada" in filtrado.columns:
        if data_ini:
            filtrado = filtrado[filtrado["data_agendada"].fillna(date.min) >= data_ini]
        if data_fim:
            filtrado = filtrado[filtrado["data_agendada"].fillna(date.max) <= data_fim]

    return filtrado


def calcular_metricas(df: pd.DataFrame) -> Dict[str, Any]:
    total = len(df)
    tecnicos_unicos = df["tecnico"].dropna().nunique() if "tecnico" in df.columns else 0

    media_dias = None
    if "created" in df.columns and not df["created"].isna().all():
        dias_abertos = (pd.Timestamp.utcnow() - df["created"]).dt.days
        media_dias = float(dias_abertos.mean()) if not dias_abertos.empty else None

    return {
        "total": total,
        "tecnicos": tecnicos_unicos,
        "media_dias": media_dias,
    }


def exibir_visao_geral(df_filtrado: pd.DataFrame):
    metricas = calcular_metricas(df_filtrado)
    col1, col2, col3 = st.columns(3)
    col1.metric("Total de Chamados Filtrados", metricas["total"])
    col2.metric("Técnicos na Seleção", metricas["tecnicos"])
    col3.metric("Média de dias em aberto", f"{metricas['media_dias']:.1f}" if metricas["media_dias"] is not None else "--")

    st.markdown("### Distribuição por Status")
    if not df_filtrado.empty and "status" in df_filtrado.columns:
        st.bar_chart(df_filtrado["status"].value_counts())
    else:
        st.info("Sem dados para exibir o gráfico de status.")

    st.markdown("### Chamados por Técnico")
    if not df_filtrado.empty and "tecnico" in df_filtrado.columns:
        st.bar_chart(df_filtrado["tecnico"].value_counts())
    else:
        st.info("Sem dados para exibir o gráfico por técnico.")


def exibir_por_tecnico(agrupados: Dict[str, List[Dict[str, Any]]], df_filtrado: pd.DataFrame, cliente: "jira.JiraAPI"):
    if df_filtrado.empty:
        st.info("Nenhum chamado encontrado com os filtros atuais.")
        return

    coluna_chave = "key" if "key" in df_filtrado.columns else ("issue_key" if "issue_key" in df_filtrado.columns else None)
    df_keys_filtrados = set(df_filtrado[coluna_chave].dropna().tolist()) if coluna_chave else set()
    for tecnico, chamados in agrupados.items():
        chamados_filtrados = [
            chamado
            for chamado in chamados
            if not df_keys_filtrados
            or chamado.get("key") in df_keys_filtrados
            or chamado.get("issue_key") in df_keys_filtrados
        ]
        if not chamados_filtrados:
            continue

        with st.expander(f"{tecnico} ({len(chamados_filtrados)})", expanded=False):
            df_tecnico = pd.DataFrame(chamados_filtrados)
            st.dataframe(df_tecnico, use_container_width=True)

            for idx, chamado in enumerate(chamados_filtrados):
                issue_key = chamado.get("key") or chamado.get("issue_key") or f"issue_{idx}"
                data_atual = _parse_date(chamado.get("data_agendada")) or date.today()
                col_data, col_botao = st.columns([3, 1])
                nova_data = col_data.date_input(
                    "Nova data",
                    value=data_atual,
                    key=f"data_{tecnico}_{issue_key}",
                    min_value=date.today(),
                )
                if col_botao.button("Salvar", key=f"salvar_{tecnico}_{issue_key}"):
                    with st.status("Agendando chamado...", expanded=True) as status_box:
                        try:
                            jira.atualizar_agendamento(cliente, issue_key, nova_data.isoformat())
                            status_box.update(label="Chamado agendado com sucesso!", state="complete", expanded=False)
                            st.toast(f"Chamado {issue_key} agendado!", icon="✅")
                            st.cache_data.clear()
                            st.experimental_rerun()
                        except Exception as erro:  # pragma: no cover
                            status_box.update(label=f"Erro ao agendar: {erro}", state="error")


def exibir_todos(df_filtrado: pd.DataFrame):
    st.dataframe(df_filtrado, use_container_width=True)


def main() -> None:
    st.sidebar.title("Filtros")

    cliente = jira.conectar_jira()

    jql_default = st.secrets.get("JQL_CHAMADOS", "project = FSA ORDER BY updated DESC")
    jql_query = st.sidebar.text_area("JQL", jql_default, height=100)

    if st.sidebar.button("Limpar Cache e Recarregar"):
        st.cache_data.clear()
        st.cache_resource.clear()
        st.experimental_rerun()

    chamados_brutos = carregar_chamados(cliente, jql_query)
    dados = preparar_dados(chamados_brutos)

    status_opcoes = dados["status"]
    tecnico_opcoes = ["Todos"] + dados["tecnicos"]

    status_sel = st.sidebar.multiselect("Status", options=status_opcoes, default=status_opcoes)
    tecnico_sel = st.sidebar.selectbox("Técnico", options=tecnico_opcoes, index=0)

    df_base = dados["dataframe"].copy()

    datas_validas = df_base["data_agendada"].dropna() if "data_agendada" in df_base.columns else pd.Series(dtype="datetime64[ns]")
    data_min = datas_validas.min() if not datas_validas.empty else date.today()
    data_max = datas_validas.max() if not datas_validas.empty else date.today()

    data_inicio = st.sidebar.date_input("Agendados de", value=data_min)
    data_fim = st.sidebar.date_input("Agendados até", value=data_max if data_max >= data_min else data_min)

    df_filtrado = aplicar_filtros(
        df_base,
        tecnico_sel,
        status_sel,
        _parse_date(data_inicio),
        _parse_date(data_fim),
    )

    aba_overview, aba_tecnicos, aba_todos = st.tabs([
        "📊 Visão Geral",
        "👨‍💻 Por Técnico",
        "📋 Todos os Chamados",
    ])

    with aba_overview:
        exibir_visao_geral(df_filtrado)

    with aba_tecnicos:
        exibir_por_tecnico(dados["agrupados"], df_filtrado, cliente)

    with aba_todos:
        exibir_todos(df_filtrado)


if __name__ == "__main__":
    main()
