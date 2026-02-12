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
    except:
        st.error("❌ Erro: Configure os Secrets no Streamlit Cloud.")
        st.stop()

supabase = init_connection()

# --- DEFINIÇÃO DO PADRÃO CONSTRUTIVO ---
TEMPLATE_ETAPAS = [
    ("1. Planejamento e Preliminares", 5000.0, ["Projetos", "Limpeza", "Ligação Água/Luz", "Tapumes"]),
    ("2. Infraestrutura", 15000.0, ["Escavação", "Sapatas", "Vigas Baldrame", "Impermeabilização"]),
    ("3. Supraestrutura", 25000.0, ["Pilares", "Vigas", "Lajes", "Alvenaria"]),
    ("4. Cobertura", 10000.0, ["Madeiramento", "Telhamento", "Calhas"]),
    ("5. Instalações", 15000.0, ["Hidráulica", "Elétrica", "Esgoto"]),
    ("6. Acabamentos", 30000.0, ["Reboco", "Pisos", "Pintura", "Esquadrias"])
]

# --- FUNÇÕES AUXILIARES ---
def extrair_numero_etapa(texto):
    try:
        match = re.match(r"(\d+)", str(texto))
        return int(match.group(1)) if match else 9999
    except: return 9999

def run_query(table_name):
    try:
        response = supabase.table(table_name).select("*").execute()
        df = pd.DataFrame(response.data)
        return df if not df.empty else pd.DataFrame()
    except: return pd.DataFrame()

@st.cache_data(ttl=2) 
def carregar_tudo():
    dados = {}
    tabelas = ["obras", "custos", "cronograma", "materiais", "fornecedores", "pontos_criticos", "tarefas"]
    for tbl in tabelas:
        df = run_query(tbl)
        if tbl == 'custos':
            if 'subetapa' not in df.columns: df['subetapa'] = ""
            if 'classe' not in df.columns: df['classe'] = "Material"
            if df.empty: df = pd.DataFrame(columns=['id', 'id_obra', 'classe', 'subetapa', 'valor', 'total', 'qtd', 'descricao', 'data', 'etapa'])
        if tbl == 'obras':
            if 'status' not in df.columns: df['status'] = 'Ativa'
            if df.empty: df = pd.DataFrame(columns=['id', 'nome', 'status'])
        if not df.empty:
            cols_num = df.select_dtypes(include=[np.number]).columns
            df[cols_num] = df[cols_num].fillna(0)
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
    nome_obra_atual = "Sem Obra"
    status_obra = "Ativa"

    if DB['obras'].empty:
        st.warning("Nenhuma obra cadastrada.")
    else:
        opcoes = DB['obras'].apply(lambda x: f"{x['id']} - {x['nome']}", axis=1).tolist()
        selecao = st.selectbox("Selecione:", opcoes)
        try:
            temp_id = int(selecao.split(" - ")[0])
            if temp_id in DB['obras']['id'].values:
                id_obra_atual = temp_id
                nome_obra_atual = selecao.split(" - ")[1]
                status_obra = DB['obras'][DB['obras']['id'] == id_obra_atual].iloc[0]['status']
        except: id_obra_atual = 0

    BLOQUEADO = status_obra in ["Concluída", "Paralisada"]

    with st.expander("➕ Nova Obra"):
        with st.form("new_obra", clear_on_submit=True):
            n_nome = st.text_input("Nome da Obra")
            if st.form_submit_button("Criar Obra"):
                res = supabase.table("obras").insert({"nome": n_nome, "status": "Ativa"}).execute()
                new_id = res.data[0]['id']
                lista_crono = [{"id_obra": new_id, "etapa": str(e), "status": "Pendente", "orcamento": float(o), "porcentagem": 0} for e, o, _ in TEMPLATE_ETAPAS]
                supabase.table("cronograma").insert(lista_crono).execute()
                st.success("Criada!"); st.cache_data.clear(); time.sleep(1); st.rerun()

    if id_obra_atual > 0:
        if st.button("🗑️ Excluir Obra Atual", type="primary"):
            supabase.table("custos").delete().eq("id_obra", id_obra_atual).execute()
            supabase.table("cronograma").delete().eq("id_obra", id_obra_atual).execute()
            supabase.table("tarefas").delete().eq("id_obra", id_obra_atual).execute()
            supabase.table("obras").delete().eq("id", id_obra_atual).execute()
            st.success("Apagada!"); st.cache_data.clear(); time.sleep(1); st.rerun()

