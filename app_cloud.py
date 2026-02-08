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
COLS_CRONO = ["Etapa", "Status", "Orcamento", "Porcentagem"] 
COLS_PONTOS = ["Etapa_Pai", "Descricao", "Feito"] 
COLS_TAREFAS = ["Data_Limite", "Descricao", "Responsavel", "Status"] # NOVA TABELA

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

# --- 2. CONEXÃO ROBUSTA ---
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

def garantir_abas(sh):
    mapa = {
        "Cronograma": COLS_CRONO,
        "Materiais": COLS_MATERIAIS,
        "Fornecedores": COLS_FORNECEDORES,
        "Pontos_Criticos": COLS_PONTOS,
        "Tarefas": COLS_TAREFAS # GARANTE QUE A ABA EXISTA
    }
    try: existentes = {ws.title: ws for ws in sh.worksheets()}
    except: return False

    for nome, cols in mapa.items():
        if nome not in existentes:
            try:
                ws = sh.add_worksheet(nome, 100, len(cols))
                ws.append_row(cols)
                time.sleep(1.5)
            except: pass
    return True

def pegar_dados_seguro():
    client = conectar_gsheets()
    try: sh = client.open("Dados_Obra")
    except: 
        st.error("Planilha 'Dados_Obra' não encontrada.")
        st.stop()
    
    garantir_abas(sh)
    
    return (
        sh.sheet1,
        sh.worksheet("Cronograma"),
        sh.worksheet("Materiais"),
        sh.worksheet("Fornecedores"),
        sh.worksheet("Pontos_Criticos"),
        sh.worksheet("Tarefas") # RETORNA A NOVA ABA
    )

@st.cache_data(ttl=5)
def carregar_dfs():
    ws1, wsc, wsm, wsf, wsp, wst = pegar_dados_seguro()
    
    def ler(ws):
        try: return pd.DataFrame(ws.get_all_records())
        except: return pd.DataFrame()

    df_custos = ler(ws1)
    df_crono = ler(wsc)
    df_mat = ler(wsm)
    df_forn = ler(wsf)
    df_pontos = ler(wsp)
    df_tarefas = ler(wst) # LÊ AS TAREFAS
    
    if not df_custos.empty:
        df_custos['row_num'] = df_custos.index + 2
        if 'Fornecedor' not in df_custos.columns: df_custos['Fornecedor'] = "-"
        for c in ['Total','Valor','Qtd']: 
            if c in df_custos.columns: df_custos[c] = df_custos[c].apply(limpar_dinheiro)

    if not df_crono.empty:
        df_crono['row_num'] = df_crono.index + 2
        if 'Orcamento' in df_crono.columns: df_crono['Orcamento'] = df_crono['Orcamento'].apply(limpar_dinheiro)
        if 'Porcentagem' not in df_crono.columns: df_crono['Porcentagem'] = 0

    # Adiciona row_num em todos para permitir edição
    for df in [df_mat, df_forn, df_pontos, df_tarefas]:
        if not df.empty: df['row_num'] = df.index + 2
        
    return df_custos, df_crono, df_mat, df_forn, df_pontos, df_tarefas

# --- 4. INTERFACE ---
st.title("🏗️ Gestor de Obras ERP")

with st.sidebar:
    st.success("Sistema Online 🟢")
    if st.button("🔄 Atualizar Dados"):
        st.cache_data.clear()
        st.rerun()
    st.divider()
    if st.button("Sair"):
        st.session_state["password_correct"] = False
        st.rerun()

df_custos, df_cronograma, df_materiais, df_fornecedores, df_pontos, df_tarefas = carregar_dfs()

# TABS (AGORA SÃO 5)
tab_lancamento, tab_cronograma, tab_tarefas, tab_cadastros, tab_historico = st.tabs([
    "📝 Lançar", "📅 Cronograma", "✅ Tarefas", "📦 Cadastros", "📊 Histórico"
])

