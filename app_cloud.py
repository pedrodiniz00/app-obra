import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import time

st.set_page_config(page_title="Gestão de Obra Pro", layout="wide")

# --- 0. SISTEMA DE LOGIN (A BARREIRA DE SEGURANÇA) ---
def check_password():
    """Retorna True se o usuário estiver logado, False caso contrário."""
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False

    if st.session_state["password_correct"]:
        return True

    # Tela de Login
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("### 🔒 Acesso Restrito - Gestão de Obras")
        pwd_input = st.text_input("Digite a senha de acesso:", type="password")
        
        if st.button("Entrar no Sistema"):
            # Verifica se a senha bate com o que está nos Secrets
            if pwd_input == st.secrets["acesso"]["senha_admin"]:
                st.session_state["password_correct"] = True
                st.success("Login realizado com sucesso!")
                time.sleep(1)
                st.rerun()
            else:
                st.error("🚫 Senha incorreta.")
                
    return False

# SE NÃO TIVER LOGADO, PARA O CÓDIGO AQUI
if not check_password():
    st.stop()

# ========================================================
# DAQUI PARA BAIXO, SÓ CARREGA SE TIVER A SENHA
# ========================================================

# --- 1. CONEXÃO COM CACHE ---
@st.cache_resource
def conectar_gsheets():
    try:
        if "gcp_service_account" not in st.secrets:
            st.error("Secrets não configurados.")
            return None
        
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        st.error(f"Erro de conexão: {e}")
        return None

# --- 2. LEITURA COM CACHE ---
@st.cache_data(ttl=60)
def carregar_dados_gerais():
    client = conectar_gsheets()
    if not client: return pd.DataFrame(), pd.DataFrame()
    
    sh = client.open("Dados_Obra")
    
    # CUSTOS
    try:
        ws_custos = sh.sheet1
        dados_c = ws_custos.get_all_records()
        df_custos = pd.DataFrame(dados_c)
    except:
        df_custos = pd.DataFrame()

    # CRONOGRAMA
    try:
        ws_crono = sh.worksheet("Cronograma")
        dados_cr = ws_crono.get_all_records()
        df_crono = pd.DataFrame(dados_cr)
    except:
        df_crono = pd.DataFrame()
        
    return df_custos, df_crono

# Função auxiliar para escrita
def pegar_abas_para_escrever():
    client = conectar_gsheets()
    sh = client.open("Dados_Obra")
    try:
        ws_cronograma = sh.worksheet("Cronograma")
    except:
        ws_cronograma = sh.add_worksheet("Cronograma", 20, 3)
    return sh.sheet1, ws_cronograma

# --- INTERFACE PRINCIPAL ---
# Botão de Sair na barra lateral
if st.sidebar.button("Sair / Logout"):
    st.session_state["password_correct"] = False
    st.rerun()

st.title("🏗️ Gestor de Obras")

df_custos, df_cronograma = carregar_dados_gerais()

# Fallback inicial se cronograma vazio
if df_cronograma.empty:
    ws_c, ws_cr = pegar_abas_para_escrever()
    if len(ws_cr.get_all_values()) < 2:
        ws_cr.append_row(["Etapa", "Status", "Responsavel"])
        etapas_padrao = ["Fundação", "Alvenaria", "Laje", "Reboco Externo", "Reboco Interno", "Acabamento"]
        for e in etapas_padrao: ws_cr.append_row([e, "Pendente", "-"])
        st.cache_data.clear()
        st.rerun()

# --- BARRA LATERAL ---
st.sidebar.header("📅 Etapas")

if not df_cronograma.empty:
    total = len(df_cronograma)
    feitos = len(df_cronograma[df_cronograma['Status'] == 'Concluído'])
    progresso = feitos / total if total > 0 else 0
    st.sidebar.progress(progresso)
    
    lista_etapas = df_cronograma.to_dict('records')
    for i, item in enumerate(lista_etapas):
        nome = item['Etapa']
        status_bool = True if item['Status'] == 'Concluído' else False
        novo_check = st.sidebar.checkbox(nome, value=status_bool, key=f"check_{i}")
        
        if novo_check != status_bool:
            ws_custos_write, ws_crono_write = pegar_abas_para_escrever()
            novo_texto = "Concluído" if novo_check else "Pendente"
            ws_crono_write.update_cell(i + 2, 2, novo_texto)
            st.toast("Status atualizado!")
            st.cache_data.clear()
            st.rerun()

# --- NOVO GASTO ---
with st.expander("💰 Novo Gasto", expanded=True):
    c1, c2, c3 = st.columns(3)
    dt = c1.date_input("Data")
    desc = c1.text_input("Descrição")
    classe = c1.selectbox("Classe", ["Material", "Mão de Obra", "Ferramentas", "Outros"])
    
    qtd = c2.number_input("Qtd", 1.0)
    un = c2.selectbox("Un", ["un", "m", "m2", "m3", "kg", "dia"])
    sub = c2.text_input("Subclasse")
    
    opcoes_etapas = df_cronograma['Etapa'].tolist() if not df_cronograma.empty else ["Geral"]
    val = c3.number_input("Valor Unit.", 0.0)
    vinc = c3.selectbox("Etapa", opcoes_etapas)
    
    if st.button("Salvar Gasto"):
        ws_custos_write, ws_crono_write = pegar_abas_para_escrever()
        ws_custos_write.append_row([
            str(dt), desc, qtd, un, val, qtd*val, classe, sub, vinc
        ])
        st.success("Salvo!")
        st.cache_data.clear()
        st.rerun()

# --- RELATÓRIO ---
if not df_custos.empty:
    if 'total' in df_custos.columns:
        total_gasto = pd.to_numeric(df_custos['total'], errors='coerce').sum()
        st.metric("Total Gasto", f"R$ {total_gasto:,.2f}")
        st.dataframe(df_custos, use_container_width=True)
