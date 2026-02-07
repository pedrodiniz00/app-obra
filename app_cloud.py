import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from fpdf import FPDF
from io import BytesIO
import time
from datetime import datetime

st.set_page_config(page_title="Gestão de Obra ERP", layout="wide")

# --- 0. SEGURANÇA (LOGIN) ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False
    if st.session_state["password_correct"]:
        return True
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("### 🔒 Acesso Restrito - ERP Obra")
        pwd = st.text_input("Senha de Acesso", type="password")
        if st.button("Entrar"):
            if pwd == st.secrets["acesso"]["senha_admin"]:
                st.session_state["password_correct"] = True
                st.rerun()
            else:
                st.error("Senha incorreta.")
    return False

if not check_password():
    st.stop()

# --- 1. FUNÇÕES DE EXPORTAÇÃO ---
def to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Relatorio')
    return output.getvalue()

class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 15)
        self.cell(0, 10, 'Relatorio de Gestao de Obra', 0, 1, 'C')
        self.ln(5)

def gerar_pdf(df_custos, df_crono):
    pdf = PDF()
    pdf.add_page()
    pdf.set_font('Arial', '', 12)
    
    # Resumo
    total_gasto = df_custos['total'].sum() if not df_custos.empty else 0
    pdf.cell(0, 10, f"Data do Relatorio: {datetime.now().strftime('%d/%m/%Y')}", 0, 1)
    pdf.cell(0, 10, f"Investimento Total Realizado: R$ {total_gasto:,.2f}", 0, 1)
    pdf.ln(10)
    
    # Status Cronograma
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, "Status das Etapas:", 0, 1)
    pdf.set_font('Arial', '', 11)
    if not df_crono.empty:
        for index, row in df_crono.iterrows():
            pdf.cell(0, 8, f"- {row['Etapa']}: {row['Status']}", 0, 1)
    
    return pdf.output(dest='S').encode('latin-1')

# --- 2. CONEXÃO E DADOS ---
@st.cache_resource
def conectar_gsheets():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), scope)
        return gspread.authorize(creds)
    except: return None

@st.cache_data(ttl=60)
def carregar_dados():
    client = conectar_gsheets()
    if not client: return pd.DataFrame(), pd.DataFrame()
    sh = client.open("Dados_Obra")
    
    try:
        df_custos = pd.DataFrame(sh.sheet1.get_all_records())
    except: df_custos = pd.DataFrame()
        
    try:
        df_crono = pd.DataFrame(sh.worksheet("Cronograma").get_all_records())
    except: df_crono = pd.DataFrame()
        
    return df_custos, df_crono

def escrever_dados():
    client = conectar_gsheets()
    sh = client.open("Dados_Obra")
    try: ws_c = sh.worksheet("Cronograma")
    except: ws_c = sh.add_worksheet("Cronograma", 20, 5)
    return sh.sheet1, ws_c

# --- 3. INTERFACE ---
st.title("🏗️ Gestor de Obras Pro")

df_custos, df_cronograma = carregar_dados()

# Garante colunas numéricas para cálculos
if not df_custos.empty and 'total' in df_custos.columns:
    df_custos['total'] = pd.to_numeric(df_custos['total'], errors='coerce').fillna(0)

if not df_cronograma.empty and 'Orcamento' in df_cronograma.columns:
    df_cronograma['Orcamento'] = pd.to_numeric(df_cronograma['Orcamento'], errors='coerce').fillna(0)

# MENU SUPERIOR (TABS)
tab1, tab2, tab3 = st.tabs(["💰 Lançamentos", "📊 Dashboard & Orçamento", "📂 Exportação"])

