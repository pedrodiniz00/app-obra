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

    # Aba Fornecedores (NOVA)
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
        # Verifica se tem a coluna Fornecedor, se não, ajusta
        if ws.row_values(1) != COLS_CUSTOS:
            # Se for diferente, vamos tentar atualizar só se estiver muito errado
            # Mas para garantir, vamos assumir a estrutura nova
            pass 
        
        dados = ws.get_all_records()
        df_custos = pd.DataFrame(dados)
        if not df_custos.empty:
            df_custos['row_num'] = df_custos.index + 2
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

    # 4. FORNECEDORES (NOVO)
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

# --- MENU LATERAL ---
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

# ==============================================================================
# ABA 1: GESTÃO DE MATERIAIS
# ==============================================================================
st.subheader("📦 Materiais & Produtos")
with st.expander("Gerenciar Materiais (Cadastro/Edição)", expanded=False):
    col_cad_mat, col_edit_mat = st.columns(2)
    
    # Cadastro Material
    with col_cad_mat:
        st.write("**Novo Material**")
        with st.form("form_mat"):
            cod = st.text_input("Código (ex: 101)")
            nome = st.text_input("Nome")
            c1, c2 = st.columns(2)
            un = c1.selectbox("Un", ["un","m","kg","sc","m²","m³"])
            ref = c2.number_input("R$ Ref", 0.0)
            if st.form_submit_button("Cadastrar Material"):
                if cod and nome:
                    _, _, ws_m, _ = pegar_planilhas_escrita()
                    ws_m.append_row([cod, nome, un, ref])
                    st.success("Salvo!")
                    st.cache_data.clear()
                    time.sleep(1)
                    st.rerun()
    
    # Edição Material
    with col_edit_mat:
        st.write("**Editar Material**")
        if not df_materiais.empty:
            df_materiais['Display'] = df_materiais['Codigo'].astype(str) + " - " + df_materiais['Nome']
            sel = st.selectbox("Selecione:", df_materiais['Display'].tolist(), key="sel_mat_edit")
            if sel:
                cod_atual = sel.split(" - ")[0]
                dado = df_materiais[df_materiais['Codigo'].astype(str)==cod_atual].iloc[0]
                with st.form("edit_mat"):
                    novo_nome = st.text_input("Nome", value=dado['Nome'])
                    c_e1, c_e2 = st.columns(2)
                    nova_un = c_e1.selectbox("Unidade", ["un","m","kg","sc","m²","m³"], index=0) # Simplificado index
                    novo_preco = c_e2.number_input("Preço", value=float(dado['Preco_Ref']) if dado['Preco_Ref'] else 0.0)
                    if st.form_submit_button("Salvar Edição"):
                        _, _, ws_m, _ = pegar_planilhas_escrita()
                        ws_m.update_cell(dado['row_num'], 2, novo_nome)
                        ws_m.update_cell(dado['row_num'], 3, nova_un)
                        ws_m.update_cell(dado['row_num'], 4, novo_preco)
                        st.success("Atualizado!")
                        st.cache_data.clear()
                        time.sleep(1)
                        st.rerun()

# ==============================================================================
# ABA 2: GESTÃO DE FORNECEDORES (NOVO!!!)
# ==============================================================================
st.subheader("🏭 Fornecedores & Parceiros")
with st.expander("Gerenciar Fornecedores (Cadastro/Edição)", expanded=False):
    col_cad_forn, col_edit_forn = st.columns(2)
    
    # Cadastro Fornecedor
    with col_cad_forn:
        st.write("**Novo Fornecedor**")
        with st.form("form_forn"):
            f_cod = st.text_input("Cód/CNPJ (ex: F01)")
            f_nome = st.text_input("Nome da Empresa")
            c_f1, c_f2 = st.columns(2)
            f_tel = c_f1.text_input("Telefone")
            f_cat = c_f2.selectbox("Categoria", ["Material", "Mão de Obra", "Equipamento", "Serviço"])
            
            if st.form_submit_button("Cadastrar Fornecedor"):
                if f_cod and f_nome:
                    _, _, _, ws_f = pegar_planilhas_escrita()
                    ws_f.append_row([f_cod, f_nome, f_tel, f_cat])
                    st.success(f"{f_nome} cadastrado!")
                    st.cache_data.clear()
                    time.sleep(1)
                    st.rerun()
                else:
                    st.warning("Preencha Código e Nome.")

    # Edição Fornecedor
    with col_edit_forn:
        st.write("**Editar Fornecedor**")
        if not df_fornecedores.empty:
            df_fornecedores['Display'] = df_fornecedores['Codigo'].astype(str) + " - " + df_fornecedores['Nome']
            sel_forn = st.selectbox("Selecione:", df_fornecedores['Display'].tolist(), key="sel_forn_edit")
            
            if sel_forn:
                cod_f_atual = sel_forn.split(" - ")[0]
                dado_f = df_fornecedores[df_fornecedores['Codigo'].astype(str)==cod_f_atual].iloc[0]
                
                with st.form("edit_forn"):
                    novo_nome_f = st.text_input("Nome", value=dado_f['Nome'])
                    c_fe1, c_fe2 = st.columns(2)
                    novo_tel_f = c_fe1.text_input("Telefone", value=dado_f['Telefone'])
                    # Tenta achar o index da categoria, se nao der usa 0
                    cats = ["Material", "Mão de Obra", "Equipamento", "Serviço"]
                    idx_cat = cats.index(dado_f['Categoria']) if dado_f['Categoria'] in cats else 0
                    nova_cat_f = c_fe2.selectbox("Categoria", cats, index=idx_cat)
                    
                    if st.form_submit_button("Salvar Fornecedor"):
                        _, _, _, ws_f = pegar_planilhas_escrita()
                        # Atualiza colunas: 2=Nome, 3=Tel, 4=Categoria
                        linha = dado_f['row_num']
                        ws_f.update_cell(linha, 2, novo_nome_f)
                        ws_f.update_cell(linha, 3, novo_tel_f)
                        ws_f.update_cell(linha, 4, nova_cat_f)
                        
                        st.success("Fornecedor atualizado!")
                        st.cache_data.clear()
                        time.sleep(1)
                        st.rerun()

