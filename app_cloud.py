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
# 2. CONEXÃO GOOGLE SHEETS (COM CORREÇÃO DE ERROS)
# ==============================================================================
def limpar_dinheiro(valor):
    """Converte texto de dinheiro para numero float de forma segura."""
    if valor is None: return 0.0
    if isinstance(valor, (int, float)): return float(valor)
    
    # Se for texto, limpa
    if isinstance(valor, str):
        if not valor.strip(): return 0.0 # Se estiver vazio, retorna 0
        try:
            limpo = valor.replace('R$', '').replace('.', '').replace(',', '.').strip()
            return float(limpo) if limpo else 0.0
        except:
            return 0.0 # Se falhar, retorna 0
    return 0.0

@st.cache_resource
def conectar_gsheets():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), scope)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"🚨 Erro Fatal de Conexão: {e}")
        return None

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
    except Exception as e:
        st.error(f"❌ Não encontrei a planilha 'Dados_Obra'. Verifique o nome no Google Sheets. Erro: {e}")
        return pd.DataFrame(), pd.DataFrame()

    # --- CUSTOS ---
    try:
        ws_custos = sh.sheet1
        dados_raw = ws_custos.get_all_records()
        df_custos = pd.DataFrame(dados_raw)
        
        # Limpeza de colunas numéricas
        if not df_custos.empty:
            cols_dinheiro = ['total', 'valor_un', 'quantidade']
            for col in cols_dinheiro:
                if col in df_custos.columns:
                    df_custos[col] = df_custos[col].apply(limpar_dinheiro)
    except Exception as e:
        st.warning(f"⚠️ Erro ao ler aba de Custos (sheet1): {e}")
        df_custos = pd.DataFrame()

    # --- CRONOGRAMA ---
    try:
        ws_crono = sh.worksheet("Cronograma")
        dados_crono = ws_crono.get_all_records()
        df_crono = pd.DataFrame(dados_crono)
        
        # Limpeza
        if not df_crono.empty and 'Orcamento' in df_crono.columns:
            df_crono['Orcamento'] = df_crono['Orcamento'].apply(limpar_dinheiro)
            
    except Exception as e:
        # Se a aba não existe, tenta criar
        try:
            ws_crono = sh.add_worksheet("Cronograma", 20, 5)
            ws_crono.append_row(["Etapa", "Status", "Orcamento"])
            st.toast("Aba Cronograma criada automaticamente!")
            df_crono = pd.DataFrame()
        except:
            st.warning(f"⚠️ Erro ao ler aba Cronograma: {e}")
            df_crono = pd.DataFrame()
        
    return df_custos, df_crono

# ==============================================================================
# 3. INTERFACE
# ==============================================================================
st.title("🏗️ Gestor de Obras")

df_custos, df_cronograma = carregar_dados()

# --- BARRA LATERAL ---
with st.sidebar:
    st.header("📅 Cronograma")
    
    if df_cronograma.empty:
        st.warning("Cronograma vazio ou não carregado.")
    else:
        # Progresso
        total = len(df_cronograma)
        concluidos = len(df_cronograma[df_cronograma['Status'] == 'Concluído'])
        prog = concluidos / total if total > 0 else 0
        st.progress(prog)
        st.caption(f"{int(prog*100)}% Concluído")
        
        st.divider()
        st.subheader("Checklist")
        
        # Checkboxes
        for i, row in df_cronograma.iterrows():
            nome_etapa = row['Etapa'] if 'Etapa' in row else f"Etapa {i}"
            status_atual = row['Status'] if 'Status' in row else "Pendente"
            is_done = (status_atual == 'Concluído')
            
            checked = st.checkbox(nome_etapa, value=is_done, key=f"c_{i}")
            
            if checked != is_done:
                _, ws_c = pegar_planilha_escrita()
                ws_c.update_cell(i+2, 2, "Concluído" if checked else "Pendente")
                st.toast("Atualizado!")
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
                st.success("Adicionado!")
                st.cache_data.clear()
                st.rerun()
        
        if not df_cronograma.empty and 'Etapa' in df_cronograma.columns:
            st.write("---")
            rem = st.selectbox("Remover:", df_cronograma['Etapa'].unique())
            if st.button("🗑️ Excluir"):
                _, ws_c = pegar_planilha_escrita()
                try:
                    cell = ws_c.find(rem)
                    ws_c.delete_rows(cell.row)
                    st.success("Removido!")
                    st.cache_data.clear()
                    st.rerun()
                except: st.error("Erro ao excluir.")

    st.divider()
    if st.button("Sair"):
        st.session_state["password_correct"] = False
        st.rerun()

# --- PRINCIPAL ---
if not df_cronograma.empty and not df_custos.empty:
    col1, col2, col3 = st.columns(3)
    
    # Cálculos seguros
    total_orc = df_cronograma['Orcamento'].sum() if 'Orcamento' in df_cronograma.columns else 0
    total_real = df_custos['total'].sum() if 'total' in df_custos.columns else 0
    saldo = total_orc - total_real
    
    col1.metric("Meta (Orçamento)", f"R$ {total_orc:,.2f}")
    col2.metric("Gasto Real", f"R$ {total_real:,.2f}")
    col3.metric("Saldo", f"R$ {saldo:,.2f}", delta=saldo)

# Formulário
with st.expander("➕ Lançar Gasto", expanded=True):
    with st.form("add_gasto", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        dt = c1.date_input("Data")
        desc = c2.text_input("Descrição")
        val = c3.number_input("Valor Unit.", min_value=0.0)
        
        c4, c5, c6 = st.columns(3)
        qtd = c4.number_input("Qtd", 1.0)
        un = c5.selectbox("Unidade", ["un", "m", "kg", "saco", "dia", "h"])
        
        opts = df_cronograma['Etapa'].tolist() if not df_cronograma.empty and 'Etapa' in df_cronograma.columns else ["Geral"]
        etapa = c6.selectbox("Etapa", opts)
        
        if st.form_submit_button("Salvar"):
            ws1, _ = pegar_planilha_escrita()
            total = val * qtd
            ws1.append_row([str(dt), desc, qtd, un, val, total, "Material", "-", etapa])
            st.success("Salvo!")
            st.cache_data.clear()
            st.rerun()

# Tabela e PDF
st.divider()
c_txt, c_pdf = st.columns([4,1])
c_txt.subheader("Histórico")

with c_pdf:
    if st.button("📄 PDF"):
        if not df_custos.empty:
            # Lógica PDF simplificada inline
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", "B", 16)
            pdf.cell(0, 10, "Relatorio de Obra", 0, 1, "C")
            pdf.set_font("Arial", "", 12)
            pdf.ln(10)
            pdf.cell(0, 10, f"Total Gasto: R$ {df_custos['total'].sum():,.2f}", 0, 1)
            pdf_bytes = pdf.output(dest='S').encode('latin-1')
            st.download_button("Baixar", pdf_bytes, "relatorio.pdf", "application/pdf")

if not df_custos.empty:
    st.dataframe(df_custos.sort_index(ascending=False), use_container_width=True)
elif not df_cronograma.empty:
    st.info("Nenhum custo lançado ainda.")
