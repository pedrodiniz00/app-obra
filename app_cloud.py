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

# --- DEFINIÇÃO DO PADRÃO CONSTRUTIVO ---
TEMPLATE_ETAPAS = [
    ("1. Planejamento e Preliminares", 5000.0),
    ("2. Infraestrutura", 15000.0),
    ("3. Supraestrutura", 25000.0),
    ("4. Cobertura", 10000.0),
    ("5. Instalações", 15000.0),
    ("6. Acabamentos", 30000.0)
]

# --- FUNÇÕES DE SEGURANÇA E AUXILIARES ---
def formatar_moeda(valor):
    try:
        return f"R$ {float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
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
    df_o = run_query("obras")
    dados['obras'] = garantir_colunas(df_o, ['id', 'nome', 'orcamento_pedreiro', 'orcamento_cliente'])
    
    df_c = run_query("custos")
    df_c = garantir_colunas(df_c, ['id', 'id_obra', 'valor', 'total', 'descricao', 'data', 'etapa'])
    if not df_c.empty:
        df_c['data'] = pd.to_datetime(df_c['data']).dt.date
    dados['custos'] = df_c

    dados['cronograma'] = garantir_colunas(run_query("cronograma"), ['id', 'id_obra', 'etapa', 'porcentagem'])
    dados['tarefas'] = garantir_colunas(run_query("tarefas"), ['id', 'id_obra', 'descricao', 'responsavel', 'status'], "texto")
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

# Lógica para manter a aba ativa
if "aba_focada" not in st.session_state:
    st.session_state.aba_focada = 0

with st.sidebar:
    st.header("🏢 Obra Ativa")
    id_obra_atual = 0
    if DB['obras'].empty:
        st.warning("Crie uma obra.")
    else:
        opcoes = DB['obras'].apply(lambda x: f"{x['id']} - {x['nome']}", axis=1).tolist()
        selecao = st.selectbox("Selecione a Obra:", opcoes)
        id_obra_atual = int(selecao.split(" - ")[0])
        row_o = DB['obras'][DB['obras']['id'] == id_obra_atual].iloc[0]
        nome_obra = row_o['nome']
        orc_p = float(row_o['orcamento_pedreiro'])
        orc_c = float(row_o['orcamento_cliente'])

    st.markdown("---")
    with st.expander("➕ Nova Obra"):
        n_nome = st.text_input("Nome da Obra")
        if st.button("Criar"):
            res = supabase.table("obras").insert({"nome": n_nome}).execute()
            new_id = res.data[0]['id']
            lista_crono = [{"id_obra": new_id, "etapa": str(e), "porcentagem": 0} for e, _ in TEMPLATE_ETAPAS]
            supabase.table("cronograma").insert(lista_crono).execute()
            st.cache_data.clear(); st.rerun()

    if id_obra_atual > 0:
        if st.button("🗑️ Excluir Obra Atual", type="primary"):
            supabase.table("custos").delete().eq("id_obra", id_obra_atual).execute()
            supabase.table("cronograma").delete().eq("id_obra", id_obra_atual).execute()
            supabase.table("tarefas").delete().eq("id_obra", id_obra_atual).execute()
            supabase.table("obras").delete().eq("id", id_obra_atual).execute()
            st.cache_data.clear(); st.rerun()

if id_obra_atual == 0: st.stop()

custos_f = DB['custos'][DB['custos']['id_obra'] == id_obra_atual]
crono_f = DB['cronograma'][DB['cronograma']['id_obra'] == id_obra_atual]
tarefas_f = DB['tarefas'][DB['tarefas']['id_obra'] == id_obra_atual]

# --- ABAS ---
# Usamos o 'index' para forçar a aba correta
tabs = st.tabs(["📝 Lançar", "📅 Cronograma", "✅ Tarefas", "📊 Histórico", "📈 Dash", "💰 Pagamentos"])

