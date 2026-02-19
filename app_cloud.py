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
    for tbl in ["obras", "custos", "cronograma", "tarefas", "materiais", "prestadores", "fornecedores"]:
        df = run_query(tbl)
        if tbl == 'obras':
            df = garantir_colunas(df, ['id', 'nome', 'orcamento_pedreiro', 'orcamento_cliente', 'arquivada'])
        if tbl == 'custos':
            df = garantir_colunas(df, ['id', 'id_obra', 'valor', 'total', 'descricao', 'data', 'etapa', 'fornecedor'])
            if not df.empty: df['data'] = pd.to_datetime(df['data']).dt.date
        if tbl == 'cronograma':
            df = garantir_colunas(df, ['id', 'id_obra', 'etapa', 'porcentagem'])
        if tbl == 'tarefas':
            df = garantir_colunas(df, ['id', 'id_obra', 'descricao', 'responsavel', 'status'], "texto")
        if tbl == 'materiais':
            df = garantir_colunas(df, ['id', 'nome'], "texto")
        if tbl == 'prestadores':
            df = garantir_colunas(df, ['id', 'nome', 'especialidade'], "texto")
        if tbl == 'fornecedores':
            df = garantir_colunas(df, ['id', 'nome', 'telefone', 'categoria'], "texto")
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
    st.header("🏢 Obras")
    ver_arquivadas = st.checkbox("Ver Arquivadas")
    id_obra_atual = 0
    if not DB['obras'].empty:
        df_f = DB['obras'][DB['obras']['arquivada'] == ver_arquivadas]
        if not df_f.empty:
            opcoes = df_f.apply(lambda x: f"{x['id']} - {x['nome']}", axis=1).tolist()
            selecao = st.selectbox("Selecione a Obra:", opcoes)
            id_obra_atual = int(selecao.split(" - ")[0])
            row_o = DB['obras'][DB['obras']['id'] == id_obra_atual].iloc[0]
            nome_obra = row_o['nome']
            orc_p = float(row_o.get('orcamento_pedreiro', 0))
            orc_c = float(row_o.get('orcamento_cliente', 0))
            status_arq = bool(row_o.get('arquivada', False))

            c_ed, c_ar = st.columns(2)
            with c_ed:
                with st.popover("✏️ Editar"):
                    nv_nome = st.text_input("Nome", value=nome_obra)
                    if st.button("Salvar Nome"):
                        supabase.table("obras").update({"nome": nv_nome}).eq("id", id_obra_atual).execute()
                        st.cache_data.clear(); st.rerun()
            with c_ar:
                txt_b = "📥 Ativar" if status_arq else "📦 Arquivar"
                if st.button(txt_b):
                    supabase.table("obras").update({"arquivada": not status_arq}).eq("id", id_obra_atual).execute()
                    st.cache_data.clear(); st.rerun()

    st.markdown("---")
    with st.expander("➕ Nova Obra"):
        n_nome = st.text_input("Nome da Nova Obra")
        if st.button("Criar Obra"):
            if n_nome:
                res = supabase.table("obras").insert({"nome": n_nome, "arquivada": False}).execute()
                new_id = res.data[0]['id']
                for item in ETAPAS_PADRAO:
                    supabase.table("cronograma").insert({"id_obra": new_id, "etapa": f"{item['pai']} | {item['sub']}", "porcentagem": 0}).execute()
                st.cache_data.clear(); st.rerun()

