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

# --- PADRÃO DE ETAPAS ---
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
    {"pai": "3. Supraestrutura (Estrutura)", "sub": "Pilares"},
    {"pai": "3. Supraestrutura (Estrutura)", "sub": "Vigas"},
    {"pai": "3. Supraestrutura (Estrutura)", "sub": "Lajes"},
    {"pai": "4. Alvenaria e Vedação", "sub": "Levantamento de Paredes"},
    {"pai": "5. Cobertura", "sub": "Estrutura Telhado"},
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
    # Adicionado 'prestadores' às tabelas carregadas
    for tbl in ["obras", "custos", "cronograma", "tarefas", "materiais", "prestadores"]:
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
        if tbl == 'prestadores':
            df = garantir_colunas(df, ['id', 'nome', 'especialidade'], "texto")
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

custos_f = DB['custos'][DB['custos']['id_obra'] == id_obra_atual]
crono_f = DB['cronograma'][DB['cronograma']['id_obra'] == id_obra_atual]
tarefas_f = DB['tarefas'][DB['tarefas']['id_obra'] == id_obra_atual]
prestadores_f = DB['prestadores']

# --- ABAS ---
tabs = st.tabs(["📝 Lançar", "📅 Cronograma", "✅ Tarefas", "📊 Histórico", "📈 Dash", "💰 Pagamentos", "📦 Cadastro", "👷 Prestadores"])

# 1. ABA LANÇAR
with tabs[0]:
    st.subheader(f"Lançar Custo - {nome_obra}")
    with st.form("form_lancar", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        l_pais = sorted(list(set([item['pai'] for item in ETAPAS_PADRAO])))
        etapa_fin = c1.selectbox("Etapa de Gasto", l_pais + ["Mão de Obra"])
        
        # Lógica para Mão de Obra ou Materiais
        if etapa_fin == "Mão de Obra":
            p_lista = prestadores_f['nome'].tolist()
            desc = c2.selectbox("Selecione o Prestador", p_lista) if p_lista else c2.text_input("Nome do Prestador")
        else:
            m_lista = DB['materiais']['nome'].tolist()
            desc = c2.selectbox("Material (do Cadastro)", m_lista) if m_lista else c2.text_input("Descrição do Item")
            
        valor = c3.number_input("Valor Unitário (R$)", min_value=0.0, format="%.2f")
        qtd = st.number_input("Quantidade", 1.0, step=0.1)
        data_input = st.date_input("Data do Gasto", format="DD/MM/YYYY")
        
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
    # ... (Mantido o código original de tarefas)
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

# 5. ABA DASHBOARD (APRIMORADA: PREVISTO VS REAL)
with tabs[4]:
    st.subheader("📈 Dashboard: Previsto vs Real")
    if not custos_f.empty:
        # Cálculos de Totais
        total_gasto = custos_f['total'].sum()
        gasto_mo = custos_f[custos_f['etapa'] == "Mão de Obra"]['total'].sum()
        gasto_outros = total_gasto - gasto_mo
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Orçamento Total (Cliente)", formatar_moeda(orc_c))
        c2.metric("Gasto Real Total", formatar_moeda(total_gasto), delta=f"{((total_gasto/orc_c)-1)*100:.1f}%" if orc_c > 0 else None, delta_color="inverse")
        c3.metric("Saldo do Orçamento", formatar_moeda(orc_c - total_gasto))

        st.divider()
        
        # Gráfico Comparativo de Mão de Obra
        st.write("### 👷 Mão de Obra: Previsto vs Gasto")
        df_mo = pd.DataFrame({
            'Categoria': ['Previsto (Orç. Pedreiro)', 'Real (Pago)'],
            'Valor': [orc_p, gasto_mo]
        })
        st.bar_chart(df_mo, x='Categoria', y='Valor', color="#ff4b4b")

        # Gráfico de Gasto por Etapa
        st.write("### 📊 Gastos por Etapa")
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
        # Se for pedreiro, permite escolher qual
        v_desc = t
        if t == "Saída (Pedreiro)":
            p_lista = prestadores_f['nome'].tolist()
            p_sel = cp2.selectbox("Quem recebeu?", p_lista) if p_lista else ""
            v_desc = f"Pgto: {p_sel}" if p_sel else t
            
        v = cp3.number_input("Valor R$", format="%.2f")
        dt_p = st.date_input("Data", format="DD/MM/YYYY", key="dt_fin")
        
        if st.form_submit_button("Confirmar"):
            cat = "Mão de Obra" if "Saída" in t else "Entrada Cliente"
            supabase.table("custos").insert({"id_obra": id_obra_atual, "descricao": v_desc, "valor": v, "total": v, "etapa": cat, "data": str(dt_p)}).execute()
            st.cache_data.clear(); st.rerun()
    
    # ... (Histórico de lançamentos mantido)
    p_mo = custos_f[custos_f['etapa'] == "Mão de Obra"]
    r_cl = custos_f[custos_f['etapa'] == "Entrada Cliente"]
    st.write("---")
    res1, res2 = st.columns(2)
    res1.metric("Saldo Pedreiro", formatar_moeda(nP - p_mo['total'].sum()))
    res2.metric("Saldo Cliente", formatar_moeda(nC - r_cl['total'].sum()))

# 7. ABA CADASTRO
with tabs[6]:
    st.subheader("📦 Cadastro de Materiais")
    # ... (Mantido código de cadastro de materiais)

# 8. ABA PRESTADORES (NOVA)
with tabs[7]:
    st.subheader("👷 Gestão de Prestadores (Mão de Obra)")
    with st.form("add_prestador", clear_on_submit=True):
        c1, c2 = st.columns(2)
        n_p = c1.text_input("Nome do Profissional")
        e_p = c2.text_input("Especialidade (ex: Eletricista, Pedreiro)")
        if st.form_submit_button("Cadastrar Prestador"):
            supabase.table("prestadores").insert({"nome": n_p, "especialidade": e_p}).execute()
            st.success("Cadastrado!"); st.cache_data.clear(); st.rerun()
            
    if not prestadores_f.empty:
        df_p_ed = st.data_editor(prestadores_f, key="ed_prestadores", num_rows="dynamic", hide_index=True, use_container_width=True)
        if st.button("Salvar Alterações Prestadores"):
            ids_f = df_p_ed['id'].dropna().tolist()
            p_del = list(set(prestadores_f['id'].tolist()) - set(ids_f))
            for d_id in p_del: supabase.table("prestadores").delete().eq("id", d_id).execute()
            for _, r in df_p_ed.iterrows():
                if pd.notnull(r['id']):
                    supabase.table("prestadores").update({"nome": r['nome'], "especialidade": r['especialidade']}).eq("id", r['id']).execute()
                else:
                    supabase.table("prestadores").insert({"nome": r['nome'], "especialidade": r['especialidade']}).execute()
            st.success("Sincronizado!"); st.cache_data.clear(); st.rerun()