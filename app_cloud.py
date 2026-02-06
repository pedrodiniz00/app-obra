import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials

st.set_page_config(page_title="Gestão de Obra Pro", layout="wide")

# --- CONEXÃO E CONFIGURAÇÃO ---
def conectar_gsheets():
    try:
        if "gcp_service_account" not in st.secrets:
            st.error("Secrets não encontrados.")
            return None, None

        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        
        # Abre a planilha principal
        sh = client.open("Dados_Obra")
        return client, sh
    except Exception as e:
        st.error(f"Erro de conexão: {e}")
        return None, None

# --- GERENCIAMENTO DE ABAS (WORKSHEETS) ---
def carregar_dados_custos(sh):
    try:
        ws = sh.sheet1
        data = ws.get_all_records()
        df = pd.DataFrame(data)
        if df.empty:
             return ws, pd.DataFrame(columns=['data', 'descricao', 'quantidade', 'unidade', 'valor_un', 'total', 'classe', 'subclasse', 'etapa'])
        return ws, df
    except:
        return None, pd.DataFrame()

def gerenciar_cronograma(sh):
    # Tenta abrir a aba 'Cronograma', se não existir, cria ela
    etapas_padrao = ["Fundação", "Alvenaria", "Laje", "Reboco Externo", "Reboco Interno", "Acabamento"]
    try:
        ws = sh.worksheet("Cronograma")
    except:
        # Cria a aba se não existir
        ws = sh.add_worksheet(title="Cronograma", rows=20, cols=3)
        ws.append_row(["Etapa", "Status", "Responsavel"]) # Cabeçalho
        for etapa in etapas_padrao:
            ws.append_row([etapa, "Pendente", "-"])
            
    # Ler os dados atuais
    dados = ws.get_all_records()
    df_cronograma = pd.DataFrame(dados)
    
    # Se estiver vazio (só cabeçalho), popula novamente
    if df_cronograma.empty:
        for etapa in etapas_padrao:
            ws.append_row([etapa, "Pendente", "-"])
        dados = ws.get_all_records()
        df_cronograma = pd.DataFrame(dados)
        
    return ws, df_cronograma

# --- INTERFACE PRINCIPAL ---
client, sh = conectar_gsheets()

if sh:
    # Carrega as duas abas
    ws_custos, df_custos = carregar_dados_custos(sh)
    ws_cronograma, df_cronograma = gerenciar_cronograma(sh)

    st.title("🏗️ Gestor de Obras - Painel Integrado")

    # --- BARRA LATERAL (CRONOGRAMA INTELIGENTE) ---
    st.sidebar.header("📅 Status da Obra")
    
    # Calcula Progresso
    total_etapas = len(df_cronograma)
    concluidas = len(df_cronograma[df_cronograma['Status'] == 'Concluído'])
    progresso = concluidas / total_etapas if total_etapas > 0 else 0
    
    st.sidebar.progress(progresso)
    st.sidebar.write(f"**Progresso: {int(progresso * 100)}%**")
    st.sidebar.divider()

    # Renderiza os Checkboxes
    # Convertemos o dataframe para uma lista de dicionários para iterar fácil
    lista_etapas = df_cronograma.to_dict('records')
    
    for i, item in enumerate(lista_etapas):
        nome_etapa = item['Etapa']
        status_atual = item['Status'] == 'Concluído'
        
        # Checkbox
        novo_status = st.sidebar.checkbox(nome_etapa, value=status_atual, key=f"crono_{i}")
        
        # Se o usuário mudou o status, atualiza no Google Sheets
        if novo_status != status_atual:
            status_texto = "Concluído" if novo_status else "Pendente"
            # O gspread usa index base 1, e temos cabeçalho, então linha = i + 2
            ws_cronograma.update_cell(i + 2, 2, status_texto)
            st.rerun() # Recarrega a página para atualizar o gráfico

    # --- ÁREA DE LANÇAMENTO DE CUSTOS ---
    # (Mantemos a lógica de lançamento que já funcionava)
    with st.expander("💸 Lançamento Financeiro", expanded=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            data_input = st.date_input("Data")
            desc = st.text_input("Descrição")
            classe = st.selectbox("Classe", ["Materiais Básicos", "Hidráulica", "Elétrica", "Mão de Obra", "Acabamento"])
        with col2:
            qtd = st.number_input("Quantidade", min_value=0.01)
            un = st.selectbox("Unidade", ["Saco", "m³", "Unid", "Peça", "Litro", "Kg", "H/m"])
            sub = st.text_input("Subclasse")
        with col3:
            valor = st.number_input("Valor Unitário (R$)", min_value=0.0)
            etapa_vinculo = st.selectbox("Vincular à Etapa", df_cronograma['Etapa'].tolist())
            
        if st.button("Salvar Custo"):
            novo_dado = [
                data_input.strftime('%d/%m/%Y'), desc, float(qtd), un,
                float(valor), float(qtd * valor), classe, sub, etapa_vinculo
            ]
            ws_custos.append_row(novo_dado)
            st.success("Custo registrado!")
            st.rerun()

    # --- DASHBOARD ---
    st.divider()
    col_kpi1, col_kpi2, col_kpi3 = st.columns(3)
    
    custo_total = df_custos['total'].sum() if not df_custos.empty else 0
    
    col_kpi1.metric("Investimento Total", f"R$ {custo_total:,.2f}")
    col_kpi2.metric("Etapas Concluídas", f"{concluidas}/{total_etapas}")
    col_kpi3.metric("Previsão de Término", "A definir") # Futura implementação

    if not df_custos.empty:
        st.subheader("Detalhamento de Gastos")
        st.dataframe(df_custos, use_container_width=True)
        
        st.subheader("Custos por Etapa")
        # Gráfico vinculando custo à etapa
        custo_por_etapa = df_custos.groupby('etapa')['total'].sum()
        st.bar_chart(custo_por_etapa)
