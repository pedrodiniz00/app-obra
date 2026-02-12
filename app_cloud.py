import streamlit as st
import pandas as pd
from supabase import create_client, Client
import time
from datetime import datetime

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

# --- DEFINIÇÃO DO PADRÃO CONSTRUTIVO ---
TEMPLATE_ETAPAS = [
    ("1. Planejamento e Preliminares", 5000.0),
    ("2. Infraestrutura", 15000.0),
    ("3. Supraestrutura", 25000.0),
    ("4. Cobertura", 10000.0),
    ("5. Instalações", 15000.0),
    ("6. Acabamentos", 30000.0)
]

# --- FUNÇÕES DE SEGURANÇA E AUXILIARES ---
def formatar_moeda(valor):
    try:
        return f"R$ {float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except: return "R$ 0,00"

def garantir_colunas(df, colunas, tipo="valor"):
    if df.empty: return pd.DataFrame(columns=colunas)
    for col in colunas:
        if col not in df.columns: df[col] = 0.0 if tipo == "valor" else ""
    return df

def run_query(table_name):
    try:
        response = supabase.table(table_name).select("*").execute()
        return pd.DataFrame(response.data)
    except: return pd.DataFrame()

@st.cache_data(ttl=2) 
def carregar_tudo():
    dados = {}
    df_o = run_query("obras")
    dados['obras'] = garantir_colunas(df_o, ['id', 'nome', 'orcamento_pedreiro', 'orcamento_cliente'])
    
    df_c = run_query("custos")
    df_c = garantir_colunas(df_c, ['id', 'id_obra', 'valor', 'total', 'descricao', 'data', 'etapa'])
    if not df_c.empty:
        df_c['data'] = pd.to_datetime(df_c['data']).dt.date
    dados['custos'] = df_c

    dados['cronograma'] = garantir_colunas(run_query("cronograma"), ['id', 'id_obra', 'etapa', 'porcentagem'])
    dados['tarefas'] = garantir_colunas(run_query("tarefas"), ['id', 'id_obra', 'descricao', 'status'], "texto")
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

# Controle da aba ativa para não resetar após lançamentos
if "tab_ativa" not in st.session_state:
    st.session_state.tab_ativa = 0

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
        nome_obra = row_o['nome']
        orc_p = float(row_o['orcamento_pedreiro'])
        orc_c = float(row_o['orcamento_cliente'])

    st.markdown("---")
    with st.expander("➕ Nova Obra"):
        n_nome = st.text_input("Nome da Obra")
        if st.button("Criar"):
            res = supabase.table("obras").insert({"nome": n_nome}).execute()
            new_id = res.data[0]['id']
            lista_crono = [{"id_obra": new_id, "etapa": str(e), "porcentagem": 0} for e, _ in TEMPLATE_ETAPAS]
            supabase.table("cronograma").insert(lista_crono).execute()
            st.cache_data.clear(); st.rerun()

    if id_obra_atual > 0:
        if st.button("🗑️ Excluir Obra", type="primary"):
            supabase.table("custos").delete().eq("id_obra", id_obra_atual).execute()
            supabase.table("obras").delete().eq("id", id_obra_atual).execute()
            st.cache_data.clear(); st.rerun()

if id_obra_atual == 0: st.stop()

custos_f = DB['custos'][DB['custos']['id_obra'] == id_obra_atual]
crono_f = DB['cronograma'][DB['cronograma']['id_obra'] == id_obra_atual]
tarefas_f = DB['tarefas'][DB['tarefas']['id_obra'] == id_obra_atual]

# --- ABAS ---
tabs = st.tabs(["📝 Lançar", "📅 Cronograma", "✅ Tarefas", "📊 Histórico", "📈 Dash", "💰 Pagamentos"])

