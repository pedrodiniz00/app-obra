import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from fpdf import FPDF
import time
from datetime import datetime

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Gestão de Obra PRO", layout="wide", page_icon="🏗️")

# Definição das colunas
COLS_CUSTOS = ["Data", "Codigo", "Descricao", "Qtd", "Unidade", "Valor", "Total", "Classe", "Etapa", "Fornecedor"]
COLS_MATERIAIS = ["Codigo", "Nome", "Unidade", "Preco_Ref"]
COLS_FORNECEDORES = ["Codigo", "Nome", "Telefone", "Categoria"]
# Cronograma agora tem % Executado Manual
COLS_CRONO = ["Etapa", "Status", "Orcamento", "Porcentagem"] 
# Nova tabela para os pontos de verificação
COLS_PONTOS = ["Etapa_Pai", "Descricao", "Feito"] 

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
    if df.empty: return 1
    try:
        numeros = pd.to_numeric(df[col_nome], errors='coerce')
        maior = numeros.max()
        if pd.isna(maior): return 1
        return int(maior) + 1
    except: return 1

@st.cache_resource
def conectar_gsheets():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), scope)
    return gspread.authorize(creds)

def pegar_planilhas_escrita():
    client = conectar_gsheets()
    sh = client.open("Dados_Obra")
    
    # 1. Cronograma
    try: ws_crono = sh.worksheet("Cronograma")
    except: 
        ws_crono = sh.add_worksheet("Cronograma", 20, 5)
        ws_crono.append_row(COLS_CRONO)
    
    # 2. Materiais
    try: ws_mat = sh.worksheet("Materiais")
    except: 
        ws_mat = sh.add_worksheet("Materiais", 100, 4)
        ws_mat.append_row(COLS_MATERIAIS)

    # 3. Fornecedores
    try: ws_forn = sh.worksheet("Fornecedores")
    except:
        ws_forn = sh.add_worksheet("Fornecedores", 100, 4)
        ws_forn.append_row(COLS_FORNECEDORES)

    # 4. Pontos Críticos (NOVO)
    try: ws_pontos = sh.worksheet("Pontos_Criticos")
    except:
        ws_pontos = sh.add_worksheet("Pontos_Criticos", 100, 3)
        ws_pontos.append_row(COLS_PONTOS)
        
    return sh.sheet1, ws_crono, ws_mat, ws_forn, ws_pontos

@st.cache_data(ttl=5)
def carregar_dados_completo():
    client = conectar_gsheets()
    if not client: return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    
    sh = client.open("Dados_Obra")

    # CUSTOS
    try:
        ws = sh.sheet1
        dados = ws.get_all_records()
        df_custos = pd.DataFrame(dados)
        if not df_custos.empty:
            df_custos['row_num'] = df_custos.index + 2
            if 'Fornecedor' not in df_custos.columns: df_custos['Fornecedor'] = "-"
            for col in ['Total', 'Valor', 'Qtd']:
                if col in df_custos.columns: df_custos[col] = df_custos[col].apply(limpar_dinheiro)
    except: df_custos = pd.DataFrame()

    # CRONOGRAMA
    try:
        ws_c = sh.worksheet("Cronograma")
        # Garante cabeçalho
        if ws_c.row_values(1) != COLS_CRONO:
            # Se não tiver a coluna Porcentagem, avisa mas lê o que der
            pass 
        
        dados_c = ws_c.get_all_records()
        df_crono = pd.DataFrame(dados_c)
        if not df_crono.empty:
            df_crono['row_num'] = df_crono.index + 2
            if 'Orcamento' in df_crono.columns: df_crono['Orcamento'] = df_crono['Orcamento'].apply(limpar_dinheiro)
            if 'Porcentagem' not in df_crono.columns: df_crono['Porcentagem'] = 0
    except: df_crono = pd.DataFrame()

    # MATERIAIS / FORNECEDORES
    try:
        df_materiais = pd.DataFrame(sh.worksheet("Materiais").get_all_records())
        if not df_materiais.empty: df_materiais['row_num'] = df_materiais.index + 2
    except: df_materiais = pd.DataFrame()

    try:
        df_fornecedores = pd.DataFrame(sh.worksheet("Fornecedores").get_all_records())
        if not df_fornecedores.empty: df_fornecedores['row_num'] = df_fornecedores.index + 2
    except: df_fornecedores = pd.DataFrame()

    # PONTOS CRITICOS
    try:
        ws_p = sh.worksheet("Pontos_Criticos")
        df_pontos = pd.DataFrame(ws_p.get_all_records())
        if not df_pontos.empty: df_pontos['row_num'] = df_pontos.index + 2
    except: df_pontos = pd.DataFrame()

    return df_custos, df_crono, df_materiais, df_fornecedores, df_pontos