# --- ABA 1: LANÇAMENTOS E CRONOGRAMA ---
with tab1:
    col_main, col_side = st.columns([3, 1])
    
    with col_side:
        st.subheader("📅 Cronograma")
        if not df_cronograma.empty:
            progresso = len(df_cronograma[df_cronograma['Status']=='Concluído']) / len(df_cronograma)
            st.progress(progresso)
            
            for i, row in df_cronograma.iterrows():
                checked = st.checkbox(row['Etapa'], value=(row['Status']=='Concluído'), key=f"c_{i}")
                if checked != (row['Status']=='Concluído'):
                    _, ws_c = escrever_dados()
                    ws_c.update_cell(i+2, 2, "Concluído" if checked else "Pendente")
                    st.cache_data.clear()
                    st.rerun()

    with col_main:
        st.subheader("Novo Custo")
        c1, c2, c3 = st.columns(3)
        dt = c1.date_input("Data")
        desc = c1.text_input("Descrição")
        classe = c1.selectbox("Classe", ["Material", "Mão de Obra", "Equipamento", "Adm"])
        qtd = c2.number_input("Qtd", 1.0)
        un = c2.selectbox("Un", ["un", "m", "kg", "saco", "dia", "h"])
        sub = c2.text_input("Subclasse")
        val = c3.number_input("Valor Unit.", 0.0)
        etapa_list = df_cronograma['Etapa'].tolist() if not df_cronograma.empty else ["Geral"]
        vinc = c3.selectbox("Etapa", etapa_list)
        
        if st.button("💾 Salvar Gasto"):
            ws_1, _ = escrever_dados()
            ws_1.append_row([str(dt), desc, qtd, un, val, qtd*val, classe, sub, vinc])
            st.success("Registrado!")
            st.cache_data.clear()
            st.rerun()
            
        if not df_custos.empty:
            st.divider()
            st.dataframe(df_custos.sort_index(ascending=False), use_container_width=True, height=200)

# --- ABA 2: ORÇAMENTO PREVISTO X REALIZADO ---
with tab2:
    if not df_custos.empty and not df_cronograma.empty:
        st.header("Análise Financeira")
        
        # Agrupa gastos por etapa
        gastos_por_etapa = df_custos.groupby('etapa')['total'].sum().reset_index()
        
        # Junta com o orçamento (Merge)
        # Atenção: Assegure que os nomes das etapas são idênticos na planilha
        resumo = pd.merge(df_cronograma, gastos_por_etapa, left_on='Etapa', right_on='etapa', how='left').fillna(0)
        
        resumo['Diferença'] = resumo['Orcamento'] - resumo['total']
        resumo = resumo[['Etapa', 'Orcamento', 'total', 'Diferença']]
        resumo.columns = ['Etapa', 'Orçamento (Meta)', 'Gasto Real', 'Saldo']
        
        # Mostra KPIs Gerais
        total_orcado = resumo['Orçamento (Meta)'].sum()
        total_gasto = resumo['Gasto Real'].sum()
        delta = total_orcado - total_gasto
        
        k1, k2, k3 = st.columns(3)
        k1.metric("Orçamento Total", f"R$ {total_orcado:,.2f}")
        k2.metric("Gasto Realizado", f"R$ {total_gasto:,.2f}")
        k3.metric("Saldo Geral", f"R$ {delta:,.2f}", delta_color="normal")
        
        st.divider()
        
        # Tabela Colorida
        st.dataframe(
            resumo,
            column_config={
                "Orçamento (Meta)": st.column_config.NumberColumn(format="R$ %.2f"),
                "Gasto Real": st.column_config.ProgressColumn(
                    format="R$ %.2f",
                    min_value=0,
                    max_value=float(resumo['Orçamento (Meta)'].max()) * 1.2, # Escala visual
                ),
                "Saldo": st.column_config.NumberColumn(format="R$ %.2f")
            },
            use_container_width=True
        )
        
        # Gráfico
        st.bar_chart(resumo.set_index('Etapa')[['Orçamento (Meta)', 'Gasto Real']])

# --- ABA 3: RELATÓRIOS E EXPORTAÇÃO ---
with tab3:
    st.header("🖨️ Central de Downloads")
    
    col_xls, col_pdf = st.columns(2)
    
    with col_xls:
        st.info("Para contabilidade e planilhas")
        if not df_custos.empty:
            excel_data = to_excel(df_custos)
            st.download_button("📥 Baixar Planilha Excel", excel_data, "custos_obra.xlsx")
            
    with col_pdf:
        st.info("Para enviar ao cliente (Resumo)")
        if st.button("📄 Gerar Relatório PDF"):
            if not df_custos.empty:
                pdf_bytes = gerar_pdf(df_custos, df_cronograma)
                st.download_button("⬇️ Baixar PDF", pdf_bytes, "relatorio_obra.pdf", "application/pdf")
            else:
                st.warning("Sem dados para gerar relatório.")
