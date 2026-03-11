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
    {"pai": "2. Infraestrutura (Fundação)", "sub": "Gabarito e Marcação"},
    {"pai": "3. Supraestrutura (Estrutura)", "sub": "Pilares"},
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

# --- INICIALIZAÇÃO DE VARIÁVEIS DE SEGURANÇA ---
id_obra_atual = 0
nome_obra = ""
orc_p_db = 0.0
orc_c_db = 0.0

# --- SIDEBAR ---
with st.sidebar:
    st.header("🏢 Obras")
    ver_arquivadas = st.checkbox("Ver Arquivadas")
    
    if not DB['obras'].empty:
        DB['obras']['arquivada'] = DB['obras']['arquivada'].fillna(False).astype(bool)
        df_f = DB['obras'][DB['obras']['arquivada'] == ver_arquivadas]
        
        if not df_f.empty:
            opcoes = df_f.apply(lambda x: f"{int(x['id'])} - {x['nome']}", axis=1).tolist()
            selecao = st.selectbox("Selecione a Obra:", opcoes)
            id_obra_atual = int(selecao.split(" - ")[0])
            
            # ATRIBUIÇÃO DAS VARIÁVEIS
            row_o = DB['obras'][DB['obras']['id'] == id_obra_atual].iloc[0]
            nome_obra = row_o['nome']
            orc_p_db = float(row_o.get('orcamento_pedreiro', 0) or 0)
            orc_c_db = float(row_o.get('orcamento_cliente', 0) or 0)
            status_arq = bool(row_o.get('arquivada', False))

            with st.popover("✏️ Editar Nome"):
                nv_nome = st.text_input("Nome", value=nome_obra)
                if st.button("Salvar Nome"):
                    supabase.table("obras").update({"nome": nv_nome}).eq("id", id_obra_atual).execute()
                    st.cache_data.clear(); st.rerun()
            
            txt_b = "📥 Ativar Obra" if status_arq else "📦 Arquivar Obra"
            if st.button(txt_b):
                supabase.table("obras").update({"arquivada": not status_arq}).eq("id", id_obra_atual).execute()
                st.cache_data.clear(); st.rerun()

    st.markdown("---")
    with st.expander("➕ Nova Obra"):
        n_nome = st.text_input("Nome da Obra")
        if st.button("Criar Obra"):
            if n_nome:
                res = supabase.table("obras").insert({"nome": n_nome, "arquivada": False}).execute()
                new_id = res.data[0]['id']
                for item in ETAPAS_PADRAO:
                    supabase.table("cronograma").insert({"id_obra": new_id, "etapa": f"{item['pai']} | {item['sub']}", "porcentagem": 0}).execute()
                st.cache_data.clear(); st.rerun()

# --- BLOQUEIO DE RENDERIZAÇÃO SE NÃO HOUVER OBRA ---
if id_obra_atual == 0:
    st.info("👈 Por favor, selecione uma obra na barra lateral para visualizar os lançamentos.")
    st.stop()

# --- DADOS FILTRADOS ---
custos_f = DB['custos'][DB['custos']['id_obra'] == id_obra_atual]
crono_f = DB['cronograma'][DB['cronograma']['id_obra'] == id_obra_atual]
tarefas_f = DB['tarefas'][DB['tarefas']['id_obra'] == id_obra_atual]
prestadores_f = DB['prestadores']
fornecedores_f = DB['fornecedores']

# --- ABAS ---
tab_titles = ["📝 Lançar", "📅 Cronograma", "✅ Tarefas", "📊 Histórico", "📈 Dash", "💰 Pagamentos", "📦 Cadastro", "👷 Prestadores"]
tabs = st.tabs(tab_titles)