# --- 3. INTERFACE ---
st.title("🏗️ Gestor de Obras ERP")
df_custos, df_cronograma, df_materiais, df_fornecedores, df_pontos = carregar_dados_completo()

# --- SIDEBAR LIMPA ---
with st.sidebar:
    st.info("Navegue pelas abas acima para gerenciar a obra.")
    if st.button("Sair"):
        st.session_state["password_correct"] = False
        st.rerun()

# ==============================================================================
# TABS PRINCIPAIS (AGORA SÃO 4)
# ==============================================================================
tab_lancamento, tab_cronograma, tab_cadastros, tab_historico = st.tabs(["📝 Lançar Gastos", "📅 Cronograma & Etapas", "📦 Cadastros", "📊 Histórico"])

# ------------------------------------------------------------------------------
# ABA 1: LANÇAMENTO
# ------------------------------------------------------------------------------
with tab_lancamento:
    st.write("### Novo Lançamento Financeiro")
    
    if df_materiais.empty:
        st.warning("⚠️ Cadastre materiais antes de lançar.")
    else:
        df_materiais['Display'] = df_materiais['Codigo'].astype(str) + " - " + df_materiais['Nome']
        escolha = st.selectbox("Buscar Produto:", [""] + df_materiais['Display'].tolist())
        
        lista_forn = ["Sem Fornecedor"]
        if not df_fornecedores.empty:
            df_fornecedores['DisplayF'] = df_fornecedores['Codigo'].astype(str) + " - " + df_fornecedores['Nome']
            lista_forn += df_fornecedores['DisplayF'].tolist()
        escolha_forn = st.selectbox("Fornecedor:", lista_forn)

        nome_sel, un_sug, preco_sug, cod_sel = "", "un", 0.0, ""
        if escolha:
            cod_sel = escolha.split(" - ")[0]
            filtro = df_materiais[df_materiais['Codigo'].astype(str) == cod_sel]
            if not filtro.empty:
                item = filtro.iloc[0]
                nome_sel = item['Nome']
                un_sug = item['Unidade']
                preco_sug = float(item['Preco_Ref']) if item['Preco_Ref'] else 0.0

        with st.form("lancar", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            dt = c1.date_input("Data")
            c2.text_input("Item", value=nome_sel, disabled=True)
            val = c3.number_input("Valor Unitário", value=preco_sug)
            c4, c5 = st.columns(2)
            qtd = c4.number_input("Qtd", 1.0)
            etapa = c5.selectbox("Etapa", df_cronograma['Etapa'].tolist() if not df_cronograma.empty else ["Geral"])
            
            if st.form_submit_button("💾 Salvar"):
                if not escolha:
                    st.error("Selecione um produto!")
                else:
                    ws, _, _, _, _ = pegar_planilhas_escrita()
                    if ws.row_values(1) != COLS_CUSTOS: ws.update(range_name="A1:J1", values=[COLS_CUSTOS])
                    total = val * qtd
                    ws.append_row([str(dt), cod_sel, nome_sel, qtd, un_sug, val, total, "Material", etapa, escolha_forn])
                    st.success("Salvo!")
                    st.cache_data.clear()
                    st.rerun()

# ------------------------------------------------------------------------------
# ABA 2: CRONOGRAMA AVANÇADO (NOVIDADE!!!)
# ------------------------------------------------------------------------------
with tab_cronograma:
    st.write("### 📅 Gestão de Etapas e Checklists")
    
    col_nova_etapa, col_resumo = st.columns([1, 2])
    
    # 1. CRIAR NOVA ETAPA
    with col_nova_etapa:
        with st.form("nova_etapa_form", clear_on_submit=True):
            st.write("**Criar Nova Etapa da Obra**")
            nome_etapa = st.text_input("Nome (ex: Fundação)")
            orcamento_meta = st.number_input("Orçamento Previsto (R$)", 0.0)
            if st.form_submit_button("➕ Adicionar Etapa"):
                _, ws_c, _, _, _ = pegar_planilhas_escrita()
                # Garante cabeçalho
                if ws_c.row_values(1) != COLS_CRONO: ws_c.update(range_name="A1:D1", values=[COLS_CRONO])
                # Salva: Nome, Status, Orcamento, Porcentagem(0)
                ws_c.append_row([nome_etapa, "Pendente", orcamento_meta, 0])
                st.success("Etapa Criada!")
                st.cache_data.clear()
                time.sleep(1)
                st.rerun()

    # 2. LISTAGEM E DETALHES
    st.divider()
    if df_cronograma.empty:
        st.info("Nenhuma etapa cadastrada. Use o formulário acima.")
    else:
        # Loop por cada etapa para criar um "Cartão" de detalhes
        for i, row in df_cronograma.iterrows():
            nome = row['Etapa']
            # Tratamento de erro caso a coluna porcentagem esteja vazia
            try: pct_atual = int(row['Porcentagem'])
            except: pct_atual = 0
            
            with st.expander(f"📌 {nome}  |  Executado: {pct_atual}%  |  Orçamento: R$ {row.get('Orcamento',0):,.2f}", expanded=False):
                c_edit1, c_edit2 = st.columns([1, 1])
                
                # --- A. EDITAR PORCENTAGEM MANUAL ---
                with c_edit1:
                    st.write("**Progresso Físico Manual**")
                    novo_pct = st.slider(f"Porcentagem Concluída ({nome})", 0, 100, pct_atual, key=f"sld_{i}")
                    if novo_pct != pct_atual:
                        _, ws_c, _, _, _ = pegar_planilhas_escrita()
                        # Atualiza coluna 4 (Porcentagem)
                        ws_c.update_cell(row['row_num'], 4, novo_pct)
                        st.toast(f"Progresso de {nome} atualizado para {novo_pct}%")
                        st.cache_data.clear()
                        time.sleep(1)
                        st.rerun()

                # --- B. PONTOS CRÍTICOS (CHECKLIST) ---
                with c_edit2:
                    st.write("**Pontos Críticos / Checklist**")
                    
                    # Filtra pontos desta etapa
                    if not df_pontos.empty:
                        pontos_desta_etapa = df_pontos[df_pontos['Etapa_Pai'] == nome]
                    else:
                        pontos_desta_etapa = pd.DataFrame()

                    # Mostra os checkboxes existentes
                    if not pontos_desta_etapa.empty:
                        for idx_p, row_p in pontos_desta_etapa.iterrows():
                            # Converte string 'TRUE'/'FALSE' do excel para booleano
                            is_checked = str(row_p['Feito']).upper() == 'TRUE'
                            check = st.checkbox(row_p['Descricao'], value=is_checked, key=f"chk_{row_p['row_num']}")
                            
                            if check != is_checked:
                                _, _, _, _, ws_p = pegar_planilhas_escrita()
                                # Atualiza coluna 3 (Feito) na aba Pontos_Criticos
                                ws_p.update_cell(row_p['row_num'], 3, "TRUE" if check else "FALSE")
                                st.cache_data.clear()
                                st.rerun()
                    else:
                        st.caption("Nenhum ponto de verificação criado.")

                    # Adicionar Novo Ponto
                    with st.form(f"add_ponto_{i}", clear_on_submit=True):
                        novo_ponto_txt = st.text_input("Adicionar Ponto Crítico (ex: Impermeabilização ok)")
                        if st.form_submit_button("➕ Add"):
                            _, _, _, _, ws_p = pegar_planilhas_escrita()
                            ws_p.append_row([nome, novo_ponto_txt, "FALSE"])
                            st.success("Ponto adicionado!")
                            st.cache_data.clear()
                            st.rerun()

# ------------------------------------------------------------------------------
# ABA 3: CADASTROS
# ------------------------------------------------------------------------------
with tab_cadastros:
    st.write("### Gerenciar Cadastros")
    subtab_mat, subtab_forn = st.tabs(["Materiais", "Fornecedores"])

    with subtab_mat:
        c_form, c_lista = st.columns([1, 2])
        with c_form:
            st.info("**Novo Material**")
            prox_cod_mat = proximo_id(df_materiais)
            with st.form("form_mat", clear_on_submit=True):
                st.text_input("Código", value=prox_cod_mat, disabled=True)
                nome = st.text_input("Nome")
                un = st.selectbox("Unidade", ["un","m","kg","sc","m²","m³","lt","cx"])
                ref = st.number_input("R$ Ref", 0.0)
                if st.form_submit_button("➕ Cadastrar"):
                    if nome:
                        _, _, ws_m, _, _ = pegar_planilhas_escrita()
                        ws_m.append_row([prox_cod_mat, nome, un, ref])
                        st.success("Cadastrado!")
                        st.cache_data.clear()
                        st.rerun()
        with c_lista:
            if not df_materiais.empty:
                st.dataframe(df_materiais[['Codigo', 'Nome', 'Unidade']], height=250)

    with subtab_forn:
        c_form_f, c_lista_f = st.columns([1, 2])
        with c_form_f:
            st.info("**Novo Fornecedor**")
            prox_cod_forn = proximo_id(df_fornecedores)
            with st.form("form_forn", clear_on_submit=True):
                st.text_input("Código", value=prox_cod_forn, disabled=True)
                fn = st.text_input("Nome")
                ft = st.text_input("Tel")
                fcat = st.selectbox("Categoria", ["Material", "Serviço"])
                if st.form_submit_button("➕ Cadastrar"):
                    if fn:
                        _, _, _, ws_f, _ = pegar_planilhas_escrita()
                        ws_f.append_row([prox_cod_forn, fn, ft, fcat])
                        st.success("Cadastrado!")
                        st.cache_data.clear()
                        st.rerun()
        with c_lista_f:
            if not df_fornecedores.empty:
                st.dataframe(df_fornecedores[['Codigo', 'Nome']], height=250)

# ------------------------------------------------------------------------------
# ABA 4: HISTÓRICO
# ------------------------------------------------------------------------------
with tab_historico:
    # KPIs
    total_orcado = df_cronograma['Orcamento'].sum() if not df_cronograma.empty and 'Orcamento' in df_cronograma.columns else 0.0
    total_realizado = df_custos['Total'].sum() if not df_custos.empty and 'Total' in df_custos.columns else 0.0
    saldo = total_orcado - total_realizado
    
    st.markdown("### 📊 Performance Financeira")
    k1, k2, k3 = st.columns(3)
    k1.metric("Orçamento", f"R$ {total_orcado:,.2f}")
    k2.metric("Gasto Real", f"R$ {total_realizado:,.2f}")
    k3.metric("Saldo", f"R$ {saldo:,.2f}", delta=saldo)
    
    st.divider()
    st.write("### 📋 Histórico")
    
    if not df_custos.empty:
        df_show = df_custos.copy()
        df_show.insert(0, "Excluir", False)
        cols_order = ["Excluir", "Data", "Fornecedor", "Descricao", "Qtd", "Unidade", "Valor", "Total", "Etapa"]
        cols_existentes = [c for c in cols_order if c in df_show.columns]
        
        edited = st.data_editor(
            df_show[cols_existentes],
            hide_index=True,
            use_container_width=True,
            column_config={
                "Excluir": st.column_config.CheckboxColumn("Del?", width="small"),
                "Valor": st.column_config.NumberColumn("Valor Un", format="R$ %.2f"),
                "Total": st.column_config.NumberColumn("Total", format="R$ %.2f")
            },
            disabled=["Data", "Fornecedor", "Descricao", "Qtd", "Unidade", "Valor", "Total", "Etapa"]
        )
        
        dels = edited[edited["Excluir"]==True]
        if not dels.empty and st.button("Confirmar Exclusão"):
            ws, _, _, _, _ = pegar_planilhas_escrita()
            rows = df_custos.loc[dels.index, "row_num"].tolist()
            rows.sort(reverse=True)
            for r in rows: ws.delete_rows(r)
            st.success("Apagado!")
            st.cache_data.clear()
            st.rerun()



