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
COLS_CUSTOS = ["Data", "Codigo", "Descricao", "Qtd", "Unidade", "Valor", "Total", "Classe", "Etapa", "Fornecedor"]
COLS_MATERIAIS = ["Codigo", "Nome", "Unidade", "Preco_Ref"]
COLS_FORNECEDORES = ["Codigo", "Nome", "Telefone", "Categoria"]

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

def proximo_id(df, col_nome='Codigo'):
    """Calcula o próximo ID baseado no maior número existente."""
    if df.empty: return 1
    try:
        # Converte para numero, ignora erros (textos viram NaN)
        numeros = pd.to_numeric(df[col_nome], errors='coerce')
        maior = numeros.max()
        if pd.isna(maior): return 1
        return int(maior) + 1
    except:
        return 1

@st.cache_resource
def conectar_gsheets():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), scope)
    return gspread.authorize(creds)

def pegar_planilhas_escrita():
    client = conectar_gsheets()
    sh = client.open("Dados_Obra")
    
    # Aba Cronograma
    try: ws_crono = sh.worksheet("Cronograma")
    except: ws_crono = sh.add_worksheet("Cronograma", 20, 5)
    
    # Aba Materiais
    try: ws_mat = sh.worksheet("Materiais")
    except: 
        ws_mat = sh.add_worksheet("Materiais", 100, 4)
        ws_mat.append_row(COLS_MATERIAIS)

    # Aba Fornecedores
    try: ws_forn = sh.worksheet("Fornecedores")
    except:
        ws_forn = sh.add_worksheet("Fornecedores", 100, 4)
        ws_forn.append_row(COLS_FORNECEDORES)
        
    return sh.sheet1, ws_crono, ws_mat, ws_forn

@st.cache_data(ttl=5)
def carregar_dados_completo():
    client = conectar_gsheets()
    if not client: return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    
    sh = client.open("Dados_Obra")

    # 1. CUSTOS
    try:
        ws = sh.sheet1
        dados = ws.get_all_records()
        df_custos = pd.DataFrame(dados)
        if not df_custos.empty:
            df_custos['row_num'] = df_custos.index + 2
            if 'Fornecedor' not in df_custos.columns: df_custos['Fornecedor'] = "-"
            for col in ['Total', 'Valor', 'Qtd']:
                if col in df_custos.columns:
                    df_custos[col] = df_custos[col].apply(limpar_dinheiro)
    except: df_custos = pd.DataFrame()

    # 2. CRONOGRAMA
    try:
        ws_c = sh.worksheet("Cronograma")
        df_crono = pd.DataFrame(ws_c.get_all_records())
        if not df_crono.empty and 'Orcamento' in df_crono.columns:
            df_crono['Orcamento'] = df_crono['Orcamento'].apply(limpar_dinheiro)
    except: df_crono = pd.DataFrame()

    # 3. MATERIAIS
    try:
        ws_m = sh.worksheet("Materiais")
        vals_m = ws_m.get_all_records()
        df_materiais = pd.DataFrame(vals_m)
        if df_materiais.empty: df_materiais = pd.DataFrame(columns=COLS_MATERIAIS)
        df_materiais['row_num'] = df_materiais.index + 2
    except: df_materiais = pd.DataFrame(columns=COLS_MATERIAIS)

    # 4. FORNECEDORES
    try:
        ws_f = sh.worksheet("Fornecedores")
        vals_f = ws_f.get_all_records()
        df_fornecedores = pd.DataFrame(vals_f)
        if df_fornecedores.empty: df_fornecedores = pd.DataFrame(columns=COLS_FORNECEDORES)
        df_fornecedores['row_num'] = df_fornecedores.index + 2
    except: df_fornecedores = pd.DataFrame(columns=COLS_FORNECEDORES)

    return df_custos, df_crono, df_materiais, df_fornecedores

# --- 3. INTERFACE ---
st.title("🏗️ Gestor de Obras ERP")
df_custos, df_cronograma, df_materiais, df_fornecedores = carregar_dados_completo()

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
                _, ws_c, _, _ = pegar_planilhas_escrita()
                ws_c.update_cell(i+2, 2, "Concluído" if check else "Pendente")
                st.cache_data.clear()
                st.rerun()

    st.divider()
    if st.button("Sair"):
        st.session_state["password_correct"] = False
        st.rerun()

# --- CADASTROS GERAIS ---
st.subheader("📦 Cadastros (Código Automático)")

# TAB 1: MATERIAIS
# TAB 2: FORNECEDORES
tab_mat, tab_forn = st.tabs(["Materiais", "Fornecedores"])

with tab_mat:
    c_form, c_lista = st.columns([1, 2])
    
    with c_form:
        st.write("**Novo Material**")
        # --- CÁLCULO DO ID AUTOMÁTICO ---
        prox_cod_mat = proximo_id(df_materiais)
        
        with st.form("form_mat"):
            # Campo desabilitado mostrando o código
            st.text_input("Código Automático", value=prox_cod_mat, disabled=True)
            
            nome = st.text_input("Nome do Material")
            un = st.selectbox("Unidade", ["un","m","kg","sc","m²","m³","lt","cx"])
            ref = st.number_input("Preço Ref (R$)", 0.0)
            
            if st.form_submit_button("➕ Cadastrar"):
                if nome:
                    _, _, ws_m, _ = pegar_planilhas_escrita()
                    ws_m.append_row([prox_cod_mat, nome, un, ref])
                    st.success(f"Material {prox_cod_mat} cadastrado!")
                    st.cache_data.clear()
                    time.sleep(1)
                    st.rerun()
                else:
                    st.warning("Digite o nome.")
                    
    with c_lista:
        st.write("**Lista de Materiais**")
        if not df_materiais.empty:
            st.dataframe(df_materiais[['Codigo', 'Nome', 'Unidade']], height=250, use_container_width=True)

