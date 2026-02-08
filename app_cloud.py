import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from fpdf import FPDF
from io import BytesIO
import time
from datetime import datetime

# --- CONFIGURAÇÃO VISUAL ---
st.set_page_config(page_title="Gestão de Obra Desktop", layout="wide", page_icon="🏗️")

# ==============================================================================
# 1. LOGIN E SEGURANÇA
# ==============================================================================
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
                else:
                    st.error("Senha incorreta.")
            except:
                st.error("Configure os Secrets primeiro!")
    return False

if not check_password():
    st.stop()

# ==============================================================================
# 2. CONEXÃO GOOGLE SHEETS
# ==============================================================================
def limpar_dinheiro(valor):
    if isinstance(valor, str):
        return float(valor.replace('R$', '').replace('.', '').replace(',', '.').strip())
    return float(valor)

@st.cache_resource
def conectar_gsheets():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), scope)
    return gspread.authorize(creds)

def garantir_estrutura(sh):
    try:
        ws = sh.worksheet("Cronograma")
    except:
        ws = sh.add_worksheet("Cronograma", 20, 5)
        ws.append_row(["Etapa", "Status", "Orcamento"])
    
    headers = ws.row_values(1)
    if "Orcamento" not in headers:
        ws.update_cell(1, 3, "Orcamento")

@st.cache_data(ttl=10)
def carregar_dados():
    client = conectar_gsheets()
    sh = client.open("Dados_Obra")
    garantir_estrutura(sh)
    
    try:
        df_custos = pd.DataFrame(sh.sheet1.get_all_records())
        if not df_custos.empty and 'total' in df_custos.columns:
            df_custos['total'] = df_custos['total'].apply(lambda x: limpar_dinheiro(x) if isinstance(x, str) else x)
    except: df_custos = pd.DataFrame()

    try:
        df_crono = pd.DataFrame(sh.worksheet("Cronograma").get_all_records())
        if not df_crono.empty and 'Orcamento' in df_crono.columns:
            df_crono['Orcamento'] = df_crono['Orcamento'].apply(lambda x: limpar_dinheiro(x) if isinstance(x, str) else x)
    except: df_crono = pd.DataFrame()
        
    return df_custos, df_crono

def pegar_planilha_escrita():
    client = conectar_gsheets()
    sh = client.open("Dados_Obra")
    return sh.sheet1, sh.worksheet("Cronograma")

# ==============================================================================
# 3. INTERFACE (LAYOUT CLÁSSICO)
# ==============================================================================
st.title("🏗️ Gestor de Obras")

df_custos, df_cronograma = carregar_dados()

# --- BARRA LATERAL (CRONOGRAMA) ---
with st.sidebar:
    st.header("📅 Cronograma")
    
    # Botão de Sair
    if st.button("Sair (Logout)"):
        st.session_state["password_correct"] = False
        st.rerun()
    st.divider()

    if not df_cronograma.empty:
        # Progresso
        concluidos = len(df_cronograma[df_cronograma['Status'] == 'Concluído'])
        total = len(df_cronograma)
        prog = concluidos / total if total > 0 else 0
        st.progress(prog)
        st.caption(f"{int(prog*100)}% Concluído")
        
        st.subheader("Etapas")
        # Checkboxes
        for i, row in df_cronograma.iterrows():
            is_done = (row['Status'] == 'Concluído')
            checked = st.checkbox(row['Etapa'], value=is_done, key=f"check_{i}")
            
            if checked != is_done:
                _, ws_c = pegar_planilha_escrita()
                ws_c.update_cell(i+2, 2, "Concluído" if checked else "Pendente")
                st.toast("Atualizado!")
                st.cache_data.clear()
                time.sleep(0.5)
                st.rerun()
    
    st.divider()
    st.info("💡 Dica: Marque as etapas conforme a obra avança.")

# --- TELA PRINCIPAL ---

# 1. BLOCO DE KPIs (Orçado vs Realizado)
if not df_cronograma.empty and not df_custos.empty:
    gastos = df_custos.groupby('etapa')['total'].sum().reset_index()
    resumo = pd.merge(df_cronograma, gastos, left_on='Etapa', right_on='etapa', how='left').fillna(0)
    
    total_orcado = resumo['Orcamento'].sum()
    total_gasto = resumo['total'].sum()
    saldo = total_orcado - total_gasto
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Orçamento (Meta)", f"R$ {total_orcado:,.2f}")
    col2.metric("Gasto Realizado", f"R$ {total_gasto:,.2f}")
    col3.metric("Saldo", f"R$ {saldo:,.2f}", delta=saldo)

# 2. FORMULÁRIO DE CADASTRO (Expansível)
with st.expander("➕ Novo Lançamento de Gasto", expanded=True):
    with st.form("form_gasto", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        data = c1.date_input("Data")
        desc = c2.text_input("Descrição")
        valor = c3.number_input("Valor Unit (R$)", min_value=0.0)
        
        c4, c5, c6 = st.columns(3)
        qtd = c4.number_input("Qtd", 1.0)
        un = c5.selectbox("Unidade", ["un", "m", "kg", "saco", "dia", "h"])
        
        lista_etapas = df_cronograma['Etapa'].tolist() if not df_cronograma.empty else ["Geral"]
        etapa = c6.selectbox("Vincular Etapa", lista_etapas)
        
        if st.form_submit_button("💾 Salvar"):
            ws_1, _ = pegar_planilha_escrita()
            total = qtd * valor
            ws_1.append_row([str(data), desc, qtd, un, valor, total, "Material", "-", etapa])
            st.success("Salvo!")
            st.cache_data.clear()
            st.rerun()

# 3. TABELA DE DADOS
st.divider()
st.subheader("📋 Histórico de Gastos")
if not df_custos.empty:
    st.dataframe(df_custos.sort_index(ascending=False), use_container_width=True)
    
    # Botão de Download Excel (Discreto)
    from io import BytesIO
    def to_excel(df):
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False)
        return output.getvalue()
        
    excel = to_excel(df_custos)
    st.download_button("📥 Baixar Excel", excel, "obra.xlsx")
