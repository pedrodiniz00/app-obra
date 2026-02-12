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

# --- PADRÃO DE ETAPAS (Baseado no seu cronograma.xlsx) ---
ETAPAS_PADRAO = [
    {"pai": "1. Planejamento e Preliminares", "sub": "Projetos e Aprovações"},
    {"pai": "1. Planejamento e Preliminares", "sub": "Limpeza do Terreno"},
    {"pai": "1. Planejamento e Preliminares", "sub": "Ligação Provisória (Água/Luz)"},
    {"pai": "1. Planejamento e Preliminares", "sub": "Barracão e Tapumes"},
    {"pai": "2. Infraestrutura (Fundação)", "sub": "Gabarito e Marcação"},
    {"pai": "2. Infraestrutura (Fundação)", "sub": "Escavação"},
    {"pai": "2. Infraestrutura (Fundação)", "sub": "Concretagem Sapatas/Estacas"},
    {"pai": "2. Infraestrutura (Fundação)", "sub": "Vigas Baldrame"},
    {"pai": "2. Infraestrutura (Fundação)", "sub": "Impermeabilização"},
    {"pai": "2. Infraestrutura (Fundação)", "sub": "Passagem de tubulação de esgoto"},
    {"pai": "3. Supraestrutura e Alvenaria", "sub": "Pilares/Vigas/Lajes"},
    {"pai": "3. Supraestrutura e Alvenaria", "sub": "Levantamento de Paredes"},
    {"pai": "3. Supraestrutura e Alvenaria", "sub": "Marcação das Paredes"},
    {"pai": "3. Supraestrutura e Alvenaria", "sub": "Impermeabilização das 3 fiadas"},
    {"pai": "4. Cobertura", "sub": "Estrutura Telhado e Telhamento"},
    {"pai": "4. Cobertura", "sub": "Montagem da Lage"},
    {"pai": "5. Instalações", "sub": "Tubulação Água/Esgoto"},
    {"pai": "5. Instalações", "sub": "Eletrodutos e Caixinhas"},
    {"pai": "6. Acabamentos", "sub": "Reboco/Gesso"},
    {"pai": "6. Acabamentos", "sub": "Revestimentos (Piso/Parede)"},
    {"pai": "6. Acabamentos", "sub": "Pintura Interna/Externa"}
]

# --- FUNÇÕES AUXILIARES ---
def formatar_moeda(valor):
    try: 
        return f"R$ {float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except: 
        return "R$ 0,00"

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
    for tbl in ["obras", "custos", "cronograma", "tarefas"]:
        df = run_query(tbl)
        if tbl == 'obras':
            df = garantir_colunas(df, ['id', 'nome', 'orcamento_pedreiro', 'orcamento_cliente'])
        if tbl == 'custos':
            df = garantir_colunas(df, ['id', 'id_obra', 'valor', 'total', 'descricao', 'data', 'etapa'])
            if not df.empty: 
                df['data'] = pd.to_datetime(df['data']).dt.date
        if tbl == 'cronograma':
            df = garantir_colunas(df, ['id', 'id_obra', 'etapa', 'porcentagem'])
        if tbl == 'tarefas':
            df = garantir_colunas(df, ['id', 'id_obra', 'descricao', 'responsavel', 'status'], "texto")
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
    if not DB['obras'].empty:
        opcoes = DB['obras'].apply(lambda x: f"{x['id']} - {x['nome']}", axis=1).tolist()
        selecao = st.selectbox("Selecione a Obra:", opcoes)
        id_obra_atual = int(selecao.split(" - ")[0])
        row_o = DB['obras'][DB['obras']['id'] == id_obra_atual].iloc[0]
        nome_obra = row_o['nome']
        orc_p = float(row_o.get('orcamento_pedreiro', 0))
        orc_c = float(row_o.get('orcamento_cliente', 0))

    st.markdown("---")
    with st.expander("➕ Nova Obra"):
        n_nome = st.text_input("Nome da Obra")
        if st.button("Criar"):
            res = supabase.table("obras").insert({"nome": n_nome}).execute()
            new_id = res.data[0]['id']
            for item in ETAPAS_PADRAO:
                nome_completo = f"{item['pai']} - {item['sub']}"
                supabase.table("cronograma").insert({"id_obra": new_id, "etapa": nome_completo, "porcentagem": 0}).execute()
            st.success("Obra Criada!"); st.cache_data.clear(); st.rerun()

    if id_obra_atual > 0:
        if st.button("🗑️ Excluir Obra Atual", type="primary"):
            supabase.table("custos").delete().eq("id_obra", id_obra_atual).execute()
            supabase.table("cronograma").delete().eq("id_obra", id_obra_atual).execute()
            supabase.table("tarefas").delete().eq("id_obra", id_obra_atual).execute()
            supabase.table("obras").delete().eq("id", id_obra_atual).execute()
            st.cache_data.clear(); st.rerun()

if id_obra_atual == 0: st.stop()

custos_f = DB['custos'][DB['custos']['id_obra'] == id_obra_atual].copy()
crono_f = DB['cronograma'][DB['cronograma']['id_obra'] == id_obra_atual]
tarefas_f = DB['tarefas'][DB['tarefas']['id_obra'] == id_obra_atual]

# --- ABAS ---
tabs = st.tabs(["📝 Lançar", "📅 Cronograma", "✅ Tarefas", "📊 Histórico", "📈 Dash", "💰 Pagamentos"])

