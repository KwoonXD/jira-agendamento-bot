import streamlit as st; st.set_page_config(page_title="🤖 Agenda Field Service", page_icon="🤖", layout="wide")
import pandas as pd
from datetime import datetime, time
from typing import Any, Dict, Iterable, List, Optional, Tuple
import re

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
    verificar_duplicidade,
)

CAMPOS_JIRA: List[str] = [
    "status",
    "summary",
    "description",
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
    "changelog",
]

STATUS_DESTINO_TEC_CAMPO = "TEC-CAMPO"

TEC_LIST_KEY = "tecnicos_df"


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


def _obter_limite_sla(chave: str, padrao: int) -> int:
    try:
        valor = st.session_state.get(chave, padrao)
        inteiro = int(valor)
    except (TypeError, ValueError):
        return padrao
    return max(0, inteiro)


def _filtrar_selecionados(df_editado: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(df_editado, pd.DataFrame) or "Selecionar" not in df_editado.columns:
        return pd.DataFrame(columns=df_editado.columns if isinstance(df_editado, pd.DataFrame) else [])
    mascara = df_editado["Selecionar"].fillna(False)
    return df_editado[mascara.astype(bool)]


def _formatar_data_agendada(valor: Any) -> str:
    if not valor:
        return "--"
    serie = pd.to_datetime(pd.Series([valor]), errors="coerce", utc=True)
    dt = serie.iloc[0]
    if pd.isna(dt):
        return "--"
    return dt.tz_convert("America/Sao_Paulo").strftime("%d/%m/%Y %H:%M") if dt.tzinfo else dt.strftime("%d/%m/%Y %H:%M")


def _slugify_chave(valor: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z]+", "_", valor).strip("_")
    return slug or "sem_identificacao"


# ESTA É A FUNÇÃO CORRIGIDA (VERSÃO ORIGINAL)
def _agrupar_por_data_agendada_raw(
    chamados: List[Dict[str, Any]]
) -> List[Tuple[str, str, List[Dict[str, Any]]]]:
    grupos: Dict[str, Dict[str, Any]] = {}
    for issue in chamados:
        fields = issue.get("fields", {}) or {}
        data = fields.get("customfield_12036")
        dt = pd.to_datetime(data, errors="coerce", utc=True) # Corrigido para usar utc=True
        if pd.isna(dt):
            label = "Sem data definida"
            ordem = None
        else:
            dt_local = dt.tz_convert("America/Sao_Paulo")
            label = dt_local.strftime("%d/%m/%Y")
            ordem = dt_local.date()

        entrada = grupos.setdefault(
            label,
            {"issues": [], "ordem": ordem, "slug": _slugify_chave(label)},
        )
        entrada["issues"].append(issue)
        if entrada.get("ordem") is None and ordem is not None:
            entrada["ordem"] = ordem

    ordenados: List[Tuple[str, str, List[Dict[str, Any]]]] = []
    for label, payload in sorted(
        grupos.items(), key=lambda item: (item[1]["ordem"] is None, item[1]["ordem"] or datetime.max.date())
    ):
        ordenados.append((label, payload.get("slug", _slugify_chave(label)), payload["issues"]))
    return ordenados


def _handle_agendar_lote(
    cliente: "jira.JiraAPI",
    df_editado: pd.DataFrame,
    data_agendada,
    contexto: str,
) -> None:
    selecionados = _filtrar_selecionados(df_editado)
    if selecionados.empty:
        st.error("Selecione ao menos um chamado para agendar.")
        return
    if not data_agendada:
        st.error("Selecione uma data antes de agendar.")
        return

    chaves = [str(chave) for chave in selecionados["key"] if chave]
    if not chaves:
        st.error("Não foi possível identificar as chaves selecionadas.")
        return

    conflitos: List[Dict[str, Any]] = []
    if "data_agendada" in selecionados.columns:
        for _, linha in selecionados.iterrows():
            atual = linha.get("data_agendada")
            if pd.isna(atual) or not atual:
                continue
            atual_dt = pd.to_datetime(atual, errors="coerce")
            if pd.isna(atual_dt):
                continue
            if atual_dt.date() != data_agendada:
                conflitos.append(
                    {
                        "key": str(linha.get("key")),
                        "data": atual_dt.strftime("%d/%m/%Y"),
                    }
                )

    if conflitos:
        conflito_chaves = {item["key"] for item in conflitos if item.get("key")}
        with st.warning(
            "Alguns chamados já possuem data de agendamento diferente. Como deseja proceder?",
            icon="⚠️",
        ):
            for conflito in conflitos:
                st.write(f"{conflito['key']}: {conflito['data']}")
            escolha = st.radio(
                "Opção",
                (
                    "Cancelar",
                    "Sobrescrever datas existentes",
                    "Pular chamados com data diferente",
                ),
                index=0,
                key=f"confirma_agendamento_{contexto}",
            )
        if escolha == "Cancelar":
            st.info("Agendamento cancelado pelo usuário.")
            return
        if escolha == "Pular chamados com data diferente":
            chaves = [ch for ch in chaves if ch not in conflito_chaves]
            if not chaves:
                st.error("Nenhum chamado restante para agendar após ignorar conflitos.")
                return

    nova_data_iso = datetime.combine(data_agendada, time(hour=8, minute=0)).isoformat()
    with st.status("Agendando chamados...", expanded=True) as status_box:
        try:
            resumo = jira.atualizar_agendamento_lote(cliente, chaves, nova_data_iso)
            status_box.write(
                f"Atualizados: {resumo['sucesso']} de {resumo['total']} chamados."
            )
            if resumo["falhas"]:
                for falha in resumo["falhas"]:
                    status_box.write(
                        f"Falha em {falha.get('key')}: {falha.get('erro', 'Motivo não informado')}"
                    )
            status_box.update(label="Agendamento concluído!", state="complete", expanded=False)
            st.toast("Agendamento atualizado!", icon="✅")
            st.cache_data.clear()
            st.rerun()
        except Exception as erro:  # pragma: no cover - feedback ao usuário
            status_box.update(label=f"Erro ao agendar: {erro}", state="error")


def _handle_despachar_mover(
    cliente: "jira.JiraAPI",
    df_editado: pd.DataFrame,
    mensagem: str,
    destino: str,
) -> None:
    selecionados = _filtrar_selecionados(df_editado)
    if selecionados.empty:
        st.error("Selecione ao menos um chamado para despachar.")
        return

    chaves = [str(chave) for chave in selecionados["key"] if chave]
    if not chaves:
        st.error("Não foi possível identificar as chaves selecionadas.")
        return

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
            resumo = jira.transicionar_chamados(cliente, chaves, destino)
            status_box.write(
                f"Movidos: {resumo['sucesso']} de {resumo['total']} chamados para {destino}."
            )
            if resumo["falhas"]:
                for falha in resumo["falhas"]:
                    motivo = falha.get("erro") or falha.get("detalhe") or "Motivo não informado"
                    status_box.write(f"Falha em {falha.get('key')}: {motivo}")
            status_box.update(label="Despacho concluído!", state="complete", expanded=False)
            st.toast("Chamados despachados!", icon="✅")
            st.cache_data.clear()
            st.rerun()
        except Exception as erro:  # pragma: no cover
            status_box.update(label=f"Erro ao transicionar: {erro}", state="error")


def _icone_idade(created: Any) -> str:
    if not created:
        return "⚪"
    dt = pd.to_datetime(created, utc=True, errors="coerce")
    if pd.isna(dt):
        return "⚪"
    agora = pd.Timestamp.now(tz="UTC")
    dias = (agora - dt).days
    amarelo = _obter_limite_sla("sla_amarelo", 3)
    vermelho = _obter_limite_sla("sla_vermelho", 7)
    if vermelho < amarelo:
        vermelho = amarelo
    if dias >= vermelho:
        return "🔴"
    if dias >= amarelo:
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


def _icone_tempo_status(dias: Optional[int]) -> str:
    if dias is None:
        return "⚪"
    amarelo = _obter_limite_sla("sla_amarelo", 3)
    vermelho = _obter_limite_sla("sla_vermelho", 7)
    if vermelho < amarelo:
        vermelho = amarelo
    if dias >= vermelho:
        return "🔴"
    if dias >= amarelo:
        return "🟡"
    return "🟢"


def _formatar_tempo_status(dias: Optional[int]) -> str:
    if dias is None:
        return "--"
    return f"{_icone_tempo_status(dias)} {dias}d"


def _obter_tecnicos_df() -> pd.DataFrame:
    base = st.session_state.get(TEC_LIST_KEY)
    if isinstance(base, pd.DataFrame):
        df = base.copy()
    elif isinstance(base, list):
        df = pd.DataFrame(base)
    elif isinstance(base, dict):
        df = pd.DataFrame([base])
    else:
        df = pd.DataFrame()

    if df.empty:
        df = pd.DataFrame(columns=["Nome", "Contato", "Região"])

    col_map: Dict[str, str] = {}
    for col in list(df.columns):
        chave = str(col).strip().lower()
        if chave in {"nome", "name", "tecnico", "técnico"}:
            col_map[col] = "Nome"
        elif chave in {"contato", "phone", "telefone", "whatsapp"}:
            col_map[col] = "Contato"
        elif chave in {"regiao", "região", "zona", "area", "área"}:
            col_map[col] = "Região"
    if col_map:
        df = df.rename(columns=col_map)

    for coluna in ("Nome", "Contato", "Região"):
        if coluna not in df.columns:
            df[coluna] = ""

    return df


def _opcoes_tecnicos(regiao_alvo: Optional[str]) -> List[Dict[str, Any]]:
    df = _obter_tecnicos_df()
    if df.empty:
        return []

    df = df.fillna("")
    if regiao_alvo and "Região" in df.columns:
        regiao_norm = str(regiao_alvo).strip().lower()
        regioes_series = df["Região"].astype(str).str.strip().str.lower()
        preferidos = df[regioes_series == regiao_norm]
        demais = df[regioes_series != regiao_norm]
        df = pd.concat([preferidos, demais], ignore_index=True)

    opcoes: List[Dict[str, Any]] = []
    vistos = set()
    for _, linha in df.iterrows():
        nome = str(linha.get("Nome", "")).strip()
        if not nome:
            continue
        if nome in vistos:
            continue
        vistos.add(nome)
        opcoes.append(
            {
                "nome": nome,
                "regiao": str(linha.get("Região", "")).strip(),
                "contato": str(linha.get("Contato", "")).strip(),
            }
        )
    return opcoes


def montar_dataframe_chamados(chamados: List[Dict[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(chamados)
    if df.empty:
        return df

    df["Prioridade"] = df["created"].apply(_icone_idade)
    df["Idade (dias)"] = df["created"].apply(_idade_dias)
    df["Criado em"] = pd.to_datetime(df["created"], errors="coerce", utc=True).dt.tz_convert("America/Sao_Paulo").dt.strftime("%d/%m/%Y %H:%M")
    df["Agendado para"] = df["data_agendada"].apply(_formatar_data_agendada)
    if "historico_alerta" in df.columns:
        df["Histórico"] = df["historico_alerta"].fillna("")
    else:
        df["Histórico"] = ""
    if "dias_no_status" in df.columns:
        df["Tempo no Status Atual"] = df["dias_no_status"].apply(_formatar_tempo_status)
    else:
        df["Tempo no Status Atual"] = "--"

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
        "Tempo no Status Atual",
        "Histórico",
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
    modo_compacto: bool = False,
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

            duplicados = verificar_duplicidade(chamados_loja)
            if duplicados:
                descricao_dup = ", ".join(f"PDV {pdv} / Ativo {ativo}" for pdv, ativo in sorted(duplicados))
                st.warning(
                    "Possíveis duplicidades identificadas para esta loja: " + descricao_dup,
                    icon="🚨",
                )

            nota_key = f"nota_{chave_status}_{loja_codigo}"
            if nota_key not in st.session_state:
                st.session_state[nota_key] = ""
            st.text_area(
                "Notas rápidas",
                key=nota_key,
                placeholder="Registre observações importantes desta loja...",
                height=80,
            )
            if st.button("Salvar Nota", key=f"btn_salvar_nota_{chave_status}_{loja_codigo}"):
                st.toast("Nota salva nesta sessão.", icon="💾")

            regiao_key = f"regiao_{loja_codigo}"
            if regiao_key not in st.session_state:
                st.session_state[regiao_key] = ""
            regiao_loja = st.text_input(
                "Região/Zona desta loja",
                key=regiao_key,
                placeholder="Informe para sugerir técnicos automaticamente...",
            )

            opcoes_tecnicos = _opcoes_tecnicos(regiao_loja)
            if opcoes_tecnicos:
                nomes = ["-- Selecionar técnico --"] + [
                    f"{item['nome']}" + (f" — {item['regiao']}" if item["regiao"] else "")
                    for item in opcoes_tecnicos
                ]
                tecnico_key = f"tecnico_externo_{chave_status}_{loja_codigo}"
                selecao = st.selectbox(
                    "Associar Técnico (controle interno)",
                    nomes,
                    key=tecnico_key,
                )
                if selecao != "-- Selecionar técnico --":
                    indice = nomes.index(selecao) - 1
                    if 0 <= indice < len(opcoes_tecnicos):
                        contato = opcoes_tecnicos[indice]["contato"]
                        if contato:
                            st.caption(f"Contato sugerido: {contato}")
            else:
                st.caption("Carregue sua lista de técnicos na aba Configurações para sugestões personalizadas.")

            if modo_compacto:
                datas_criacao = [
                    pd.to_datetime(ch.get("created"), utc=True, errors="coerce")
                    for ch in chamados_loja
                ]
                datas_validas = [dt for dt in datas_criacao if not pd.isna(dt)]
                mais_antigo = min(datas_validas).tz_convert("America/Sao_Paulo") if datas_validas else None
                resumo_status = pd.Series([ch.get("status") for ch in chamados_loja]).value_counts()
                st.markdown(
                    "\n".join(
                        [
                            f"Chamados: **{len(chamados_loja)}**",
                            "Status:" + ", ".join(f" {status} ({qtd})" for status, qtd in resumo_status.items()),
                            (
                                f"Chamado mais antigo: {mais_antigo.strftime('%d/%m/%Y %H:%M') if mais_antigo else '--'}"
                            ),
                        ]
                    )
                )
                st.info("Desative o Modo Compacto para visualizar mensagens e ações em lote.")
                continue

            df_loja = montar_dataframe_chamados(chamados_loja)
            if df_loja.empty:
                st.info("Sem dados tabulares para esta loja.")
                continue

            df_editor = df_loja.copy()
            df_editor.insert(0, "Detalhes", False)
            df_editor.insert(0, "Selecionar", False)
            column_config = {
                "Selecionar": st.column_config.CheckboxColumn(
                    "Selecionar",
                    help="Marque os chamados que deseja incluir nas ações em lote.",
                    default=False,
                ),
                "Detalhes": st.column_config.CheckboxColumn(
                    "👁️ Detalhes",
                    help="Marque para revelar informações completas do chamado abaixo.",
                    default=False,
                ),
            }
            for coluna in df_loja.columns:
                column_config[coluna] = st.column_config.Column(coluna, disabled=True)

            df_editado = st.data_editor(
                df_editor,
                use_container_width=True,
                hide_index=True,
                num_rows="fixed",
                column_config=column_config,
                key=f"editor_{chave_status}_{loja_codigo}",
            )
            if not isinstance(df_editado, pd.DataFrame):
                df_editado = pd.DataFrame(df_editado)

            selecionados_df = _filtrar_selecionados(df_editado)
            selecionados_keys = (
                {str(chave) for chave in selecionados_df["key"].tolist() if chave}
                if not selecionados_df.empty
                else set()
            )
            if selecionados_keys:
                chamados_para_mensagem = [
                    chamado
                    for chamado in chamados_loja
                    if str(chamado.get("key")) in selecionados_keys
                ]
            else:
                chamados_para_mensagem = chamados_loja

            detalhes_marcados = []
            if "Detalhes" in df_editado.columns:
                detalhes_marcados = df_editado[df_editado["Detalhes"].fillna(False)]
            for _, linha in detalhes_marcados.iterrows():
                chave_chamado = linha.get("key")
                registro = next(
                    (item for item in chamados_loja if item.get("key") == chave_chamado),
                    {},
                )
                with st.expander(f"Detalhes do chamado {chave_chamado}", expanded=True):
                    st.markdown(
                        "\n".join(
                            [
                                f"**Resumo:** {registro.get('resumo', '--')}",
                                f"**Problema:** {registro.get('problema', '--')}",
                                f"**Endereço:** {registro.get('endereco', '--')} - {registro.get('cidade', '--')} / {registro.get('estado', '--')}",
                                f"**CEP:** {registro.get('cep', '--')}",
                                f"**Tempo no status:** {linha.get('Tempo no Status Atual', '--')}",
                                f"**Histórico:** {registro.get('historico_alerta', '--')}",
                                (f"**Descrição completa:**\n{registro.get('descricao_completa')}" if registro.get('descricao_completa') else ""),
                            ]
                        )
                    )

            template_opcoes = list(TEMPLATES_DISPONIVEIS.keys())
            template_label = st.selectbox(
                "Template da mensagem",
                template_opcoes,
                format_func=lambda key: TEMPLATES_DISPONIVEIS[key],
                key=f"template_{chave_status}_{loja_codigo}",
            )

            mensagem = gerar_mensagem(
                descricao_loja,
                chamados_para_mensagem,
                template_id=template_label,
            )
            st.code(mensagem, language="markdown")
            st.caption("Copie a mensagem acima antes de confirmar o despacho.")

            col_agenda, col_agendar, col_despachar = st.columns([2, 1, 1])
            data_agendada = col_agenda.date_input(
                "Agendar selecionados para:",
                key=f"data_agendar_{chave_status}_{loja_codigo}",
                format="DD/MM/YYYY",
            )

            if col_agendar.button(
                "Agendar Selecionados",
                key=f"btn_agendar_{chave_status}_{loja_codigo}",
            ):
                _handle_agendar_lote(
                    cliente,
                    df_editado,
                    data_agendada,
                    contexto=f"{chave_status}_{loja_codigo}",
                )

            if col_despachar.button(
                "Despachar Selecionados",
                key=f"btn_transicionar_{chave_status}_{loja_codigo}",
            ):
                _handle_despachar_mover(
                    cliente,
                    df_editado,
                    mensagem,
                    STATUS_DESTINO_TEC_CAMPO,
                )


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

    lojas_disponiveis = sorted(df["loja_codigo"].dropna().unique())
    if lojas_disponiveis:
        selecao_lojas = st.multiselect(
            "Comparar lojas",
            lojas_disponiveis,
            default=lojas_disponiveis[: min(2, len(lojas_disponiveis))],
        )
        if selecao_lojas:
            df_sel = df[df["loja_codigo"].isin(selecao_lojas)].copy()
            if df_sel.empty:
                st.info("Sem dados para as lojas selecionadas.")
            else:
                df_sel["Data"] = (
                    pd.to_datetime(df_sel["created"], errors="coerce", utc=True)
                    .dt.tz_convert("America/Sao_Paulo")
                    .dt.date
                )
                st.subheader("Comparativo: Chamados abertos por dia")
                serie_comparativa = df_sel.groupby(["Data", "loja_codigo"]).size().unstack(fill_value=0)
                st.line_chart(serie_comparativa)

                if "problema" in df_sel.columns:
                    st.subheader("Distribuição de problemas nas lojas selecionadas")
                    distrib = df_sel.groupby(["loja_codigo", "problema"]).size().unstack(fill_value=0)
                    st.bar_chart(distrib)

                st.subheader("Tempo médio em aberto (dias)")
                tempo_medio = df_sel.groupby("loja_codigo")["Idade (dias)"].mean().round(1)
                st.bar_chart(tempo_medio)


def _renderizar_configuracoes() -> None:
    st.subheader("Lista de Técnicos (controle interno)")
    uploader = st.file_uploader(
        "Carregar planilha de técnicos",
        type=["csv", "xlsx", "xls"],
        accept_multiple_files=False,
    )
    if uploader is not None:
        try:
            if uploader.name.lower().endswith(".csv"):
                df_upload = pd.read_csv(uploader)
            else:
                df_upload = pd.read_excel(uploader)
            st.session_state[TEC_LIST_KEY] = df_upload
            st.success("Lista carregada com sucesso para esta sessão.")
        except Exception as exc:
            st.error(f"Não foi possível ler o arquivo enviado: {exc}")

    df_tecnicos = _obter_tecnicos_df()
    st.caption("As alterações realizadas aqui ficam salvas apenas durante a sessão atual.")
    df_editado = st.data_editor(
        df_tecnicos,
        use_container_width=True,
        num_rows="dynamic",
        key="editor_tecnicos",
    )
    if isinstance(df_editado, pd.DataFrame):
        st.session_state[TEC_LIST_KEY] = df_editado


def main() -> None:
    st.sidebar.title("Configurações")

    cliente = jira.conectar_jira()

    jql_pendentes_default = st.secrets.get(
        "JQL_PENDENTES",
        "project = FSA AND Status in (AGENDAMENTO)",
    )
    jql_agendados_default = st.secrets.get(
        "JQL_AGENDADOS",
        "project = FSA AND Status = Agendado AND \"Data/Hora - Agendamento\" is not EMPTY",
    )
    jql_teccampo_default = st.secrets.get(
        "JQL_TEC_CAMPO",
        "project = FSA AND Status in (TEC-CAMPO)",
    )
    jql_spare_default = st.secrets.get(
        "JQL_SPARE",
        "project = FSA AND status = \"Aguardando Spare\"",
    )

    defaults_state = {
        "sla_amarelo": st.secrets.get("SLA_AMARELO", 3),
        "sla_vermelho": st.secrets.get("SLA_VERMELHO", 7),
        "jql_pendentes": jql_pendentes_default,
        "jql_agendados": jql_agendados_default,
        "jql_teccampo": jql_teccampo_default,
        "jql_spare": jql_spare_default,
    }
    for chave, valor in defaults_state.items():
        if chave not in st.session_state:
            st.session_state[chave] = valor

    st.sidebar.number_input(
        "SLA Amarelo (dias)",
        min_value=0,
        max_value=365,
        step=1,
        value=int(st.session_state.get("sla_amarelo", 3)),
        key="sla_amarelo",
    )
    st.sidebar.number_input(
        "SLA Vermelho (dias)",
        min_value=0,
        max_value=365,
        step=1,
        value=int(st.session_state.get("sla_vermelho", 7)),
        key="sla_vermelho",
    )

    busca_texto = st.sidebar.text_input(
        "Buscar chamados",
        placeholder="Chave, loja, PDV, problema...",
        key="busca_global",
    )

    with st.sidebar.expander("Consultas JQL", expanded=False):
        st.text_area(
            "Pendentes",
            value=st.session_state.get("jql_pendentes", jql_pendentes_default),
            key="jql_pendentes",
            height=120,
        )
        st.text_area(
            "Agendados",
            value=st.session_state.get("jql_agendados", jql_agendados_default),
            key="jql_agendados",
            height=120,
        )
        st.text_area(
            "Tec-Campo",
            value=st.session_state.get("jql_teccampo", jql_teccampo_default),
            key="jql_teccampo",
            height=120,
        )
        st.text_area(
            "Spare",
            value=st.session_state.get("jql_spare", jql_spare_default),
            key="jql_spare",
            height=120,
        )

    if st.sidebar.button("Limpar Cache e Recarregar"):
        st.cache_data.clear()
        st.cache_resource.clear()
        st.rerun()

    jql_pendentes = st.session_state.get("jql_pendentes", jql_pendentes_default)
    jql_agendados = st.session_state.get("jql_agendados", jql_agendados_default)
    jql_teccampo = st.session_state.get("jql_teccampo", jql_teccampo_default)
    jql_spare = st.session_state.get("jql_spare", jql_spare_default)

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

    tab_loja, tab_agenda, tab_dashboard, tab_config = st.tabs([
        "Visão por Loja (Despacho)",
        "🗓️ Agenda",
        "📊 Dashboard",
        "⚙️ Configurações",
    ])

    with tab_loja:
        st.subheader("Despacho por Loja")
        modo_compacto = st.toggle(
            "Modo Compacto",
            key="modo_compacto",
            help="Exibe apenas um resumo por loja quando ativado.",
        )
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
                
                # ESTA É A LÓGICA CORRIGIDA (VERSÃO ORIGINAL)
                grupos_por_data = _agrupar_por_data_agendada_raw(lista)
                if not grupos_por_data:
                    st.info("Nenhum chamado encontrado com os filtros atuais.")
                    continue

                for data_label, slug, itens in grupos_por_data:
                    if data_label == "Sem data definida":
                        # Renderiza "Sem data" apenas para abas que não sejam "Agendado"
                        if titulo == "Agendado":
                            continue
                        st.subheader("Sem data de agendamento")
                    else:
                        st.subheader(f"Agenda de {data_label}")
                    
                    _renderizar_lojas(
                        cliente,
                        itens,
                        spare_keys,
                        busca_texto,
                        f"{titulo}_{slug}", # Chave única para o status/data
                        modo_compacto=modo_compacto,
                    )

    with tab_agenda:
        st.subheader("Agenda de Chamados")
        _renderizar_agenda(cliente, [ch for ch in todos_chamados if ch])

    with tab_dashboard:
        st.subheader("Indicadores Gerais")
        _renderizar_dashboard(cliente, [ch for ch in todos_chamados if ch])

    with tab_config:
        _renderizar_configuracoes()


if __name__ == "__main__":
    main()

