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
        if tbl == 'custos' and not df.empty:
            df['data'] = pd.to_datetime(df['data']).dt.date
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

# --- SIDEBAR (SISTEMA DE EXCLUSÃO DIRETA RESTAURADO) ---
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
                lista_crono = [{"id_obra": new_id, "etapa": str(e), "porcentagem": 0} for e, _ in TEMPLATE_ETAPAS]
                supabase.table("cronograma").insert(lista_crono).execute()
                st.success("Obra Criada!"); st.cache_data.clear(); time.sleep(1); st.rerun()

    if id_obra_atual > 0:
        st.markdown("---")
        if st.button("🗑️ Excluir Obra Atual", type="primary"):
            # Exclusão definitiva direta
            supabase.table("custos").delete().eq("id_obra", id_obra_atual).execute()
            supabase.table("cronograma").delete().eq("id_obra", id_obra_atual).execute()
            supabase.table("tarefas").delete().eq("id_obra", id_obra_atual).execute()
            supabase.table("obras").delete().eq("id", id_obra_atual).execute()
            st.error("Obra excluída permanentemente!"); st.cache_data.clear(); time.sleep(1); st.rerun()

if id_obra_atual == 0:
    st.info("👈 Selecione ou crie uma obra no menu lateral.")
    st.stop()

custos_f = DB['custos'][DB['custos']['id_obra'] == id_obra_atual] if not DB['custos'].empty else pd.DataFrame()

# --- ABAS ---
tabs = st.tabs(["📝 Lançar", "📅 Cronograma", "✅ Tarefas", "📊 Histórico", "📈 Dash", "💰 Pagamentos"])

# Aba 6: PAGAMENTOS (ESTRUTURA COMPLETA MANTIDA)
with tabs[5]:
    st.subheader(f"💰 Gestão Financeira - {nome_obra_atual}")
    
    col_orc1, col_orc2 = st.columns(2)
    with col_orc1:
        novo_orc_p = st.number_input("Orçamento Pedreiro (R$)", min_value=0.0, value=orc_pedreiro_atual, step=100.0)
    with col_orc2:
        novo_orc_c = st.number_input("Orçamento Cliente (R$)", min_value=0.0, value=orc_cliente_atual, step=100.0)
        
    if st.button("💾 Salvar Orçamentos"):
        supabase.table("obras").update({"orcamento_pedreiro": novo_orc_p, "orcamento_cliente": novo_orc_c}).eq("id", id_obra_atual).execute()
        st.success("Orçamentos atualizados!"); st.cache_data.clear(); st.rerun()
    
    st.markdown("---")
    
    with st.form("form_financeiro", clear_on_submit=True):
        st.write("➕ **Lançar Movimentação**")
        cp1, cp2, cp3 = st.columns(3)
        tipo = cp1.selectbox("Tipo", ["Pagamento (Saída)", "Recebimento (Entrada)"])
        dt_mov = cp2.date_input("Data", datetime.now())
        v_mov = cp3.number_input("Valor (R$)", min_value=0.0)
        
        if st.form_submit_button("Confirmar Lançamento"):
            if v_mov > 0:
                etapa_fin = "Mão de Obra" if tipo == "Pagamento (Saída)" else "Entrada Cliente"
                desc_fin = "Pagamento Pedreiro" if tipo == "Pagamento (Saída)" else "Recebimento Cliente"
                supabase.table("custos").insert({
                    "id_obra": id_obra_atual, "descricao": desc_fin,
                    "valor": v_mov, "qtd": 1, "total": v_mov,
                    "etapa": etapa_fin, "data": str(dt_mov)
                }).execute()
                st.success("Lançamento realizado!"); st.cache_data.clear(); st.rerun()

    pagos_mo = custos_f[custos_f['etapa'] == "Mão de Obra"] if not custos_f.empty else pd.DataFrame()
    recebido_cli = custos_f[custos_f['etapa'] == "Entrada Cliente"] if not custos_f.empty else pd.DataFrame()
    
    st.markdown("### 📊 Resumo")
    r1, r2 = st.columns(2)
    with r1:
        total_p_mo = pagos_mo['total'].sum() if not pagos_mo.empty else 0
        st.info("**Mão de Obra**")
        st.metric("Total Pago", formatar_moeda(total_p_mo))
        st.metric("Saldo a Pagar", formatar_moeda(novo_orc_p - total_p_mo), delta_color="inverse")
    with r2:
        total_r_cli = recebido_cli['total'].sum() if not recebido_cli.empty else 0
        st.success("**Cliente**")
        st.metric("Total Recebido", formatar_moeda(total_r_cli))
        st.metric("Saldo a Receber", formatar_moeda(novo_orc_c - total_r_cli))

    st.markdown("---")
    ch1, ch2 = st.columns(2)
    with ch1:
        st.write("🔴 **Saídas (Pedreiro)**")
        st.dataframe(pagos_mo[['data', 'total']], hide_index=True, use_container_width=True,
                     column_config={"data": st.column_config.DateColumn(format="DD/MM/YYYY"), "total": st.column_config.NumberColumn(format="R$ %.2f")})
    with ch2:
        st.write("🟢 **Entradas (Cliente)**")
        st.dataframe(recebido_cli[['data', 'total']], hide_index=True, use_container_width=True,
                     column_config={"data": st.column_config.DateColumn(format="DD/MM/YYYY"), "total": st.column_config.NumberColumn(format="R$ %.2f")})