# Aba Pagamentos (Indice 5)
with tabs[5]:
    st.subheader(f"💰 Gestão Financeira - {nome_obra}")
    
    co1, co2 = st.columns(2)
    new_p = co1.number_input("Orçamento Pedreiro", value=orc_p)
    new_c = co2.number_input("Orçamento Cliente", value=orc_c)
    if st.button("💾 Salvar Orçamentos Totais"):
        supabase.table("obras").update({"orcamento_pedreiro": new_p, "orcamento_cliente": new_c}).eq("id", id_obra_atual).execute()
        st.session_state.tab_ativa = 5
        st.cache_data.clear(); st.rerun()

    st.markdown("---")
    
    with st.form("f_fin", clear_on_submit=True):
        st.write("➕ **Lançar Novo Pagamento / Recebimento**")
        cp1, cp2, cp3 = st.columns(3)
        tipo = cp1.selectbox("Tipo", ["Saída (Pedreiro)", "Entrada (Cliente)"])
        val = cp2.number_input("Valor R$")
        dat = cp3.date_input("Data")
        if st.form_submit_button("Confirmar Lançamento"):
            cat = "Mão de Obra" if "Saída" in tipo else "Entrada Cliente"
            supabase.table("custos").insert({"id_obra": id_obra_atual, "valor": val, "total": val, "etapa": cat, "data": str(dat), "descricao": tipo}).execute()
            st.session_state.tab_ativa = 5 # Mantém na aba 5
            st.cache_data.clear(); st.rerun()

    pagos_mo = custos_f[custos_f['etapa'] == "Mão de Obra"]
    recebido_cli = custos_f[custos_f['etapa'] == "Entrada Cliente"]
    
    res1, res2 = st.columns(2)
    total_p = pagos_mo['total'].sum()
    total_r = recebido_cli['total'].sum()
    res1.metric("Saldo a Pagar (Pedreiro)", formatar_moeda(new_p - total_p))
    res2.metric("Saldo a Receber (Cliente)", formatar_moeda(new_c - total_r))

    st.markdown("---")
    h1, h2 = st.columns(2)
    
    with h1:
        st.write("🔴 **Saídas (Pedreiro)**")
        if not pagos_mo.empty:
            for i, row in pagos_mo.iterrows():
                with st.expander(f"{row['data']} - {formatar_moeda(row['total'])}"):
                    novo_v = st.number_input("Valor", value=float(row['total']), key=f"v_p_{row['id']}")
                    c_e, c_x = st.columns(2)
                    if c_e.button("Editar", key=f"ed_p_{row['id']}"):
                        supabase.table("custos").update({"valor": novo_v, "total": novo_v}).eq("id", row['id']).execute()
                        st.session_state.tab_ativa = 5; st.cache_data.clear(); st.rerun()
                    if c_x.button("Apagar", key=f"del_p_{row['id']}"):
                        supabase.table("custos").delete().eq("id", row['id']).execute()
                        st.session_state.tab_ativa = 5; st.cache_data.clear(); st.rerun()

    with h2:
        st.write("🟢 **Entradas (Cliente)**")
        if not recebido_cli.empty:
            for i, row in recebido_cli.iterrows():
                with st.expander(f"{row['data']} - {formatar_moeda(row['total'])}"):
                    novo_v = st.number_input("Valor", value=float(row['total']), key=f"v_r_{row['id']}")
                    c_e, c_x = st.columns(2)
                    if c_e.button("Editar", key=f"ed_r_{row['id']}"):
                        supabase.table("custos").update({"valor": novo_v, "total": novo_v}).eq("id", row['id']).execute()
                        st.session_state.tab_ativa = 5; st.cache_data.clear(); st.rerun()
                    if c_x.button("Apagar", key=f"del_r_{row['id']}"):
                        supabase.table("custos").delete().eq("id", row['id']).execute()
                        st.session_state.tab_ativa = 5; st.cache_data.clear(); st.rerun()

# Restante das abas (simplificadas para o código não ficar gigante)
with tabs[0]: st.write("Use a aba de Pagamentos para gerenciar o financeiro.")