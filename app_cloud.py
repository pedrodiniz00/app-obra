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
# 1. LOGIN
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
# 2. CONEXÃO E CORREÇÃO DE PLANILHA (O SEGREDO ESTÁ AQUI)
# ==============================================================================
def limpar_dinheiro(valor):
    if valor is None: return 0.0
    if isinstance(valor, (int, float)): return float(valor)
    if isinstance(valor, str):
        try:
            limpo = valor.replace('R$', '').replace('.', '').replace(',', '.').strip()
            return float(limpo) if limpo else 0.0
        except: return 0.0
    return 0.0

@st.cache_resource
def conectar_gsheets():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), scope)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Erro de Conexão: {e}")
        return None

def corrigir_cabecalhos(ws, tipo):
    """Verifica se a linha 1 está certa. Se não estiver, cria o cabeçalho."""
    try:
        cabecalho_atual = ws.row_values(1)
        
        # Definição dos cabeçalhos corretos
        if tipo == "custos":
            cols_corretas = ['data', 'descricao', 'quantidade', 'unidade', 'valor_un', 'total', 'classe', 'subclasse', 'etapa']
        else: # cronograma
            cols_corretas = ['Etapa', 'Status', 'Orcamento']

        # Se a linha 1 estiver vazia OU tiver números (ex: o erro '10'), REFAZ
        precisa_corrigir = False
        if not cabecalho_atual:
            precisa_corrigir = True
        else:
            # Se a primeira célula for um número ou data, é sinal que o cabeçalho sumiu
            prim_cel = str(cabecalho_atual[0])
            if any(char.isdigit() for char in prim_cel): 
                precisa_corrigir = True
            # Se não tiver as colunas essenciais
            elif tipo == "custos" and "total" not in cabecalho_atual:
                precisa_corrigir = True
        
        if precisa_corrigir:
            st.toast(f"Corrigindo cabeçalho da aba {tipo}...", icon="🔧")
            # Insere a linha de cabeçalho na posição 1, empurrando o resto para baixo
            ws.insert_row(cols_corretas, index=1)
            return True
    except:
        pass
    return False

def pegar_planilha_escrita():
    client = conectar_gsheets()
    sh = client.open("Dados_Obra")
    return sh.sheet1, sh.worksheet("Cronograma")

@st.cache_data(ttl=5)
def carregar_dados():
    client = conectar_gsheets()
    if not client: return pd.DataFrame(), pd.DataFrame()
    
    try:
        sh = client.open("Dados_Obra")
    except:
        return pd.DataFrame(), pd.DataFrame()

    # --- CUSTOS ---
    try:
        ws_custos = sh.sheet1
        # AUTO-CORREÇÃO ANTES DE LER
        corrigir_cabecalhos(ws_custos, "custos")
        
        dados = ws_custos.get_all_records()
        df_custos = pd.DataFrame(dados)
        
        # Limpa dinheiro
        if not df_custos.empty:
            for c in ['total', 'valor_un', 'quantidade']:
                if c in df_custos.columns:
                    df_custos[c] = df_custos[c].apply(limpar_dinheiro)
    except: df_custos = pd.DataFrame()

    # --- CRONOGRAMA ---
    try:
        ws_crono = sh.worksheet("Cronograma")
        corrigir_cabecalhos(ws_crono, "cronograma")
        
        dados_c = ws_crono.get_all_records()
        df_crono = pd.DataFrame(dados_c)
        
        if not df_crono.empty and 'Orcamento' in df_crono.columns:
            df_crono['Orcamento'] = df_crono['Orcamento'].apply(limpar_dinheiro)
    except:
        # Se não existir, cria
        try:
            ws_crono = sh.add_worksheet("Cronograma", 20, 5)
            ws_crono.append_row(['Etapa', 'Status', 'Orcamento'])
            df_crono = pd.DataFrame()
        except: df_crono = pd.DataFrame()
        
    return df_custos, df_crono

# ==============================================================================
# 3. INTERFACE
# ==============================================================================
st.title("🏗️ Gestor de Obras")
df_custos, df_cronograma = carregar_dados()

