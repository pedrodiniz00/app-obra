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
COLS_CUSTOS = ["Data", "Codigo", "Descricao", "Qtd", "Unidade", "Valor", "Total", "Classe", "Etapa"]
COLS_MATERIAIS = ["Codigo", "Nome", "Unidade", "Preco_Ref"]

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
        
    return sh.sheet1, ws_crono, ws_mat

@st.cache_data(ttl=5)
def carregar_dados_completo():
    client = conectar_gsheets()
    if not client: return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    
    sh = client.open("Dados_Obra")

    # 1. CUSTOS
    try:
        ws = sh.sheet1
        if ws.row_values(1) != COLS_CUSTOS:
            ws.update(range_name="A1:I1", values=[COLS_CUSTOS])
        
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
        if df_materiais.empty:
            df_materiais = pd.DataFrame(columns=COLS_MATERIAIS)
        # Cria coluna row_num para saber onde editar
        df_materiais['row_num'] = df_materiais.index + 2
    except:
        df_materiais = pd.DataFrame(columns=COLS_MATERIAIS)

    return df_custos, df_crono, df_materiais

# --- 3. INTERFACE ---
st.title("🏗️ Gestor de Obras ERP")
df_custos, df_cronograma, df_materiais = carregar_dados_completo()

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
                _, ws_c, _ = pegar_planilhas_escrita()
                ws_c.update_cell(i+2, 2, "Concluído" if check else "Pendente")
                st.cache_data.clear()
                st.rerun()

    st.divider()
    if st.button("Sair"):
        st.session_state["password_correct"] = False
        st.rerun()

# ==============================================================================
# ÁREA DE GESTÃO DE MATERIAIS (CADASTRO E EDIÇÃO)
# ==============================================================================
st.subheader("📦 Gestão de Materiais")

col_cad, col_edit = st.columns(2)

# --- 1. CADASTRO NOVO ---
with col_cad:
    with st.expander("➕ Cadastrar Novo Material", expanded=True):
        with st.form("form_cadastro_material", clear_on_submit=True):
            novo_cod = st.text_input("Código (ex: 101)")
            novo_nome = st.text_input("Nome do Material")
            
            c_un, c_pre = st.columns(2)
            novo_un = c_un.selectbox("Unidade", ["un", "m", "kg", "saco", "m²", "m³", "sc", "lt"])
            novo_ref = c_pre.number_input("Preço Ref (Opcional)", 0.0)
            
            if st.form_submit_button("Cadastrar"):
                if novo_cod and novo_nome:
                    if not df_materiais.empty and str(novo_cod) in df_materiais['Codigo'].astype(str).values:
                        st.error("Código já existe!")
                    else:
                        _, _, ws_mat = pegar_planilhas_escrita()
                        ws_mat.append_row([novo_cod, novo_nome, novo_un, novo_ref])
                        st.success("Cadastrado!")
                        st.cache_data.clear()
                        time.sleep(1)
                        st.rerun()
                else:
                    st.warning("Preencha Código e Nome.")

# --- 2. EDIÇÃO (O QUE VOCÊ PEDIU) ---
with col_edit:
    with st.expander("✏️ Editar/Alterar Material Existente", expanded=True):
        if df_materiais.empty:
            st.info("Nenhum material cadastrado.")
        else:
            # Cria lista para seleção
            df_materiais['Display'] = df_materiais['Codigo'].astype(str) + " - " + df_materiais['Nome']
            lista_edit = df_materiais['Display'].tolist()
            
            sel_edit = st.selectbox("Selecione o Material para Editar:", lista_edit)
            
            if sel_edit:
                # Pega os dados atuais do material selecionado
                cod_atual = sel_edit.split(" - ")[0]
                linha_dados = df_materiais[df_materiais['Codigo'].astype(str) == cod_atual].iloc[0]
                
                # Formulário de Edição
                with st.form("form_edicao"):
                    # O código geralmente não se muda, mas o nome sim
                    st.write(f"**Editando Código:** {cod_atual}")
                    
                    novo_nome_edit = st.text_input("Descrição / Nome", value=linha_dados['Nome'])
                    
                    c_e1, c_e2 = st.columns(2)
                    nova_un_edit = c_e1.selectbox("Unidade", ["un", "m", "kg", "saco", "m²", "m³", "sc", "lt"], index=["un", "m", "kg", "saco", "m²", "m³", "sc", "lt"].index(linha_dados['Unidade']) if linha_dados['Unidade'] in ["un", "m", "kg", "saco", "m²", "m³", "sc", "lt"] else 0)
                    novo_preco_edit = c_e2.number_input("Preço Ref.", value=float(linha_dados['Preco_Ref']) if linha_dados['Preco_Ref'] else 0.0)
                    
                    if st.form_submit_button("💾 Salvar Alterações"):
                        _, _, ws_mat = pegar_planilhas_escrita()
                        
                        # Acha a linha no Google Sheets
                        linha_gs = linha_dados['row_num']
                        
                        # Atualiza as colunas (B=Nome, C=Unidade, D=Preço)
                        ws_mat.update_cell(linha_gs, 2, novo_nome_edit)
                        ws_mat.update_cell(linha_gs, 3, nova_un_edit)
                        ws_mat.update_cell(linha_gs, 4, novo_preco_edit)
                        
                        st.success(f"Material {cod_atual} atualizado!")
                        st.cache_data.clear()
                        time.sleep(1)
                        st.rerun()

