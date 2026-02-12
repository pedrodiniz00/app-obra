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

# --- PADRÃO DE ETAPAS (Fiel ao seu arquivo cronograma.xlsx) ---
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
    {"pai": "2. Infraestrutura (Fundação)", "sub": "Passagem de tubulação de alimentação de energia"},
    {"pai": "3. Supraestrutura (Estrutura)", "sub": "Pilares"},
    {"pai": "3. Supraestrutura (Estrutura)", "sub": "Vigas"},
    {"pai": "3. Supraestrutura (Estrutura)", "sub": "Lajes"},
    {"pai": "3. Supraestrutura (Estrutura)", "sub": "Escadas"},
    {"pai": "3. Supraestrutura e Alvenaria", "sub": "Marcação das Paredes"},
    {"pai": "3. Supraestrutura e Alvenaria", "sub": "Levantamento de Paredes"},
    {"pai": "3. Supraestrutura e Alvenaria", "sub": "Impermeabilização das 3 fiadas"},
    {"pai": "3. Supraestrutura e Alvenaria", "sub": "Locação Caixinhas"},
    {"pai": "4. Alvenaria e Vedação", "sub": "Vergas e Contravergas"},
    {"pai": "4. Alvenaria e Vedação", "sub": "Chapisco e Emboço"},
    {"pai": "5. Cobertura", "sub": "Estrutura Telhado"},
    {"pai": "5. Cobertura", "sub": "Telhamento"},
    {"pai": "6. Instalações", "sub": "Tubulação Água/Esgoto"},
    {"pai": "7. Acabamentos", "sub": "Revestimentos (Piso/Parede)"},
    {"pai": "8. Área Externa e Finalização", "sub": "Pintura Interna/Externa"}
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
        if tbl == 'tarefas':
            df = garantir_colunas(df, ['id', 'id_obra', 'descricao', 'responsavel', 'status'], "texto")
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

    st.markdown("---")
    with st.expander("➕ Nova Obra"):
        n_nome = st.text_input("Nome da Obra")
        if st.button("Criar Obra"):
            if n_nome:
                res = supabase.table("obras").insert({"nome": n_nome}).execute()
                new_id = res.data[0]['id']
                for item in ETAPAS_PADRAO:
                    nome_completo = f"{item['pai']} | {item['sub']}"
                    supabase.table("cronograma").insert({"id_obra": new_id, "etapa": nome_completo, "porcentagem": 0}).execute()
                st.success("Obra e Cronograma Criados!"); st.cache_data.clear(); st.rerun()

if id_obra_atual == 0:
    st.info("👈 Selecione uma obra na barra lateral para começar.")
    st.stop()

# Filtros globais para a obra atual
custos_f = DB['custos'][DB['custos']['id_obra'] == id_obra_atual]
crono_f = DB['cronograma'][DB['cronograma']['id_obra'] == id_obra_atual]
tarefas_f = DB['tarefas'][DB['tarefas']['id_obra'] == id_obra_atual]

# --- ABAS ---
tabs = st.tabs(["📝 Lançar", "📅 Cronograma", "✅ Tarefas", "📊 Histórico", "📈 Dash", "💰 Pagamentos", "📦 Cadastro"])

