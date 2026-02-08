import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from fpdf import FPDF
import time
from datetime import datetime

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Gestão de Obra PRO", layout="wide", page_icon="🏗️")

# Definição das colunas padrão
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

# --- 2. CONEXÃO E FUNÇÕES AUXILIARES ---
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
    
    try:
        sh = client.open("Dados_Obra")
    except:
        return pd.DataFrame(), pd.DataFrame()

    # --- CUSTOS ---
    try:
        ws = sh.sheet1
        # Verifica cabeçalho
        headers_atuais = ws.row_values(1)
        if headers_atuais != COLS_PADRAO:
            # AQUI ESTAVA O ERRO - Corrigido com parênteses certos e update seguro
            ws.update(range_name="A1:I1", values=[COLS_PADRAO])
            time.sleep(1)
        
        dados = ws.get_all_records()
        df_custos = pd.DataFrame(dados)
        
        if not df_custos.empty:
            # Cria coluna auxiliar com numero da linha (row_num)
            # Linha 1 é Header. Dados começam na 2. O indice do Pandas começa em 0.
            # Logo: Linha Excel = Index + 2
            df_custos['row_num'] = df_custos.index + 2
            
            if 'Total' in df_custos.columns:
                df_custos['Total'] = df_custos['Total'].apply(limpar_dinheiro)
            if 'Valor' in df_custos.columns:
                df_custos['Valor'] = df_custos['Valor'].apply(limpar_dinheiro)
                
    except Exception as e:
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

# --- SIDEBAR (CRONOGRAMA) ---
with st.sidebar:
    st.header("📅 Cronograma")
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
    with st.expander("⚙️ Gerenciar Etapas"):
        nova = st.text_input("Nova Etapa")
        if st.button("➕ Criar"):
            _, ws_c = pegar_planilha_escrita()
            ws_c.append_row([nova, "Pendente", 0])
            st.cache_data.clear()
            st.rerun()
        
        if not df_cronograma.empty:
            st.write("")
            opcoes_remocao = df_cronograma['Etapa'].unique()
            rem = st.selectbox("Apagar Etapa:", opcoes_remocao)
            if st.button("🗑️ Excluir Etapa"):
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

# --- DASHBOARD ---
if not df_custos.empty and not df_cronograma.empty:
    orc = df_cronograma['Orcamento'].sum() if 'Orcamento' in df_cronograma.columns else 0
    real = df_custos['Total'].sum() if 'Total' in df_custos.columns else 0
    k1, k2, k3 = st.columns(3)
    k1.metric("Orçamento", f"R$ {orc:,.2f}")
    k2.metric("Gasto Real", f"R$ {real:,.2f}")
    k3.metric("Saldo", f"R$ {orc-real:,.2f}", delta=orc-real)

# --- LANÇAR GASTOS ---
with st.expander("➕ Lançar Novo Gasto", expanded=True):
    with st.form("form_gasto", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        dt = c1.date_input("Data")
        desc = c2.text_input("Descrição")
        val = c3.number_input("Valor Unitário (R$)", 0.0)
        c4, c5, c6 = st.columns(3)
        qtd = c4.number_input("Quantidade", 1.0)
        un = c5.selectbox("Un", ["un","m","kg","saco","m²","m³","dia"])
        lista_etapas = df_cronograma['Etapa'].tolist() if not df_cronograma.empty else ["Geral"]
        etapa = c6.selectbox("Etapa", lista_etapas)
        
        if st.form_submit_button("💾 Salvar Gasto"):
            ws, _ = pegar_planilha_escrita()
            total_calc = val * qtd
            ws.append_row([str(dt), desc, qtd, un, val, total_calc, "Material", "-", etapa])
            st.success("Salvo!")
            st.cache_data.clear()
            st.rerun()

# --- HISTÓRICO COM EXCLUSÃO (TABELA DELETÁVEL) ---
st.divider()
st.subheader("📋 Histórico e Gestão")

if not df_custos.empty:
    # Cria uma cópia para o editor
    df_editor = df_custos.copy()
    # Insere coluna de Checkbox no inicio
    df_editor.insert(0, "Excluir", False)
    
    colunas_visiveis = ["Excluir", "Data", "Descricao", "Etapa", "Qtd", "Unidade", "Valor", "Total"]
    # Filtra apenas colunas que realmente existem para evitar erros
    colunas_finais = [c for c in colunas_visiveis if c in df_editor.columns]
    
    # Exibe o editor na tela
    df_editado = st.data_editor(
        df_editor[colunas_finais],
        column_config={
            "Excluir": st.column_config.CheckboxColumn(
                "Apagar?",
                help="Marque para excluir",
                default=False,
            )
        },
        disabled=["Data", "Descricao", "Etapa", "Qtd", "Unidade", "Valor", "Total"],
        hide_index=True,
        use_container_width=True
    )

    # Verifica o que foi marcado
    linhas_para_excluir = df_editado[df_editado["Excluir"] == True]
    
    if not linhas_para_excluir.empty:
        st.warning(f"⚠️ {len(linhas_para_excluir)} item(ns) selecionado(s) para exclusão.")
        
        if st.button("🗑️ Confirmar Exclusão", type="primary"):
            ws, _ = pegar_planilha_escrita()
            
            # Recupera o índice original da linha no Google Sheets
            # (row_num foi calculado lá no carregar_dados)
            indices = linhas_para_excluir.index
            # Mapeia para o numero da linha real
            rows_to_delete = df_custos.loc[indices, "row_num"].tolist()
            
            # Ordena reverso para apagar de baixo para cima (segurança)
            rows_to_delete.sort(reverse=True)
            
            for r in rows_to_delete:
                ws.delete_rows(r)
            
            st.success("Itens excluídos!")
            st.cache_data.clear()
            time.sleep(1)
            st.rerun()

    # Botão PDF
    st.divider()
    if st.button("📄 Baixar PDF do Relatório"):
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", "B", 16)
        pdf.cell(0, 10, "Relatorio de Custos", 0, 1, "C")
        pdf.set_font("Arial", "", 12)
        pdf.ln(10)
        
        soma_total = df_custos['Total'].sum() if 'Total' in df_custos.columns else 0
        pdf.cell(0, 10, f"Total Gasto: R$ {soma_total:,.2f}", 0, 1)
        
        st.download_button("Download PDF", pdf.output(dest='S').encode('latin-1'), "relatorio.pdf")

else:
    st.info("Nenhum lançamento encontrado.")