# BARRA LATERAL
with st.sidebar:
    st.header("📅 Cronograma")
    if not df_cronograma.empty:
        # Progresso
        total = len(df_cronograma)
        concluidos = len(df_cronograma[df_cronograma['Status'] == 'Concluído'])
        prog = concluidos / total if total > 0 else 0
        st.progress(prog)
        st.caption(f"{int(prog*100)}% Concluído")
        
        st.divider()
        # Checklist
        for i, row in df_cronograma.iterrows():
            nome = row['Etapa'] if 'Etapa' in row else f"Etapa {i}"
            status = row['Status'] if 'Status' in row else "Pendente"
            is_done = (status == 'Concluído')
            
            if st.checkbox(nome, value=is_done, key=f"ck_{i}") != is_done:
                _, ws_c = pegar_planilha_escrita()
                ws_c.update_cell(i+2, 2, "Concluído" if not is_done else "Pendente")
                st.cache_data.clear()
                time.sleep(0.5)
                st.rerun()
    
    # Gestão de Etapas
    st.divider()
    with st.expander("⚙️ Gerenciar Etapas"):
        nova = st.text_input("Nova Etapa:")
        if st.button("➕ Adicionar"):
            if nova:
                _, ws_c = pegar_planilha_escrita()
                ws_c.append_row([nova, "Pendente", 0])
                st.success("Criado!")
                st.cache_data.clear()
                st.rerun()
        
        if not df_cronograma.empty and 'Etapa' in df_cronograma.columns:
            st.write("---")
            rem = st.selectbox("Apagar:", df_cronograma['Etapa'].unique())
            if st.button("🗑️ Excluir"):
                _, ws_c = pegar_planilha_escrita()
                try:
                    cell = ws_c.find(rem)
                    ws_c.delete_rows(cell.row)
                    st.success("Apagado!")
                    st.cache_data.clear()
                    st.rerun()
                except: pass
                
    st.divider()
    if st.button("Sair"):
        st.session_state["password_correct"] = False
        st.rerun()

# KPIs PRINCIPAIS
if not df_cronograma.empty and not df_custos.empty:
    orc = df_cronograma['Orcamento'].sum() if 'Orcamento' in df_cronograma.columns else 0
    real = df_custos['total'].sum() if 'total' in df_custos.columns else 0
    saldo = orc - real
    
    k1, k2, k3 = st.columns(3)
    k1.metric("Orçamento", f"R$ {orc:,.2f}")
    k2.metric("Gasto Real", f"R$ {real:,.2f}")
    k3.metric("Saldo", f"R$ {saldo:,.2f}", delta=saldo)

# FORMULÁRIO
with st.expander("➕ Novo Gasto", expanded=True):
    with st.form("gasto_form", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        dt = c1.date_input("Data")
        desc = c2.text_input("Descrição")
        val = c3.number_input("Valor Unit.", min_value=0.0)
        
        c4, c5, c6 = st.columns(3)
        qtd = c4.number_input("Qtd", 1.0)
        un = c5.selectbox("Unidade", ["un", "m", "kg", "saco", "dia", "h"])
        
        opts = df_cronograma['Etapa'].tolist() if not df_cronograma.empty and 'Etapa' in df_cronograma.columns else ["Geral"]
        etapa = c6.selectbox("Etapa", opts)
        
        if st.form_submit_button("💾 Salvar"):
            ws1, _ = pegar_planilha_escrita()
            total = val * qtd
            ws1.append_row([str(dt), desc, qtd, un, val, total, "Material", "-", etapa])
            st.success("Salvo!")
            st.cache_data.clear()
            st.rerun()

# TABELA
st.divider()
col_txt, col_pdf = st.columns([4, 1])
col_txt.subheader("Histórico")

with col_pdf:
    if st.button("📄 PDF"):
        if not df_custos.empty:
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", "B", 16)
            pdf.cell(0, 10, "Relatorio de Obra", 0, 1, "C")
            pdf.set_font("Arial", "", 12)
            pdf.ln(10)
            
            # Resumo
            pdf.cell(0, 10, f"Total Gasto: R$ {df_custos['total'].sum():,.2f}", 0, 1)
            pdf.ln(5)
            
            # Etapas
            pdf.cell(0, 10, "Etapas:", 0, 1)
            if not df_cronograma.empty:
                for _, r in df_cronograma.iterrows():
                    e = r['Etapa'] if 'Etapa' in r else '?'
                    s = r['Status'] if 'Status' in r else '?'
                    pdf.cell(0, 8, f"- {e}: {s}", 0, 1)
                    
            pdf_bytes = pdf.output(dest='S').encode('latin-1')
            st.download_button("Download", pdf_bytes, "relatorio.pdf", "application/pdf")

if not df_custos.empty:
    st.dataframe(df_custos.sort_index(ascending=False), use_container_width=True)
