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

# --- PADRÃO DE ETAPAS (Fiel ao seu arquivo original) ---
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
    {"pai": "3. Supraestrutura (Estrutura)", "sub": "Pilares"},
    {"pai": "3. Supraestrutura (Estrutura)", "sub": "Vigas"},
    {"pai": "3. Supraestrutura (Estrutura)", "sub": "Lajes"},
    {"pai": "4. Alvenaria e Vedação", "sub": "Levantamento de Paredes"},
    {"pai": "4. Alvenaria e Vedação", "sub": "Vergas e Contravergas"},
    {"pai": "4. Alvenaria e Vedação", "sub": "Chapisco e Emboço"}
]

# --- FUNÇÕES AUXILIARES ---
def formatar_moeda(valor):
    try: return f"R$ {float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
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
    for tbl in ["obras", "custos", "cronograma", "tarefas", "materiais"]:
        df = run_query(tbl)
        if tbl == 'obras':
            df = garantir_colunas(df, ['id', 'nome', 'orcamento_pedreiro', 'orcamento_cliente'])
        if tbl == 'custos':
            df = garantir_colunas(df, ['id', 'id_obra', 'valor', 'total', 'descricao', 'data', 'etapa'])
            if not df.empty: df['data'] = pd.to_datetime(df['data']).dt.date
        if tbl == 'cronograma':
            df = garantir_colunas(df, ['id', 'id_obra', 'etapa', 'porcentagem'])
        if tbl == 'materiais':
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

DB = carregar_tudo()

# --- SIDEBAR ---
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

# --- ABAS ---
tabs = st.tabs(["📝 Lançar", "📅 Cronograma", "✅ Tarefas", "📊 Histórico", "📈 Dash", "💰 Pagamentos", "📦 Cadastro"])

# 1. LANÇAR (Mantido)
with tabs[0]:
    st.subheader(f"Lançar Custo - {nome_obra}")
    # ... (Manter código de formulário de lançamento)

# 2. CRONOGRAMA (ESTRUTURA ENUMERADA E GESTÃO COMPLETA)
with tabs[1]:
    st.subheader(f"📅 Cronograma de Execução - {nome_obra}")

    # --- ADICIONAR NOVA ETAPA/SUBETAPA ---
    with st.expander("➕ Adicionar Novo Item ao Cronograma"):
        with st.form("add_crono", clear_on_submit=True):
            col_n, col_s = st.columns([1, 2])
            num_etapa = col_n.text_input("Nº Etapa (Ex: 1, 2, 3.1)")
            nome_sub = col_s.text_input("Descrição da Subetapa")
            if st.form_submit_button("Confirmar Adição"):
                if num_etapa and nome_sub:
                    texto_final = f"{num_etapa} | {nome_sub}"
                    supabase.table("cronograma").insert({"id_obra": id_obra_atual, "etapa": texto_final, "porcentagem": 0}).execute()
                    st.success("Item adicionado!"); st.cache_data.clear(); st.rerun()

    st.divider()

    # --- LISTAGEM ENUMERADA ---
    crono_f = DB['cronograma'][DB['cronograma']['id_obra'] == id_obra_atual]
    
    if not crono_f.empty:
        # Separar a numeração da descrição para ordenar e exibir
        crono_f['num'] = crono_f['etapa'].apply(lambda x: x.split(' | ')[0] if ' | ' in x else "99")
        crono_f['desc'] = crono_f['etapa'].apply(lambda x: x.split(' | ')[1] if ' | ' in x else x)
        
        # Ordenar pela numeração
        crono_f = crono_f.sort_values(by='num')

        for index, row in crono_f.iterrows():
            # Estrutura Visual Enumerada
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([1, 3, 2, 1])
                
                with c1:
                    st.markdown(f"### {row['num']}")
                
                with c2:
                    # Campo para alterar o nome diretamente
                    novo_nome = st.text_input("Descrição", value=row['desc'], key=f"desc_{row['id']}", label_visibility="collapsed")
                
                with c3:
                    # Slider de progresso
                    novo_prog = st.slider("Progresso", 0, 100, int(row['porcentagem']), key=f"prog_{row['id']}", label_visibility="collapsed")
                
                with c4:
                    # Botões de Ação
                    if st.button("💾", key=f"sv_{row['id']}", help="Salvar Alterações"):
                        final_etapa = f"{row['num']} | {novo_nome}"
                        supabase.table("cronograma").update({"etapa": final_etapa, "porcentagem": novo_prog}).eq("id", row['id']).execute()
                        st.cache_data.clear(); st.rerun()
                    
                    if st.button("🗑️", key=f"del_{row['id']}", help="Excluir Etapa"):
                        supabase.table("cronograma").delete().eq("id", row['id']).execute()
                        st.cache_data.clear(); st.rerun()
    else:
        st.info("Cronograma vazio. Adicione itens acima.")

# (Manter o restante das abas Tarefas, Histórico, Dash, Pagamentos e Cadastro igual ao código anterior)