with tab_forn:
    c_form_f, c_lista_f = st.columns([1, 2])
    
    with c_form_f:
        st.write("**Novo Fornecedor**")
        # --- CÁLCULO DO ID AUTOMÁTICO ---
        prox_cod_forn = proximo_id(df_fornecedores)
        
        with st.form("form_forn"):
            # Campo desabilitado
            st.text_input("Código Automático", value=prox_cod_forn, disabled=True)
            
            fn = st.text_input("Nome da Empresa")
            ft = st.text_input("Telefone")
            fcat = st.selectbox("Categoria", ["Material", "Serviço", "Mão de Obra"])
            
            if st.form_submit_button("➕ Cadastrar"):
                if fn:
                    _, _, _, ws_f = pegar_planilhas_escrita()
                    ws_f.append_row([prox_cod_forn, fn, ft, fcat])
                    st.success(f"Fornecedor {prox_cod_forn} cadastrado!")
                    st.cache_data.clear()
                    time.sleep(1)
                    st.rerun()
                else:
                    st.warning("Digite o nome.")

    with c_lista_f:
        st.write("**Lista de Fornecedores**")
        if not df_fornecedores.empty:
            st.dataframe(df_fornecedores[['Codigo', 'Nome', 'Telefone']], height=250, use_container_width=True)

# --- LANÇAMENTO ---
st.divider()
st.subheader("📝 Lançamento de Despesas")

if df_materiais.empty:
    st.warning("Cadastre materiais acima primeiro.")
else:
    # Filtro Material
    df_materiais['Display'] = df_materiais['Codigo'].astype(str) + " - " + df_materiais['Nome']
    escolha = st.selectbox("Produto:", [""] + df_materiais['Display'].tolist())
    
    # Filtro Fornecedor
    lista_forn = ["Sem Fornecedor"]
    if not df_fornecedores.empty:
        df_fornecedores['DisplayF'] = df_fornecedores['Codigo'].astype(str) + " - " + df_fornecedores['Nome']
        lista_forn += df_fornecedores['DisplayF'].tolist()
    
    escolha_forn = st.selectbox("Fornecedor:", lista_forn)

    nome_sel, un_sug, preco_sug, cod_sel = "", "un", 0.0, ""
    if escolha:
        cod_sel = escolha.split(" - ")[0]
        item = df_materiais[df_materiais['Codigo'].astype(str) == cod_sel].iloc[0]
        nome_sel = item['Nome']
        un_sug = item['Unidade']
        preco_sug = float(item['Preco_Ref']) if item['Preco_Ref'] else 0.0

    with st.form("lancar"):
        c1, c2, c3 = st.columns(3)
        dt = c1.date_input("Data")
        c2.text_input("Item", value=nome_sel, disabled=True)
        val = c3.number_input("Valor", value=preco_sug)
        c4, c5 = st.columns(2)
        qtd = c4.number_input("Qtd", 1.0)
        etapa = c5.selectbox("Etapa", df_cronograma['Etapa'].tolist() if not df_cronograma.empty else ["Geral"])
        
        if st.form_submit_button("💾 Salvar"):
            if not escolha:
                st.error("Selecione Material")
            else:
                ws, _, _, _ = pegar_planilhas_escrita()
                if ws.row_values(1) != COLS_CUSTOS:
                    ws.update(range_name="A1:J1", values=[COLS_CUSTOS])
                
                total = val * qtd
                forn_txt = escolha_forn # Salva o texto inteiro "1 - Deposito"
                
                ws.append_row([str(dt), cod_sel, nome_sel, qtd, un_sug, val, total, "Material", etapa, forn_txt])
                st.success("Lançado!")
                st.cache_data.clear()
                time.sleep(1)
                st.rerun()

# --- HISTÓRICO ---
st.divider()
st.subheader("📋 Histórico Geral")

if not df_custos.empty:
    df_show = df_custos.copy()
    if 'Fornecedor' not in df_show.columns: df_show['Fornecedor'] = "-"
    df_show.insert(0, "Excluir", False)
    
    colunas_finais = ["Excluir", "Data", "Fornecedor", "Descricao", "Unidade", "Valor", "Total"]
    cols_existentes = [c for c in colunas_finais if c in df_show.columns]
    
    edited = st.data_editor(
        df_show[cols_existentes],
        hide_index=True,
        use_container_width=True,
        column_config={
            "Excluir": st.column_config.CheckboxColumn("Del?", width="small"),
            "Valor": st.column_config.NumberColumn("Valor Un", format="R$ %.2f"),
            "Total": st.column_config.NumberColumn("Total", format="R$ %.2f")
        },
        disabled=["Data", "Fornecedor", "Descricao", "Unidade", "Valor", "Total"]
    )
    
    dels = edited[edited["Excluir"]==True]
    if not dels.empty and st.button("Confirmar Exclusão"):
        ws, _, _, _ = pegar_planilhas_escrita()
        rows = df_custos.loc[dels.index, "row_num"].tolist()
        rows.sort(reverse=True)
        for r in rows: ws.delete_rows(r)
        st.success("Apagado!")
        st.cache_data.clear()
        st.rerun()



