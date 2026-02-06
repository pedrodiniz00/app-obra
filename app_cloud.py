import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from io import BytesIO

st.set_page_config(page_title="Gestão de Obra", layout="wide")

st.title("🏗️ Gestor de Obras - Diagnóstico")

# --- BLOCO DE CONEXÃO BLINDADO ---
def conectar_gsheets():
    try:
        # 1. Verifica se os segredos existem
        if "gcp_service_account" not in st.secrets:
            st.error("ERRO CRÍTICO: Não encontrei a seção [gcp_service_account] nos Secrets.")
            return None

        # 2. Tenta montar as credenciais
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        
        # 3. Tenta abrir a planilha
        sheet = client.open("Dados_Obra").sheet1 
        return sheet
        
    except Exception as e:
        st.error(f"⚠️ OCORREU UM ERRO DE CONEXÃO: {e}")
        st.info("Dica: Verifique se o nome da planilha no Google é exatamente 'Dados_Obra' e se você compartilhou com o email do client_email.")
        return None

# --- CARREGAMENTO DE DADOS ---
sheet = conectar_gsheets()

if sheet:
    st.success("✅ Conexão com Google Sheets realizada com sucesso!")
    
    # Lógica do App
    try:
        data = sheet.get_all_records()
        df_existente = pd.DataFrame(data)
        if df_existente.empty:
             df_existente = pd.DataFrame(columns=['data', 'descricao', 'quantidade', 'unidade', 'valor_un', 'total', 'classe', 'subclasse', 'etapa'])
    except:
        df_existente = pd.DataFrame(columns=['data', 'descricao', 'quantidade', 'unidade', 'valor_un', 'total', 'classe', 'subclasse', 'etapa'])

    # --- BARRA LATERAL ---
    st.sidebar.header("📅 Cronograma")
    etapas = ["Fundação", "Alvenaria", "Laje", "Reboco Externo", "Reboco Interno", "Acabamento"]
    for etapa in etapas:
        st.sidebar.checkbox(etapa, key=f"status_{etapa}")

    # --- FORMULÁRIO ---
    with st.expander("➕ Novo Lançamento", expanded=True):
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
            etapa_vinculo = st.selectbox("Vincular à Etapa", etapas)
            
        if st.button("Salvar na Nuvem"):
            novo_dado = [
                data_input.strftime('%d/%m/%Y'),
                desc,
                float(qtd),
                un,
                float(valor),
                float(qtd * valor),
                classe,
                sub,
                etapa_vinculo
            ]
            try:
                sheet.append_row(novo_dado)
                st.success("Salvo com sucesso!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao salvar: {e}")

    # --- RELATÓRIOS ---
    if not df_existente.empty:
        st.divider()
        st.metric("Total Gasto", f"R$ {df_existente['total'].sum():,.2f}")
        st.dataframe(df_existente, use_container_width=True)
else:
    st.warning("O aplicativo parou porque não conseguiu conectar na planilha.")

