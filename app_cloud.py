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
    {"pai": "3. Supraestrutura e Alvenaria", "sub": "Locação Caixinhas (conferencia de altura e alinhamento)"},
    {"pai": "3. Supraestrutura e Alvenaria", "sub": "Conferencia dos pontos hidráulicos e esgoto (altura dos mesmos)"},
    {"pai": "3. Supraestrutura e Alvenaria", "sub": "Embuço"},
    {"pai": "3. Supraestrutura e Alvenaria", "sub": "Impermeabilização dos Banheiros"},
    {"pai": "4. Alvenaria e Vedação", "sub": "Vergas e Contravergas"},
    {"pai": "4. Alvenaria e Vedação", "sub": "Chapisco e Emboço"},
    {"pai": "5. Cobertura", "sub": "Estrutura Telhado"},
    {"pai": "5. Cobertura", "sub": "Telhamento"},
    {"pai": "5. Cobertura", "sub": "Calhas e Rufos"},
    {"pai": "5. Cobertura", "sub": "Montagem da Lage"},
    {"pai": "5. Cobertura", "sub": "Passagem e Conferencia dos Conduites"},
    {"pai": "6. Instalações", "sub": "Tubulação Água/Esgoto"},
    {"pai": "6. Instalações", "sub": "Eletrodutos e Caixinhas"},
    {"pai": "6. Instalações", "sub": "Fiação e Cabos"},
    {"pai": "6. Instalações", "sub": "Tubulação Gás/Ar"},
    {"pai": "6. Instalações", "sub": "Conferir medidas de saida de esgoto do vaso"},
    {"pai": "6. Instalações", "sub": "Ralo dentro e fora do boxe"},
    {"pai": "6. Instalações", "sub": "Conferir medida do desnível para o chuveiro"},
    {"pai": "6. Instalações", "sub": "Conferir novamente pontos de esgoto e aguá das pias(alturas)"},
    {"pai": "7. Acabamentos", "sub": "Contrapiso"},
    {"pai": "7. Acabamentos", "sub": "Reboco/Gesso"},
    {"pai": "7. Acabamentos", "sub": "Revestimentos (Piso/Parede)"},
    {"pai": "7. Acabamentos", "sub": "Louças e Metais"},
    {"pai": "7. Acabamentos", "sub": "Esquadrias (Portas/Janelas)"},
    {"pai": "7. Acabamentos", "sub": "Conferir alinhamento dos pisos"},
    {"pai": "7. Acabamentos", "sub": "Conferir alinhamento dos pisos nas varandas em todos os cantos"},
    {"pai": "7. Acabamentos", "sub": "Conferir largura do desnível dos banheiros"},
    {"pai": "8. Área Externa e Finalização", "sub": "Muros e Calçadas"},
    {"pai": "8. Área Externa e Finalização", "sub": "Pintura Interna/Externa"},
    {"pai": "8. Área Externa e Finalização", "sub": "Elétrica Final (Tomadas/Luz)"},
    {"pai": "8. Área Externa e Finalização", "sub": "Limpeza Pós-Obra"}
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

    if id_obra_atual > 0:
        if st.button("🗑️ Excluir Obra Atual", type="primary"):
            supabase.table("custos").delete().eq("id_obra", id_obra_atual).execute()
            supabase.table("cronograma").delete().eq("id_obra", id_obra_atual).execute()
            supabase.table("tarefas").delete().eq("id_obra", id_obra_atual).execute()
            supabase.table("obras").delete().eq("id", id_obra_atual).execute()
            st.cache_data.clear(); st.rerun()

if id_obra_atual == 0:
    st.info("👈 Selecione ou crie uma obra.")
    st.stop()

custos_f = DB['custos'][DB['custos']['id_obra'] == id_obra_atual]
crono_f = DB['cronograma'][DB['cronograma']['id_obra'] == id_obra_atual]
tarefas_f = DB['tarefas'][DB['tarefas']['id_obra'] == id_obra_atual]

# --- ABAS ---
tabs = st.tabs(["📝 Lançar", "📅 Cronograma", "✅ Tarefas", "📊 Histórico", "📈 Dash", "💰 Pagamentos", "📦 Cadastro"])

