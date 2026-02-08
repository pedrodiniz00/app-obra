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
    
    # Aba Materiais (NOVA)
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
        # Verifica e corrige cabeçalho
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

    # 3. MATERIAIS (CATÁLOGO)
    try:
        ws_m = sh.worksheet("Materiais")
        vals_m = ws_m.get_all_records()
        df_materiais = pd.DataFrame(vals_m)
        # Garante que as colunas existem mesmo se vazia
        if df_materiais.empty:
            df_materiais = pd.DataFrame(columns=COLS_MATERIAIS)
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

# --- ÁREA 1: CADASTRO DE MATERIAIS (NOVO) ---
with st.expander("📦 Cadastro de Produtos/Materiais", expanded=False):
    st.info("Cadastre aqui os materiais para usar nos lançamentos.")
    with st.form("form_cadastro_material", clear_on_submit=True):
        c_cod, c_nom, c_un, c_pre = st.columns([1, 3, 1, 1])
        
        novo_cod = c_cod.text_input("Código (ex: 101)")
        novo_nome = c_nom.text_input("Nome do Material (ex: Cimento CP II)")
        novo_un = c_un.selectbox("Unidade", ["un", "m", "kg", "saco", "m²", "m³", "sc", "lt"])
        novo_ref = c_pre.number_input("Preço Ref (Opcional)", 0.0)
        
        if st.form_submit_button("➕ Cadastrar Material"):
            if novo_cod and novo_nome:
                # Verifica duplicidade
                if not df_materiais.empty and novo_cod in df_materiais['Codigo'].astype(str).values:
                    st.error("Erro: Código já existe!")
                else:
                    _, _, ws_mat = pegar_planilhas_escrita()
                    ws_mat.append_row([novo_cod, novo_nome, novo_un, novo_ref])
                    st.success(f"{novo_nome} cadastrado com sucesso!")
                    st.cache_data.clear()
                    time.sleep(1)
                    st.rerun()
            else:
                st.warning("Preencha Código e Nome.")

    if not df_materiais.empty:
        st.dataframe(df_materiais, use_container_width=True, height=150)

# --- ÁREA 2: DASHBOARD RÁPIDO ---
if not df_custos.empty and not df_cronograma.empty:
    orc = df_cronograma['Orcamento'].sum() if 'Orcamento' in df_cronograma.columns else 0
    real = df_custos['Total'].sum() if 'Total' in df_custos.columns else 0
    
    k1, k2, k3 = st.columns(3)
    k1.metric("Orçamento", f"R$ {orc:,.2f}")
    k2.metric("Gasto Real", f"R$ {real:,.2f}")
    k3.metric("Saldo", f"R$ {orc-real:,.2f}", delta=orc-real)

# --- ÁREA 3: LANÇAMENTO DE GASTOS (INTEGRADO) ---
st.divider()
st.subheader("📝 Lançamento de Despesas")

if df_materiais.empty:
    st.warning("⚠️ Você precisa cadastrar materiais na aba acima antes de lançar gastos.")
else:
    with st.container(border=True):
        # 1. Seleção Inteligente do Material
        # Cria uma lista de textos combinando "COD - NOME" para facilitar a busca
        df_materiais['Display'] = df_materiais['Codigo'].astype(str) + " - " + df_materiais['Nome']
        lista_opcoes = df_materiais['Display'].tolist()
        
        c_prod, c_det = st.columns([2, 1])
        
        with c_prod:
            # O Selectbox permite digitar para filtrar!
            escolha = st.selectbox("Buscar Produto (Digite para filtrar):", [""] + lista_opcoes)
        
        # Se escolheu algo, pega os dados automaticamente
        cod_selecionado = ""
        nome_selecionado = ""
        un_sugerida = "un"
        preco_sugerido = 0.0
        
        if escolha:
            # Separa o codigo do nome
            cod_selecionado = escolha.split(" - ")[0]
            # Filtra no dataframe para pegar a unidade certa
            item = df_materiais[df_materiais['Codigo'].astype(str) == cod_selecionado].iloc[0]
            nome_selecionado = item['Nome']
            un_sugerida = item['Unidade']
            preco_sugerido = float(item['Preco_Ref']) if item['Preco_Ref'] else 0.0

        with c_det:
             st.info(f"Unidade: {un_sugerida} | Ref: R$ {preco_sugerido}")

        # Formulário Final
        with st.form("form_lancamento", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            data_lanc = c1.date_input("Data")
            
            # Campos travados para garantir integridade, mas visuais
            c_desc = c2.text_input("Material", value=nome_selecionado, disabled=True)
            
            val_unit = c3.number_input("Valor Pago (Unitário)", min_value=0.0, value=preco_sugerido)
            
            c4, c5 = st.columns(2)
            qtd = c4.number_input("Quantidade", min_value=0.0, value=1.0)
            
            lista_etapas = df_cronograma['Etapa'].tolist() if not df_cronograma.empty else ["Geral"]
            etapa = c5.selectbox("Etapa da Obra", lista_etapas)
            
            btn_lancar = st.form_submit_button("💾 Confirmar Lançamento")
            
            if btn_lancar:
                if not escolha:
                    st.error("Selecione um material da lista!")
                else:
                    ws, _, _ = pegar_planilhas_escrita()
                    total = val_unit * qtd
                    # Salva: Data, Codigo, Nome, Qtd, Un, Valor, Total,
