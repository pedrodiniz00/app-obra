import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime

# --- CONFIGURAÇÃO DA PÁGINA ---
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
    except:
        return pd.DataFrame()

@st.cache_data(ttl=2) 
def carregar_tudo():
    dados = {}
    for tbl in ["obras", "custos", "cronograma", "tarefas", "materiais"]:
        df = run_query(tbl)
        if tbl == 'obras':
            df = garantir_colunas(df, ['id', 'nome', 'orcamento_pedreiro', 'orcamento_cliente'])
        elif tbl == 'custos':
            df = garantir_colunas(df, ['id', 'id_obra', 'valor', 'total', 'descricao', 'data', 'etapa'])
            if not df.empty: df['data'] = pd.to_datetime(df['data']).dt.date
        elif tbl == 'materiais':
            df = garantir_colunas(df, ['id', 'nome'], "texto")
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

# --- DADOS E SIDEBAR ---
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
    else:
        st.warning("Crie uma obra na lateral.")

if id_obra_atual == 0: st.stop()

custos_f = DB['custos'][DB['custos']['id_obra'] == id_obra_atual].copy()
materiais_f = DB['materiais']

# --- ABAS ---
tabs = st.tabs(["📅 Cronograma", "💰 Pagamentos", "📦 Cadastro", "📝 Lançar", "📊 Histórico"])

# 1. CRONOGRAMA
with tabs[0]:
    st.subheader(f"Cronograma: {nome_obra}")
    # Estrutura baseada no seu cronograma.xlsx
    estrutura = [
        {"etapa": "1. Planejamento e Preliminares", "subs": ["Projetos e Aprovações", "Limpeza do Terreno", "Ligação Provisória", "Barracão"]},
        {"etapa": "2. Infraestrutura (Fundação)", "subs": ["Gabarito", "Escavação", "Concretagem", "Vigas Baldrame", "Impermeabilização"]},
        {"etapa": "3. Supraestrutura (Estrutura)", "subs": ["Pilares", "Vigas", "Lajes", "Escadas"]}
    ]
    for i, item in enumerate(estrutura):
        with st.expander(f"📌 {item['etapa']}"):
            for j, sub in enumerate(item['subs']):
                col1, col2 = st.columns([0.8, 0.2])
                col1.write(sub)
                st.checkbox("Concluído", key=f"check_{i}_{j}")

# 2. PAGAMENTOS
with tabs[1]:
    st.subheader("💰 Gestão Financeira")
    c1, c2 = st.columns(2)
    orc_total = c1.number_input("Orçamento Pedreiro (R$)", value=orc_p, format="%.2f")
    data_ref = c2.date_input("Data do Lançamento", format="DD/MM/YYYY")
    
    gastos_mo = custos_f[custos_f['etapa'] == "Mão de Obra"]['total'].sum()
    st.metric("Saldo Restante (R$)", formatar_moeda(orc_total - gastos_mo))

# 3. CADASTRO (Importar, Editar, Excluir)
with tabs[2]:
    st.subheader("📦 Cadastro de Materiais")
    
    with st.expander("📥 Importar do Ficheiro"):
        if st.button("Carregar 'Cadastro material.xlsx'"):
            try:
                df_csv = pd.read_csv("Cadastro material.xlsx - Planilha1.csv")
                itens = df_csv.iloc[:, 0].dropna().unique()
                for item in itens:
                    supabase.table("materiais").upsert({"nome": str(item)}).execute()
                st.success("Importação concluída!"); st.cache_data.clear(); st.rerun()
            except: st.error("Ficheiro não encontrado no diretório.")

    # Editor para Editar e Excluir
    if not materiais_f.empty:
        df_ed = st.data_editor(materiais_f[['id', 'nome']], num_rows="dynamic", use_container_width=True, key="editor_mat")
        if st.button("💾 Aplicar Alterações"):
            ids_finais = df_ed['id'].dropna().tolist()
            para_deletar = set(materiais_f['id'].tolist()) - set(ids_finais)
            for d_id in para_deletar: supabase.table("materiais").delete().eq("id", d_id).execute()
            for _, r in df_ed.iterrows():
                if pd.notnull(r['id']): supabase.table("materiais").update({"nome": r['nome']}).eq("id", r['id']).execute()
                else: supabase.table("materiais").insert({"nome": r['nome']}).execute()
            st.cache_data.clear(); st.rerun()

# 4. LANÇAR
with tabs[3]:
    st.subheader("📝 Lançar Gasto")
    with st.form("form_gasto", clear_on_submit=True):
        m_opcoes = materiais_f['nome'].tolist() if not materiais_f.empty else []
        desc = st.selectbox("Material", m_opcoes) if m_opcoes else st.text_input("Descrição")
        valor = st.number_input("Valor (R$)", format="%.2f")
        etapa = st.selectbox("Categoria", ["Materiais", "Mão de Obra", "Outros"])
        data_g = st.date_input("Data", format="DD/MM/YYYY")
        if st.form_submit_button("Salvar"):
            supabase.table("custos").insert({"id_obra": id_obra_atual, "descricao": desc, "total": valor, "etapa": etapa, "data": str(data_g)}).execute()
            st.success("Salvo!"); st.cache_data.clear(); st.rerun()

# 5. HISTÓRICO
with tabs[4]:
    st.subheader("📊 Histórico")
    st.dataframe(custos_f[['data', 'descricao', 'total', 'etapa']], 
                 column_config={"total": st.column_config.NumberColumn(format="R$ %.2f"),
                                "data": st.column_config.DateColumn(format="DD/MM/YYYY")},
                 use_container_width=True)