if id_obra_atual == 0:
    st.info("👈 Selecione uma obra.")
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
        l_pais = sorted(list(set([item['pai'] for item in ETAPAS_PADRAO])))
        etapa_fin = c1.selectbox("Etapa", l_pais + ["Mão de Obra"])
        
        if etapa_fin == "Mão de Obra":
            p_lista = prestadores_f['nome'].tolist()
            desc = c2.selectbox("Prestador", p_lista) if p_lista else c2.text_input("Nome")
            forn_vinculo = ""
        else:
            m_lista = DB['materiais']['nome'].tolist()
            desc = c2.selectbox("Material", m_lista) if m_lista else c2.text_input("Descrição")
            f_lista = fornecedores_f['nome'].tolist()
            forn_vinculo = c3.selectbox("Fornecedor/Loja", ["-"] + f_lista)

        valor = st.number_input("Valor Unitário (R$)", 0.0, format="%.2f")
        qtd = st.number_input("Quantidade", 1.0, step=0.1)
        dt_in = st.date_input("Data", format="DD/MM/YYYY")
        
        if st.form_submit_button("Salvar Lançamento"):
            forn_final = forn_vinculo if forn_vinculo != "-" else ""
            supabase.table("custos").insert({
                "id_obra": id_obra_atual, "descricao": desc, "valor": valor, "qtd": qtd, 
                "total": valor*qtd, "etapa": etapa_fin, "data": str(dt_in), "fornecedor": forn_final
            }).execute()
            st.cache_data.clear(); st.rerun()

# 2. ABA CRONOGRAMA
with tabs[1]:
    st.subheader("📅 Cronograma de Execução")
    if not crono_f.empty:
        crono_f['pai'] = crono_f['etapa'].apply(lambda x: x.split(' | ')[0] if ' | ' in x else x)
        crono_f['sub'] = crono_f['etapa'].apply(lambda x: x.split(' | ')[1] if ' | ' in x else "")
        
        for i, pai in enumerate(sorted(crono_f['pai'].unique()), 1):
            with st.expander(f"📁 {pai}"):
                with st.popover(f"➕ Add Atividade em: {pai}"):
                    nova_sub = st.text_input("Nome da Atividade", key=f"new_sub_{i}")
                    if st.button("Confirmar Adição", key=f"btn_add_{i}"):
                        if nova_sub:
                            supabase.table("cronograma").insert({"id_obra": id_obra_atual, "etapa": f"{pai} | {nova_sub}", "porcentagem": 0}).execute()
                            st.cache_data.clear(); st.rerun()
                st.divider()
                subs = crono_f[crono_f['pai'] == pai].sort_values(by='sub')
                for j, (_, row) in enumerate(subs.iterrows(), 1):
                    ex_n = row['sub'] if row['sub'] != "" else row['pai']
                    with st.container(border=True):
                        col1, col2, col3, col4, col5 = st.columns([0.5, 3, 3, 1, 1])
                        col1.write(f"**{i}.{j}**")
                        nv_n = col2.text_input("Nome", ex_n, key=f"n_{row['id']}", label_visibility="collapsed")
                        nv_p = col3.slider("Progresso", 0, 100, int(row['porcentagem']), key=f"p_{row['id']}", label_visibility="collapsed")
                        if col4.button("💾", key=f"s_{row['id']}"):
                            final = f"{pai} | {nv_n}" if row['sub'] != "" else nv_n
                            supabase.table("cronograma").update({"etapa": final, "porcentagem": nv_p}).eq("id", row['id']).execute()
                            st.cache_data.clear(); st.rerun()
                        if col5.button("🗑️", key=f"d_{row['id']}"):
                            supabase.table("cronograma").delete().eq("id", row['id']).execute()
                            st.cache_data.clear(); st.rerun()

# 3. ABA TAREFAS
with tabs[2]:
    st.subheader("📋 Gestão de Tarefas")
    with st.form("f_tar", clear_on_submit=True):
        c1, c2 = st.columns(2)
        nt = c1.text_input("Tarefa")
        rp = c2.text_input("Responsável")
        if st.form_submit_button("Adicionar Tarefa"):
            supabase.table("tarefas").insert({"id_obra": id_obra_atual, "descricao": nt, "responsavel": rp, "status": "Pendente"}).execute()
            st.cache_data.clear(); st.rerun()
    if not tarefas_f.empty:
        df_e = st.data_editor(tarefas_f[['id', 'descricao', 'responsavel', 'status']], key="ed_t", hide_index=True, use_container_width=True)
        if st.button("Salvar Alterações Tarefas"):
            for _, r in df_e.iterrows():
                supabase.table("tarefas").update({"descricao": r['descricao'], "responsavel": r['responsavel'], "status": r['status']}).eq("id", r['id']).execute()
            st.cache_data.clear(); st.rerun()

