import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
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

@st.cache_data(ttl=5) # Cache bem curto para atualizar rápido ao adicionar etapas
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

# --- BARRA LATERAL (CRONOGRAMA & GESTÃO) ---
with st.sidebar:
    st.header("📅 Cronograma")
    
    # 1. VISUALIZAÇÃO DO PROGRESSO
    if not df_cronograma.empty:
        concluidos = len(df_cronograma[df_cronograma['Status'] == 'Concluído'])
        total = len(df_cronograma)
        prog = concluidos / total if total > 0 else 0
        st.progress(prog)
        st.caption(f"{int(prog*100)}% Concluído ({concluidos}/{total})")
        
        st.divider()
        st.subheader("Checklist")
        # Checkboxes das etapas existentes
        for i, row in df_cronograma.iterrows():
            is_done = (row['Status'] == 'Concluído')
            checked = st.checkbox(row['Etapa'], value=is_done, key=f"check_{i}")
            
            if checked != is_done:
                _, ws_c = pegar_planilha_escrita()
                ws_c.update_cell(i+2, 2, "Concluído" if checked else "Pendente")
                st.toast("Status Atualizado!")
                st.cache_data.clear()
                time.sleep(0.5)
                st.rerun()
    else:
        st.info("Nenhuma etapa cadastrada.")

    # 2. GERENCIADOR DE ETAPAS (ADICIONAR/REMOVER)
    st.divider()
    with st.expander("⚙️ Gerenciar Etapas"):
        st.write("**Adicionar Nova Etapa**")
        nova_etapa = st.text_input("Nome da etapa (ex: Pintura)")
        if st.button("➕ Adicionar"):
            if nova_etapa:
                _, ws_c = pegar_planilha_escrita()
                # Adiciona: Nome, Status Pendente, Orçamento 0
                ws_c.append_row([nova_etapa, "Pendente", 0])
                st.success(f"Etapa '{nova_etapa}' criada!")
                st.cache_data.clear()
                time.sleep(1)
                st.rerun()
        
        st.divider()
        
        st.write("**Remover Etapa**")
        if not df_cronograma.empty:
            etapa_para_remover = st.selectbox("Selecione para excluir:", df_cronograma['Etapa'].unique())
            if st.button("🗑️ Excluir"):
                _, ws_c = pegar_planilha_escrita()
                try:
                    cell = ws_c.find(etapa_para_remover)
                    ws_c.delete_rows(cell.row)
                    st.success(f"Etapa removida!")
                    st.cache_data.clear()
                    time.sleep(1)
                    st.rerun()
                except:
                    st.error("Erro ao encontrar etapa na planilha.")

    st.divider()
    if st.button("Sair (Logout)"):
        st.session_state["password_correct"] = False
        st.rerun()

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

    # Pequeno editor de orçamento na tela principal também
    with st.expander("💰 Ajustar Metas de Orçamento"):
        c_ed1, c_ed2, c_btn = st.columns([2,1,1])
        etapa_meta = c_ed1.selectbox("Etapa", df_cronograma['Etapa'].unique(), key="meta_sel")
        valor_atual_meta = df_cronograma.loc[df_cronograma['Etapa']==etapa_meta, 'Orcamento'].values[0]
        nova_meta = c_ed2.number_input("Meta R$", value=float(valor_atual_meta))
        if c_btn.button("Atualizar"):
            _, ws_c = pegar_planilha_escrita()
            cell = ws_c.find(etapa_meta)
            col_orc = ws_c.find("Orcamento").col
            ws_c.update_cell(cell.row, col_orc, nova_meta)
            st.success("Meta atualizada!")
            st.cache_data.clear()
            st.rerun()

# 2. FORMULÁRIO DE CADASTRO
with st.expander("➕ Novo Lançamento de Gasto", expanded=True):
    with st.form("form_gasto", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        data = c1.date_input("Data")
        desc = c2.text_input("Descrição")
        valor = c3.number_input("Valor Unit (R$)", min_value=0.0)
        
        c4, c5, c6 = st.columns(3)
        qtd = c4.number_input("Qtd", 1.0)
        un = c5.selectbox("Unidade", ["un", "m", "kg", "saco", "dia", "h", "vb", "m²", "m³"])
        
        lista_etapas = df_cronograma['Etapa'].tolist() if not df_cronograma.empty else ["Geral"]
        etapa = c6.selectbox("Vincular Etapa", lista_etapas)
        
        if st.form_submit_button("💾 Salvar Gasto"):
            ws_1, _ = pegar_planilha_escrita()
            total = qtd * valor
            ws_1.append_row([str(data), desc, qtd, un, valor, total, "Material", "-", etapa])
            st.success("Salvo!")
            st.cache_data.clear()
            st.rerun()

# 3. TABELA DE DADOS E EXPORTAÇÃO
st.divider()
c_tab, c_exp = st.columns([4, 1])
with c_tab:
    st.subheader("📋 Histórico de Gastos")
with c_exp:
    # Botão de Exportar PDF
    from fpdf import FPDF
    class PDF(FPDF):
        def header(self):
            self.set_font('Arial', 'B', 15)
            self.cell(0, 10, 'Relatorio de Obra', 0, 1, 'C')
            self.ln(5)
    
    def gerar_pdf(df, df_c):
        pdf = PDF()
        pdf.add_page()
        pdf.set_font('Arial', '', 12)
        pdf.cell(0, 10, f"Gerado: {datetime.now().strftime('%d/%m/%Y')}", 0, 1)
        if not df.empty:
            pdf.cell(0, 10, f"Total Gasto: R$ {df['total'].sum():,.2f}", 0, 1)
        pdf.ln(5)
        pdf.cell(0, 10, "Etapas:", 0, 1)
        if not df_c.empty:
            for _, r in df_c.iterrows():
                pdf.cell(0, 8, f"- {r['Etapa']}: {r['Status']}", 0, 1)
        return pdf.output(dest='S').encode('latin-1')

    if st.button("📄 Baixar PDF"):
        if not df_custos.empty:
            pdf_bytes = gerar_pdf(df_custos, df_cronograma)
            st.download_button("Clique p/ Download", pdf_bytes, "relatorio.pdf", "application/pdf")

if not df_custos.empty:
    st.dataframe(df_custos.sort_index(ascending=False), use_container_width=True)
