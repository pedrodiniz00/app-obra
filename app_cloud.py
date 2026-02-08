import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from fpdf import FPDF
import time
from datetime import datetime

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Gestão de Obra PRO", layout="wide", page_icon="🏗️")

# --- DEFINIÇÃO DAS COLUNAS (AGORA COM ID_OBRA NO INÍCIO) ---
# A primeira coluna de tudo (exceto cadastros globais) agora é ID_Obra
COLS_OBRAS = ["ID", "Nome", "Endereco", "Status"] # NOVA ABA
COLS_CUSTOS = ["ID_Obra", "Data", "Codigo", "Descricao", "Qtd", "Unidade", "Valor", "Total", "Classe", "Etapa", "Fornecedor"]
COLS_MATERIAIS = ["Codigo", "Nome", "Unidade", "Preco_Ref"] # Global
COLS_FORNECEDORES = ["Codigo", "Nome", "Telefone", "Categoria"] # Global
COLS_CRONO = ["ID_Obra", "Etapa", "Status", "Orcamento", "Porcentagem"] 
COLS_PONTOS = ["ID_Obra", "Etapa_Pai", "Descricao", "Feito"] 
COLS_TAREFAS = ["ID_Obra", "Data_Limite", "Descricao", "Responsavel", "Status"]

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

# --- 2. CONEXÃO E UTILITÁRIOS ---
def limpar_dinheiro(valor):
    if isinstance(valor, (int, float)): return float(valor)
    if isinstance(valor, str):
        try: return float(valor.replace('R$', '').replace('.', '').replace(',', '.').strip())
        except: return 0.0
    return 0.0

def proximo_id(df, col_nome='Codigo'):
    if df.empty: return 1
    try:
        # Tenta pegar apenas numeros
        numeros = pd.to_numeric(df[col_nome], errors='coerce').dropna()
        if numeros.empty: return 1
        return int(numeros.max()) + 1
    except: return 1

@st.cache_resource
def conectar_gsheets():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), scope)
    return gspread.authorize(creds)

# Inicialização Segura das Abas
def inicializar_abas(sh):
    mapa = {
        "Obras": COLS_OBRAS, # Nova aba Mestra
        "Cronograma": COLS_CRONO,
        "Materiais": COLS_MATERIAIS,
        "Fornecedores": COLS_FORNECEDORES,
        "Pontos_Criticos": COLS_PONTOS,
        "Tarefas": COLS_TAREFAS
    }
    try: existentes = {ws.title: ws for ws in sh.worksheets()}
    except: return

    for nome, cols in mapa.items():
        if nome not in existentes:
            try:
                ws = sh.add_worksheet(nome, 100, len(cols))
                ws.append_row(cols)
                time.sleep(1.5)
            except: pass
    
    # Verifica a Sheet1 (Custos) separadamente
    ws1 = sh.sheet1
    if not ws1.row_values(1):
        ws1.append_row(COLS_CUSTOS)

def pegar_dados_brutos():
    client = conectar_gsheets()
    try: sh = client.open("Dados_Obra")
    except: 
        st.error("Planilha 'Dados_Obra' não encontrada.")
        st.stop()
    
    inicializar_abas(sh)
    
    return (
        sh.sheet1, # Custos
        sh.worksheet("Cronograma"),
        sh.worksheet("Materiais"),
        sh.worksheet("Fornecedores"),
        sh.worksheet("Pontos_Criticos"),
        sh.worksheet("Tarefas"),
        sh.worksheet("Obras") # Nova
    )

@st.cache_data(ttl=5)
def carregar_tudo():
    ws_custos, ws_crono, ws_mat, ws_forn, ws_pontos, ws_tarefas, ws_obras = pegar_dados_brutos()
    
    def ler(ws):
        try: return pd.DataFrame(ws.get_all_records())
        except: return pd.DataFrame()

    df_custos = ler(ws_custos)
    df_crono = ler(ws_crono)
    df_mat = ler(ws_mat)
    df_forn = ler(ws_forn)
    df_pontos = ler(ws_pontos)
    df_tarefas = ler(ws_tarefas)
    df_obras = ler(ws_obras)
    
    # Tratamento de Dados
    if not df_custos.empty:
        df_custos['row_num'] = df_custos.index + 2
        for c in ['Total','Valor','Qtd']: 
            if c in df_custos.columns: df_custos[c] = df_custos[c].apply(limpar_dinheiro)

    if not df_crono.empty:
        df_crono['row_num'] = df_crono.index + 2
        if 'Orcamento' in df_crono.columns: df_crono['Orcamento'] = df_crono['Orcamento'].apply(limpar_dinheiro)

    # Adiciona row_num nos outros
    for df in [df_mat, df_forn, df_pontos, df_tarefas, df_obras]:
        if not df.empty: df['row_num'] = df.index + 2
        
    return df_custos, df_crono, df_mat, df_forn, df_pontos, df_tarefas, df_obras

