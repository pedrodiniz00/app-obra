import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials

st.set_page_config(page_title="Gestão de Obra Pro", layout="wide")

# --- CONEXÃO ---
def conectar_gsheets():
    try:
        if "gcp_service_account" not in st.secrets:
            st.error("Secrets não configurados.")
            return None, None
        
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sh = client.open("Dados_Obra")
        return client, sh
    except Exception as e:
        st.error(f"Erro de conexão: {e}")
        return None, None

# --- FUNÇÃO AUTO-CORRETORA DE CRONOGRAMA ---
def garantir_cronograma(sh):
    etapas_padrao = ["Fundação", "Alvenaria", "Laje", "Reboco Externo", "Reboco Interno", "Acabamento"]
    
    try:
        ws = sh.worksheet("Cronograma")
    except:
        ws = sh.add_worksheet(title="Cronograma", rows=20, cols=3)

    # Verifica se a aba está vazia ou com cabeçalho errado
    valores = ws.get_all_values()
    
    # Se tiver menos de 2 linhas ou o cabeçalho estiver errado, REFAZ TUDO
    if len(valores) < 2 or valores[0] != ["Etapa", "Status", "Responsavel"]:
        ws.clear() # Limpa a bagunça
        ws.append_row(["Etapa", "Status", "Responsavel"]) # Cria Cabeçalho
        for etapa in etapas_padrao:
            ws.append_row([etapa, "Pendente", "-"])
        st.toast("Aba Cronograma configurada automaticamente!", icon="✅")
            
    return ws

# --- CARREGAR CUSTOS ---
def carregar_custos(sh):
    ws = sh.sheet1
    try:
        df = pd.DataFrame(ws.get_all_records())
    except:
        df = pd.DataFrame()
    return ws, df

# --- APP ---
client, sh = conectar_gsheets()

if sh:
    # 1. Garante que as abas existem e estão certas
    ws_cronograma = garantir_cronograma(sh)
    ws_custos, df_custos = carregar_custos(sh)

    # 2. Lê os dados do cronograma já corrigidos
    df_cronograma = pd.DataFrame(ws_cronograma.get_all_records())

    st.title("🏗️ Gestor de Obras")

    # --- BARRA LATERAL (CHECKBOXES) ---
    st.sidebar.header("📅 Etapas")
    
    # Barra de Progresso
    total = len(df_cronograma)
    feitos = len(df_cronograma[df_cronograma['Status'] == 'Concluído'])
    progresso = feitos / total if total > 0 else 0
    st.sidebar.progress(progresso)
    st.sidebar.caption(f"{int(progresso*100)}% Concluído")
    
    # Checkboxes com atualização em tempo real
    lista_etapas = df_cronograma.to_dict('records')
    for i, item in enumerate(lista_etapas):
        nome = item['Etapa']
        status_bool = True if item['Status'] == 'Concluído' else False
        
        # O key=f"check_{i}" é vital para não misturar os botões
        novo_check = st.sidebar.checkbox(nome, value=status_bool, key=f"check_{i}")
        
        # Se mudou o status, salva no Google
        if novo_check != status_bool:
            novo_texto = "Concluído" if novo_check else "Pendente"
            ws_cronograma.update_cell(i + 2, 2, novo_texto)
            st.rerun()

    # --- TELA PRINCIPAL (CUSTOS) ---
    with st.expander("💰 Novo Gasto", expanded=True):
        c1, c2, c3 = st.columns(3)
        dt = c1.date_input("Data")
        desc = c1.text_input("Descrição")
        classe = c1.selectbox("Classe", ["Material", "Mão de Obra", "Ferramentas", "Outros"])
        
        qtd = c2.number_input("Qtd", 1.0)
        un = c2.selectbox("Un", ["un", "m", "m2", "m3", "kg", "dia"])
        sub = c2.text_input("Subclasse (ex: Cimento)")
        
        val = c3.number_input("Valor Unit.", 0.0)
        vinc = c3.selectbox("Etapa", df_cronograma['Etapa'].tolist())
        
        if st.button("Salvar"):
            ws_custos.append_row([
                str(dt), desc, qtd, un, val, qtd*val, classe, sub, vinc
            ])
            st.success("Salvo!")
            st.rerun()

    # --- RELATÓRIO ---
    if not df_custos.empty:
        # Garante que a coluna 'total' seja numérica para somar
        if 'total' in df_custos.columns:
            total_gasto = pd.to_numeric(df_custos['total'], errors='coerce').sum()
            st.metric("Total Gasto", f"R$ {total_gasto:,.2f}")
            st.dataframe(df_custos, use_container_width=True)