# 1. LANÇAR (Mantido original)
with tabs[0]:
    st.subheader(f"Lançar Custo - {nome_obra}")
    with st.form("form_lancar", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        lista_materiais = DB['materiais']['nome'].tolist()
        if lista_materiais:
            desc = c1.selectbox("Material (do Cadastro)", lista_materiais)
        else:
            desc = c1.text_input("Descrição do Item")
        valor = c2.number_input("Valor Unitário (R$)", min_value=0.0, format="%.2f", step=0.01)
        qtd = c3.number_input("Qtd", 1.0, step=0.1)
        lista_pais = sorted(list(set([item['pai'] for item in ETAPAS_PADRAO])))
        etapa_fin = st.selectbox("Etapa de Gasto", lista_pais + ["Mão de Obra"])
        if st.form_submit_button("Salvar Gasto"):
            supabase.table("custos").insert({"id_obra": id_obra_atual, "descricao": desc, "valor": valor, "qtd": qtd, "total": valor*qtd, "etapa": etapa_fin, "data": str(datetime.now().date())}).execute()
            st.success("Salvo!"); st.cache_data.clear(); st.rerun()

# 2. CRONOGRAMA (ATUALIZADO: Com Adição de Subetapas, Alteração e Exclusão)
with tabs[1]:
    st.subheader(f"📅 Gestão do Cronograma - {nome_obra}")
    
    # Campo para adicionar Nova Subetapa Manualmente
    with st.expander("➕ Adicionar Nova Subetapa Manual"):
        with st.form("form_nova_subetapa", clear_on_submit=True):
            col_pai, col_sub = st.columns(2)
            # Lista as etapas pai existentes para facilitar a escolha
            pais_existentes = sorted(list(set([item['pai'] for item in ETAPAS_PADRAO])))
            pai_selecionado = col_pai.selectbox("Etapa Pai", pais_existentes + ["Outros"])
            nova_sub = col_sub.text_input("Nome da Subetapa")
            
            if st.form_submit_button("Adicionar ao Cronograma"):
                if nova_sub:
                    nome_db = f"{pai_selecionado} | {nova_sub}"
                    supabase.table("cronograma").insert({"id_obra": id_obra_atual, "etapa": nome_db, "porcentagem": 0}).execute()
                    st.success("Subetapa adicionada!"); st.cache_data.clear(); st.rerun()

    st.markdown("---")

    if not crono_f.empty:
        # Extração de Pai e Sub para exibição organizada
        crono_f['pai'] = crono_f['etapa'].apply(lambda x: x.split(' | ')[0] if ' | ' in x else "Extra")
        crono_f['sub'] = crono_f['etapa'].apply(lambda x: x.split(' | ')[1] if ' | ' in x else x)
        
        for pai in sorted(crono_f['pai'].unique()):
            st.markdown(f"#### 🏗️ {pai}")
            sub_itens = crono_f[crono_f['pai'] == pai]
            
            for _, row in sub_itens.iterrows():
                # Cada subetapa tem seu expander com opções de edição e exclusão
                with st.expander(f"{row['sub']} - {row['porcentagem']}%"):
                    c1, c2, c3 = st.columns([3, 1, 1])
                    
                    # Alterar Nome e Progresso
                    nv_n = c1.text_input("Alterar Nome", value=row['sub'], key=f"n_{row['id']}")
                    nv_p = c1.slider("Progresso (%)", 0, 100, int(row['porcentagem']), key=f"p_{row['id']}")
                    
                    # Botão Salvar Alteração
                    if c2.button("💾 Salvar", key=f"s_{row['id']}"):
                        db_name = f"{pai} | {nv_n}" if pai != "Extra" else nv_n
                        supabase.table("cronograma").update({"etapa": db_name, "porcentagem": nv_p}).eq("id", row['id']).execute()
                        st.success("Alterado!"); st.cache_data.clear(); st.rerun()
                    
                    # Botão Excluir
                    if c3.button("🗑️ Excluir", key=f"d_{row['id']}"):
                        supabase.table("cronograma").delete().eq("id", row['id']).execute()
                        st.warning("Removido!"); st.cache_data.clear(); st.rerun()
            st.markdown("---")

# 3. TAREFAS (Mantido original)
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

# 4. HISTÓRICO (Mantido original com formatação)
with tabs[3]:
    st.subheader("📊 Histórico Completo")
    st.dataframe(custos_f[['data', 'descricao', 'total', 'etapa']], use_container_width=True, 
                 column_config={
                     "total": st.column_config.NumberColumn("Total", format="R$ %.2f"),
                     "data": st.column_config.DateColumn("Data", format="DD/MM/YYYY")
                 })

# 5. DASHBOARD (Mantido original)
with tabs[4]:
    st.subheader("📈 Resumo de Custos")
    if not custos_f.empty:
        st.metric("Total Gasto", formatar_moeda(custos_f['total'].sum()))
        st.bar_chart(custos_f.groupby('etapa')['total'].sum())

# 6. PAGAMENTOS (Mantido original)
with tabs[5]:
    st.subheader(f"💰 Financeiro - {nome_obra}")
    co1, co2 = st.columns(2)
    nP = co1.number_input("Orçamento Pedreiro", value=orc_p)
    nC = co2.number_input("Orçamento Cliente", value=orc_c)
    if st.button("💾 Salvar Orçamentos Totais"):
        supabase.table("obras").update({"orcamento_pedreiro": nP, "orcamento_cliente": nC}).eq("id", id_obra_atual).execute()
        st.cache_data.clear(); st.rerun()
    with st.form("f_fin", clear_on_submit=True):
        st.write("➕ **Lançar Pagamento / Recebimento**")
        cp1, cp2, cp3 = st.columns(3)
        t = cp1.selectbox("Tipo", ["Saída (Pedreiro)", "Entrada (Cliente)"])
        v = cp2.number_input("Valor R$")
        if st.form_submit_button("Confirmar"):
            cat = "Mão de Obra" if "Saída" in t else "Entrada Cliente"
            supabase.table("custos").insert({"id_obra": id_obra_atual, "descricao": t, "valor": v, "total": v, "etapa": cat, "data": str(datetime.now().date())}).execute()
            st.cache_data.clear(); st.rerun()
    p_mo = custos_f[custos_f['etapa'] == "Mão de Obra"]
    r_cl = custos_f[custos_f['etapa'] == "Entrada Cliente"]
    res1, res2 = st.columns(2)
    res1.metric("Saldo Pedreiro", formatar_moeda(nP - p_mo['total'].sum()))
    res2.metric("Saldo Cliente", formatar_moeda(nC - r_cl['total'].sum()))

# 7. CADASTRO (Aba mantida conforme solicitado anteriormente)
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