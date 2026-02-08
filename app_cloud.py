import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from fpdf import FPDF
import time
from datetime import datetime

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Gestão de Obra PRO", layout="wide", page_icon="🏗️")

# Definição da ordem EXATA das colunas que o app usa
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

# --- 2. CONEXÃO E LIMPEZA ---
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

    # --- CUSTOS (REPARO AUTOMÁTICO) ---
    try:
        ws = sh.sheet1
        # Verifica se o cabeçalho está certo. Se não, FORÇA a correção.
        headers_atuais = ws.row_values(1)
        
        # Se a linha 1 for diferente do padrão ou estiver vazia
        if headers_atuais != COLS_PADRAO:
            # Sobrescreve a linha 1 com os nomes certos na ordem certa
            ws.update("A1:I1", [COLS_PADRAO])
            time.sleep(1) # Espera o Google salvar
        
        # Agora lê seguro usando get_all_records que mapeia pelo nome
        dados = ws.get_all_records()
        df_custos = pd.DataFrame(dados)
        
        # Garante que as colunas existem e são números
        if not df_custos.empty:
            if 'Total' in df_custos.columns:
                df_custos['Total'] = df_custos['Total'].apply(limpar_dinheiro)
            if 'Valor' in df_custos.columns:
                df_custos['Valor'] = df_custos['Valor'].apply(limpar_dinheiro)
                
    except Exception as e:
        st.error(f"Erro lendo custos: {e}")
        df_custos = pd.DataFrame()

    # --- CRONOGRAMA ---
    try:
        ws_c = sh.worksheet("Cronograma")
        dados_c = ws_c.get_all_records()
        df_crono = pd.DataFrame(dados_c)
        if not df_crono.empty and 'Orcamento' in df_crono.columns:
            df_crono['Orcamento'] = df_crono['Orcamento'].apply(limpar_dinheiro)
    except:
        df_crono = pd.DataFrame()

    return df_custos, df_crono

# --- 3. INTERFACE ---
st.title("🏗️ Gestor de Obras")
df_custos, df_cronograma = carregar_dados_organizados()

# --- BARRA LATERAL (CRONOGRAMA) ---
with st.sidebar:
    st.header("📅 Etapas da Obra")
    
    # Checkboxes de Conclusão
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

    # Gerenciador de Etapas
    st.write("---")
    with st.expander("⚙️ Adicionar/Remover Etapas"):
        nova = st.text_input("Nome da Nova Etapa")
        if st.button("➕ Criar Etapa"):
            _, ws_c = pegar_planilha_escrita()
            ws_c.append_row([nova, "Pendente", 0])
            st.success("Criada!")
            st.cache_data.clear()
            st.rerun()
            
        if not df_cronograma.empty:
            st.write("")
            rem = st.selectbox("Excluir Etapa:", df_cronograma['Etapa'].unique())
            if st.button("🗑️ Excluir"):
                _, ws_c = pegar_planilha_escrita()
                try:
                    cell = ws_c.find(rem)
                    ws_c.delete_rows(cell.row)
                    st.success("Excluída!")
                    st.cache_data.clear()
                    st.rerun()
                except: pass
    
    if st.button("Sair"):
        st.session_state["password_correct"] = False
        st.rerun()

# --- DASHBOARD PRINCIPAL ---
if not df_custos.empty and not df_cronograma.empty:
    orc = df_cronograma['Orcamento'].sum() if 'Orcamento' in df_cronograma.columns else 0
    real = df_custos['Total'].sum() if 'Total' in df_custos.columns else 0
    
    k1, k2, k3 = st.columns(3)
    k1.metric("Orçamento Total", f"R$ {orc:,.2f}")
    k2.metric("Gasto Realizado", f"R$ {real:,.2f}")
    k3.metric("Saldo", f"R$ {orc-real:,.2f}", delta=orc-real)

# --- FORMULÁRIO DE GASTOS ---
with st.expander("➕ Lançar Novo Gasto", expanded=True):
    with st.form("form_gasto", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        dt = c1.date_input("Data")
        desc = c2.text_input("Descrição (Ex: Cimento)")
        val = c3.number_input("Valor Unitário (R$)", 0.0)
        
        c4, c5, c6 = st.columns(3)
        qtd = c4.number_input("Quantidade", 1.0)
        un = c5.selectbox("Unidade", ["un","m","kg","saco","m²","m³","dia"])
        
        lista_etapas = df_cronograma['Etapa'].tolist() if not df_cronograma.empty else ["Geral"]
        etapa = c6.selectbox("Vincular Etapa", lista_etapas)
        
        if st.form_submit_button("💾 Salvar Gasto"):
            ws, _ = pegar_planilha_escrita()
            total_calc = val * qtd
            # A ordem aqui TEM que bater com a lista COLS_PADRAO lá do topo
            ws.append_row([str(dt), desc, qtd, un, val, total_calc, "Material", "-", etapa])
            st.success("Salvo!")
            st.cache_data.clear()
            st.rerun()

# --- TABELA DE HISTÓRICO ---
st.divider()
c_txt, c_pdf = st.columns([4, 1])
c_txt.subheader("📋 Histórico de Compras")

# Botão PDF
with c_pdf:
    if st.button("📄 Gerar PDF"):
        if not df_custos.empty:
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", "B", 16)
            pdf.cell(0, 10, "Relatorio de Custos", 0, 1, "C")
            pdf.set_font("Arial", "", 12)
            pdf.ln(10)
            pdf.cell(0, 10, f"Total Gasto: R$ {df_custos['Total'].sum():,.2f}", 0, 1)
            pdf.ln(5)
            # Imprime ultimos 10 gastos
            pdf.cell(0, 10, "Ultimos Lancamentos:", 0, 1)
            for _, row in df_custos.tail(10).iterrows():
                txt = f"{row['Data']} | {row['Descricao']} | R$ {row['Total']}"
                pdf.cell(0, 8, txt, 0, 1)
            
            st.download_button("Download PDF", pdf.output(dest='S').encode('latin-1'), "relatorio.pdf")

# Exibição da Tabela Organizada
if not df_custos.empty:
    # Seleciona apenas as colunas que importam para leitura fácil
    colunas_visiveis = ["Data", "Descricao", "Etapa", "Qtd", "Unidade", "Valor", "Total"]
    # Filtra apenas as colunas que realmente existem no dataframe para não dar erro
    colunas_finais = [c for c in colunas_visiveis if c in df_custos.columns]
    
    st.dataframe(
        df_custos[colunas_finais].sort_index(ascending=False), 
        use_container_width=True
    )
