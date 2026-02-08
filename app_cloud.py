import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from fpdf import FPDF
from io import BytesIO
import time
from datetime import datetime

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Gestão de Obra PRO", layout="wide", page_icon="🏗️")

# ==============================================================================
# 🔐 1. SEGURANÇA E LOGIN
# ==============================================================================
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
        st.info("Entre com a senha de administrador configurada nos Secrets.")
        pwd_input = st.text_input("Senha:", type="password")
        
        if st.button("Acessar Sistema"):
            # Verifica se a senha bate com o que está nos Secrets
            try:
                if pwd_input == st.secrets["acesso"]["senha_admin"]:
                    st.session_state["password_correct"] = True
                    st.rerun()
                else:
                    st.error("🚫 Senha incorreta.")
            except:
                st.error("Erro: Configure a senha nos Secrets do Streamlit.")
                
    return False

# Bloqueia o app se não estiver logado
if not check_password():
    st.stop()

# ==============================================================================
# 📡 2. CONEXÃO E DADOS (BACKEND)
# ==============================================================================

# Função auxiliar para limpar valores monetários (R$ 1.000,00 -> 1000.00)
def limpar_dinheiro(valor):
    if isinstance(valor, str):
        return float(valor.replace('R$', '').replace('.', '').replace(',', '.').strip())
    return float(valor)

@st.cache_resource
def conectar_gsheets():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), scope)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Erro grave de conexão: {e}")
        return None

# Função para garantir que a planilha tenha a estrutura certa
def garantir_estrutura(sh):
    try:
        # Verifica aba Cronograma
        try:
            ws = sh.worksheet("Cronograma")
        except:
            ws = sh.add_worksheet("Cronograma", 20, 5)
            ws.append_row(["Etapa", "Status", "Orcamento"])
        
        # Verifica se tem cabeçalho de Orçamento
        headers = ws.row_values(1)
        if "Orcamento" not in headers:
            ws.update_cell(1, 3, "Orcamento")
    except:
        pass

@st.cache_data(ttl=10)
def carregar_dados():
    client = conectar_gsheets()
    if not client: return pd.DataFrame(), pd.DataFrame()
    
    sh = client.open("Dados_Obra")
    garantir_estrutura(sh)
    
    # Carrega Custos (Aba 1)
    try:
        df_custos = pd.DataFrame(sh.sheet1.get_all_records())
        # Garante coluna total numérica
        if not df_custos.empty and 'total' in df_custos.columns:
            df_custos['total'] = df_custos['total'].apply(lambda x: limpar_dinheiro(x) if isinstance(x, str) else x)
    except: 
        df_custos = pd.DataFrame()

    # Carrega Cronograma (Aba Cronograma)
    try:
        df_crono = pd.DataFrame(sh.worksheet("Cronograma").get_all_records())
        # Garante coluna Orçamento numérica
        if not df_crono.empty and 'Orcamento' in df_crono.columns:
            df_crono['Orcamento'] = df_crono['Orcamento'].apply(lambda x: limpar_dinheiro(x) if isinstance(x, str) else x)
    except: 
        df_crono = pd.DataFrame()
        
    return df_custos, df_crono

def pegar_planilha_escrita():
    """Retorna as abas prontas para escrever (sem cache)"""
    client = conectar_gsheets()
    sh = client.open("Dados_Obra")
    return sh.sheet1, sh.worksheet("Cronograma")

# ==============================================================================
# 🖨️ 3. FUNÇÕES DE EXPORTAÇÃO
# ==============================================================================
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
    pdf.cell(0, 10, f"Gerado em: {datetime.now().strftime('%d/%m/%Y')}", 0, 1)
    
    total = df_custos['total'].sum() if not df_custos.empty else 0
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, f"Custo Total da Obra: R$ {total:,.2f}", 0, 1)
    pdf.ln(5)
    
    pdf.cell(0, 10, "Status das Etapas:", 0, 1)
    pdf.set_font('Arial', '', 11)
    if not df_crono.empty:
        for _, row in df_crono.iterrows():
            status = row['Status'] if 'Status' in row else 'Pendente'
            etapa = row['Etapa'] if 'Etapa' in row else '?'
            pdf.cell(0, 8, f"- {etapa}: {status}", 0, 1)
            
    return pdf.output(dest='S').encode('latin-1')

