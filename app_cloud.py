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
    {"pai": "2. Infraestrutura (Fundação)", "sub": "Gabarito e Marcação"},
    {"pai": "3. Supraestrutura (Estrutura)", "sub": "Pilares"},
    {"pai": "4. Alvenaria e Vedação", "sub": "Levantamento de Paredes"},
    {"pai": "5. Cobertura", "sub": "Telhado"},
    {"pai": "6. Instalações", "sub": "Hidráulica/Elétrica"},
    {"pai": "7. Acabamentos", "sub": "Pisos/Revestimentos"},
    {"pai": "8. Finalização", "sub": "Pintura/Limpeza"}
]

# --- FUNÇÕES AUXILIARES ---
def formatar_moeda(valor):
    try: return f"R$ {float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except: return "R$ 0,00"

def garantir_colunas(df, colunas, tipo="valor"):
    if df.empty: return pd.DataFrame(columns=colunas)
    for col in colunas:
        if col not in df.columns: 
            df[col] = 0.0 if tipo == "valor" else ""
    return df

def run_query(table_name):
    try:
        response = supabase.table(table_name).select("*").execute()
        return pd.DataFrame(response.data)
    except: return pd.DataFrame()

@st.cache_data(ttl=2) 
def carregar_tudo():
    dados = {}
    for tbl in ["obras", "custos", "cronograma", "tarefas", "materiais", "prestadores", "fornecedores"]:
        df = run_query(tbl)
        if tbl == 'obras':
            df = garantir_colunas(df, ['id', 'nome', 'orcamento_pedreiro', 'orcamento_cliente', 'arquivada'])
        if tbl == 'custos':
            df = garantir_colunas(df, ['id', 'id_obra', 'valor', 'total', 'descricao', 'data', 'etapa', 'fornecedor'])
            if not df.empty: df['data'] = pd.to_datetime(df['data']).dt.date
        if tbl == 'cronograma':
            df = garantir_colunas(df, ['id', 'id_obra', 'etapa', 'porcentagem', 'planejada'])
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

DB = carregar_tudo()
id_obra_atual = 0
nome_obra = "Nenhuma obra selecionada"
orc_c_db = 0.0
orc_p_db = 0.0

# --- SIDEBAR ---
with st.sidebar:
    st.header("🏢 Obras")
    ver_arquivadas = st.checkbox("Ver Arquivadas")
    if not DB['obras'].empty:
        df_f = DB['obras'][DB['obras']['arquivada'].apply(lambda x: str(x).lower() in ['true', '1', 't']) == ver_arquivadas]
        if not df_f.empty:
            opcoes = df_f.apply(lambda x: f"{int(x['id'])} - {x['nome']}", axis=1).tolist()
            selecao = st.selectbox("Selecione a Obra:", opcoes)
            id_obra_atual = int(selecao.split(" - ")[0])
            row_o = DB['obras'][DB['obras']['id'] == id_obra_atual].iloc[0]
            nome_obra = row_o['nome']
            orc_c_db = float(row_o.get('orcamento_cliente', 0) or 0)
            orc_p_db = float(row_o.get('orcamento_pedreiro', 0) or 0)
            status_arq = row_o['arquivada']

            with st.popover("✏️ Editar Nome"):
                nv_n = st.text_input("Nome", value=nome_obra)
                if st.button("Salvar Nome"):
                    supabase.table("obras").update({"nome": nv_n}).eq("id", id_obra_atual).execute()
                    st.cache_data.clear(); st.rerun()
            
            txt_b = "📥 Ativar Obra" if status_arq else "📦 Arquivar Obra"
            if st.button(txt_b):
                supabase.table("obras").update({"arquivada": not status_arq}).eq("id", id_obra_atual).execute()
                st.cache_data.clear(); st.rerun()

    st.markdown("---")
    with st.expander("➕ Nova Obra"):
        n_nome = st.text_input("Nome da Nova Obra")
        if st.button("Cadastrar Obra"):
            if n_nome:
                res = supabase.table("obras").insert({"nome": n_nome, "arquivada": False}).execute()
                new_id = res.data[0]['id']
                for item in ETAPAS_PADRAO:
                    supabase.table("cronograma").insert({"id_obra": new_id, "etapa": f"{item['pai']} | {item['sub']}", "porcentagem": 0, "planejada": 0}).execute()
                st.cache_data.clear(); st.rerun()

