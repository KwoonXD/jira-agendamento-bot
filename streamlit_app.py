import streamlit as st; st.set_page_config(page_title="🤖 Agenda Field Service", page_icon="🤖", layout="wide")
import pandas as pd
from datetime import datetime, time
from typing import Any, Dict, Iterable, List, Optional

try:
    import pyperclip
except Exception:  # pragma: no cover - fallback em ambientes sem clipboard
    pyperclip = None

try:
    from streamlit_calendar import calendar
except Exception as exc:  # pragma: no cover - feedback em runtime
    calendar = None  # type: ignore

from utils import jira_api as jira
from utils.messages import (
    TEMPLATES_DISPONIVEIS,
    gerar_mensagem,
)

CAMPOS_JIRA: List[str] = [
    "status",
    "summary",
    "created",
    "customfield_14829",  # PDV
    "customfield_14825",  # Ativo
    "customfield_12374",  # Problema
    "customfield_12271",  # Endereço
    "customfield_11948",  # Estado
    "customfield_11993",  # CEP
    "customfield_11994",  # Cidade
    "customfield_12036",  # Data agendada
    "customfield_14954",  # Loja
]

STATUS_DESTINO_TEC_CAMPO = "TEC-CAMPO"


@st.cache_data(ttl=600, hash_funcs={jira.JiraAPI: lambda _: "jira_client"})
def carregar_chamados(cliente: "jira.JiraAPI", jql: str) -> List[Dict[str, Any]]:
    issues, _ = cliente.buscar_chamados_enhanced(jql, fields=CAMPOS_JIRA)
    return issues


