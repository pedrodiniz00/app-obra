import streamlit as st
import pandas as pd
from supabase import create_client, Client
import time
from datetime import datetime
import numpy as np 

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Gestão de Obra PRO", layout="wide", page_icon="🏗️")

# --- CONEXÃO SUPABASE ---
@st.cache_resource
def init_connection():
    try:
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"]
        return create_client(url, key)
    except Exception as e:
        st.error(f"Erro de Conexão: {e}")
        st.stop()

supabase = init_connection()

# --- FUNÇÕES DE LIMPEZA E SEGURANÇA (O segredo para o erro sumir) ---
def garantir_colunas(df, colunas_desejadas, tipo="valor"):
    """Cria colunas faltantes no DataFrame para evitar KeyError"""
    if df.empty:
        return pd.DataFrame(columns=colunas_desejadas)
    for col in colunas_desejadas:
        if col not in df.columns:
            df[col] = 0.0 if tipo == "valor" else ""
    return df

def run_query(table_name):
    try:
        response = supabase.table(table_name).select("*").execute()
        return pd.DataFrame(response.data)
    except: return pd.DataFrame()

@st.cache_data(ttl=2) 
def carregar_tudo():
    dados = {}
    # 1. Obras
    df_obras = run_query("obras")
    df_obras = garantir_colunas(df_obras, ['id', 'nome', 'orcamento_pedreiro', 'orcamento_cliente'])
    dados['obras'] = df_obras
    
    # 2. Custos
    df_custos = run_query("custos")
    df_custos = garantir_colunas(df_custos, ['id', 'id_obra', 'valor', 'qtd', 'total', 'descricao', 'data', 'etapa'])
    if not df_custos.empty:
        df_custos['total'] = df_custos['valor'] * df_custos['qtd'] # Recalcula por segurança
        df_custos['data'] = pd.to_datetime(df_custos['data']).dt.date
    dados['custos'] = df_custos

    # 3. Cronograma e Tarefas
    dados['cronograma'] = garantir_colunas(run_query("cronograma"), ['id', 'id_obra', 'etapa', 'porcentagem'])
    dados['tarefas'] = garantir_colunas(run_query("tarefas"), ['id', 'id_obra', 'descricao', 'responsavel', 'status'], "texto")
    
    return dados

# --- LOGIN ---
if "password_correct" not in st.session_state: st.session_state["password_correct"] = False
if not st.session_state["password_correct"]:
    c1, c2, c3 = st.columns([1,2,1])
    with c2:
        st.title("🔒 Acesso")
        pwd = st.text_input("Senha", type="password")
        if st.button("Entrar"):
            if pwd == st.secrets["acesso"]["senha_admin"]:
                st.session_state["password_correct"] = True
                st.rerun()
    st.stop()

# --- INTERFACE ---
DB = carregar_tudo()
formatar_r = lambda v: f"R$ {float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

with st.sidebar:
    st.header("🏢 Obra Ativa")
    id_obra_atual = 0
    if DB['obras'].empty:
        st.warning("Crie uma obra.")
    else:
        opcoes = DB['obras'].apply(lambda x: f"{x['id']} - {x['nome']}", axis=1).tolist()
        selecao = st.selectbox("Selecione:", opcoes)
        id_obra_atual = int(selecao.split(" - ")[0])
        row_o = DB['obras'][DB['obras']['id'] == id_obra_atual].iloc[0]
        orc_p = float(row_o['orcamento_pedreiro'])
        orc_c = float(row_o['orcamento_cliente'])
        nome_o = row_o['nome']

    if st.button("🗑️ Excluir Obra Atual", type="primary") and id_obra_atual > 0:
        supabase.table("custos").delete().eq("id_obra", id_obra_atual).execute()
        supabase.table("obras").delete().eq("id", id_obra_atual).execute()
        st.cache_data.clear(); st.rerun()

if id_obra_atual == 0: st.stop()

custos_f = DB['custos'][DB['custos']['id_obra'] == id_obra_atual]

# --- ABAS (ESTRUTURA ORIGINAL) ---
t1, t2, t3, t4, t5, t6 = st.tabs(["📝 Lançar", "📅 Cronograma", "✅ Tarefas", "📊 Histórico", "📈 Dash", "💰 Pagamentos"])

with t1: # Lançar
    with st.form("f1", clear_on_submit=True):
        col1, col2 = st.columns(2)
        desc = col1.text_input("Item")
        v_u = col2.number_input("Valor Unitário", 0.0)
        etp = st.selectbox("Etapa", ["Infra", "Supra", "Acabamento", "Mão de Obra"])
        if st.form_submit_button("Salvar"):
            supabase.table("custos").insert({"id_obra": id_obra_atual, "descricao": desc, "valor": v_u, "total": v_u, "etapa": etp, "data": str(datetime.now().date())}).execute()
            st.cache_data.clear(); st.rerun()

with t6: # Pagamentos (Aba solicitada com entradas/saídas)
    st.subheader(f"💰 Financeiro - {nome_o}")
    c_orc1, c_orc2 = st.columns(2)
    new_p = c_orc1.number_input("Orc. Pedreiro", value=orc_p)
    new_c = c_orc2.number_input("Orc. Cliente", value=orc_c)
    if st.button("💾 Salvar Orçamentos"):
        supabase.table("obras").update({"orcamento_pedreiro": new_p, "orcamento_cliente": new_c}).eq("id", id_obra_atual).execute()
        st.cache_data.clear(); st.rerun()

    pago_mo = custos_f[custos_f['etapa'] == "Mão de Obra"]
    recebido = custos_f[custos_f['etapa'] == "Entrada Cliente"]
    
    col_res1, col_res2 = st.columns(2)
    col_res1.metric("Saldo Pedreiro", formatar_r(new_p - pago_mo['total'].sum()))
    col_res2.metric("Saldo Cliente", formatar_r(new_c - recebido['total'].sum()))

    st.markdown("---")
    h1, h2 = st.columns(2)
    h1.write("🔴 Saídas (Pedreiro)")
    h1.dataframe(pago_mo[['data', 'total']], hide_index=True)
    h2.write("🟢 Entradas (Cliente)")
    h2.dataframe(recebido[['data', 'total']], hide_index=True)