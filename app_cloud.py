import streamlit as st
import pandas as pd
from supabase import create_client, Client
import time
from datetime import datetime
import numpy as np 
import re 

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
        st.error(f"❌ Erro de Conexão: {e}")
        st.stop()

supabase = init_connection()

# --- DEFINIÇÃO DO PADRÃO CONSTRUTIVO ---
TEMPLATE_ETAPAS = [
    ("1. Planejamento e Preliminares", 5000.0),
    ("2. Infraestrutura", 15000.0),
    ("3. Supraestrutura", 25000.0),
    ("4. Cobertura", 10000.0),
    ("5. Instalações", 15000.0),
    ("6. Acabamentos", 30000.0)
]

# --- FUNÇÕES AUXILIARES ---
def formatar_moeda(valor):
    try:
        return f"R$ {float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except: return "R$ 0,00"

def run_query(table_name):
    try:
        response = supabase.table(table_name).select("*").execute()
        return pd.DataFrame(response.data)
    except: return pd.DataFrame()

@st.cache_data(ttl=2) 
def carregar_tudo():
    dados = {}
    for tbl in ["obras", "custos", "cronograma", "tarefas"]:
        df = run_query(tbl)
        if tbl == 'obras':
            # Proteção contra colunas faltantes (KeyError)
            for col in ['status', 'orcamento_pedreiro', 'orcamento_cliente']:
                if col not in df.columns: df[col] = "Ativa" if col == 'status' else 0.0
        dados[tbl] = df
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

if "active_tab" not in st.session_state: st.session_state.active_tab = "📝 Lançar"

with st.sidebar:
    st.header("🏢 Obra Ativa")
    id_obra_atual = 0
    nome_obra_atual = ""
    orc_pedreiro_atual = 0.0
    orc_cliente_atual = 0.0

    # Seleção de Obras Ativas
    obras_ativas = DB['obras'][DB['obras']['status'] == 'Ativa'] if not DB['obras'].empty else pd.DataFrame()
    
    if not obras_ativas.empty:
        opcoes = obras_ativas.apply(lambda x: f"{x['id']} - {x['nome']}", axis=1).tolist()
        selecao = st.selectbox("Selecione a Obra:", opcoes)
        id_obra_atual = int(selecao.split(" - ")[0])
        nome_obra_atual = selecao.split(" - ")[1]
        row = obras_ativas[obras_ativas['id'] == id_obra_atual].iloc[0]
        orc_pedreiro_atual = float(row.get('orcamento_pedreiro', 0))
        orc_cliente_atual = float(row.get('orcamento_cliente', 0))
    else:
        st.warning("Nenhuma obra ativa.")

    st.markdown("---")
    with st.expander("➕ Nova Obra"):
        n_nome = st.text_input("Nome da Obra")
        if st.button("Criar"):
            res = supabase.table("obras").insert({"nome": n_nome, "status": "Ativa"}).execute()
            st.cache_data.clear(); st.rerun()

    if id_obra_atual > 0:
        if st.button("📦 Arquivar Obra"):
            supabase.table("obras").update({"status": "Arquivada"}).eq("id", id_obra_atual).execute()
            st.cache_data.clear(); st.rerun()

    with st.expander("🗄️ Arquivadas"):
        obras_arq = DB['obras'][DB['obras']['status'] == 'Arquivada'] if not DB['obras'].empty else pd.DataFrame()
        for _, arq in obras_arq.iterrows():
            st.write(arq['nome'])
            c_a1, c_a2 = st.columns(2)
            if c_a1.button("🔄", key=f"r{arq['id']}"):
                supabase.table("obras").update({"status": "Ativa"}).eq("id", arq['id']).execute()
                st.cache_data.clear(); st.rerun()
            if c_a2.button("🗑️", key=f"d{arq['id']}"):
                supabase.table("obras").delete().eq("id", arq['id']).execute()
                st.cache_data.clear(); st.rerun()

if id_obra_atual == 0:
    st.stop()

# Filtros
custos_f = DB['custos'][DB['custos']['id_obra'] == id_obra_atual] if not DB['custos'].empty else pd.DataFrame()

# --- ABAS ---
tabs = st.tabs(["📝 Lançar", "📅 Cronograma", "✅ Tarefas", "📊 Histórico", "📈 Dash", "💰 Pagamentos"])

# ABA PAGAMENTOS (Ajustada)
with tabs[5]:
    st.subheader(f"💰 Financeiro - {nome_obra_atual}")
    c_o1, c_o2 = st.columns(2)
    new_p = c_o1.number_input("Orçamento Pedreiro", value=orc_pedreiro_atual)
    new_c = c_o2.number_input("Orçamento Cliente", value=orc_cliente_atual)
    
    if st.button("💾 Salvar Orçamentos"):
        supabase.table("obras").update({"orcamento_pedreiro": new_p, "orcamento_cliente": new_c}).eq("id", id_obra_atual).execute()
        st.cache_data.clear(); st.rerun()

    with st.form("mov"):
        col1, col2, col3 = st.columns(3)
        tipo = col1.selectbox("Tipo", ["Saída (Pedreiro)", "Entrada (Cliente)"])
        v = col2.number_input("Valor R$")
        if st.form_submit_button("Lançar"):
            cat = "Mão de Obra" if "Saída" in tipo else "Entrada Cliente"
            supabase.table("custos").insert({"id_obra": id_obra_atual, "valor": v, "total": v, "etapa": cat, "data": str(datetime.now().date()), "descricao": tipo}).execute()
            st.cache_data.clear(); st.rerun()

    # Resumo
    pago = custos_f[custos_f['etapa'] == "Mão de Obra"]['total'].sum() if not custos_f.empty else 0
    recebido = custos_f[custos_f['etapa'] == "Entrada Cliente"]['total'].sum() if not custos_f.empty else 0
    
    r1, r2 = st.columns(2)
    r1.metric("Saldo Pedreiro", formatar_moeda(new_p - pago))
    r2.metric("Saldo Cliente", formatar_moeda(new_c - recebido))