# 1. ABA LANÇAR
with tabs[0]:
    st.subheader(f"Lançar Custo - {nome_obra}")
    with st.form("form_lancar", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        opcoes_etapa = sorted(crono_f['etapa'].apply(lambda x: x.split(' | ')[0] if ' | ' in x else x).unique().tolist()) if not crono_f.empty else []
        etapa_fin = c1.selectbox("Etapa", opcoes_etapa + ["Mão de Obra"])
        if etapa_fin == "Mão de Obra":
            p_lista = prestadores_f['nome'].tolist()
            desc = c2.selectbox("Prestador", p_lista) if p_lista else c2.text_input("Nome")
            forn_vinculo = ""
        else:
            m_lista = DB['materiais']['nome'].tolist()
            desc = c2.selectbox("Material", m_lista) if m_lista else c2.text_input("Descrição")
            f_lista = fornecedores_f['nome'].tolist()
            forn_vinculo = c3.selectbox("Fornecedor", ["-"] + f_lista)
        valor = st.number_input("Valor Unitário (R$)", 0.0, format="%.2f")
        qtd = st.number_input("Qtd", 1.0, step=0.1)
        dt_in = st.date_input("Data", format="DD/MM/YYYY")
        if st.form_submit_button("Salvar"):
            supabase.table("custos").insert({"id_obra": id_obra_atual, "descricao": desc, "valor": valor, "qtd": qtd, "total": valor*qtd, "etapa": etapa_fin, "data": str(dt_in), "fornecedor": forn_vinculo if forn_vinculo != "-" else ""}).execute()
            st.success("Salvo!"); st.cache_data.clear()

# 2. ABA CRONOGRAMA
with tabs[1]:
    st.subheader("📅 Cronograma")
    with st.expander("📁 Criar Nova Pasta"):
        n_p = st.text_input("Nome da Pasta")
        if st.button("Criar"):
            if n_p:
                supabase.table("cronograma").insert({"id_obra": id_obra_atual, "etapa": f"{n_p} | Início", "porcentagem": 0}).execute()
                st.cache_data.clear(); st.rerun()
    st.divider()
    if not crono_f.empty:
        crono_f['pai'] = crono_f['etapa'].apply(lambda x: x.split(' | ')[0] if ' | ' in x else x)
        crono_f['sub'] = crono_f['etapa'].apply(lambda x: x.split(' | ')[1] if ' | ' in x else "")
        for i, pai in enumerate(sorted(crono_f['pai'].unique()), 1):
            c_f, c_e, c_d = st.columns([6, 1, 1])
            with c_f: exp = st.expander(f"📁 {pai}")
            with c_e:
                with st.popover("✏️"):
                    nv = st.text_input("Renomear", value=pai, key=f"ep_{i}")
                    if st.button("OK", key=f"bp_{i}"):
                        for _, r in crono_f[crono_f['pai'] == pai].iterrows():
                            supabase.table("cronograma").update({"etapa": f"{nv} | {r['sub']}"}).eq("id", r['id']).execute()
                        st.cache_data.clear(); st.rerun()
            with c_d:
                if st.button("🗑️", key=f"dp_{i}"):
                    supabase.table("cronograma").delete().eq("id_obra", id_obra_atual).ilike("etapa", f"{pai}%").execute()
                    st.cache_data.clear(); st.rerun()
            with exp:
                with st.popover("➕ Add"):
                    ns = st.text_input("Atividade", key=f"ns_{i}")
                    if st.button("Salvar Atividade", key=f"bas_{i}"):
                        supabase.table("cronograma").insert({"id_obra": id_obra_atual, "etapa": f"{pai} | {ns}", "porcentagem": 0}).execute()
                        st.cache_data.clear(); st.rerun()
                for j, (_, row) in enumerate(crono_f[crono_f['pai'] == pai].sort_values(by='sub').iterrows(), 1):
                    with st.container(border=True):
                        c1, c2, c3, c4, c5 = st.columns([0.5, 3, 3, 1, 1])
                        c1.write(f"**{i}.{j}**")
                        n_at = c2.text_input("Nome", row['sub'], key=f"n_{row['id']}", label_visibility="collapsed")
                        p_at = c3.slider("Progresso", 0, 100, int(row['porcentagem']), key=f"p_{row['id']}", label_visibility="collapsed")
                        if c4.button("💾", key=f"s_{row['id']}"):
                            supabase.table("cronograma").update({"etapa": f"{pai} | {n_at}", "porcentagem": p_at}).eq("id", row['id']).execute()
                            st.cache_data.clear(); st.rerun()
                        if c5.button("🗑️", key=f"d_{row['id']}"):
                            supabase.table("cronograma").delete().eq("id", row['id']).execute()
                            st.cache_data.clear(); st.rerun()

# 3. ABA TAREFAS
with tabs[2]:
    st.subheader("📋 Tarefas")
    with st.form("f_t", clear_on_submit=True):
        c1, c2 = st.columns(2)
        nt, rp = c1.text_input("Tarefa"), c2.text_input("Resp")
        if st.form_submit_button("Add"):
            supabase.table("tarefas").insert({"id_obra": id_obra_atual, "descricao": nt, "responsavel": rp, "status": "Pendente"}).execute()
            st.success("Adicionado!"); st.cache_data.clear()
    v_c = st.toggle("Ver Concluídas")
    df_v = tarefas_f[tarefas_f['status'] == ("Concluída" if v_c else "Pendente")]
    if not df_v.empty:
        df_edit = st.data_editor(df_v[['id', 'descricao', 'responsavel', 'status']], key=f"et_{v_c}", hide_index=True, use_container_width=True, column_config={"status": st.column_config.SelectboxColumn("Status", options=["Pendente", "Em Andamento", "Concluída"])})
        if st.button("💾 Salvar Tarefas"):
            for _, r in df_edit.iterrows():
                supabase.table("tarefas").update({"descricao": r['descricao'], "responsavel": r['responsavel'], "status": r['status']}).eq("id", r['id']).execute()
            st.cache_data.clear(); st.rerun()

# 4. ABA HISTÓRICO
with tabs[3]:
    st.subheader("📊 Histórico")
    st.dataframe(custos_f[['data', 'descricao', 'fornecedor', 'total', 'etapa']], use_container_width=True, column_config={"total": st.column_config.NumberColumn(format="R$ %.2f"), "data": st.column_config.DateColumn(format="DD/MM/YYYY")})

# 5. ABA DASHBOARD
with tabs[4]:
    st.subheader("📈 Resumo Financeiro")
    tg = custos_f['total'].sum() if not custos_f.empty else 0
    c1, c2, c3 = st.columns(3); c1.metric("Orçado (Cliente)", formatar_moeda(orc_c_db)); c2.metric("Gasto Atual", formatar_moeda(tg)); c3.metric("Saldo", formatar_moeda(orc_c_db - tg))
    if not custos_f.empty: st.bar_chart(custos_f.groupby('etapa')['total'].sum())

# 6. ABA PAGAMENTOS
with tabs[5]:
    st.subheader("💰 Pagamentos")
    with st.expander("⚙️ Definir Orçamentos", expanded=False):
        c_orc1, c_orc2, c_orc3 = st.columns([2, 2, 1])
        nv_orc_c = c_orc1.number_input("Cliente (R$)", value=orc_c_db, format="%.2f")
        nv_orc_p = c_orc2.number_input("Pedreiro (R$)", value=orc_p_db, format="%.2f")
        if c_orc3.button("💾 Salvar"):
            supabase.table("obras").update({"orcamento_cliente": nv_orc_c, "orcamento_pedreiro": nv_orc_p}).eq("id", id_obra_atual).execute()
            st.cache_data.clear(); st.rerun()
    st.divider()
    p_m = custos_f[custos_f['etapa'] == "Mão de Obra"].copy()
    r_cl = custos_f[custos_f['etapa'] == "Entrada Cliente"].copy()
    res1, res2, res3, res4 = st.columns(4)
    res1.metric("Recebido", formatar_moeda(r_cl['total'].sum()))
    res2.metric("Pago", formatar_moeda(p_m['total'].sum()))
    res3.metric("A Pagar", formatar_moeda(orc_p_db - p_m['total'].sum()))
    res4.metric("Saldo Cliente", formatar_moeda(orc_c_db - r_cl['total'].sum()))
    with st.form("f_p", clear_on_submit=True):
        cp1, cp2, cp3, cp4 = st.columns(4)
        tp = cp1.selectbox("Tipo", ["Saída (Pedreiro)", "Entrada (Cliente)"])
        p_sel = cp2.selectbox("Quem?", prestadores_f['nome'].tolist()) if tp == "Saída (Pedreiro)" else ""
        v_l = cp3.number_input("R$", 0.0, format="%.2f")
        d_l = cp4.date_input("Data", format="DD/MM/YYYY")
        if st.form_submit_button("Lançar Pagamento"):
            desc_l = f"Pgto: {p_sel}" if tp == "Saída (Pedreiro)" else tp
            supabase.table("custos").insert({"id_obra": id_obra_atual, "descricao": desc_l, "valor": v_l, "total": v_l, "etapa": "Mão de Obra" if "Saída" in tp else "Entrada Cliente", "data": str(d_l)}).execute()
            st.success("Lançado!"); st.cache_data.clear()
    c_s, c_e = st.columns(2)
    with c_s: st.error("🔴 Saídas"); p_m_edit = st.data_editor(p_m[['id', 'data', 'descricao', 'total']], key="eds", hide_index=True, num_rows="dynamic", use_container_width=True, column_config={"total": st.column_config.NumberColumn(format="R$ %.2f")})
    with c_e: st.success("🟢 Entradas"); r_cl_edit = st.data_editor(r_cl[['id', 'data', 'descricao', 'total']], key="ede", hide_index=True, num_rows="dynamic", use_container_width=True, column_config={"total": st.column_config.NumberColumn(format="R$ %.2f")})
    if st.button("💾 Sincronizar"):
        for d in [(p_m, p_m_edit), (r_cl, r_cl_edit)]:
            orig, edit = d; ids_o, ids_e = set(orig['id'].tolist()), set(edit['id'].dropna().tolist())
            for d_id in (ids_o - ids_e): supabase.table("custos").delete().eq("id", d_id).execute()
            for _, r in edit.iterrows():
                if pd.notnull(r['id']): supabase.table("custos").update({"data": str(r['data']), "descricao": r['descricao'], "total": r['total']}).eq("id", r['id']).execute()
        st.cache_data.clear(); st.rerun()

# 7. ABA CADASTRO
with tabs[6]:
    st.subheader("📦 Cadastros")
    s_m, s_f = st.tabs(["Materiais", "Fornecedores"])
    with s_m:
        with st.form("a_m"):
            nm = st.text_input("Material")
            if st.form_submit_button("Salvar Material"):
                supabase.table("materiais").insert({"nome": nm}).execute(); st.cache_data.clear()
        if not DB['materiais'].empty:
            df_m_e = st.data_editor(DB['materiais'][['id', 'nome']], key="em", num_rows="dynamic", hide_index=True, use_container_width=True)
            if st.button("Sincronizar Materiais"):
                for _, r in df_m_e.iterrows():
                    if pd.notnull(r['id']): supabase.table("materiais").update({"nome": r['nome']}).eq("id", r['id']).execute()
                    else: supabase.table("materiais").insert({"nome": r['nome']}).execute()
                st.cache_data.clear(); st.rerun()
    with s_f:
        with st.form("a_f"):
            f1, f2, f3 = st.columns(3); fn, ft, fc = f1.text_input("Loja"), f2.text_input("Fone"), f3.selectbox("Tipo", ["Materiais", "Elétrica", "Hidráulica", "Acabamentos", "Outros"])
            if st.form_submit_button("Salvar Fornecedor"):
                supabase.table("fornecedores").insert({"nome": fn, "telefone": ft, "categoria": fc}).execute(); st.cache_data.clear()
        if not fornecedores_f.empty:
            df_f_e = st.data_editor(fornecedores_f[['id', 'nome', 'telefone', 'categoria']], key="efo", num_rows="dynamic", hide_index=True, use_container_width=True)
            if st.button("Sincronizar Fornecedores"):
                for _, r in df_f_e.iterrows():
                    if pd.notnull(r['id']): supabase.table("fornecedores").update({"nome": r['nome'], "telefone": r['telefone'], "categoria": r['categoria']}).eq("id", r['id']).execute()
                    else: supabase.table("fornecedores").insert({"nome": r['nome'], "telefone": r['telefone'], "categoria": r['categoria']}).execute()
                st.cache_data.clear(); st.rerun()

# 8. ABA PRESTADORES
with tabs[7]:
    st.subheader("👷 Prestadores")
    with st.form("a_p"):
        c1, c2 = st.columns(2); np, ep = c1.text_input("Nome"), c2.text_input("Especialidade")
        if st.form_submit_button("Cadastrar"):
            supabase.table("prestadores").insert({"nome": np, "especialidade": ep}).execute(); st.cache_data.clear()
    if not prestadores_f.empty: st.data_editor(prestadores_f, key="epre", hide_index=True, use_container_width=True)