# 1. LANÇAR
with tabs[0]:
    st.subheader(f"Lançar Custo - {nome_obra}")
    with st.form("form_lancar", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        desc = c1.text_input("Descrição do Item")
        valor = c2.number_input("Valor Unitário (R$)", 0.0)
        qtd = c3.number_input("Qtd", 1.0)
        etapa = st.selectbox("Etapa", [e for e, _ in TEMPLATE_ETAPAS] + ["Mão de Obra"])
        if st.form_submit_button("Salvar Gasto"):
            supabase.table("custos").insert({"id_obra": id_obra_atual, "descricao": desc, "valor": valor, "qtd": qtd, "total": valor*qtd, "etapa": etapa, "data": str(datetime.now().date())}).execute()
            st.success("Salvo!"); st.cache_data.clear(); st.rerun()

# 2. CRONOGRAMA
with tabs[1]:
    st.subheader("Progresso por Etapa")
    for _, row in crono_f.iterrows():
        st.write(f"**{row['etapa']}**")
        p = st.slider("Progresso (%)", 0, 100, int(row['porcentagem']), key=f"c_{row['id']}")
        if p != int(row['porcentagem']):
            supabase.table("cronograma").update({"porcentagem": p}).eq("id", row['id']).execute()
            st.cache_data.clear(); st.rerun()

# 3. TAREFAS
with tabs[2]:
    st.subheader("Gestão de Tarefas")
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

# 4. HISTÓRICO
with tabs[3]:
    st.subheader("Todos os Lançamentos")
    st.dataframe(custos_f[['data', 'descricao', 'total', 'etapa']], use_container_width=True, 
                 column_config={"total": st.column_config.NumberColumn(format="R$ %.2f")})

# 5. DASHBOARD
with tabs[4]:
    st.subheader("Resumo de Gastos")
    if not custos_f.empty:
        st.metric("Gasto Total", formatar_moeda(custos_f['total'].sum()))
        st.bar_chart(custos_f.groupby('etapa')['total'].sum())

# 6. PAGAMENTOS (COM EDIÇÃO E TRAVA DE ABA)
with tabs[5]:
    st.subheader(f"💰 Financeiro - {nome_obra}")
    
    co1, co2 = st.columns(2)
    new_p = co1.number_input("Orçamento Total Pedreiro", value=orc_p)
    new_c = co2.number_input("Orçamento Total Cliente", value=orc_c)
    if st.button("💾 Salvar Orçamentos"):
        supabase.table("obras").update({"orcamento_pedreiro": new_p, "orcamento_cliente": new_c}).eq("id", id_obra_atual).execute()
        st.cache_data.clear(); st.rerun()

    st.markdown("---")
    
    with st.form("form_financeiro", clear_on_submit=True):
        st.write("➕ **Lançar Pagamento / Recebimento**")
        cp1, cp2, cp3 = st.columns(3)
        tipo = cp1.selectbox("Tipo", ["Saída (Pedreiro)", "Entrada (Cliente)"])
        val = cp2.number_input("Valor R$", min_value=0.0)
        dat = cp3.date_input("Data", datetime.now())
        if st.form_submit_button("Confirmar Lançamento"):
            cat = "Mão de Obra" if "Saída" in tipo else "Entrada Cliente"
            supabase.table("custos").insert({"id_obra": id_obra_atual, "descricao": tipo, "valor": val, "total": val, "etapa": cat, "data": str(dat)}).execute()
            st.cache_data.clear(); st.rerun()

    pagos_mo = custos_f[custos_f['etapa'] == "Mão de Obra"]
    recebido_cli = custos_f[custos_f['etapa'] == "Entrada Cliente"]
    
    r1, r2 = st.columns(2)
    t_pago = pagos_mo['total'].sum()
    t_recebido = recebido_cli['total'].sum()
    r1.metric("Saldo Pedreiro", formatar_moeda(new_p - t_pago))
    r2.metric("Saldo Cliente", formatar_moeda(new_c - t_recebido))

    st.markdown("---")
    h1, h2 = st.columns(2)
    
    with h1:
        st.write("🔴 **Saídas (Pedreiro)**")
        for i, row in pagos_mo.iterrows():
            with st.expander(f"{row['data']} - {formatar_moeda(row['total'])}"):
                nv = st.number_input("Ajustar Valor", value=float(row['total']), key=f"e_p_{row['id']}")
                c_ed, c_ap = st.columns(2)
                if c_ed.button("💾 Salvar", key=f"s_p_{row['id']}"):
                    supabase.table("custos").update({"valor": nv, "total": nv}).eq("id", row['id']).execute()
                    st.cache_data.clear(); st.rerun()
                if c_ap.button("🗑️ Apagar", key=f"a_p_{row['id']}"):
                    supabase.table("custos").delete().eq("id", row['id']).execute()
                    st.cache_data.clear(); st.rerun()

    with h2:
        st.write("🟢 **Entradas (Cliente)**")
        for i, row in recebido_cli.iterrows():
            with st.expander(f"{row['data']} - {formatar_moeda(row['total'])}"):
                nv = st.number_input("Ajustar Valor", value=float(row['total']), key=f"e_c_{row['id']}")
                c_ed, c_ap = st.columns(2)
                if c_ed.button("💾 Salvar", key=f"s_c_{row['id']}"):
                    supabase.table("custos").update({"valor": nv, "total": nv}).eq("id", row['id']).execute()
                    st.cache_data.clear(); st.rerun()
                if c_ap.button("🗑️ Apagar", key=f"a_c_{row['id']}"):
                    supabase.table("custos").delete().eq("id", row['id']).execute()
                    st.cache_data.clear(); st.rerun()