if id_obra_atual == 0:
    st.info("👈 Selecione uma obra na barra lateral.")
    st.stop()

custos_f = DB['custos'][DB['custos']['id_obra'] == id_obra_atual]
crono_f = DB['cronograma'][DB['cronograma']['id_obra'] == id_obra_atual]
tarefas_f = DB['tarefas'][DB['tarefas']['id_obra'] == id_obra_atual]
prestadores_f = DB['prestadores']
fornecedores_f = DB['fornecedores']

# --- ABAS ---
tabs = st.tabs(["📝 Lançar", "📅 Cronograma", "✅ Tarefas", "📊 Histórico", "📈 Dash", "💰 Pagamentos", "📦 Cadastro", "👷 Prestadores"])

# 1. ABA LANÇAR
with tabs[0]:
    st.subheader(f"Lançar Custo - {nome_obra}")
    with st.form("form_lancar", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        opcoes_etapa = sorted(crono_f['etapa'].apply(lambda x: x.split(' | ')[0] if ' | ' in x else x).unique().tolist()) if not crono_f.empty else []
        etapa_fin = c1.selectbox("Etapa", opcoes_etapa + ["Mão de Obra"])
        
        if etapa_fin == "Mão de Obra":
            p_lista = DB['prestadores']['nome'].tolist()
            desc = c2.selectbox("Prestador", p_lista) if p_lista else c2.text_input("Nome")
            forn_vinculo = ""
        else:
            m_lista = DB['materiais']['nome'].tolist()
            desc = c2.selectbox("Material", m_lista) if m_lista else c2.text_input("Descrição")
            f_lista = DB['fornecedores']['nome'].tolist()
            forn_vinculo = c3.selectbox("Fornecedor", ["-"] + f_lista)
        
        valor = st.number_input("Valor Unitário (R$)", 0.0, format="%.2f")
        qtd = st.number_input("Qtd", 1.0, step=0.1)
        dt_in = st.date_input("Data", format="DD/MM/YYYY")
        if st.form_submit_button("Salvar"):
            supabase.table("custos").insert({"id_obra": id_obra_atual, "descricao": desc, "valor": valor, "qtd": qtd, "total": valor*qtd, "etapa": etapa_fin, "data": str(dt_in), "fornecedor": forn_vinculo if forn_vinculo != "-" else ""}).execute()
            st.success("Lançado!"); st.cache_data.clear()

# 2. ABA CRONOGRAMA (Planejado vs Executado + Pesos)
with tabs[1]:
    st.subheader("📅 Cronograma: Planejado vs Executado")
    
    if not crono_f.empty:
        crono_f['pai'] = crono_f['etapa'].apply(lambda x: x.split(' | ')[0] if ' | ' in x else x)
        crono_f['sub'] = crono_f['etapa'].apply(lambda x: x.split(' | ')[1] if ' | ' in x else "")
        
        # Resumo por Etapa Pai
        resumo_etapas = crono_f.groupby('pai').agg({'porcentagem': 'mean', 'planejada': 'mean'}).reset_index()
        
        with st.expander("⚖️ Configurar Pesos das Etapas (Soma = 100%)", expanded=False):
            cols_p = st.columns(len(resumo_etapas))
            pesos_dict = {}
            s_pesos = 0
            for i, r_pai in resumo_etapas.iterrows():
                p_val = cols_p[i].number_input(f"{r_pai['pai']}", 0, 100, 10, key=f"w_{r_pai['pai']}")
                pesos_dict[r_pai['pai']] = p_val
                s_pesos += p_val
            if s_pesos != 100: st.warning(f"Soma: {s_pesos}% (Ajuste para 100%)")

        # Cálculos Totais
        total_exec = sum((row['porcentagem'] / 100) * pesos_dict.get(row['pai'], 0) for _, row in resumo_etapas.iterrows())
        total_plan = sum((row['planejada'] / 100) * pesos_dict.get(row['pai'], 0) for _, row in resumo_etapas.iterrows())
        
        c_m1, c_m2 = st.columns(2)
        c_m1.metric("🏗️ EXECUTADO REAL", f"{total_exec:.2f}%", f"{total_exec - total_plan:.1f}% desvio")
        c_m2.metric("📅 PLANEJADO (META)", f"{total_plan:.2f}%")
        st.progress(total_exec / 100 if total_exec <= 100 else 1.0)

    st.divider()

    if not crono_f.empty:
        for i, pai in enumerate(sorted(crono_f['pai'].unique()), 1):
            d_pai = resumo_etapas[resumo_etapas['pai'] == pai].iloc[0]
            
            c_f, c_e, c_d = st.columns([6, 1, 1])
            with c_f: exp = st.expander(f"📁 {pai} — Real: {d_pai['porcentagem']:.1f}% | Meta: {d_pai['planejada']:.1f}%")
            
            with c_e:
                with st.popover("✏️"):
                    nv = st.text_input("Renomear Pasta", value=pai, key=f"ep_{i}")
                    if st.button("OK", key=f"bp_{i}"):
                        for _, r in crono_f[crono_f['pai'] == pai].iterrows():
                            supabase.table("cronograma").update({"etapa": f"{nv} | {r['sub']}"}).eq("id", r['id']).execute()
                        st.cache_data.clear(); st.rerun()
            with c_d:
                if st.button("🗑️", key=f"dp_{i}"):
                    supabase.table("cronograma").delete().eq("id_obra", id_obra_atual).ilike("etapa", f"{pai}%").execute()
                    st.cache_data.clear(); st.rerun()

            with exp:
                with st.popover("➕ Add Atividade"):
                    ns = st.text_input("Atividade", key=f"ns_{i}")
                    if st.button("Salvar Atividade", key=f"bas_{i}"):
                        supabase.table("cronograma").insert({"id_obra": id_obra_atual, "etapa": f"{pai} | {ns}", "porcentagem": 0, "planejada": 0}).execute()
                        st.cache_data.clear(); st.rerun()
                
                st.divider()
                for j, (_, row) in enumerate(crono_f[crono_f['pai'] == pai].sort_values(by='sub').iterrows(), 1):
                    with st.container(border=True):
                        # Layout com colunas para Planejada e Executada
                        col1, col2, col3, col4, col5, col6 = st.columns([0.4, 4.5, 1.2, 1.2, 0.7, 0.7])
                        col1.write(f"**{i}.{j}**")
                        
                        # Nome e Status
                        nv_sub = col2.text_input("Ativ", row['sub'], key=f"n_{row['id']}", label_visibility="collapsed")
                        status_color = "🔴" if row['porcentagem'] < row['planejada'] else "🟢" if row['porcentagem'] > row['planejada'] else "⚪"
                        col2.caption(f"{status_color} {row['porcentagem'] - row['planejada']}% de desvio")

                        # Valores
                        nv_p = col3.number_input("Plan %", 0, 100, int(row.get('planejada', 0)), key=f"pl_{row['id']}", help="Planejado")
                        nv_e = col4.number_input("Exec %", 0, 100, int(row['porcentagem']), key=f"ex_{row['id']}", help="Executado")

                        if col5.button("💾", key=f"s_{row['id']}"):
                            supabase.table("cronograma").update({"etapa": f"{pai} | {nv_sub}", "planejada": nv_p, "porcentagem": nv_e}).eq("id", row['id']).execute()
                            st.cache_data.clear(); st.rerun()
                        if col6.button("🗑️", key=f"d_{row['id']}"):
                            supabase.table("cronograma").delete().eq("id", row['id']).execute()
                            st.cache_data.clear(); st.rerun()

# 3. ABA TAREFAS
with tabs[2]:
    st.subheader("📋 Gestão de Tarefas")
    with st.form("f_t", clear_on_submit=True):
        c1, c2 = st.columns(2)
        nt, rp = c1.text_input("Tarefa"), c2.text_input("Responsável")
        if st.form_submit_button("Adicionar"):
            supabase.table("tarefas").insert({"id_obra": id_obra_atual, "descricao": nt, "responsavel": rp, "status": "Pendente"}).execute()
            st.success("Tarefa adicionada!"); st.cache_data.clear()
    v_c = st.toggle("Ver Concluídas")
    df_v = tarefas_f[tarefas_f['status'] == ("Concluída" if v_c else "Pendente")]
    if not df_v.empty:
        df_edit = st.data_editor(df_v[['id', 'descricao', 'responsavel', 'status']], key=f"et_{v_c}", hide_index=True, use_container_width=True, column_config={"status": st.column_config.SelectboxColumn("Status", options=["Pendente", "Em Andamento", "Concluída"])})
        if st.button("💾 Salvar Alterações"):
            for _, r in df_edit.iterrows():
                supabase.table("tarefas").update({"descricao": r['descricao'], "responsavel": r['responsavel'], "status": r['status']}).eq("id", r['id']).execute()
            st.cache_data.clear(); st.rerun()

# 4-8. DEMAIS ABAS (PAGAMENTOS, DASH, CADASTROS)
with tabs[3]: 
    st.subheader("📊 Histórico")
    st.dataframe(custos_f[['data', 'descricao', 'fornecedor', 'total', 'etapa']], use_container_width=True, column_config={"total": st.column_config.NumberColumn(format="R$ %.2f")})

with tabs[4]:
    st.subheader("📈 Dash")
    tg = custos_f['total'].sum() if not custos_f.empty else 0
    st.metric("Gasto Atual", formatar_moeda(tg))
    if not custos_f.empty: st.bar_chart(custos_f.groupby('etapa')['total'].sum())

with tabs[5]:
    st.subheader("💰 Pagamentos")
    with st.expander("⚙️ Orçamentos", expanded=False):
        c_orc1, c_orc2, c_orc3 = st.columns([2, 2, 1])
        nv_c = c_orc1.number_input("Cliente", value=orc_c_db, format="%.2f")
        nv_p = c_orc2.number_input("Pedreiro", value=orc_p_db, format="%.2f")
        if c_orc3.button("Salvar Orçamentos"):
            supabase.table("obras").update({"orcamento_cliente": nv_c, "orcamento_pedreiro": nv_p}).eq("id", id_obra_atual).execute()
            st.cache_data.clear(); st.rerun()
    p_m, r_cl = custos_f[custos_f['etapa'] == "Mão de Obra"].copy(), custos_f[custos_f['etapa'] == "Entrada Cliente"].copy()
    st.metric("Saldo Pedreiro", formatar_moeda(orc_p_db - p_m['total'].sum()))
    # ... Restante da lógica de sincronização financeira de versões anteriores ...

with tabs[6]:
    s_m, s_f = st.tabs(["Materiais", "Fornecedores"])
    with s_m:
        with st.form("a_m"):
            nm = st.text_input("Material")
            if st.form_submit_button("Salvar"):
                supabase.table("materiais").insert({"nome": nm}).execute(); st.cache_data.clear()
        if not DB['materials'].empty: st.data_editor(DB['materiais'][['id', 'nome']], key="em", hide_index=True)

with tabs[7]:
    st.subheader("👷 Prestadores")
    with st.form("a_pre"):
        n_p, e_p = st.columns(2)
        if st.form_submit_button("Cadastrar"):
            supabase.table("prestadores").insert({"nome": n_p.text_input("Nome"), "especialidade": e_p.text_input("Especialidade")}).execute(); st.cache_data.clear()