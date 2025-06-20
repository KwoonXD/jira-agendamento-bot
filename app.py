# main.py - Dashboard Principal
import streamlit as st
from streamlit_autorefresh import st_autorefresh
import pandas as pd
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go
from data.jira_client import JiraFieldServiceClient
from data.data_processor import FieldServiceProcessor
from components.filters import AdvancedFilters
from components.visualizations import FieldServiceVisualizations
from components.alerts import FieldServiceAlerts
from utils.exports import ExportManager
from utils.helpers import format_datetime, generate_ticket_message

# Configuração da página
st.set_page_config(
    page_title="Field Service Dashboard",
    page_icon="🔧",
    layout="wide",
    initial_sidebar_state="expanded"
)

class FieldServiceDashboard:
    def __init__(self):
        self.jira_client = JiraFieldServiceClient()
        self.processor = FieldServiceProcessor()
        self.filters = AdvancedFilters()
        self.visualizations = FieldServiceVisualizations()
        self.alerts = FieldServiceAlerts()
        self.export_manager = ExportManager()
        
        # Auto-refresh a cada 60 segundos
        st_autorefresh(interval=60 * 1000, key="auto_refresh")
        
    def initialize_session_state(self):
        """Inicializa estado da sessão"""
        defaults = {
            'data_loaded': False,
            'raw_data': None,
            'filtered_data': None,
            'selected_tickets': [],
            'view_mode': 'dashboard',  # 'dashboard', 'agendamento', 'agendados'
            'last_update': None
        }
        
        for key, value in defaults.items():
            if key not in st.session_state:
                st.session_state[key] = value
    
    def load_data(self, force_refresh=False):
        """Carrega dados do Jira com cache inteligente"""
        if force_refresh or not st.session_state.data_loaded:
            with st.spinner("🔄 Carregando dados do Jira..."):
                try:
                    # Carrega dados de ambos os status
                    agendamento_data = self.jira_client.fetch_agendamento_tickets()
                    agendados_data = self.jira_client.fetch_agendados_tickets()
                    spare_data = self.jira_client.fetch_spare_tickets()
                    
                    # Processa e combina os dados
                    processed_data = self.processor.process_all_data(
                        agendamento_data, agendados_data, spare_data
                    )
                    
                    st.session_state.raw_data = processed_data
                    st.session_state.data_loaded = True
                    st.session_state.last_update = datetime.now()
                    
                    st.success(f"✅ {len(processed_data)} chamados carregados com sucesso!")
                    return processed_data
                    
                except Exception as e:
                    st.error(f"❌ Erro ao carregar dados: {str(e)}")
                    return pd.DataFrame()
        
        return st.session_state.raw_data
    
    def render_header(self):
        """Renderiza cabeçalho com controles"""
        col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
        
        with col1:
            st.title("🔧 Field Service Dashboard")
            if st.session_state.last_update:
                st.caption(f"🕒 Última atualização: {st.session_state.last_update.strftime('%d/%m/%Y %H:%M:%S')}")
        
        with col2:
            if st.button("🔄 Refresh", type="secondary", use_container_width=True):
                st.session_state.data_loaded = False
                st.rerun()
        
        with col3:
            # Seletor de visualização
            view_options = {
                'dashboard': '📊 Dashboard',
                'agendamento': '⏳ Agendamento',
                'agendados': '📋 Agendados'
            }
            
            selected_view = st.selectbox(
                "Visualização:",
                options=list(view_options.keys()),
                format_func=lambda x: view_options[x],
                key="view_selector"
            )
            st.session_state.view_mode = selected_view
        
        with col4:
            # Botões de exportação
            if st.session_state.get('filtered_data') is not None:
                self.export_manager.render_export_section(st.session_state.filtered_data)
    
    def render_dashboard_view(self, data):
        """Renderiza vista do dashboard completo"""
        if data.empty:
            st.warning("⚠️ Nenhum dado disponível.")
            return
            
        # Métricas principais
        self.render_key_metrics(data)
        
        # Alertas importantes
        self.alerts.render_all_alerts(data)
        
        # Visualizações em grid
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📊 Status dos Chamados")
            self.visualizations.render_status_distribution(data)
            
            st.subheader("📅 Chamados por Data")
            self.visualizations.render_timeline_chart(data)
        
        with col2:
            st.subheader("🏪 Distribuição por Loja")
            self.visualizations.render_store_distribution(data)
            
            st.subheader("🎯 Top Ativos")
            self.visualizations.render_asset_ranking(data)
        
        # Tabela detalhada com funcionalidades avançadas
        self.render_advanced_table(data)
    
    def render_agendamento_view(self, data):
        """Renderiza vista específica de agendamento (baseada no código original)"""
        st.header("⏳ Chamados PENDENTES de Agendamento")
        
        agendamento_data = data[data['status'] == 'AGENDAMENTO']
        
        if agendamento_data.empty:
            st.warning("Nenhum chamado em AGENDAMENTO encontrado no momento.")
            return
        
        st.success(f"{len(agendamento_data)} chamados em AGENDAMENTO encontrados.")
        
        # Agrupa por loja
        grouped_by_store = agendamento_data.groupby('loja')
        
        for loja, group in grouped_by_store:
            tickets_list = group.to_dict('records')
            
            with st.expander(f"Loja {loja} - {len(tickets_list)} chamado(s) AGENDAMENTO", expanded=False):
                # Gera mensagem formatada (mantém lógica original)
                message = self.generate_formatted_message(loja, tickets_list)
                st.code(message, language="text")
                
                # Botões de ação para cada ticket
                self.render_ticket_actions(tickets_list)
    
    def render_agendados_view(self, data):
        """Renderiza vista específica de agendados (baseada no código original)"""
        st.header("📋 Chamados AGENDADOS")
        
        agendados_data = data[data['status'] == 'AGENDADO']
        
        if agendados_data.empty:
            st.info("Nenhum chamado em AGENDADO encontrado.")
            return
        
        # Agrupa por data e loja
        grouped_data = self.processor.group_by_date_and_store(agendados_data)
        
        # Filtro de loja
        available_stores = sorted(agendados_data['loja'].unique())
        selected_store = st.selectbox(
            "🔍 Filtrar por loja:",
            ["Todas"] + available_stores,
            key="store_filter"
        )
        
        for date_str, stores in sorted(grouped_data.items()):
            # Filtra por loja se selecionada
            filtered_stores = self.filter_stores_by_selection(stores, selected_store)
            
            if not filtered_stores:
                continue
                
            total_tickets = sum(len(tickets) for tickets in filtered_stores.values())
            st.subheader(f"📅 Data Agendada: {date_str} ({total_tickets} chamado(s))")
            
            for loja, tickets_list in filtered_stores.items():
                # Verifica tickets aguardando spare para esta loja
                spare_warning = self.check_spare_tickets_for_store(data, loja)
                
                with st.expander(f"Loja {loja} - {len(tickets_list)} chamado(s)", expanded=False):
                    # Mensagem formatada
                    message = self.generate_formatted_message(loja, tickets_list)
                    st.code(message, language="text")
                    
                    # Aviso sobre spare
                    if spare_warning:
                        st.warning(spare_warning)
                    else:
                        st.success("✅ Sem chamados em Aguardando Spare para esta loja.")
                    
                    # Ações para os tickets
                    self.render_ticket_actions(tickets_list)
    
    def render_key_metrics(self, data):
        """Renderiza métricas principais"""
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            total = len(data)
            st.metric("Total Chamados", total)
        
        with col2:
            agendamento = len(data[data['status'] == 'AGENDAMENTO'])
            st.metric("Agendamento", agendamento)
        
        with col3:
            agendados = len(data[data['status'] == 'AGENDADO'])
            st.metric("Agendados", agendados)
        
        with col4:
            spare = len(data[data['status'] == 'Aguardando Spare'])
            delta_spare = f"-{spare}" if spare > 0 else None
            st.metric("Aguardando Spare", spare, delta=delta_spare)
        
        with col5:
            duplicates = self.processor.detect_duplicates(data)
            delta_dup = f"-{len(duplicates)}" if duplicates else None
            st.metric("Possíveis Duplicatas", len(duplicates), delta=delta_dup)
    
    def render_advanced_table(self, data):
        """Renderiza tabela avançada com edição"""
        st.subheader("📋 Tabela Detalhada dos Chamados")
        
        # Configuração das colunas
        column_config = {
            "key": st.column_config.TextColumn("Ticket", width="small"),
            "loja": st.column_config.TextColumn("Loja", width="small"),
            "status": st.column_config.SelectboxColumn(
                "Status",
                options=["AGENDAMENTO", "AGENDADO", "Aguardando Spare", "Em Andamento", "Concluído"]
            ),
            "data_agendada": st.column_config.DatetimeColumn("Data Agendada"),
            "pdv": st.column_config.TextColumn("PDV", width="small"),
            "ativo": st.column_config.TextColumn("Ativo", width="medium"),
            "problema": st.column_config.TextColumn("Problema", width="large"),
            "cidade": st.column_config.TextColumn("Cidade", width="medium"),
            "estado": st.column_config.TextColumn("Estado", width="small")
        }
        
        # Seletor de colunas para exibir
        available_columns = list(column_config.keys())
        selected_columns = st.multiselect(
            "Selecione colunas para exibir:",
            available_columns,
            default=["key", "loja", "status", "data_agendada", "ativo", "problema"],
            key="table_columns"
        )
        
        if selected_columns:
            display_data = data[selected_columns].copy()
            
            edited_data = st.data_editor(
                display_data,
                column_config={k: v for k, v in column_config.items() if k in selected_columns},
                use_container_width=True,
                hide_index=True,
                num_rows="dynamic",
                key="tickets_editor"
            )
            
            # Detecta mudanças
            if not edited_data.equals(display_data):
                st.info("💡 Mudanças detectadas! Funcionalidade de salvamento será implementada em breve.")
                
                # Mostra preview das mudanças
                with st.expander("👀 Preview das Mudanças"):
                    changes = self.processor.detect_changes(display_data, edited_data)
                    if changes:
                        st.json(changes)
    
    def render_ticket_actions(self, tickets_list):
        """Renderiza ações para tickets"""
        if not tickets_list:
            return
            
        st.markdown("**Ações Disponíveis:**")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("📞 Transição para Agendado", key=f"trans_{tickets_list[0]['key']}"):
                # Implementar transição de status
                st.info("Funcionalidade de transição será implementada!")
        
        with col2:
            if st.button("📋 Copiar Mensagem", key=f"copy_{tickets_list[0]['key']}"):
                # Copiar mensagem formatada
                st.success("Mensagem copiada! (funcionalidade em desenvolvimento)")
        
        with col3:
            selected_tickets = st.multiselect(
                "Selecionar tickets:",
                [t['key'] for t in tickets_list],
                key=f"select_{tickets_list[0]['key']}"
            )
            
            if selected_tickets:
                st.session_state.selected_tickets.extend(selected_tickets)
    
    def generate_formatted_message(self, loja, tickets_list):
        """Gera mensagem formatada (mantém lógica original)"""
        blocos = []
        
        for ticket in tickets_list:
            data_agendada = ticket.get('data_agendada')
            if data_agendada and data_agendada != '--':
                try:
                    data_formatada = datetime.strptime(data_agendada, "%Y-%m-%dT%H:%M:%S.%f%z").strftime('%d/%m/%Y %H:%M')
                except:
                    data_formatada = str(data_agendada)
            else:
                data_formatada = '--'
            
            bloco = f"""*{ticket['key']}*
*Loja:* {loja}
*PDV:* {ticket.get('pdv', '--')}
*ATIVO:* {ticket.get('ativo', '--')}
*Problema:* {ticket.get('problema', '--')}
*Data Agendada:* {data_formatada}
*****"""
            blocos.append(bloco)
        
        # Adiciona informações da loja (do primeiro ticket)
        if tickets_list:
            primeiro_ticket = tickets_list[0]
            info_loja = f"""*Endereço:* {primeiro_ticket.get('endereco', '--')}
*Estado:* {primeiro_ticket.get('estado', '--')}
*CEP:* {primeiro_ticket.get('cep', '--')}
*Cidade:* {primeiro_ticket.get('cidade', '--')}"""
            blocos.append(info_loja)
        
        return "\n".join(blocos)
    
    def check_spare_tickets_for_store(self, data, loja):
        """Verifica tickets aguardando spare para uma loja"""
        spare_tickets = data[
            (data['status'] == 'Aguardando Spare') & 
            (data['loja'] == loja)
        ]
        
        if not spare_tickets.empty:
            ticket_keys = ', '.join(spare_tickets['key'].tolist())
            return f"⚠️ {len(spare_tickets)} chamado(s) em Aguardando Spare para esta loja: {ticket_keys}"
        
        return None
    
    def filter_stores_by_selection(self, stores, selected_store):
        """Filtra lojas baseado na seleção"""
        if selected_store == "Todas":
            return stores
        else:
            return {k: v for k, v in stores.items() if k == selected_store}
    
    def render_sidebar_filters(self, data):
        """Renderiza filtros avançados na sidebar"""
        st.sidebar.header("🎛️ Filtros Avançados")
        
        # Aplica filtros
        filtered_data = self.filters.apply_filters(data)
        st.session_state.filtered_data = filtered_data
        
        # Resumo dos filtros
        st.sidebar.markdown("---")
        st.sidebar.subheader("📊 Resumo")
        st.sidebar.metric("Chamados Filtrados", len(filtered_data))
        st.sidebar.metric("Total Disponível", len(data))
        
        return filtered_data
    
    def run(self):
        """Executa o dashboard principal"""
        self.initialize_session_state()
        
        # Carrega dados
        data = self.load_data()
        if data is None or data.empty:
            st.error("❌ Não foi possível carregar os dados do Jira.")
            st.info("Verifique suas credenciais e conexão.")
            return
        
        # Renderiza cabeçalho
        self.render_header()
        
        # Aplica filtros na sidebar
        filtered_data = self.render_sidebar_filters(data)
        
        # Renderiza vista baseada na seleção
        view_mode = st.session_state.view_mode
        
        if view_mode == 'dashboard':
            self.render_dashboard_view(filtered_data)
        elif view_mode == 'agendamento':
            self.render_agendamento_view(filtered_data)
        elif view_mode == 'agendados':
            self.render_agendados_view(filtered_data)
        
        # Rodapé
        st.markdown("---")
        st.caption(f"🔧 Field Service Dashboard | Desenvolvido com Streamlit")