# --- ÁREA DE LANÇAMENTO (COM FORNECEDOR AGORA) ---
st.divider()
st.subheader("📝 Lançamento de Despesas")

if df_materiais.empty:
    st.warning("Cadastre materiais primeiro.")
else:
    # Seleção Material
    df_materiais['Display'] = df_materiais['Codigo'].astype(str) + " - " + df_materiais['Nome']
    escolha = st.selectbox("Produto:", [""] + df_materiais['Display'].tolist())
    
    # Seleção Fornecedor (Opcional)
    lista_forn = ["Sem Fornecedor"]
    if not df_fornecedores.empty:
        lista_forn += df_fornecedores['Nome'].tolist()
    
    escolha_forn = st.selectbox("Fornecedor (Opcional):", lista_forn)

    # Dados pré-carregados
    cod_sel, nome_sel, un_sug, preco_sug = "", "", "un", 0.0
    if escolha:
        cod_sel = escolha.split(" - ")[0]
        item = df_materiais[df_materiais['Codigo'].astype(str) == cod_sel].iloc[0]
        nome_sel = item['Nome']
        un_sug = item['Unidade']
        preco_sug = float(item['Preco_Ref']) if item['Preco_Ref'] else 0.0

    with st.form("lancar_gasto"):
        c1, c2, c3 = st.columns(3)
        dt = c1.date_input("Data")
        c2.text_input("Item", value=nome_sel, disabled=True)
        val = c3.number_input("Valor Unit", value=preco_sug)
        
        c4, c5 = st.columns(2)
        qtd = c4.number_input("Qtd", 1.0)
        etapa = c5.selectbox("Etapa", df_cronograma['Etapa'].tolist() if not df_cronograma.empty else ["Geral"])
        
        if st.form_submit_button("💾 Lançar Gasto"):
            if not escolha:
                st.error("Escolha um material!")
            else:
                ws, _, _, _ = pegar_planilhas_escrita()
                total = val * qtd
                fornecedor_txt = escolha_forn if escolha_forn != "Sem Fornecedor" else "-"
                # Ordem: Data, Cod, Nome, Qtd, Un, Val, Total, Classe, Etapa, FORNECEDOR
                ws.append_row([str(dt), cod_sel, nome_sel, qtd, un_sug, val, total, "Material", etapa, fornecedor_txt])
                st.success("Lançado!")
                st.cache_data.clear()
                time.sleep(1)
                st.rerun()

# --- HISTÓRICO ---
st.divider()
st.subheader("📋 Histórico Geral")

if not df_custos.empty:
    # Se nao tiver coluna fornecedor no historico antigo, nao quebra
    if 'Fornecedor' not in df_custos.columns:
        df_custos['Fornecedor'] = "-"

    df_show = df_custos.copy()
    df_show.insert(0, "Excluir", False)
    
    # Agora mostra Fornecedor na tabela
    cols = ["Excluir", "Data", "Descricao", "Qtd", "Unidade", "Valor", "Total", "Etapa", "Fornecedor"]
    
    edited = st.data_editor(
        df_show[[c for c in cols if c in df_show.columns]], 
        hide_index=True, 
        use_container_width=True,
        disabled=["Data", "Descricao", "Total"]
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
