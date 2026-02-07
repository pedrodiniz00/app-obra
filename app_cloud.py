import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from fpdf import FPDF
from io import BytesIO
import time
from datetime import datetime

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Gestão de Obra PRO", layout="wide")

# --- 0. SEGURANÇA (LOGIN) ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False
    if st.session_state["password_correct"]:
        return True
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("### 🔒 Acesso Restrito")
        pwd = st.text_input("Digite a Senha:", type="password")
        if st.button("Entrar"):
            # Verifica se a senha bate com os Secrets
            if pwd == st.secrets["acesso"]["senha_admin"]:
                st.session_state["password_correct"] = True
                st.rerun()
            else:
                st.error("Senha incorreta.")
    return False

if not check_password():
    st.stop()

# --- 1. FUNÇÕES AUXILIARES (PDF/EXCEL) ---
def to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Relatorio')
    return output.getvalue()

class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 15)
        self.cell(0, 10, 'Relatorio de Obra', 0, 1, 'C')
        self.ln(5)

def gerar_pdf(df_custos, df_crono):
    pdf = PDF()
    pdf.add_page()
    pdf.set_font('Arial', '', 12)
    pdf.cell(0, 10, f"Gerado em: {datetime.now().strftime('%d/%m/%Y')}", 0, 1)
    
    total = df_custos['total'].sum() if not df_custos.empty else 0
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, f"Total Gasto: R$ {total:,.2f}", 0, 1)
    pdf.ln(5)
    
    pdf.cell(0, 10, "Progresso das Etapas:", 0, 1)
    pdf.set_font('Arial', '', 11)
    if not df_crono.empty:
        for _, row in df_crono.iterrows():
            pdf.cell(0, 8, f"- {row['Etapa']}: {row['Status']}", 0, 1)
    return pdf.output(dest='S').encode('latin-1')

# --- 2. CONEXÃO GOOGLE SHEETS ---
@st.cache_resource
def conectar_gsheets():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), scope)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Erro na conexão: {e}")
        return None

# Função para garantir que a aba Cronograma tem a coluna Orçamento
def garantir_estrutura(sh):
    try:
        ws = sh.worksheet("Cronograma")
        headers = ws.row_values(1)
        if "Orcamento" not in headers:
            # Se não existir, cria a coluna na célula C1
            ws.update_cell(1, 3, "Orcamento") 
            # Preenche com zeros para não dar erro
            qtd_linhas = len(ws.get_all_values())
            if qtd_linhas > 1:
                col_range = f"C2:C{qtd_linhas}"
                ws.format(col_range, {"numberFormat": {"type": "NUMBER"}})
    except:
        pass # Se der erro, segue o jogo

@st.cache_data(ttl=10) # Cache curto para atualizar rápido
def carregar_dados():
    client = conectar_gsheets()
    if not client: return pd.DataFrame(), pd.DataFrame()
    sh = client.open("Dados_Obra")
    
    # Garante estrutura
    garantir_estrutura(sh)
    
    try:
        df_custos = pd.DataFrame(sh.sheet1.get_all_records())
    except: df_custos = pd.DataFrame()
        
    try:
        df_crono = pd.DataFrame(sh.worksheet("Cronograma").get_all_records())
    except: df_crono = pd.DataFrame()
        
    return df_custos, df_crono

def pegar_planilha_escrita():
    client = conectar_gsheets()
    sh = client.open("Dados_Obra")
    return sh.sheet1, sh.worksheet("Cronograma")

# --- 3. INTERFACE PRINCIPAL ---
st.title("🏗️ Gestor de Obras Pro")

# Menu de Abas
tab1, tab2, tab3 = st.tabs(["💰 Lançamentos", "📊 Orçamento & Metas", "📂 Relatórios"])

df_custos, df_cronograma = carregar_dados()

# Tratamento de erro para dados vazios
if not df_custos.empty and 'total' in df_custos.columns:
    df_custos['total'] = pd.to_numeric(df_custos['total'], errors='coerce').fillna(0)