# --- TABELA DE MATERIAIS CADASTRADOS ---
if not df_materiais.empty:
    with st.expander("Ver Todos os Materiais Cadastrados"):
        st.dataframe(df_materiais[['Codigo', 'Nome', 'Unidade', 'Preco_Ref']], use_container_width=True)

# --- ÁREA DE LANÇAMENTO ---
st.divider()
st.subheader("📝 Lançamento de Despesas")

if not df_materiais.empty:
    # Lógica de seleção inteligente
    df_materiais['Display'] = df_materiais['Codigo'].astype(str) + " - " + df_materiais['Nome']
    lista_opcoes = df_materiais['Display'].tolist()
    
    escolha = st.selectbox("Buscar Produto (Digite para filtrar):", [""] + lista_opcoes)
    
    cod_sel, nome_sel, un_sug, preco_sug = "", "", "un", 0.0
    
    if escolha:
        cod_sel = escolha.split(" - ")[0]
        item = df_materiais[df_materiais['Codigo'].astype(str) == cod_sel].iloc[0]
        nome_sel = item['Nome']
        un_sug = item['Unidade']
        preco_sug = float(item['Preco_Ref']) if item['Preco_Ref'] else 0.0

    with st.form("form_lancamento", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        dt = c1.date_input("Data")
        c2.text_input("Material", value=nome_sel, disabled=True)
        val = c3.number_input("Valor Unitário", min_value=0.0, value=preco_sug)
        
        c4, c5 = st.columns(2)
        qtd = c4.number_input("Quantidade", min_value=0.0, value=1.0)
        etapa = c5.selectbox("Etapa", df_cronograma['Etapa'].tolist() if not df_cronograma.empty else ["Geral"])
        
        if st.form_submit_button("💾 Lançar"):
            if not escolha:
                st.error("Selecione um material!")
            else:
                ws, _, _ = pegar_planilhas_escrita()
                ws.append_row([str(dt), cod_sel, nome_sel, qtd, un_sug, val, val*qtd, "Material", etapa])
                st.success("Lançado!")
                st.cache_data.clear()
                time.sleep(1)
                st.rerun()

# --- HISTÓRICO ---
st.divider()
st.subheader("📋 Histórico")

if not df_custos.empty:
    orc = df_cronograma['Orcamento'].sum() if 'Orcamento' in df_cronograma.columns else 0
    real = df_custos['Total'].sum() if 'Total' in df_custos.columns else 0
    st.metric("Saldo da Obra", f"R$ {orc-real:,.2f}", delta=orc-real)

    df_show = df_custos.copy()
    df_show.insert(0, "Excluir", False)
    cols = ["Excluir", "Data", "Descricao", "Qtd", "Unidade", "Valor", "Total", "Etapa"]
    
    edited = st.data_editor(
        df_show[[c for c in cols if c in df_show.columns]], 
        hide_index=True, 
        use_container_width=True,
        disabled=["Data", "Descricao", "Total"]
    )
    
    dels = edited[edited["Excluir"]==True]
    if not dels.empty and st.button("🗑️ Confirmar Exclusão"):
        ws, _, _ = pegar_planilhas_escrita()
        rows = df_custos.loc[dels.index, "row_num"].tolist()
        rows.sort(reverse=True)
        for r in rows: ws.delete_rows(r)
        st.success("Apagado!")
        st.cache_data.clear()
        st.rerun()