# Execução principal
if __name__ == "__main__":
    dashboard = FieldServiceDashboard()
    dashboard.run()


# data/jira_client.py - Cliente Jira Adaptado
import streamlit as st
import requests
from requests.auth import HTTPBasicAuth
import pandas as pd
from datetime import datetime
from typing import List, Dict, Any

class JiraFieldServiceClient:
    def __init__(self):
        self.email = st.secrets["EMAIL"]
        self.api_token = st.secrets["API_TOKEN"]
        self.jira_url = "https://delfia.atlassian.net"
        self.auth = HTTPBasicAuth(self.email, self.api_token)
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        # Mapeamento dos campos customizados
        self.field_mapping = {
            "loja": "customfield_14954",
            "pdv": "customfield_14829", 
            "ativo": "customfield_14825",
            "problema": "customfield_12374",
            "endereco": "customfield_12271",
            "estado": "customfield_11948",
            "cep": "customfield_11993",
            "cidade": "customfield_11994",
            "data_agendada": "customfield_12036"
        }
    
    def _make_request(self, jql: str, max_results: int = 100) -> List[Dict]:
        """Faz requisição para API do Jira"""
        fields = "summary," + ",".join(self.field_mapping.values())
        
        params = {
            "jql": jql,
            "maxResults": max_results,
            "fields": fields
        }
        
        try:
            response = requests.get(
                f"{self.jira_url}/rest/api/3/search",
                headers=self.headers,
                auth=self.auth,
                params=params,
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json().get("issues", [])
            else:
                st.error(f"Erro na API Jira: {response.status_code} - {response.text}")
                return []
                
        except requests.exceptions.RequestException as e:
            st.error(f"Erro de conexão com Jira: {str(e)}")
            return []
    
    def fetch_agendamento_tickets(self) -> List[Dict]:
        """Busca chamados em status AGENDAMENTO"""
        jql = "project = FSA AND status = AGENDAMENTO"
        return self._make_request(jql)
    
    def fetch_agendados_tickets(self) -> List[Dict]:
        """Busca chamados em status AGENDADO"""
        jql = "project = FSA AND status = AGENDADO"
        return self._make_request(jql)
    
    def fetch_spare_tickets(self) -> List[Dict]:
        """Busca chamados aguardando spare"""
        jql = 'project = FSA AND status = "Aguardando Spare"'
        return self._make_request(jql)
    
    def fetch_all_field_service_tickets(self) -> List[Dict]:
        """Busca todos os chamados de field service"""
        jql = 'project = FSA AND status IN (AGENDAMENTO, AGENDADO, "Aguardando Spare", "Em Andamento")'
        return self._make_request(jql, max_results=500)
    
    def transition_ticket_status(self, issue_key: str, transition_id: str) -> bool:
        """Transiciona status de um ticket"""
        try:
            response = requests.post(
                f"{self.jira_url}/rest/api/3/issue/{issue_key}/transitions",
                headers=self.headers,
                auth=self.auth,
                json={"transition": {"id": str(transition_id)}},
                timeout=30
            )
            return response.status_code == 204
        except requests.exceptions.RequestException:
            return False


# data/data_processor.py - Processador de Dados
import pandas as pd
from datetime import datetime
from typing import List, Dict, Any
import streamlit as st

class FieldServiceProcessor:
    def __init__(self):
        self.field_mapping = {
            "loja": "customfield_14954",
            "pdv": "customfield_14829", 
            "ativo": "customfield_14825",
            "problema": "customfield_12374",
            "endereco": "customfield_12271",
            "estado": "customfield_11948",
            "cep": "customfield_11993",
            "cidade": "customfield_11994",
            "data_agendada": "customfield_12036"
        }
    
    def extract_field_value(self, field_data: Any, field_type: str = "text") -> str:
        """Extrai valor de campo customizado do Jira"""
        if not field_data:
            return "--"
        
        if field_type == "select" and isinstance(field_data, dict):
            return field_data.get("value", "--")
        
        return str(field_data) if field_data else "--"
    
    def process_ticket_data(self, issue: Dict) -> Dict:
        """Processa dados de um ticket individual"""
        fields = issue.get("fields", {})
        
        # Extrai dados básicos
        ticket_data = {
            "key": issue.get("key", ""),
            "summary": fields.get("summary", ""),
            "loja": self.extract_field_value(fields.get(self.field_mapping["loja"]), "select"),
            "pdv": self.extract_field_value(fields.get(self.field_mapping["pdv"])),
            "ativo": self.extract_field_value(fields.get(self.field_mapping["ativo"]), "select"),
            "problema": self.extract_field_value(fields.get(self.field_mapping["problema"])),
            "endereco": self.extract_field_value(fields.get(self.field_mapping["endereco"])),
            "estado": self.extract_field_value(fields.get(self.field_mapping["estado"]), "select"),
            "cep": self.extract_field_value(fields.get(self.field_mapping["cep"])),
            "cidade": self.extract_field_value(fields.get(self.field_mapping["cidade"])),
            "data_agendada": fields.get(self.field_mapping["data_agendada"]),
            "status": "Unknown"  # Será definido pelo contexto
        }
        
        # Processa data agendada
        if ticket_data["data_agendada"]:
            try:
                dt = datetime.strptime(ticket_data["data_agendada"], "%Y-%m-%dT%H:%M:%S.%f%z")
                ticket_data["data_agendada_formatted"] = dt.strftime('%d/%m/%Y %H:%M')
                ticket_data["data_agendada_date"] = dt.date()
            except:
                ticket_data["data_agendada_formatted"] = "--"
                ticket_data["data_agendada_date"] = None
        else:
            ticket_data["data_agendada_formatted"] = "--"
            ticket_data["data_agendada_date"] = None
        
        return ticket_data
    
    def process_all_data(self, agendamento_data: List, agendados_data: List, spare_data: List) -> pd.DataFrame:
        """Processa todos os dados e retorna DataFrame unificado"""
        all_tickets = []
        
        # Processa tickets de agendamento
        for issue in agendamento_data:
            ticket = self.process_ticket_data(issue)
            ticket["status"] = "AGENDAMENTO"
            all_tickets.append(ticket)
        
        # Processa tickets agendados
        for issue in agendados_data:
            ticket = self.process_ticket_data(issue)
            ticket["status"] = "AGENDADO"
            all_tickets.append(ticket)
        
        # Processa tickets aguardando spare
        for issue in spare_data:
            ticket = self.process_ticket_data(issue)
            ticket["status"] = "Aguardando Spare"
            all_tickets.append(ticket)
        
        # Converte para DataFrame
        df = pd.DataFrame(all_tickets)
        
        # Limpeza e padronização
        df = self.clean_and_standardize_data(df)
        
        return df
    
    def clean_and_standardize_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Limpa e padroniza os dados"""
        if df.empty:
            return df
        
        # Remove espaços extras
        text_columns = ["loja", "pdv", "ativo", "problema", "endereco", "estado", "cidade"]
        for col in text_columns:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip()
        
        # Padroniza nomes de lojas
        df["loja"] = df["loja"].replace("Loja Desconhecida", "Não Identificada")
        
        # Adiciona colunas calculadas
        df["data_criacao"] = datetime.now().date()
        df["dias_desde_criacao"] = 0  # Placeholder
        
        return df
    
    def group_by_date_and_store(self, df: pd.DataFrame) -> Dict:
        """Agrupa dados por data e loja"""
        grouped_data = {}
        
        for _, row in df.iterrows():
            date_key = row.get("data_agendada_formatted", "Não definida")
            if date_key == "--":
                date_key = "Não definida"
            
            loja = row.get("loja", "Não Identificada")
            
            if date_key not in grouped_data:
                grouped_data[date_key] = {}
            
            if loja not in grouped_data[date_key]:
                grouped_data[date_key][loja] = []
            
            grouped_data[date_key][loja].append(row.to_dict())
        
        return grouped_data
    
    def detect_duplicates(self, df: pd.DataFrame) -> List[Dict]:
        """Detecta possíveis duplicatas"""
        if df.empty:
            return []
        
        duplicates = []
        
        # Agrupa por loja + ativo + problema
        grouped = df.groupby(["loja", "ativo", "problema"])
        
        for (loja, ativo, problema), group in grouped:
            if len(group) > 1:
                duplicates.append({
                    "loja": loja,
                    "ativo": ativo,
                    "problema": problema,
                    "tickets": group["key"].tolist(),
                    "count": len(group)
                })
        
        return duplicates
    
    def detect_changes(self, original_df: pd.DataFrame, edited_df: pd.DataFrame) -> List[Dict]:
        """Detecta mudanças entre DataFrames"""
        changes = []
        
        # Compara apenas linhas que existem em ambos
        for idx in original_df.index:
            if idx in edited_df.index:
                original_row = original_df.loc[idx]
                edited_row = edited_df.loc[idx]
                
                row_changes = {}
                for col in original_df.columns:
                    if col in edited_df.columns:
                        if original_row[col] != edited_row[col]:
                            row_changes[col] = {
                                "old": original_row[col],
                                "new": edited_row[col]
                            }
                
                if row_changes:
                    changes.append({
                        "index": idx,
                        "ticket_key": original_row.get("key", "Unknown"),
                        "changes": row_changes
                    })
        
        return changes