# 4. ABA HISTÓRICO
with tabs[3]:
    st.subheader("📊 Histórico Geral")
    st.dataframe(custos_f[['data', 'descricao', 'fornecedor', 'total', 'etapa']], use_container_width=True, 
                 column_config={"total": st.column_config.NumberColumn("Total", format="R$ %.2f"), "data": st.column_config.DateColumn("Data", format="DD/MM/YYYY")})

# 5. ABA DASHBOARD
with tabs[4]:
    st.subheader("📈 Dashboard Financeiro")
    if not custos_f.empty:
        tg = custos_f['total'].sum()
        c1, c2, c3 = st.columns(3)
        c1.metric("Orçamento", formatar_moeda(orc_c))
        c2.metric("Gasto Real", formatar_moeda(tg))
        c3.metric("Saldo", formatar_moeda(orc_c - tg))
        st.divider()
        st.bar_chart(custos_f.groupby('etapa')['total'].sum())

# 6. ABA PAGAMENTOS
with tabs[5]:
    st.subheader("💰 Gestão de Pagamentos e Recebimentos")
    p_m = custos_f[custos_f['etapa'] == "Mão de Obra"].copy()
    r_cl = custos_f[custos_f['etapa'] == "Entrada Cliente"].copy()
    t_s = p_m['total'].sum()
    t_e = r_cl['total'].sum()
    res1, res2, res3, res4 = st.columns(4)
    res1.metric("Entradas", formatar_moeda(t_e))
    res2.metric("Saídas (MO)", formatar_moeda(t_s))
    res3.metric("Saldo Pedreiro", formatar_moeda(orc_p - t_s))
    res4.metric("Saldo Cliente", formatar_moeda(orc_c - t_e))
    st.info(f"💵 Caixa Atual: {formatar_moeda(t_e - t_s)}")
    st.divider()
    with st.form("f_fin_new", clear_on_submit=True):
        cp1, cp2, cp3 = st.columns(3)
        tipo = cp1.selectbox("Tipo", ["Saída (Pedreiro)", "Entrada (Cliente)"])
        p_list = prestadores_f['nome'].tolist()
        p_sel = cp2.selectbox("Quem?", p_list) if (tipo == "Saída (Pedreiro)" and p_list) else ""
        val = cp3.number_input("Valor R$", min_value=0.0, format="%.2f")
        dt_p = st.date_input("Data", format="DD/MM/YYYY")
        if st.form_submit_button("Confirmar Lançamento"):
            v_d = f"Pgto: {p_sel}" if (tipo == "Saída (Pedreiro)" and p_sel) else tipo
            cat = "Mão de Obra" if "Saída" in tipo else "Entrada Cliente"
            supabase.table("custos").insert({"id_obra": id_obra_atual, "descricao": v_d, "valor": val, "total": val, "etapa": cat, "data": str(dt_p)}).execute()
            st.cache_data.clear(); st.rerun()
    st.markdown("---")
    c_s, c_e = st.columns(2)
    with c_s:
        st.error("🔴 Detalhe de Saídas")
        p_m_edit = st.data_editor(p_m[['id', 'data', 'descricao', 'total']], key="ed_s", hide_index=True, num_rows="dynamic", use_container_width=True,
                                  column_config={"total": st.column_config.NumberColumn("Valor", format="R$ %.2f"), "data": st.column_config.DateColumn("Data", format="DD/MM/YYYY")})
    with c_e:
        st.success("🟢 Detalhe de Entradas")
        r_cl_edit = st.data_editor(r_cl[['id', 'data', 'descricao', 'total']], key="ed_e", hide_index=True, num_rows="dynamic", use_container_width=True,
                                   column_config={"total": st.column_config.NumberColumn("Valor", format="R$ %.2f"), "data": st.column_config.DateColumn("Data", format="DD/MM/YYYY")})
    if st.button("💾 Sincronizar Pagamentos"):
        for d in [(p_m, p_m_edit), (r_cl, r_cl_edit)]:
            orig, edit = d
            ids_orig = set(orig['id'].tolist()); ids_edit = set(edit['id'].dropna().tolist())
            for d_id in (ids_orig - ids_edit): supabase.table("custos").delete().eq("id", d_id).execute()
            for _, r in edit.iterrows():
                if pd.notnull(r['id']): supabase.table("custos").update({"data": str(r['data']), "descricao": r['descricao'], "total": r['total']}).eq("id", r['id']).execute()
        st.cache_data.clear(); st.rerun()

