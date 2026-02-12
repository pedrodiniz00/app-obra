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
    # Obras
    df_o = run_query("obras")
    dados['obras'] = garantir_colunas(df_o, ['id', 'nome', 'orcamento_pedreiro', 'orcamento_cliente'])
    
    # Custos
    df_c = run_query("custos")
    df_c = garantir_colunas(df_c, ['id', 'id_obra', 'valor', 'total', 'descricao', 'data', 'etapa'])
    if not df_c.empty:
        df_c['data'] = pd.to_datetime(df_c['data']).dt.date
    dados['custos'] = df_c

    # Cronograma e Tarefas
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
        if st.button("🗑️ Excluir Obra Atual", type="primary"):
            supabase.table("custos").delete().eq("id_obra", id_obra_atual).execute()
            supabase.table("obras").delete().eq("id", id_obra_atual).execute()
            st.cache_data.clear(); st.rerun()

if id_obra_atual == 0: st.stop()

custos_f = DB['custos'][DB['custos']['id_obra'] == id_obra_atual]
crono_f = DB['cronograma'][DB['cronograma']['id_obra'] == id_obra_atual]
tarefas_f = DB['tarefas'][DB['tarefas']['id_obra'] == id_obra_atual]

# --- ABAS ---
tabs = st.tabs(["📝 Lançar", "📅 Cronograma", "✅ Tarefas", "📊 Histórico", "📈 Dash", "💰 Pagamentos"])

with tabs[0]: # Lançar
    with st.form("f_lancar", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        d = c1.text_input("Descrição")
        v = c2.number_input("Valor")
        e = st.selectbox("Etapa", [et for et, _ in TEMPLATE_ETAPAS])
        if st.form_submit_button("Salvar"):
            supabase.table("custos").insert({"id_obra": id_obra_atual, "descricao": d, "valor": v, "total": v, "etapa": e, "data": str(datetime.now().date())}).execute()
            st.cache_data.clear(); st.rerun()

with tabs[1]: # Cronograma
    for _, r in crono_f.iterrows():
        st.write(f"**{r['etapa']}**")
        p = st.slider("%", 0, 100, int(r['porcentagem']), key=f"c_{r['id']}")
        if p != int(r['porcentagem']):
            supabase.table("cronograma").update({"porcentagem": p}).eq("id", r['id']).execute()
            st.cache_data.clear(); st.rerun()

with tabs[2]: # Tarefas
    with st.form("f_tar", clear_on_submit=True):
        nt = st.text_input("Nova Tarefa")
        if st.form_submit_button("Add"):
            supabase.table("tarefas").insert({"id_obra": id_obra_atual, "descricao": nt, "status": "Pendente"}).execute()
            st.cache_data.clear(); st.rerun()
    st.data_editor(tarefas_f[['descricao', 'status']], use_container_width=True)

with tabs[3]: # Histórico
    st.dataframe(custos_f[['data', 'descricao', 'total', 'etapa']], use_container_width=True)

with tabs[5]: # 💰 PAGAMENTOS (FOCO DA SOLICITAÇÃO)
    st.subheader(f"💰 Gestão Financeira - {nome_obra}")
    
    # Configuração de Orçamentos
    co1, co2 = st.columns(2)
    new_p = co1.number_input("Orçamento Pedreiro", value=orc_p)
    new_c = co2.number_input("Orçamento Cliente", value=orc_c)
    if st.button("💾 Salvar Orçamentos Totais"):
        supabase.table("obras").update({"orcamento_pedreiro": new_p, "orcamento_cliente": new_c}).eq("id", id_obra_atual).execute()
        st.cache_data.clear(); st.rerun()

    st.markdown("---")
    
    # Lançamentos Financeiros
    with st.form("f_fin", clear_on_submit=True):
        st.write("➕ **Lançar Pagamento / Recebimento**")
        cp1, cp2, cp3 = st.columns(3)
        tipo = cp1.selectbox("Tipo", ["Saída (Pedreiro)", "Entrada (Cliente)"])
        val = cp2.number_input("Valor R$")
        dat = cp3.date_input("Data")
        if st.form_submit_button("Confirmar Lançamento"):
            cat = "Mão de Obra" if "Saída" in tipo else "Entrada Cliente"
            supabase.table("custos").insert({"id_obra": id_obra_atual, "valor": val, "total": val, "etapa": cat, "data": str(dat), "descricao": tipo}).execute()
            st.cache_data.clear(); st.rerun()

    # Cálculos de Saldo
    pagos_mo = custos_f[custos_f['etapa'] == "Mão de Obra"]
    recebido_cli = custos_f[custos_f['etapa'] == "Entrada Cliente"]
    
    total_pago = pagos_mo['total'].sum()
    total_recebido = recebido_cli['total'].sum()

    st.markdown("### 📊 Resumo de Saldos")
    res1, res2 = st.columns(2)
    res1.metric("Saldo a Pagar (Pedreiro)", formatar_moeda(new_p - total_pago), delta=formatar_moeda(total_pago), delta_color="inverse")
    res2.metric("Saldo a Receber (Cliente)", formatar_moeda(new_c - total_recebido), delta=formatar_moeda(total_recebido))

    st.markdown("---")
    # Tabelas de Histórico
    h1, h2 = st.columns(2)
    with h1:
        st.write("🔴 **Histórico de Pagamentos (Pedreiro)**")
        st.dataframe(pagos_mo[['data', 'total']], hide_index=True, use_container_width=True)
    with h2:
        st.write("🟢 **Histórico de Recebimentos (Cliente)**")
        st.dataframe(recebido_cli[['data', 'total']], hide_index=True, use_container_width=True)