# ==============================================================================
# 🖥️ 4. INTERFACE DO USUÁRIO (FRONTEND)
# ==============================================================================
st.title("🏗️ Gestor de Obras Pro")

# Carrega dados
df_custos, df_cronograma = carregar_dados()

# Botão de Logout Lateral
with st.sidebar:
    st.write(f"Usuário Logado: Admin")
    if st.button("Sair (Logout)"):
        st.session_state["password_correct"] = False
        st.rerun()

# Abas Principais
tab1, tab2, tab3 = st.tabs(["💰 Lançamentos & Obra", "📊 Dashboard Financeiro", "📂 Relatórios & Exportação"])

# --- ABA 1: LANÇAMENTOS ---
with tab1:
    col_cronograma, col_form = st.columns([1, 2])
    
    # 1. Coluna Esquerda: Checklist de Obra
    with col_cronograma:
        st.subheader("📅 Cronograma Físico")
        if df_cronograma.empty:
            st.warning("Cronograma vazio. Adicione etapas na planilha.")
        else:
            # Barra de Progresso
            concluidos = len(df_cronograma[df_cronograma['Status'] == 'Concluído'])
            total_etapas = len(df_cronograma)
            progresso = concluidos / total_etapas if total_etapas > 0 else 0
            st.progress(progresso)
            st.caption(f"{int(progresso*100)}% da obra concluída")
            
            # Checkboxes
            for i, row in df_cronograma.iterrows():
                is_done = (row['Status'] == 'Concluído')
                checked = st.checkbox(row['Etapa'], value=is_done, key=f"check_{i}")
                
                if checked != is_done:
                    _, ws_c = pegar_planilha_escrita()
                    novo_status = "Concluído" if checked else "Pendente"
                    ws_c.update_cell(i+2, 2, novo_status) # Coluna 2 é Status
                    st.toast(f"Status de {row['Etapa']} atualizado!")
                    st.cache_data.clear()
                    time.sleep(0.5)
                    st.rerun()

    # 2. Coluna Direita: Formulário de Custos
    with col_form:
        st.subheader("📝 Novo Gasto")
        with st.form("form_custos", clear_on_submit=True):
            c1, c2 = st.columns(2)
            data_input = c1.date_input("Data")
            descricao = c2.text_input("Descrição (ex: Cimento CP-II)")
            
            c3, c4, c5 = st.columns(3)
            qtd = c3.number_input("Qtd", min_value=0.0, value=1.0)
            unidade = c4.selectbox("Unidade", ["un", "m", "m²", "m³", "kg", "saco", "dia", "h"])
            valor_un = c5.number_input("Valor Unitário (R$)", min_value=0.0)
            
            lista_etapas = df_cronograma['Etapa'].tolist() if not df_cronograma.empty else ["Geral"]
            etapa_vinc = st.selectbox("Vincular à Etapa", lista_etapas)
            classe = st.selectbox("Classe de Custo", ["Material", "Mão de Obra", "Equipamento", "Administrativo"])
            
            enviado = st.form_submit_button("💾 Salvar Lançamento")
            
            if enviado:
                ws_custos, _ = pegar_planilha_escrita()
                total_calc = qtd * valor_un
                # Ordem: Data, Desc, Qtd, Un, Valor, Total, Classe, Subclasse, Etapa
                ws_custos.append_row([
                    str(data_input), descricao, qtd, unidade, valor_un, total_calc, classe, "-", etapa_vinc
                ])
                st.success(f"Gasto de R$ {total_calc:.2f} salvo com sucesso!")
                st.cache_data.clear()
                st.rerun()