# --- 3. LÓGICA DE SELEÇÃO DE OBRA ---
st.title("🏗️ Gestor Multi-Obras ERP")
df_custos, df_crono, df_mat, df_forn, df_pontos, df_tarefas, df_obras = carregar_tudo()

# --- SIDEBAR: SELETOR DE OBRA ---
with st.sidebar:
    st.header("🏢 Seleção de Obra")
    
    # Se não tem obra nenhuma cadastrada
    if df_obras.empty:
        st.warning("Nenhuma obra cadastrada!")
        obra_atual = None
    else:
        # Cria lista de seleção: "1 - Casa João"
        opcoes_obras = df_obras.apply(lambda x: f"{x['ID']} - {x['Nome']}", axis=1).tolist()
        selecao = st.selectbox("Obra Ativa:", opcoes_obras)
        
        # Pega o ID da obra selecionada
        id_obra_atual = int(selecao.split(" - ")[0])
        nome_obra_atual = selecao.split(" - ")[1]
        
        st.success(f"Gerenciando: **{nome_obra_atual}**")
        obra_atual = id_obra_atual

    st.divider()
    
    # Botão para criar NOVA OBRA
    with st.expander("➕ Nova Obra"):
        with st.form("nova_obra"):
            n_nome = st.text_input("Nome da Obra")
            n_end = st.text_input("Endereço")
            if st.form_submit_button("Criar"):
                prox_id = proximo_id(df_obras, 'ID')
                _, _, _, _, _, _, ws_o = pegar_dados_brutos()
                ws_o.append_row([prox_id, n_nome, n_end, "Ativa"])
                st.success("Obra Criada!")
                st.cache_data.clear()
                time.sleep(1)
                st.rerun()
                
    st.divider()
    if st.button("Atualizar Dados"):
        st.cache_data.clear()
        st.rerun()

# SE NÃO TIVER OBRA SELECIONADA, PARA AQUI
if obra_atual is None:
    st.info("👈 Cadastre uma nova obra na barra lateral para começar.")
    st.stop()

# --- FILTRAGEM DOS DADOS PELA OBRA SELECIONADA ---
# Aqui acontece a mágica: filtramos todos os dataframes pelo ID da obra
# Materiais e Fornecedores NÃO são filtrados (são globais)

def filtrar(df):
    if df.empty or 'ID_Obra' not in df.columns: return pd.DataFrame(columns=df.columns)
    return df[df['ID_Obra'] == obra_atual]

df_custos_f = filtrar(df_custos)
df_crono_f = filtrar(df_crono)
df_pontos_f = filtrar(df_pontos)
df_tarefas_f = filtrar(df_tarefas)

# ==============================================================================
# INTERFACE PRINCIPAL
# ==============================================================================

tab_lanc, tab_crono, tab_tarefa, tab_cad, tab_hist = st.tabs([
    "📝 Lançar", "📅 Cronograma", "✅ Tarefas", "📦 Cadastros", "📊 Histórico"
])

