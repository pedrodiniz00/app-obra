import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from fpdf import FPDF
import time
from datetime import datetime

st.set_page_config(page_title="Gestão de Obra Blindado", layout="wide", page_icon="🏗️")

# --- 1. LOGIN ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False
    if st.session_state["password_correct"]:
        return True

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
            except: st.error("Sem secrets configurados.")
    return False

if not check_password(): st.stop()

# --- 2. CONEXÃO E LEITURA SEGURA ---
def limpar_dinheiro(valor):
    if isinstance(valor, (int, float)): return float(valor)
    if isinstance(valor, str):
        try:
            return float(valor.replace('R$', '').replace('.', '').replace(',', '.').strip())
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
    # Tenta pegar cronograma, se nao existir cria
    try: ws_c = sh.worksheet("Cronograma")
    except: ws_c = sh.add_worksheet("Cronograma", 20, 5)
    return sh.sheet1, ws_c

@st.cache_data(ttl=5)
def carregar_dados_brutos():
    client = conectar_gsheets()
    if not client: return pd.DataFrame(), pd.DataFrame()
    
    try: sh = client.open("Dados_Obra")
    except: return pd.DataFrame(), pd.DataFrame()

    # --- LEITURA DOS CUSTOS (MODO BRUTO) ---
    try:
        ws = sh.sheet1
        # get_all_values PULA a verificação chata de cabeçalho
        dados_raw = ws.get_all_values()
        
        if len(dados_raw) > 1:
            # Se a primeira linha parece cabeçalho (tem 'Data' ou 'Desc'), usa ela
            if 'Data' in dados_raw[0] or 'data' in dados_raw[0]:
                df_custos = pd.DataFrame(dados_raw[1:], columns=dados_raw[0])
            else:
                # Se a primeira linha for DADOS (ex: tem data 2023-..), cria cabeçalho artificial
                colunas_padrao = ["Data", "Descricao", "Qtd", "Unidade", "Valor", "Total", "Classe", "Sub", "Etapa"]
                # Ajusta tamanho se sobrar ou faltar colunas
                df_custos = pd.DataFrame(dados_raw, columns=colunas_padrao[:len(dados_raw[0])])
            
            # Renomeia para garantir que o codigo entenda
            mapa = {
                'Data': 'data', 'Descricao': 'descricao', 'Qtd': 'quantidade', 
                'Unidade': 'unidade', 'Valor': 'valor_un', 'Total': 'total', 
                'Classe': 'classe', 'Etapa': 'etapa'
            }
            df_custos.rename(columns=lambda x: mapa.get(x, x), inplace=True)
            
            # Limpa numeros
            if 'total' in df_custos.columns:
                df_custos['total'] = df_custos['total'].apply(limpar_dinheiro)
        else:
            df_custos = pd.DataFrame()
            
    except Exception as e:
        st.error(f"Erro lendo custos: {e}")
        df_custos = pd.DataFrame()

    # --- LEITURA CRONOGRAMA ---
    try:
        ws_c = sh.worksheet("Cronograma")
        dados_c = ws_c.get_all_records() # Aqui mantemos o padrao pois costuma ser limpo
        df_crono = pd.DataFrame(dados_c)
        if not df_crono.empty and 'Orcamento' in df_crono.columns:
            df_crono['Orcamento'] = df_crono['Orcamento'].apply(limpar_dinheiro)
    except:
        df_crono = pd.DataFrame()

    return df_custos, df_crono

# --- 3. INTERFACE ---
st.title("🏗️ Gestor de Obras")
df_custos, df_cronograma = carregar_dados_brutos()

# SIDEBAR
with st.sidebar:
    st.header("Cronograma")
    if not df_cronograma.empty:
        total = len(df_cronograma)
        feitos = len(df_cronograma[df_cronograma['Status']=='Concluído'])
        st.progress(feitos/total if total>0 else 0)
        
        st.write("---")
        for i, row in df_cronograma.iterrows():
            nome = row.get('Etapa', f'Etapa {i}')
            status = row.get('Status', 'Pendente')
            check = st.checkbox(nome, value=(status=='Concluído'), key=f"c_{i}")
            if check != (status=='Concluído'):
                _, ws_c = pegar_planilha_escrita()
                ws_c.update_cell(i+2, 2, "Concluído" if check else "Pendente")
                st.cache_data.clear()
                st.rerun()
                
    st.write("---")
    with st.expander("Gerenciar Etapas"):
        nova = st.text_input("Nova Etapa")
        if st.button("Add"):
            _, ws_c = pegar_planilha_escrita()
            ws_c.append_row([nova, "Pendente", 0])
            st.cache_data.clear()
            st.rerun()

# MAIN KPI
if not df_custos.empty and not df_cronograma.empty:
    orc = df_cronograma['Orcamento'].sum() if 'Orcamento' in df_cronograma.columns else 0
    real = df_custos['total'].sum() if 'total' in df_custos.columns else 0
    c1, c2, c3 = st.columns(3)
    c1.metric("Orçamento", f"R$ {orc:,.2f}")
    c2.metric("Gasto Real", f"R$ {real:,.2f}")
    c3.metric("Saldo", f"R$ {orc-real:,.2f}")

# FORMULARIO
with st.expander("➕ Lançar Gasto", expanded=True):
    with st.form("f1", clear_on_submit=True):
        c1,c2,c3 = st.columns(3)
        dt = c1.date_input("Data")
        desc = c2.text_input("Descricao")
        val = c3.number_input("Valor", 0.0)
        c4,c5,c6 = st.columns(3)
        qtd = c4.number_input("Qtd", 1.0)
        un = c5.selectbox("Un", ["un","m","kg","sc","dia"])
        etapas = df_cronograma['Etapa'].tolist() if not df_cronograma.empty else ["Geral"]
        etapa = c6.selectbox("Etapa", etapas)
        
        if st.form_submit_button("Salvar"):
            ws, _ = pegar_planilha_escrita()
            ws.append_row([str(dt), desc, qtd, un, val, val*qtd, "Material", "-", etapa])
            st.success("Salvo!")
            st.cache_data.clear()
            st.rerun()

# TABELA
st.divider()
st.subheader("Histórico de Materiais")
if not df_custos.empty:
    # Mostra apenas as colunas úteis
    cols_uteis = [c for c in df_custos.columns if c in ['data','descricao','quantidade','unidade','valor_un','total','etapa']]
    st.dataframe(df_custos[cols_uteis], use_container_width=True)
else:
    st.info("Nenhum dado encontrado na planilha.")