# 1. LANÇAR
with tabs[0]:
    st.subheader(f"Lançar Custo - {nome_obra}")
    with st.form("form_lancar", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        desc = c1.text_input("Descrição do Item")
        valor = c2.number_input("Valor Unitário (R$)", min_value=0.0, format="%.2f", step=0.01)
        qtd = c3.number_input("Qtd", 1.0, step=0.1)
        
        c4, c5 = st.columns(2)
        etapa_l = c4.selectbox("Etapa", list(set([item['pai'] for item in ETAPAS_PADRAO])) + ["Mão de Obra"])
        data_l = c5.date_input("Data do Gasto", datetime.now(), format="DD/MM/YYYY")
        
        if st.form_submit_button("Salvar Gasto"):
            supabase.table("custos").insert({
                "id_obra": id_obra_atual, 
                "descricao": desc, 
                "valor": valor, 
                "qtd": qtd, 
                "total": valor*qtd, 
                "etapa": etapa_l, 
                "data": str(data_l)
            }).execute()
            st.success("Salvo!"); st.cache_data.clear(); st.rerun()

# 2. CRONOGRAMA
with tabs[1]:
    st.subheader(f"📅 Cronograma Detalhado")
    for i, row in crono_f.iterrows():
        with st.expander(f"{row['etapa']} - {row['porcentagem']}%"):
            c1, c2 = st.columns([3, 1])
            nv_nome = c1.text_input("Editar Nome", value=row['etapa'], key=f"nm_{row['id']}")
            nv_prog = c1.slider("Progresso (%)", 0, 100, int(row['porcentagem']), key=f"sl_{row['id']}")
            if c2.button("💾 Salvar", key=f"sv_{row['id']}"):
                supabase.table("cronograma").update({"etapa": nv_nome, "porcentagem": nv_prog}).eq("id", row['id']).execute()
                st.cache_data.clear(); st.rerun()

# 3. TAREFAS
with tabs[2]:
    st.subheader("📋 Gestão de Tarefas")
    # ... (Manteve estrutura existente)

# 4. HISTÓRICO
with tabs[3]:
    st.subheader("📊 Histórico de Gastos")
    if not custos_f.empty:
        st.dataframe(
            custos_f[['data', 'descricao', 'total', 'etapa']], 
            use_container_width=True, 
            column_config={
                "total": st.column_config.NumberColumn("Total", format="R$ %.2f"),
                "data": st.column_config.DateColumn("Data", format="DD/MM/YYYY")
            }
        )

# 5. DASHBOARD
with tabs[4]:
    st.subheader("📈 Resumo Visual")
    if not custos_f.empty:
        st.metric("Gasto Total", formatar_moeda(custos_f['total'].sum()))
        st.bar_chart(custos_f.groupby('etapa')['total'].sum())

# 6. PAGAMENTOS
with tabs[5]:
    st.subheader(f"💰 Financeiro - {nome_obra}")
    co1, co2 = st.columns(2)
    # Formatação R$ nos inputs de orçamento total
    new_p = co1.number_input("Orc. Pedreiro (R$)", value=orc_p, format="%.2f")
    new_c = co2.number_input("Orc. Cliente (R$)", value=orc_c, format="%.2f")
    
    if st.button("💾 Salvar Orçamentos Totais"):
        supabase.table("obras").update({"orcamento_pedreiro": new_p, "orcamento_cliente": new_c}).eq("id", id_obra_atual).execute()
        st.cache_data.clear(); st.rerun()
    
    with st.form("f_fin", clear_on_submit=True):
        st.write("➕ **Lançar Pagamento / Recebimento**")
        cp1, cp2, cp3 = st.columns(3)
        tipo = cp1.selectbox("Tipo", ["Saída (Pedreiro)", "Entrada (Cliente)"])
        val = cp2.number_input("Valor R$", format="%.2f")
        data_p = cp3.date_input("Data", datetime.now(), format="DD/MM/YYYY")
        
        if st.form_submit_button("Confirmar"):
            cat = "Mão de Obra" if "Saída" in tipo else "Entrada Cliente"
            supabase.table("custos").insert({
                "id_obra": id_obra_atual, 
                "descricao": tipo, 
                "valor": val, 
                "total": val, 
                "etapa": cat, 
                "data": str(data_p)
            }).execute()
            st.cache_data.clear(); st.rerun()

    pagos_mo = custos_f[custos_f['etapa'] == "Mão de Obra"]
    recebido_cli = custos_f[custos_f['etapa'] == "Entrada Cliente"]
    
    r1, r2 = st.columns(2)
    r1.metric("Saldo Pedreiro", formatar_moeda(new_p - pagos_mo['total'].sum()))
    r2.metric("Saldo Cliente", formatar_moeda(new_c - recebido_cli['total'].sum()))

    st.markdown("---")
    # Tabelas de histórico com data e valor formatados
    h1, h2 = st.columns(2)
    h1.write("🔴 Saídas (Mão de Obra)")
    h1.dataframe(
        pagos_mo[['data', 'total']], 
        hide_index=True,
        column_config={
            "total": st.column_config.NumberColumn("Valor", format="R$ %.2f"),
            "data": st.column_config.DateColumn("Data", format="DD/MM/YYYY")
        }
    )
    h2.write("🟢 Entradas (Cliente)")
    h2.dataframe(
        recebido_cli[['data', 'total']], 
        hide_index=True,
        column_config={
            "total": st.column_config.NumberColumn("Valor", format="R$ %.2f"),
            "data": st.column_config.DateColumn("Data", format="DD/MM/YYYY")
        }
    )