# 1. ABA LANÇAR
with tabs[0]:
    st.subheader(f"Lançar Custo - {nome_obra}")
    with st.form("form_lancar", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        m_lista = DB['materiais']['nome'].tolist()
        desc = c1.selectbox("Material (do Cadastro)", m_lista) if m_lista else c1.text_input("Descrição do Item")
        valor = c2.number_input("Valor Unitário (R$)", min_value=0.0, format="%.2f", step=0.01)
        qtd = c3.number_input("Qtd", 1.0, step=0.1)
        
        c4, c5 = st.columns(2)
        l_pais = sorted(list(set([item['pai'] for item in ETAPAS_PADRAO])))
        etapa_fin = c4.selectbox("Etapa de Gasto", l_pais + ["Mão de Obra"])
        data_input = c5.date_input("Data do Gasto", format="DD/MM/YYYY")
        
        if st.form_submit_button("Salvar Gasto"):
            supabase.table("custos").insert({"id_obra": id_obra_atual, "descricao": desc, "valor": valor, "qtd": qtd, "total": valor*qtd, "etapa": etapa_fin, "data": str(data_input)}).execute()
            st.success("Salvo!"); st.cache_data.clear(); st.rerun()

# 2. ABA CRONOGRAMA
with tabs[1]:
    st.subheader(f"📅 Cronograma de Execução")
    if not crono_f.empty:
        crono_f['pai'] = crono_f['etapa'].apply(lambda x: x.split(' | ')[0] if ' | ' in x else x)
        crono_f['sub'] = crono_f['etapa'].apply(lambda x: x.split(' | ')[1] if ' | ' in x else "")
        pais = sorted(crono_f['pai'].unique())
        for i, pai in enumerate(pais, 1):
            with st.expander(f"📁 {pai}", expanded=False):
                subs = crono_f[crono_f['pai'] == pai].sort_values(by='sub')
                for j, (_, row) in enumerate(subs.iterrows(), 1):
                    exibir_nome = row['sub'] if row['sub'] != "" else row['pai']
                    with st.container(border=True):
                        c1, c2, c3, c4, c5 = st.columns([0.5, 3, 3, 1, 1])
                        c1.write(f"**{i}.{j}**")
                        n_txt = c2.text_input("Nome", exibir_nome, key=f"n_{row['id']}", label_visibility="collapsed")
                        n_prog = c3.slider("Progresso", 0, 100, int(row['porcentagem']), key=f"p_{row['id']}", label_visibility="collapsed")
                        if c4.button("💾", key=f"s_{row['id']}"):
                            nome_salvar = f"{pai} | {n_txt}" if row['sub'] != "" else n_txt
                            supabase.table("cronograma").update({"etapa": nome_salvar, "porcentagem": n_prog}).eq("id", row['id']).execute()
                            st.cache_data.clear(); st.rerun()
                        if c5.button("🗑️", key=f"d_{row['id']}"):
                            supabase.table("cronograma").delete().eq("id", row['id']).execute()
                            st.cache_data.clear(); st.rerun()

# 3. ABA TAREFAS
with tabs[2]:
    st.subheader("📋 Gestão de Tarefas")
    with st.form("form_tarefa", clear_on_submit=True):
        c1, c2 = st.columns(2)
        nt = c1.text_input("Nova Tarefa")
        rp = c2.text_input("Responsável")
        if st.form_submit_button("Adicionar"):
            supabase.table("tarefas").insert({"id_obra": id_obra_atual, "descricao": nt, "responsavel": rp, "status": "Pendente"}).execute()
            st.cache_data.clear(); st.rerun()
    if not tarefas_f.empty:
        df_ed = st.data_editor(tarefas_f[['id', 'descricao', 'responsavel', 'status']], key="ed_tar", hide_index=True, use_container_width=True)
        if st.button("Salvar Alterações Tarefas"):
            for _, r in df_ed.iterrows():
                supabase.table("tarefas").update({"descricao": r['descricao'], "responsavel": r['responsavel'], "status": r['status']}).eq("id", r['id']).execute()
            st.cache_data.clear(); st.rerun()

# 4. ABA HISTÓRICO
with tabs[3]:
    st.subheader("📊 Histórico Completo")
    st.dataframe(custos_f[['data', 'descricao', 'total', 'etapa']], use_container_width=True, 
                 column_config={"total": st.column_config.NumberColumn("Total", format="R$ %.2f"), "data": st.column_config.DateColumn("Data", format="DD/MM/YYYY")})

# 5. ABA DASHBOARD
with tabs[4]:
    st.subheader("📈 Resumo de Custos")
    if not custos_f.empty:
        st.metric("Total Gasto", formatar_moeda(custos_f['total'].sum()))
        st.bar_chart(custos_f.groupby('etapa')['total'].sum())

# 6. ABA PAGAMENTOS
with tabs[5]:
    st.subheader(f"💰 Financeiro - {nome_obra}")
    co1, co2 = st.columns(2)
    nP = co1.number_input("Orçamento Pedreiro (R$)", value=orc_p, format="%.2f")
    nC = co2.number_input("Orçamento Cliente (R$)", value=orc_c, format="%.2f")
    if st.button("💾 Salvar Orçamentos Totais"):
        supabase.table("obras").update({"orcamento_pedreiro": nP, "orcamento_cliente": nC}).eq("id", id_obra_atual).execute()
        st.cache_data.clear(); st.rerun()
    
    with st.form("f_fin", clear_on_submit=True):
        st.write("➕ **Lançar Pagamento / Recebimento**")
        cp1, cp2, cp3 = st.columns(3)
        t = cp1.selectbox("Tipo", ["Saída (Pedreiro)", "Entrada (Cliente)"])
        v = cp2.number_input("Valor R$", format="%.2f")
        dt_p = cp3.date_input("Data", format="DD/MM/YYYY")
        if st.form_submit_button("Confirmar"):
            cat = "Mão de Obra" if "Saída" in t else "Entrada Cliente"
            supabase.table("custos").insert({"id_obra": id_obra_atual, "descricao": t, "valor": v, "total": v, "etapa": cat, "data": str(dt_p)}).execute()
            st.cache_data.clear(); st.rerun()

    p_mo = custos_f[custos_f['etapa'] == "Mão de Obra"]
    r_cl = custos_f[custos_f['etapa'] == "Entrada Cliente"]
    
    res1, res2 = st.columns(2)
    res1.metric("Saldo Pedreiro", formatar_moeda(nP - p_mo['total'].sum()))
    res2.metric("Saldo Cliente", formatar_moeda(nC - r_cl['total'].sum()))

    st.markdown("---")
    st.write("### 📜 Histórico de Lançamentos")
    h1, h2 = st.columns(2)
    with h1:
        st.error("🔴 Saídas (Mão de Obra)")
        st.dataframe(p_mo[['data', 'descricao', 'total']].sort_values(by='data', ascending=False), hide_index=True, use_container_width=True,
            column_config={"total": st.column_config.NumberColumn("Valor", format="R$ %.2f"), "data": st.column_config.DateColumn("Data", format="DD/MM/YYYY")})
    with h2:
        st.success("🟢 Entradas (Cliente)")
        st.dataframe(r_cl[['data', 'descricao', 'total']].sort_values(by='data', ascending=False), hide_index=True, use_container_width=True,
            column_config={"total": st.column_config.NumberColumn("Valor", format="R$ %.2f"), "data": st.column_config.DateColumn("Data", format="DD/MM/YYYY")})

# 7. ABA CADASTRO
with tabs[6]:
    st.subheader("📦 Cadastro de Materiais")
    with st.expander("📥 Importar materiais do arquivo"):
        if st.button("Importar 'Cadastro material.xlsx'"):
            try:
                df_imp = pd.read_csv('Cadastro material.xlsx - Planilha1.csv')
                col_name = df_imp.columns[0]
                lista_imp = df_imp[col_name].dropna().unique().tolist()
                for item in lista_imp:
                    supabase.table("materiais").upsert({"nome": str(item)}).execute()
                st.success(f"Importados {len(lista_imp)} itens!")
                st.cache_data.clear(); st.rerun()
            except Exception as e:
                st.error(f"Erro: {e}")
    
    with st.form("add_manual", clear_on_submit=True):
        nm_mat = st.text_input("Novo Material")
        if st.form_submit_button("Cadastrar"):
            supabase.table("materiais").insert({"nome": nm_mat}).execute()
            st.cache_data.clear(); st.rerun()
            
    if not DB['materiais'].empty:
        df_edit_mat = st.data_editor(DB['materiais'][['id', 'nome']], key="ed_mat", num_rows="dynamic", hide_index=True, use_container_width=True)
        if st.button("Salvar Alterações no Cadastro"):
            ids_finais = df_edit_mat['id'].dropna().tolist()
            para_deletar = list(set(DB['materiais']['id'].tolist()) - set(ids_finais))
            for d_id in para_deletar:
                supabase.table("materiais").delete().eq("id", d_id).execute()
            for _, r in df_edit_mat.iterrows():
                if pd.notnull(r['id']):
                    supabase.table("materiais").update({"nome": r['nome']}).eq("id", r['id']).execute()
                else:
                    supabase.table("materiais").insert({"nome": r['nome']}).execute()
            st.success("Sincronizado!"); st.cache_data.clear(); st.rerun()