# --- TAB 1: LANÇAMENTO ---
with tab_lancamento:
    st.write("### Novo Lançamento")
    if df_materiais.empty:
        st.warning("Cadastre materiais primeiro.")
    else:
        df_materiais['Display'] = df_materiais['Codigo'].astype(str) + " - " + df_materiais['Nome']
        escolha = st.selectbox("Produto:", [""] + df_materiais['Display'].tolist())
        
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

        with st.form("lancar", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            dt = c1.date_input("Data")
            c2.text_input("Item", value=nome_sel, disabled=True)
            val = c3.number_input("Valor", value=preco_sug)
            c4, c5 = st.columns(2)
            qtd = c4.number_input("Qtd", 1.0)
            etapa = c5.selectbox("Etapa", df_cronograma['Etapa'].tolist() if not df_cronograma.empty else ["Geral"])
            
            if st.form_submit_button("Salvar"):
                if not escolha: st.error("Escolha um produto")
                else:
                    ws, _, _, _, _, _ = pegar_dados_seguro()
                    if ws.row_values(1) != COLS_CUSTOS: ws.update(range_name="A1:J1", values=[COLS_CUSTOS])
                    
                    ws.append_row([str(dt), cod_sel, nome_sel, qtd, un_sug, val, val*qtd, "Material", etapa, escolha_forn])
                    st.success("Salvo!")
                    st.cache_data.clear()
                    st.rerun()

# --- TAB 2: CRONOGRAMA ---
with tab_cronograma:
    c_new, c_list = st.columns([1, 2])
    with c_new:
        with st.form("new_etapa", clear_on_submit=True):
            st.write("**Nova Etapa**")
            nome = st.text_input("Nome")
            orc = st.number_input("Meta (R$)", 0.0)
            if st.form_submit_button("Criar"):
                _, ws, _, _, _, _ = pegar_dados_seguro()
                ws.append_row([nome, "Pendente", orc, 0])
                st.success("Criado!")
                st.cache_data.clear()
                st.rerun()
    
    st.divider()
    if not df_cronograma.empty:
        for i, row in df_cronograma.iterrows():
            nome_atual = row['Etapa']
            pct = int(row.get('Porcentagem', 0))
            orc_atual = float(row.get('Orcamento', 0))
            
            
            with st.expander(f"📌 {nome_atual} ({pct}%) | Meta: R$ {orc_atual:,.2f}"):
                t_prog, t_check, t_edit = st.tabs(["📊 Progresso", "✅ Checklist", "✏️ Editar"])
                
                with t_prog:
                    novo_pct = st.slider(f"Executado", 0, 100, pct, key=f"s_{i}")
                    if novo_pct != pct:
                        _, ws, _, _, _, _ = pegar_dados_seguro()
                        ws.update_cell(row['row_num'], 4, novo_pct)
                        st.cache_data.clear()
                        st.rerun()

                with t_check:
                    if not df_pontos.empty:
                        pts = df_pontos[df_pontos['Etapa_Pai']==nome_atual]
                        for idx, p in pts.iterrows():
                            chk = st.checkbox(p['Descricao'], value=(str(p['Feito']).upper()=='TRUE'), key=f"pk_{p['row_num']}")
                            if chk != (str(p['Feito']).upper()=='TRUE'):
                                _, _, _, _, wsp, _ = pegar_dados_seguro()
                                wsp.update_cell(p['row_num'], 3, "TRUE" if chk else "FALSE")
                                st.cache_data.clear()
                                st.rerun()
                    
                    with st.form(f"add_p_{i}", clear_on_submit=True):
                        pt_txt = st.text_input("Novo Ponto")
                        if st.form_submit_button("Add"):
                            _, _, _, _, wsp, _ = pegar_dados_seguro()
                            wsp.append_row([nome_atual, pt_txt, "FALSE"])
                            st.cache_data.clear()
                            st.rerun()

                with t_edit:
                    with st.form(f"edit_etapa_{i}"):
                        nome_edit = st.text_input("Nome", value=nome_atual)
                        orc_edit = st.number_input("Orçamento", value=orc_atual)
                        if st.form_submit_button("Salvar Edição"):
                            _, ws_crono, _, _, _, _ = pegar_dados_seguro()
                            ws_crono.update_cell(row['row_num'], 1, nome_edit)
                            ws_crono.update_cell(row['row_num'], 3, orc_edit)
                            st.success("Atualizado!")
                            st.cache_data.clear()
                            st.rerun()

# --- TAB 3: TAREFAS (NOVA ABA) ---
with tab_tarefas:
    st.write("### 📌 Caderno de Tarefas e Pendências")
    
    # 1. FORMULÁRIO DE NOVA TAREFA
    with st.expander("➕ Adicionar Nova Tarefa", expanded=True):
        with st.form("form_tarefa", clear_on_submit=True):
            c1, c2, c3 = st.columns([2, 1, 1])
            desc_t = c1.text_input("O que precisa ser feito?", placeholder="Ex: Comprar cimento, Ligar pro pedreiro...")
            resp_t = c2.text_input("Responsável", placeholder="Quem?")
            data_t = c3.date_input("Prazo Limite")
            
            if st.form_submit_button("Adicionar Tarefa"):
                if desc_t:
                    _, _, _, _, _, ws_tarefas = pegar_dados_seguro()
                    # Salva: Data, Descricao, Responsavel, Status
                    ws_tarefas.append_row([str(data_t), desc_t, resp_t, "Pendente"])
                    st.success("Tarefa anotada!")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.warning("Escreva a descrição da tarefa.")

    st.divider()

    # 2. LISTA DE TAREFAS PENDENTES
    st.subheader("⚠️ Pendentes")
    if not df_tarefas.empty:
        pendentes = df_tarefas[df_tarefas['Status'] != 'Concluída']
        
        if pendentes.empty:
            st.info("Nenhuma pendência! Tudo em dia.")
        else:
            for i, t in pendentes.iterrows():
                # Layout de cartão para a tarefa
                col_check, col_info, col_del = st.columns([0.5, 4, 0.5])
                
                with col_check:
                    # Checkbox para concluir
                    if st.checkbox("", key=f"t_check_{t['row_num']}"):
                        _, _, _, _, _, ws_tarefas = pegar_dados_seguro()
                        ws_tarefas.update_cell(t['row_num'], 4, "Concluída")
                        st.balloons()
                        st.cache_data.clear()
                        time.sleep(1)
                        st.rerun()
                
                with col_info:
                    st.markdown(f"**{t['Descricao']}**")
                    st.caption(f"📅 Prazo: {t['Data_Limite']} | 👤 Resp: {t['Responsavel']}")
                
                with col_del:
                    if st.button("🗑️", key=f"del_t_{t['row_num']}"):
                        _, _, _, _, _, ws_tarefas = pegar_dados_seguro()
                        ws_tarefas.delete_rows(t['row_num'])
                        st.cache_data.clear()
                        st.rerun()
                st.write("---")

    # 3. TAREFAS CONCLUÍDAS (EXPANSÍVEL)
    with st.expander("Ver Tarefas Concluídas"):
        if not df_tarefas.empty:
            feitas = df_tarefas[df_tarefas['Status'] == 'Concluída']
            if not feitas.empty:
                st.dataframe(feitas[['Data_Limite', 'Descricao', 'Responsavel']], use_container_width=True)
            else:
                st.caption("Nenhuma tarefa concluída ainda.")

# --- TAB 4: CADASTROS ---
with tab_cadastros:
    sub1, sub2 = st.tabs(["Materiais", "Fornecedores"])
    with sub1:
        c1, c2 = st.columns(2)
        with c1:
            st.write("Novo Material")
            pid = proximo_id(df_materiais)
            with st.form("fm", clear_on_submit=True):
                st.text_input("ID", pid, disabled=True)
                nm = st.text_input("Nome")
                un = st.selectbox("Un", ["un","m","kg","sc","m²"])
                ref = st.number_input("R$", 0.0)
                if st.form_submit_button("Salvar"):
                    _, _, ws, _, _, _ = pegar_dados_seguro()
                    ws.append_row([pid, nm, un, ref])
                    st.cache_data.clear()
                    st.rerun()
        with c2:
            if not df_materiais.empty: st.dataframe(df_materiais[['Codigo','Nome','Unidade']])
            
    with sub2:
        c1, c2 = st.columns(2)
        with c1:
            st.write("Novo Fornecedor")
            fid = proximo_id(df_fornecedores)
            with st.form("ff", clear_on_submit=True):
                st.text_input("ID", fid, disabled=True)
                fn = st.text_input("Nome")
                ft = st.text_input("Tel")
                fc = st.selectbox("Cat", ["Material", "Serviço"])
                if st.form_submit_button("Salvar"):
                    _, _, _, ws, _, _ = pegar_dados_seguro()
                    ws.append_row([fid, fn, ft, fc])
                    st.cache_data.clear()
                    st.rerun()
        with c2:
            if not df_fornecedores.empty: st.dataframe(df_fornecedores[['Codigo','Nome']])

# --- TAB 5: HISTÓRICO ---
with tab_historico:
    orc = df_cronograma['Orcamento'].sum() if not df_cronograma.empty and 'Orcamento' in df_cronograma.columns else 0
    real = df_custos['Total'].sum() if not df_custos.empty and 'Total' in df_custos.columns else 0
    
    k1, k2, k3 = st.columns(3)
    k1.metric("Orçamento", f"R$ {orc:,.2f}")
    k2.metric("Gasto", f"R$ {real:,.2f}")
    k3.metric("Saldo", f"R$ {orc-real:,.2f}", delta=orc-real)
    
    st.divider()
    if not df_custos.empty:
        df_show = df_custos.copy()
        df_show.insert(0, "Excluir", False)
        
        edited = st.data_editor(
            df_show[["Excluir","Data","Fornecedor","Descricao","Valor","Total","Etapa"]],
            hide_index=True, use_container_width=True,
            disabled=["Data","Fornecedor","Descricao","Valor","Total","Etapa"]
        )
        
        dels = edited[edited["Excluir"]==True]
        if not dels.empty and st.button("Confirmar Exclusão"):
            ws, _, _, _, _, _ = pegar_dados_seguro()
            rows = df_custos.loc[dels.index, "row_num"].tolist()
            rows.sort(reverse=True)
            for r in rows: ws.delete_rows(r)
            st.success("Feito!")
            st.cache_data.clear()
            st.rerun()


