import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from fpdf import FPDF
import time
from datetime import datetime

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Gestão de Obra PRO", layout="wide", page_icon="🏗️")

# Definição das colunas padrão
COLS_PADRAO = ["Data", "Descricao", "Qtd", "Unidade", "Valor", "Total", "Classe", "Subclasse", "Etapa"]

# --- 1. LOGIN ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False
    if st.session_state["password_correct"]: return True

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("### 🔐 Acesso Restrito")
        pwd = st.text_input("Senha:", type="password")
        if st.button("Entrar"):
            try:
                if pwd == st.secrets["acesso"]["senha_admin"]:
                    st.session_state["password_correct"] = True
                    st.rerun()
                else: st.error("Senha incorreta.")
            except: st.error("Erro nos Secrets.")
    return False

if not check_password(): st.stop()

# --- 2. CONEXÃO E FUNÇÕES AUXILIARES ---
def limpar_dinheiro(valor):
    if isinstance(valor, (int, float)): return float(valor)
    if isinstance(valor, str):
        try: return float(valor.replace('R$', '').replace('.', '').replace(',', '.').strip())
        except: return 0.0
    return 0.0

@st.cache_resource
def conectar_gsheets():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), scope)
    return gspread.authorize(creds)

def pegar_planilha_escrita():
    client = conectar_gsheets()
    sh = client.open("Dados_Obra")
    try: ws_c = sh.worksheet("Cronograma")
    except: ws_c = sh.add_worksheet("Cronograma", 20, 5)
    return sh.sheet1, ws_c

@st.cache_data(ttl=5)
def carregar_dados_organizados():
    client = conectar_gsheets()
    if not client: return pd.DataFrame(), pd.DataFrame()
    
    sh = client.open("Dados_Obra")

    # --- CUSTOS ---
    try:
        ws = sh.sheet1
        # Verifica cabeçalho
        headers_atuais = ws.row_values(1)
        if headers_atuais != COLS_PADRAO:
            ws.update("A1:I1",