if id_obra_atual == 0:
    st.info("👈 Selecione uma obra.")
    st.stop()

custos_f = DB['custos'][DB['custos']['id_obra'] == id_obra_atual] if not DB['custos'].empty else pd.DataFrame()
crono_f = DB['cronograma'][DB['cronograma']['id_obra'] == id_obra_atual] if not DB['cronograma'].empty else pd.DataFrame()
tarefas_f = DB['tarefas'][DB['tarefas']['id_obra'] == id_obra_atual] if not DB['tarefas'].empty else pd.DataFrame()

# --- ABAS ---
t1, t2, t3, t4, t5, t6 = st.tabs(["📝 Lançar", "📅 Cronograma", "✅ Tarefas", "📦 Cadastros", "📊 Histórico", "📈 Dash"])

# 1. LANÇAR
with t1:
    st.subheader(f"Lançar Custo - {nome_obra_atual}")
    with st.form("lancar_form", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        desc = c1.text_input("Descrição do Item")
        valor = c2.number_input("Valor Unitário", 0.0)
        qtd = c3.number_input("Qtd", 1.0)
        etapa = st.selectbox("Etapa", [e for e, _, _ in TEMPLATE_ETAPAS])
        if st.form_submit_button("Salvar Gasto"):
            supabase.table("custos").insert({"id_obra": id_obra_atual, "descricao": desc, "valor": valor, "qtd": qtd, "total": valor*qtd, "etapa": etapa, "data": str(datetime.now().date())}).execute()
            st.success("Salvo!"); st.cache_data.clear(); st.rerun()

# 2. CRONOGRAMA
with t2:
    if not crono_f.empty:
        for _, row in crono_f.iterrows():
            st.write(f"**{row['etapa']}**")
            new_p = st.slider("Progresso (%)", 0, 100, int(row['porcentagem']), key=f"p_{row['id']}")
            if new_p != int(row['porcentagem']):
                supabase.table("cronograma").update({"porcentagem": new_p}).eq("id", row['id']).execute()
                st.cache_data.clear(); st.rerun()

# 3. TAREFAS (ATUALIZADA)
with t3:
    st.subheader("📋 Gerenciar Tarefas")
    
    # Reset de campos
    if "tarefa_reset" not in st.session_state: st.session_state.tarefa_reset = 0

    with st.form("form_tarefa", clear_on_submit=True):
        c1, c2 = st.columns(2)
        nt_desc = c1.text_input("Nova Tarefa", key=f"nt_d_{st.session_state.tarefa_reset}")
        nt_resp = c2.text_input("Responsável", key=f"nt_r_{st.session_state.tarefa_reset}")
        if st.form_submit_button("➕ Adicionar"):
            if nt_desc:
                supabase.table("tarefas").insert({"id_obra": id_obra_atual, "descricao": nt_desc, "responsavel": nt_resp, "status": "Pendente"}).execute()
                st.session_state.tarefa_reset += 1
                st.cache_data.clear(); st.rerun()

    st.markdown("---")
    if not tarefas_f.empty:
        st.write("📝 **Editar Tarefas**")
        df_ed = st.data_editor(
            tarefas_f[['id', 'descricao', 'responsavel', 'status']],
            key="ed_tarefas", hide_index=True, use_container_width=True,
            column_config={"id": None, "status": st.column_config.SelectboxColumn("Status", options=["Pendente", "Andamento", "Concluída"])}
        )
        if st.button("💾 Salvar Alterações"):
            for _, row in df_ed.iterrows():
                supabase.table("tarefas").update({"descricao": row['descricao'], "responsavel": row['responsavel'], "status": row['status']}).eq("id", row['id']).execute()
            st.success("Salvo!"); st.cache_data.clear(); st.rerun()

# 4. CADASTROS
with t4:
    st.write("Utilize para pré-cadastrar materiais ou fornecedores.")
    # (Simplicidade mantida)

# 5. HISTORICO
with t5:
    if not custos_f.empty:
        st.dataframe(custos_f[['data', 'descricao', 'qtd', 'valor', 'total', 'etapa']], use_container_width=True)

# 6. DASHBOARDS
with t6:
    if not custos_f.empty:
        st.metric("Total Gasto", f"R$ {custos_f['total'].sum():,.2f}")
        st.bar_chart(custos_f.groupby('etapa')['total'].sum())