# 7. ABA CADASTRO
with tabs[6]:
    st.subheader("📦 Central de Cadastros")
    sub_mat, sub_forn = st.tabs(["Materiais", "Fornecedores"])
    with sub_mat:
        with st.form("add_mat"):
            nm = st.text_input("Novo Material")
            if st.form_submit_button("Cadastrar Material"):
                supabase.table("materiais").insert({"nome": nm}).execute()
                st.cache_data.clear(); st.rerun()
        if not DB['materiais'].empty:
            df_em = st.data_editor(DB['materiais'][['id', 'nome']], key="ed_m", num_rows="dynamic", hide_index=True, use_container_width=True)
            if st.button("Sincronizar Materiais"):
                for _, r in df_em.iterrows():
                    if pd.notnull(r['id']): supabase.table("materiais").update({"nome": r['nome']}).eq("id", r['id']).execute()
                    else: supabase.table("materiais").insert({"nome": r['nome']}).execute()
                st.cache_data.clear(); st.rerun()
    with sub_forn:
        with st.form("add_forn", clear_on_submit=True):
            f1, f2, f3 = st.columns(3)
            f_nome = f1.text_input("Nome Loja"); f_tel = f2.text_input("Contato"); f_cat = f3.selectbox("Tipo", ["Materiais", "Elétrica", "Hidráulica", "Acabamentos", "Outros"])
            if st.form_submit_button("Salvar Fornecedor"):
                supabase.table("fornecedores").insert({"nome": f_nome, "telefone": f_tel, "categoria": f_cat}).execute()
                st.cache_data.clear(); st.rerun()
        if not fornecedores_f.empty:
            df_ef = st.data_editor(fornecedores_f[['id', 'nome', 'telefone', 'categoria']], key="ed_f", num_rows="dynamic", hide_index=True, use_container_width=True)
            if st.button("Sincronizar Fornecedores"):
                for _, r in df_ef.iterrows():
                    if pd.notnull(r['id']): supabase.table("fornecedores").update({"nome": r['nome'], "telefone": r['telefone'], "categoria": r['categoria']}).eq("id", r['id']).execute()
                    else: supabase.table("fornecedores").insert({"nome": r['nome'], "telefone": r['telefone'], "categoria": r['categoria']}).execute()
                st.cache_data.clear(); st.rerun()

# 8. ABA PRESTADORES
with tabs[7]:
    st.subheader("👷 Gestão de Profissionais")
    with st.form("add_pre", clear_on_submit=True):
        c1, c2 = st.columns(2)
        n_p = c1.text_input("Nome"); e_p = c2.text_input("Especialidade")
        if st.form_submit_button("Salvar Profissional"):
            supabase.table("prestadores").insert({"nome": n_p, "especialidade": e_p}).execute()
            st.cache_data.clear(); st.rerun()
    if not prestadores_f.empty:
        st.data_editor(prestadores_f, key="ed_pre", hide_index=True, use_container_width=True)