def _deduplicar_chamados(*listas: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    vistos: Dict[str, Dict[str, Any]] = {}
    for lista in listas:
        for issue in lista:
            chave = issue.get("key") or issue.get("id") or issue.get("self")
            if chave and chave not in vistos:
                vistos[chave] = issue
    return list(vistos.values())


def _filtrar_por_busca(chamados: List[Dict[str, Any]], termo: str) -> List[Dict[str, Any]]:
    if not termo:
        return chamados

    termo_norm = termo.strip().lower()
    if not termo_norm:
        return chamados

    filtrados: List[Dict[str, Any]] = []
    for issue in chamados:
        fields = issue.get("fields", {}) or {}
        loja_valor = fields.get("customfield_14954")
        loja_texto = ""
        if isinstance(loja_valor, dict):
            loja_texto = " ".join(
                str(loja_valor.get(chave) or "")
                for chave in ("value", "label", "name", "displayName", "text")
            )
        elif isinstance(loja_valor, str):
            loja_texto = loja_valor

        candidatos = [
            issue.get("key", ""),
            fields.get("summary", ""),
            fields.get("customfield_14829", ""),
            fields.get("customfield_12374", ""),
            fields.get("customfield_12036", ""),
            loja_texto,
        ]
        if any(termo_norm in str(valor).lower() for valor in candidatos if valor):
            filtrados.append(issue)
    return filtrados


def _flatten_agrupado(agrupado: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    chamados: List[Dict[str, Any]] = []
    for lista in agrupado.values():
        chamados.extend(lista)
    return chamados


def _formatar_data_agendada(valor: Any) -> str:
    if not valor:
        return "--"
    serie = pd.to_datetime(pd.Series([valor]), errors="coerce", utc=True)
    dt = serie.iloc[0]
    if pd.isna(dt):
        return "--"
    return dt.tz_convert("America/Sao_Paulo").strftime("%d/%m/%Y %H:%M") if dt.tzinfo else dt.strftime("%d/%m/%Y %H:%M")


def _icone_idade(created: Any) -> str:
    if not created:
        return "⚪"
    dt = pd.to_datetime(created, utc=True, errors="coerce")
    if pd.isna(dt):
        return "⚪"
    agora = pd.Timestamp.now(tz="UTC")
    dias = (agora - dt).days
    if dias >= 5:
        return "🔴"
    if dias >= 2:
        return "🟡"
    return "🟢"


def _idade_dias(created: Any) -> Optional[int]:
    if not created:
        return None
    dt = pd.to_datetime(created, utc=True, errors="coerce")
    if pd.isna(dt):
        return None
    agora = pd.Timestamp.now(tz="UTC")
    return (agora - dt).days


def montar_dataframe_chamados(chamados: List[Dict[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(chamados)
    if df.empty:
        return df

    df["Prioridade"] = df["created"].apply(_icone_idade)
    df["Idade (dias)"] = df["created"].apply(_idade_dias)
    df["Criado em"] = pd.to_datetime(df["created"], errors="coerce", utc=True).dt.tz_convert("America/Sao_Paulo").dt.strftime("%d/%m/%Y %H:%M")
    df["Agendado para"] = df["data_agendada"].apply(_formatar_data_agendada)

    colunas = [
        "Prioridade",
        "Idade (dias)",
        "key",
        "status",
        "loja_codigo",
        "loja",
        "pdv",
        "ativo",
        "problema",
        "Agendado para",
        "Criado em",
        "resumo",
        "endereco",
        "estado",
        "cidade",
        "cep",
    ]

    existentes = [col for col in colunas if col in df.columns]
    restantes = [col for col in df.columns if col not in existentes]
    df = df[existentes + restantes]
    return df


def _renderizar_lojas(
    cliente: "jira.JiraAPI",
    chamados: List[Dict[str, Any]],
    spare_keys: set[str],
    termo_busca: str,
    chave_status: str,
) -> None:
    chamados_filtrados = _filtrar_por_busca(chamados, termo_busca)
    agrupados = cliente.agrupar_chamados(chamados_filtrados)

    if not agrupados:
        st.info("Nenhum chamado encontrado com os filtros atuais.")
        return

    for loja_codigo in sorted(agrupados.keys(), key=str.casefold):
        chamados_loja = agrupados[loja_codigo]
        if not chamados_loja:
            continue

        loja_nome = chamados_loja[0].get("loja")
        descricao_loja = loja_nome or loja_codigo
        if loja_nome and loja_nome != loja_codigo:
            descricao_loja = f"{loja_codigo} — {loja_nome}"

        aguardando_spare = [ch for ch in chamados_loja if ch.get("key") in spare_keys]
        header = f"{descricao_loja} ({len(chamados_loja)})"
        with st.expander(header, expanded=False):
            if aguardando_spare:
                st.warning(
                    "Chamados aguardando Spare: "
                    + ", ".join(str(ch.get("key")) for ch in aguardando_spare if ch.get("key")),
                    icon="⚠️",
                )

            template_opcoes = list(TEMPLATES_DISPONIVEIS.keys())
            template_label = st.selectbox(
                "Template da mensagem",
                template_opcoes,
                format_func=lambda key: TEMPLATES_DISPONIVEIS[key],
                key=f"template_{chave_status}_{loja_codigo}",
            )

            mensagem = gerar_mensagem(descricao_loja, chamados_loja, template_id=template_label)
            st.code(mensagem, language="markdown")
            st.caption("Copie a mensagem acima antes de confirmar o despacho.")

            col_agenda, col_botao = st.columns([2, 1])
            data_agendada = col_agenda.date_input(
                "Agendar todos para:",
                key=f"data_agendar_{chave_status}_{loja_codigo}",
                format="DD/MM/YYYY",
            )

            if col_botao.button(
                "Agendar Todos para esta Data",
                key=f"btn_agendar_{chave_status}_{loja_codigo}",
            ):
                if not data_agendada:
                    st.warning("Selecione uma data antes de agendar.")
                else:
                    nova_data_iso = datetime.combine(data_agendada, time(hour=8, minute=0)).isoformat()
                    with st.status("Agendando chamados...", expanded=True) as status_box:
                        try:
                            resumo = jira.atualizar_agendamento_lote(
                                cliente,
                                [ch.get("key") for ch in chamados_loja if ch.get("key")],
                                nova_data_iso,
                            )
                            status_box.write(
                                f"Atualizados: {resumo['sucesso']} de {resumo['total']} chamados."
                            )
                            if resumo["falhas"]:
                                status_box.write(f"Falhas: {resumo['falhas']}")
                            status_box.update(label="Agendamento concluído!", state="complete", expanded=False)
                            st.toast("Agendamento atualizado!", icon="✅")
                            st.cache_data.clear()
                            st.rerun()
                        except Exception as erro:  # pragma: no cover - feedback ao usuário
                            status_box.update(label=f"Erro ao agendar: {erro}", state="error")

            if st.button(
                "Copiar Mensagem e Mover para TEC-CAMPO",
                key=f"btn_transicionar_{chave_status}_{loja_codigo}",
            ):
                with st.status("Despachando chamados...", expanded=True) as status_box:
                    if pyperclip:
                        try:
                            pyperclip.copy(mensagem)
                            status_box.write("Mensagem copiada para a área de transferência.")
                        except Exception as erro:  # pragma: no cover
                            status_box.write(f"Não foi possível copiar automaticamente: {erro}")
                    else:
                        status_box.write("Copie manualmente a mensagem exibida acima.")

                    try:
                        resumo = jira.transicionar_chamados(
                            cliente,
                            [ch.get("key") for ch in chamados_loja if ch.get("key")],
                            STATUS_DESTINO_TEC_CAMPO,
                        )
                        status_box.write(
                            f"Movidos: {resumo['sucesso']} de {resumo['total']} chamados para {STATUS_DESTINO_TEC_CAMPO}."
                        )
                        if resumo["falhas"]:
                            status_box.write(f"Falhas: {resumo['falhas']}")
                        status_box.update(label="Despacho concluído!", state="complete", expanded=False)
                        st.toast("Chamados despachados!", icon="✅")
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as erro:  # pragma: no cover
                        status_box.update(label=f"Erro ao transicionar: {erro}", state="error")

            df_loja = montar_dataframe_chamados(chamados_loja)
            if df_loja.empty:
                st.info("Sem dados tabulares para esta loja.")
            else:
                st.dataframe(df_loja, use_container_width=True)


def _renderizar_agenda(cliente: "jira.JiraAPI", chamados: List[Dict[str, Any]]) -> None:
    agrupados = cliente.agrupar_chamados(chamados)
    normalizados = [ch for ch in _flatten_agrupado(agrupados) if ch.get("data_agendada")]

    if not normalizados:
        st.info("Não há chamados com data de agendamento definida.")
        return

    eventos = []
    for chamado in normalizados:
        inicio = pd.to_datetime(chamado["data_agendada"], errors="coerce", utc=True)
        if pd.isna(inicio):
            continue
        fim = inicio + pd.Timedelta(hours=1)
        eventos.append(
            {
                "title": f"{chamado.get('key')} — {chamado.get('loja_codigo')}",
                "start": inicio.isoformat(),
                "end": fim.isoformat(),
            }
        )

    if not eventos:
        st.info("Não foi possível montar eventos válidos para o calendário.")
        return

    if calendar is None:
        st.warning("streamlit-calendar não está disponível. Verifique as dependências.")
        st.json(eventos)
        return

    options = {
        "initialView": "timeGridWeek",
        "locale": "pt-br",
        "slotMinTime": "06:00:00",
        "slotMaxTime": "22:00:00",
        "height": 700,
    }
    calendar(events=eventos, options=options)


def _renderizar_dashboard(cliente: "jira.JiraAPI", chamados: List[Dict[str, Any]]) -> None:
    agrupados = cliente.agrupar_chamados(chamados)
    normalizados = _flatten_agrupado(agrupados)
    if not normalizados:
        st.info("Nenhum dado disponível para o dashboard.")
        return

    df = montar_dataframe_chamados(normalizados)
    if df.empty:
        st.info("Nenhum dado disponível para o dashboard.")
        return

    st.subheader("Distribuição por Status")
    contagem_status = df["status"].value_counts().sort_values(ascending=False)
    st.bar_chart(contagem_status)

    st.subheader("Chamados por Loja")
    contagem_loja = df["loja_codigo"].value_counts().sort_values(ascending=False)
    st.bar_chart(contagem_loja)

    st.subheader("Tendência de Abertura (Created)")
    datas_criacao = (
        pd.to_datetime(df["created"], errors="coerce", utc=True)
        .dt.tz_convert("America/Sao_Paulo")
        .dt.date
    )
    tendencia = datas_criacao.value_counts().sort_index()
    st.line_chart(tendencia)


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

    busca_texto = st.sidebar.text_input("Buscar chamados", placeholder="Chave, loja, PDV, problema...")

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
    todos_chamados = _deduplicar_chamados(
        chamados_pendentes,
        chamados_agendados,
        chamados_teccampo,
        chamados_spare,
    )

    tab_loja, tab_agenda, tab_dashboard = st.tabs([
        "Visão por Loja (Despacho)",
        "🗓️ Agenda",
        "📊 Dashboard",
    ])

    with tab_loja:
        st.subheader("Despacho por Loja")
        secoes = [
            ("Pendente Agendamento", chamados_pendentes),
            ("Agendado", chamados_agendados),
            ("Tec-Campo", chamados_teccampo),
            ("Aguardando Spare", chamados_spare),
        ]
        abas_status = st.tabs([titulo for titulo, _ in secoes])
        for (titulo, lista), aba in zip(secoes, abas_status):
            with aba:
                st.markdown(f"### {titulo}")
                _renderizar_lojas(cliente, lista, spare_keys, busca_texto, titulo)

    with tab_agenda:
        st.subheader("Agenda de Chamados")
        _renderizar_agenda(cliente, [ch for ch in todos_chamados if ch])

    with tab_dashboard:
        st.subheader("Indicadores Gerais")
        _renderizar_dashboard(cliente, [ch for ch in todos_chamados if ch])


if __name__ == "__main__":
    main()