# --- ABA 2: DASHBOARD ---
with tab2:
    st.header("Análise: Previsto x Realizado")
    
    # Editor de Orçamento Rápido
    with st.expander("⚙️ Definir/Editar Orçamento das Etapas"):
        c_input1, c_input2, c_btn = st.columns([2, 1, 1])
        if not df_cronograma.empty:
            etapa_edit = c_input1.selectbox("Selecione a Etapa:", df_cronograma['Etapa'].unique())
            
            # Tenta pegar valor atual
            val_atual = df_cronograma.loc[df_cronograma['Etapa'] == etapa_edit, 'Orcamento'].values[0]
            val_atual = limpar_dinheiro(val_atual) if val_atual else 0.0
            
            novo_orcamento = c_input2.number_input("Meta de Orçamento (R$):", value=float(val_atual))
            
            if c_btn.button("Atualizar Meta"):
                _, ws_c = pegar_planilha_escrita()
                cell = ws_c.find(etapa_edit)
                # Procura a coluna Orcamento
                try:
                    col_idx = ws_c.find("Orcamento").col
                    ws_c.update_cell(cell.row, col_idx, novo_orcamento)
                    st.success("Meta atualizada!")
                    st.cache_data.clear()
                    time.sleep(1)
                    st.rerun()
                except:
                    st.error("Erro: Coluna 'Orcamento' não encontrada na planilha.")

    # Gráficos e KPIs
    if not df_custos.empty and not df_cronograma.empty:
        # Prepara dados
        gastos = df_custos.groupby('etapa')['total'].sum().reset_index()
        # Merge (Cronograma + Gastos)
        resumo = pd.merge(df_cronograma, gastos, left_on='Etapa', right_on='etapa', how='left').fillna(0)
        
        # Seleciona e renomeia
        resumo = resumo[['Etapa', 'Orcamento', 'total']]
        resumo.columns = ['Etapa', 'Orçamento (Meta)', 'Gasto Real']
        
        # KPIs
        total_meta = resumo['Orçamento (Meta)'].sum()
        total_real = resumo['Gasto Real'].sum()
        saldo = total_meta - total_real
        
        k1, k2, k3 = st.columns(3)
        k1.metric("Orçamento Total", f"R$ {total_meta:,.2f}")
        k2.metric("Gasto Executado", f"R$ {total_real:,.2f}")
        k3.metric("Saldo Disponível", f"R$ {saldo:,.2f}", delta=saldo)
        
        st.divider()
        
        # Gráfico
        st.subheader("Gráfico de Acompanhamento Financeiro")
        resumo_chart = resumo.set_index('Etapa')
        st.bar_chart(resumo_chart)
        
        # Tabela Detalhada
        st.dataframe(resumo, use_container_width=True)
    else:
        st.info("Insira dados de custos e defina o orçamento para ver os gráficos.")

# --- ABA 3: EXPORTAÇÃO ---
with tab3:
    st.header("🖨️ Central de Relatórios")
    col_pdf, col_excel = st.columns(2)
    
    with col_pdf:
        st.info("📄 Relatório Executivo (PDF)")
        st.write("Resumo para envio ao cliente.")
        if st.button("Gerar PDF"):
            if not df_custos.empty:
                pdf_data = gerar_pdf(df_custos, df_cronograma)
                st.download_button("⬇️ Baixar PDF", pdf_data, "relatorio_obra.pdf", "application/pdf")
            else:
                st.warning("Sem dados.")

    with col_excel:
        st.info("📊 Planilha Completa (Excel)")
        st.write("Dados brutos para contabilidade.")
        if st.button("Gerar Excel"):
            if not df_custos.empty:
                excel_data = to_excel(df_custos)
                st.download_button("⬇️ Baixar Excel (.xlsx)", excel_data, "dados_obra.xlsx")
            else:
                st.warning("Sem dados.")