# --- ABA 1: LANÇAMENTOS ---
with tab1:
    col_left, col_right = st.columns([1, 2])
    
    with col_left:
        st.subheader("Status")
        if not df_cronograma.empty:
            for i, row in df_cronograma.iterrows():
                is_checked = (row['Status'] == 'Concluído')
                checked = st.checkbox(row['Etapa'], value=is_checked, key=f"status_{i}")
                if checked != is_checked:
                    _, ws_c = pegar_planilha_escrita()
                    ws_c.update_cell(i+2, 2, "Concluído" if checked else "Pendente")
                    st.toast("Status Atualizado!")
                    st.cache_data.clear()
                    time.sleep(1)
                    st.rerun()

    with col_right:
        st.subheader("Novo Gasto")
        with st.form("form_gasto"):
            c1, c2 = st.columns(2)
            dt = c1.date_input("Data")
            desc = c2.text_input("Descrição")
            
            c3, c4, c5 = st.columns(3)
            val = c3.number_input("Valor Unit (R$)", 0.0)
            qtd = c4.number_input("Quantidade", 1.0)
            
            opcoes = df_cronograma['Etapa'].tolist() if not df_cronograma.empty else ["Geral"]
            etapa = c5.selectbox("Vincular Etapa", opcoes)
            
            submitted = st.form_submit_button("💾 Salvar Lançamento")
            if submitted:
                ws_custos, _ = pegar_planilha_escrita()
                ws_custos.append_row([str(dt), desc, qtd, "un", val, val*qtd, "Material", "-", etapa])
                st.success("Gasto Salvo!")
                st.cache_data.clear()
                st.rerun()

# --- ABA 2: ORÇAMENTO (PREVISTO X REALIZADO) ---
with tab2:
    st.header("Controle Financeiro")
    
    # Área para definir o orçamento PELO APP
    with st.expander("✏️ Definir Metas de Orçamento", expanded=False):
        if not df_cronograma.empty:
            c_input1, c_input2, c_btn = st.columns([2, 1, 1])
            etapa_sel = c_input1.selectbox("Escolha a Etapa:", df_cronograma['Etapa'].unique())
            valor_meta = c_input2.number_input("Valor da Meta (R$):", min_value=0.0)
            
            if c_btn.button("Atualizar Meta"):
                _, ws_c = pegar_planilha_escrita()
                # Acha a linha da etapa
                cell = ws_c.find(etapa_sel)
                # Atualiza a coluna 3 (Orcamento) naquela linha
                ws_c.update_cell(cell.row, 3, valor_meta)
                st.success(f"Meta de {etapa_sel} atualizada!")
                st.cache_data.clear()
                time.sleep(1)
                st.rerun()

    # Gráfico Comparativo
    if not df_custos.empty and not df_cronograma.empty:
        # Garante que a coluna Orcamento existe e é número
        if 'Orcamento' not in df_cronograma.columns:
            df_cronograma['Orcamento'] = 0
        
        df_cronograma['Orcamento'] = pd.to_numeric(df_cronograma['Orcamento'], errors='coerce').fillna(0)
        
        gastos = df_custos.groupby('etapa')['total'].sum().reset_index()
        resumo = pd.merge(df_cronograma, gastos, left_on='Etapa', right_on='etapa', how='left').fillna(0)
        
        resumo = resumo[['Etapa', 'Orcamento', 'total']]
        resumo.columns = ['Etapa', 'Meta (R$)', 'Gasto Real (R$)']
        
        # Cores condicionais
        st.bar_chart(resumo.set_index('Etapa'))
        st.dataframe(resumo, use_container_width=True)

# --- ABA 3: EXPORTAÇÃO ---
with tab3:
    st.header("🖨️ Central de Downloads")
    c1, c2 = st.columns(2)
    
    with c1:
        if st.button("📄 Gerar PDF da Obra"):
            if not df_custos.empty:
                pdf_data = gerar_pdf(df_custos, df_cronograma)
                st.download_button("⬇️ Baixar PDF", pdf_data, "relatorio.pdf", "application/pdf")
            else:
                st.warning("Sem dados para gerar PDF.")
                
    with c2:
        if st.button("📊 Gerar Excel Completo"):
            if not df_custos.empty:
                excel_data = to_excel(df_custos)
                st.download_button("⬇️ Baixar Excel", excel_data, "obra.xlsx")
            else:
                st.warning("Sem dados para Excel.")


