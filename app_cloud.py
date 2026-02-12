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
            for col in ['orcamento_pedreiro', 'orcamento_cliente']:
                if col not in df.columns: df[col] = 0.0
            if df.empty: df = pd.DataFrame(columns=['id', 'nome', 'orcamento_pedreiro', 'orcamento_cliente'])
        
        if tbl == 'custos':
            # PROTEÇÃO CONTRA KEYERROR 'TOTAL'
            if not df.empty:
                if 'valor' not in df.columns: df['valor'] = 0.0
                if 'qtd' not in df.columns: df['qtd'] = 1.0
                if 'total' not in df.columns: df['total'] = df['valor'] * df['qtd']
                df['data'] = pd.to_datetime(df['data']).dt.date
            else:
                df = pd.DataFrame(columns=['id', 'id_obra', 'valor', 'total', 'qtd', 'descricao', 'data', 'etapa'])
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

with st.sidebar:
    st.header("🏢 Obra Ativa")
    id_obra_atual = 0
    nome_obra_atual = ""
    orc_pedreiro_atual = 0.0
    orc_cliente_atual = 0.0

    if DB['obras'].empty:
        st.warning("Nenhuma obra cadastrada.")
    else:
        opcoes = DB['obras'].apply(lambda x: f"{x['id']} - {x['nome']}", axis=1).tolist()
        selecao = st.selectbox("Selecione a Obra:", opcoes)
        try:
            temp_id = int(selecao.split(" - ")[0])
            id_obra_atual = temp_id
            nome_obra_atual = selecao.split(" - ")[1]
            row = DB['obras'][DB['obras']['id'] == id_obra_atual].iloc[0]
            orc_pedreiro_atual = float(row.get('orcamento_pedreiro', 0))
            orc_cliente_atual = float(row.get('orcamento_cliente', 0))
        except: id_obra_atual = 0

    st.markdown("---")
    with st.expander("➕ Nova Obra"):
        n_nome = st.text_input("Nome da Obra")
        if st.button("Criar Obra"):
            if n_nome:
                res = supabase.table("obras").insert({"nome": n_nome}).execute()
                new_id = res.data[0]['id']
                st.success("Obra Criada!"); st.cache_data.clear(); time.sleep(1); st.rerun()

    if id_obra_atual > 0:
        if st.button("🗑️ Excluir Obra Atual", type="primary"):
            supabase.table("custos").delete().eq("id_obra", id_obra_atual).execute()
            supabase.table("obras").delete().eq("id", id_obra_atual).execute()
            st.error("Excluída!"); st.cache_data.clear(); time.sleep(1); st.rerun()

if id_obra_atual == 0:
    st.stop()

custos_f = DB['custos'][DB['custos']['id_obra'] == id_obra_atual] if not DB['custos'].empty else pd.DataFrame()

# --- ABAS ---
tabs = st.tabs(["📝 Lançar", "📊 Histórico", "📈 Dash", "💰 Pagamentos"])

# ABA LANÇAR
with tabs[0]:
    st.subheader(f"Lançar Custo - {nome_obra_atual}")
    with st.form("lancar_form", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        desc = c1.text_input("Descrição")
        valor = c2.number_input("Valor Unitário (R$)", 0.0)
        qtd = c3.number_input("Qtd", 1.0)
        etapa = st.selectbox("Etapa", [e for e, _ in TEMPLATE_ETAPAS] + ["Mão de Obra"])
        if st.form_submit_button("Salvar"):
            supabase.table("custos").insert({"id_obra": id_obra_atual, "descricao": desc, "valor": valor, "qtd": qtd, "total": valor*qtd, "etapa": etapa, "data": str(datetime.now().date())}).execute()
            st.success("Salvo!"); st.cache_data.clear(); st.rerun()

# ABA HISTÓRICO
with tabs[1]:
    if not custos_f.empty:
        st.dataframe(custos_f[['data', 'descricao', 'total', 'etapa']], use_container_width=True, 
                     column_config={"data": st.column_config.DateColumn(format="DD/MM/YYYY"), "total": st.column_config.NumberColumn(format="R$ %.2f")})

# ABA PAGAMENTOS
with tabs[3]:
    st.subheader(f"💰 Financeiro - {nome_obra_atual}")
    c_o1, c_o2 = st.columns(2)
    novo_orc_p = c_o1.number_input("Orçamento Pedreiro", value=orc_pedreiro_atual)
    novo_orc_c = c_o2.number_input("Orçamento Cliente", value=orc_cliente_atual)
    
    if st.button("💾 Salvar Orçamentos"):
        supabase.table("obras").update({"orcamento_pedreiro": novo_orc_p, "orcamento_cliente": novo_orc_c}).eq("id", id_obra_atual).execute()
        st.cache_data.clear(); st.rerun()

    pagos_mo = custos_f[custos_f['etapa'] == "Mão de Obra"] if not custos_f.empty else pd.DataFrame()
    recebido_cli = custos_f[custos_f['etapa'] == "Entrada Cliente"] if not custos_f.empty else pd.DataFrame()

    r1, r2 = st.columns(2)
    with r1:
        st.info("**Mão de Obra**")
        p = pagos_mo['total'].sum() if not pagos_mo.empty else 0
        st.metric("Total Pago", formatar_moeda(p))
        st.metric("Saldo a Pagar", formatar_moeda(novo_orc_p - p))
        if not pagos_mo.empty:
            st.write("🔴 Saídas")
            st.dataframe(pagos_mo[['data', 'total']], hide_index=True)

    with r2:
        st.success("**Cliente**")
        r = recebido_cli['total'].sum() if not recebido_cli.empty else 0
        st.metric("Total Recebido", formatar_moeda(r))
        st.metric("Saldo a Receber", formatar_moeda(novo_orc_c - r))
        if not recebido_cli.empty:
            st.write("🟢 Entradas")
            st.dataframe(recebido_cli[['data', 'total']], hide_index=True)