# --- 1. LANÇAR (FILTRADO) ---
with tab_lanc:
    st.subheader(f"Novo Gasto - {nome_obra_atual}")
    
    if df_mat.empty: st.warning("Cadastre materiais na aba Cadastros.")
    else:
        df_mat['Display'] = df_mat['Codigo'].astype(str) + " - " + df_mat['Nome']
        escolha = st.selectbox("Produto:", [""] + df_mat['Display'].tolist())
        
        lista_forn = ["Sem Fornecedor"]
        if not df_forn.empty:
            df_forn['DisplayF'] = df_forn['Codigo'].astype(str) + " - " + df_forn['Nome']
            lista_forn += df_forn['DisplayF'].tolist()
        escolha_forn = st.selectbox("Fornecedor:", lista_forn)

        nome_s, un_s, preco_s, cod_s = "", "un", 0.0, ""
        if escolha:
            cod_s = escolha.split(" - ")[0]
            item = df_mat[df_mat['Codigo'].astype(str) == cod_s].iloc[0]
            nome_s = item['Nome']
            un_s = item['Unidade']
            preco_s = float(item['Preco_Ref']) if item['Preco_Ref'] else 0.0

        with st.form("lanca_custo", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            dt = c1.date_input("Data")
            c2.text_input("Item", value=nome_s, disabled=True)
            val = c3.number_input("Valor Unit", value=preco_s)
            c4, c5 = st.columns(2)
            qtd = c4.number_input("Qtd", 1.0)
            
            # Etapas apenas desta obra
            etapas_obra = df_crono_f['Etapa'].unique().tolist() if not df_crono_f.empty else ["Geral"]
            etapa = c5.selectbox("Etapa", etapas_obra)
            
            if st.form_submit_button("Salvar"):
                if not escolha: st.error("Selecione produto")
                else:
                    ws, _, _, _, _, _, _ = pegar_dados_brutos()
                    if ws.row_values(1) != COLS_CUSTOS: ws.update(range_name="A1:K1", values=[COLS_CUSTOS])
                    
                    # Salva com ID_OBRA na primeira coluna
                    ws.append_row([obra_atual, str(dt), cod_s, nome_s, qtd, un_s, val, val*qtd, "Material", etapa, escolha_forn])
                    st.success("Salvo na obra selecionada!")
                    st.cache_data.clear()
                    st.rerun()

# --- 2. CRONOGRAMA (FILTRADO) ---
with tab_crono:
    st.subheader(f"Cronograma - {nome_obra_atual}")
    c_new, c_list = st.columns([1, 2])
    
    with c_new:
        with st.form("new_stg", clear_on_submit=True):
            nm = st.text_input("Nova Etapa")
            orc = st.number_input("Orçamento Meta", 0.0)
            if st.form_submit_button("Criar"):
                _, ws, _, _, _, _, _ = pegar_dados_brutos()
                # ID_Obra, Etapa, Status, Orcamento, Porcentagem
                ws.append_row([obra_atual, nm, "Pendente", orc, 0])
                st.success("Etapa criada!")
                st.cache_data.clear()
                st.rerun()
                
    st.divider()
    if not df_crono_f.empty:
        for i, row in df_crono_f.iterrows():
            
            with st.expander(f"📌 {row['Etapa']} ({row['Porcentagem']}%) | Meta: R$ {row['Orcamento']:,.2f}"):
                t1, t2, t3 = st.tabs(["Progresso", "Checklist", "Editar"])
                
                with t1:
                    novo_pct = st.slider("Executado", 0, 100, int(row['Porcentagem']), key=f"p_{row['row_num']}")
                    if novo_pct != int(row['Porcentagem']):
                        _, ws, _, _, _, _, _ = pegar_dados_brutos()
                        ws.update_cell(row['row_num'], 5, novo_pct) # Col 5 é %
                        st.cache_data.clear()
                        st.rerun()
                
                with t2:
                    pts = df_pontos_f[df_pontos_f['Etapa_Pai'] == row['Etapa']]
                    for ix, p in pts.iterrows():
                        chk = st.checkbox(p['Descricao'], value=(str(p['Feito']).upper()=='TRUE'), key=f"k_{p['row_num']}")
                        if chk != (str(p['Feito']).upper()=='TRUE'):
                            _, _, _, _, wsp, _, _ = pegar_dados_brutos()
                            wsp.update_cell(p['row_num'], 4, "TRUE" if chk else "FALSE") # Col 4 é Feito
                            st.cache_data.clear()
                            st.rerun()
                    with st.form(f"add_pt_{row['row_num']}", clear_on_submit=True):
                        txt = st.text_input("Novo Ponto")
                        if st.form_submit_button("Add"):
                            _, _, _, _, wsp, _, _ = pegar_dados_brutos()
                            wsp.append_row([obra_atual, row['Etapa'], txt, "FALSE"])
                            st.cache_data.clear()
                            st.rerun()
                            
                with t3:
                    with st.form(f"ed_{row['row_num']}"):
                        ne = st.text_input("Nome", row['Etapa'])
                        oe = st.number_input("Meta", value=float(row['Orcamento']))
                        if st.form_submit_button("Salvar"):
                            _, ws, _, _, _, _, _ = pegar_dados_brutos()
                            ws.update_cell(row['row_num'], 2, ne)
                            ws.update_cell(row['row_num'], 4, oe)
                            st.success("Salvo")
                            st.cache_data.clear()
                            st.rerun()

# --- 3. TAREFAS (FILTRADO) ---
with tab_tarefa:
    st.subheader(f"Pendências - {nome_obra_atual}")
    with st.expander("Nova Tarefa"):
        with st.form("nt"):
            d = st.text_input("Descrição")
            r = st.text_input("Responsável")
            dl = st.date_input("Prazo")
            if st.form_submit_button("Criar"):
                _, _, _, _, _, wst, _ = pegar_dados_brutos()
                wst.append_row([obra_atual, str(dl), d, r, "Pendente"])
                st.cache_data.clear()
                st.rerun()
    
    if not df_tarefas_f.empty:
        pend = df_tarefas_f[df_tarefas_f['Status']!='Concluída']
        for i, t in pend.iterrows():
            c1, c2, c3 = st.columns([0.5, 4, 0.5])
            with c1:
                if st.checkbox("", key=f"tc_{t['row_num']}"):
                    _, _, _, _, _, wst, _ = pegar_dados_brutos()
                    wst.update_cell(t['row_num'], 5, "Concluída")
                    st.rerun()
            with c2: st.write(f"**{t['Descricao']}** ({t['Responsavel']}) - {t['Data_Limite']}")
            with c3:
                if st.button("🗑️", key=f"td_{t['row_num']}"):
                    _, _, _, _, _, wst, _ = pegar_dados_brutos()
                    wst.delete_rows(t['row_num'])
                    st.rerun()

# --- 4. CADASTROS (GLOBAIS) ---
with tab_cad:
    st.info("💡 Materiais e Fornecedores são globais (compartilhados entre todas as obras).")
    s1, s2 = st.tabs(["Materiais", "Fornecedores"])
    with s1:
        c1, c2 = st.columns(2)
        with c1:
            pid = proximo_id(df_mat)
            with st.form("mat"):
                st.text_input("ID", pid, disabled=True)
                n = st.text_input("Nome")
                u = st.selectbox("Un", ["un","m","kg","sc"])
                v = st.number_input("R$")
                if st.form_submit_button("Salvar"):
                    _, _, ws, _, _, _, _ = pegar_dados_brutos()
                    ws.append_row([pid, n, u, v])
                    st.cache_data.clear()
                    st.rerun()
        with c2: st.dataframe(df_mat[['Codigo','Nome']])
    
    with s2:
        c1, c2 = st.columns(2)
        with c1:
            fid = proximo_id(df_forn)
            with st.form("forn"):
                st.text_input("ID", fid, disabled=True)
                n = st.text_input("Nome")
                t = st.text_input("Tel")
                c = st.selectbox("Cat", ["Material", "Serviço"])
                if st.form_submit_button("Salvar"):
                    _, _, _, ws, _, _, _ = pegar_dados_brutos()
                    ws.append_row([fid, n, t, c])
                    st.cache_data.clear()
                    st.rerun()
        with c2: st.dataframe(df_forn[['Codigo','Nome']])

# --- 5. HISTÓRICO (FILTRADO) ---
with tab_hist:
    st.subheader(f"Financeiro - {nome_obra_atual}")
    orc = df_crono_f['Orcamento'].sum() if not df_crono_f.empty else 0
    real = df_custos_f['Total'].sum() if not df_custos_f.empty else 0
    
    k1, k2, k3 = st.columns(3)
    k1.metric("Orçado", f"R$ {orc:,.2f}")
    k2.metric("Realizado", f"R$ {real:,.2f}")
    k3.metric("Saldo", f"R$ {orc-real:,.2f}", delta=orc-real)
    
    st.divider()
    if not df_custos_f.empty:
        df_show = df_custos_f.copy()
        df_show.insert(0, "Excluir", False)
        # Esconde ID_Obra da visualização pois já sabemos qual é
        cols = ["Excluir", "Data", "Fornecedor", "Descricao", "Valor", "Total", "Etapa"]
        
        edited = st.data_editor(df_show[cols], hide_index=True, use_container_width=True)
        
        dels = edited[edited["Excluir"]==True]
        if not dels.empty and st.button("Confirmar Exclusão"):
            ws, _, _, _, _, _, _ = pegar_dados_brutos()
            rows = df_custos.loc[dels.index, "row_num"].tolist() # Pega row_num original
            rows.sort(reverse=True)
            for r in rows: ws.delete_rows(r)
            st.success("Apagado")
            st.cache_data.clear()
            st.rerun()


