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
def formatar_moeda(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def run_query(table_name):
    try:
        response = supabase.table(table_name).select("*").execute()
        df = pd.DataFrame(response.data)
        return df if not df.empty else pd.DataFrame()
    except: return pd.DataFrame()

@st.cache_data(ttl=2) 
def carregar_tudo():
    dados = {}
    tabelas = ["obras", "custos", "cronograma", "tarefas"]
    for tbl in tabelas:
        df = run_query(tbl)
        if tbl == 'custos':
            if df.empty: df = pd.DataFrame(columns=['id', 'id_obra', 'valor', 'total', 'qtd', 'descricao', 'data', 'etapa'])
            else: df['data'] = pd.to_datetime(df['data']).dt.date
        if tbl == 'obras':
            if 'orcamento_pedreiro' not in df.columns: df['orcamento_pedreiro'] = 0.0
            if 'orcamento_cliente' not in df.columns: df['orcamento_cliente'] = 0.0
            if df.empty: df = pd.DataFrame(columns=['id', 'nome', 'status', 'orcamento_pedreiro', 'orcamento_cliente'])
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

if "active_tab" not in st.session_state:
    st.session_state.active_tab = "📝 Lançar"

# --- SIDEBAR (MENU ESQUERDO RESTAURADO) ---
with st.sidebar:
    st.header("🏢 Obra Ativa")
    id_obra_atual = 0
    nome_obra_atual = "Sem Obra"
    orc_pedreiro_atual = 0.0
    orc_cliente_atual = 0.0

    if DB['obras'].empty:
        st.warning("Nenhuma obra cadastrada.")
    else:
        opcoes = DB['obras'].apply(lambda x: f"{x['id']} - {x['nome']}", axis=1).tolist()
        selecao = st.selectbox("Selecione a Obra:", opcoes)
        try:
            temp_id = int(selecao.split(" - ")[0])
            if temp_id in DB['obras']['id'].values:
                id_obra_atual = temp_id
                nome_obra_atual = selecao.split(" - ")[1]
                obra_row = DB['obras'][DB['obras']['id'] == id_obra_atual].iloc[0]
                orc_pedreiro_atual = float(obra_row.get('orcamento_pedreiro', 0.0))
                orc_cliente_atual = float(obra_row.get('orcamento_cliente', 0.0))
        except: id_obra_atual = 0

    st.markdown("---")
    
    # BOTAO CRIAR OBRA
    with st.expander("➕ Nova Obra"):
        with st.form("new_obra_sidebar", clear_on_submit=True):
            n_nome = st.text_input("Nome da Obra")
            if st.form_submit_button("Criar Obra"):
                if n_nome:
                    res = supabase.table("obras").insert({"nome": n_nome, "status": "Ativa"}).execute()
                    new_id = res.data[0]['id']
                    # Criar Cronograma Base
                    lista_crono = [{"id_obra": new_id, "etapa": str(e), "status": "Pendente", "orcamento": float(o), "porcentagem": 0} for e, o, _ in TEMPLATE_ETAPAS]
                    supabase.table("cronograma").insert(lista_crono).execute()
                    st.success("Obra Criada!"); st.cache_data.clear(); time.sleep(1); st.rerun()

    # BOTAO EXCLUIR OBRA
    if id_obra_atual > 0:
        st.markdown("---")
        if st.button("🗑️ Excluir Obra Atual", type="primary"):
            # Deletar tudo ligado a essa obra
            supabase.table("custos").delete().eq("id_obra", id_obra_atual).execute()
            supabase.table("cronograma").delete().eq("id_obra", id_obra_atual).execute()
            supabase.table("tarefas").delete().eq("id_obra", id_obra_atual).execute()
            supabase.table("obras").delete().eq("id", id_obra_atual).execute()
            st.success("Obra e dados excluídos!"); st.cache_data.clear(); time.sleep(1); st.rerun()

if id_obra_atual == 0:
    st.info("👈 Selecione ou crie uma obra no menu lateral.")
    st.stop()

custos_f = DB['custos'][DB['custos']['id_obra'] == id_obra_atual] if not DB['custos'].empty else pd.DataFrame()
crono_f = DB['cronograma'][DB['cronograma']['id_obra'] == id_obra_atual] if not DB['cronograma'].empty else pd.DataFrame()
tarefas_f = DB['tarefas'][DB['tarefas']['id_obra'] == id_obra_atual] if not DB['tarefas'].empty else pd.DataFrame()

# --- ABAS ---
lista_abas = ["📝 Lançar", "📅 Cronograma", "✅ Tarefas", "📊 Histórico", "📈 Dash", "💰 Pagamentos"]
tabs = st.tabs(lista_abas)

# 1. LANÇAR
with tabs[0]:
    st.session_state.active_tab = "📝 Lançar"
    st.subheader(f"Lançar Custo - {nome_obra_atual}")
    with st.form("lancar_form", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        desc = c1.text_input("Descrição do Item")
        valor = c2.number_input("Valor Unitário (R$)", 0.0)
        qtd = c3.number_input("Qtd", 1.0)
        etapa = st.selectbox("Etapa", [e for e, _, _ in TEMPLATE_ETAPAS] + ["Mão de Obra"])
        if st.form_submit_button("Salvar Gasto"):
            supabase.table("custos").insert({"id_obra": id_obra_atual, "descricao": desc, "valor": valor, "qtd": qtd, "total": valor*qtd, "etapa": etapa, "data": str(datetime.now().date())}).execute()
            st.success("Salvo!"); st.cache_data.clear(); st.rerun()

# 2. CRONOGRAMA
with tabs[1]:
    st.session_state.active_tab = "📅 Cronograma"
    if not crono_f.empty:
        for _, row in crono_f.iterrows():
            st.write(f"**{row['etapa']}**")
            new_p = st.slider("Progresso (%)", 0, 100, int(row['porcentagem']), key=f"p_{row['id']}")
            if new_p != int(row['porcentagem']):
                supabase.table("cronograma").update({"porcentagem": new_p}).eq("id", row['id']).execute()
                st.cache_data.clear(); st.rerun()

# 3. TAREFAS
with tabs[2]:
    st.session_state.active_tab = "✅ Tarefas"
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
    if not tarefas_f.empty:
        df_ed = st.data_editor(tarefas_f[['id', 'descricao', 'responsavel', 'status']], key="ed_tarefas", hide_index=True, use_container_width=True)
        if st.button("💾 Salvar Alterações"):
            for _, row in df_ed.iterrows():
                supabase.table("tarefas").update({"descricao": row['descricao'], "responsavel": row['responsavel'], "status": row['status']}).eq("id", row['id']).execute()
            st.success("Salvo!"); st.cache_data.clear(); st.rerun()

# 4. HISTORICO
with tabs[3]:
    st.session_state.active_tab = "📊 Histórico"
    if not custos_f.empty:
        st.dataframe(custos_f[['data', 'descricao', 'total', 'etapa']], use_container_width=True, 
                     column_config={"data": st.column_config.DateColumn(format="DD/MM/YYYY"), "total": st.column_config.NumberColumn(format="R$ %.2f")})

# 5. DASHBOARDS
with tabs[4]:
    st.session_state.active_tab = "📈 Dash"
    if not custos_f.empty:
        st.metric("Total Gasto Geral", formatar_moeda(custos_f['total'].sum()))
        st.bar_chart(custos_f.groupby('etapa')['total'].sum())

# 6. PAGAMENTOS
with tabs[5]:
    st.session_state.active_tab = "💰 Pagamentos"
    st.subheader(f"💰 Gestão Financeira - {nome_obra_atual}")
    
    col_orc1, col_orc2 = st.columns(2)
    with col_orc1:
        novo_orc_p = st.number_input("Orçamento Total Pedreiro (R$)", min_value=0.0, value=orc_pedreiro_atual, step=100.0)
    with col_orc2:
        novo_orc_c = st.number_input("Orçamento Total Cliente (R$)", min_value=0.0, value=orc_cliente_atual, step=100.0)
        
    if novo_orc_p != orc_pedreiro_atual or novo_orc_c != orc_cliente_atual:
        if st.button("💾 Salvar Orçamentos"):
            supabase.table("obras").update({"orcamento_pedreiro": novo_orc_p, "orcamento_cliente": novo_orc_c}).eq("id", id_obra_atual).execute()
            st.success("Orçamentos atualizados!"); st.cache_data.clear(); st.rerun()
    
    st.markdown("---")
    
    with st.form("form_financeiro", clear_on_submit=True):
        st.write("➕ **Lançar Movimentação**")
        cp1, cp2, cp3 = st.columns(3)
        tipo = cp1.selectbox("Tipo", ["Pagamento (Saída)", "Recebimento (Entrada)"])
        dt_mov = cp2.date_input("Data", datetime.now())
        v_mov = cp3.number_input("Valor (R$)", min_value=0.0)
        
        if st.form_submit_button("Confirmar Lançamento"):
            if v_mov > 0:
                etapa_fin = "Mão de Obra" if tipo == "Pagamento (Saída)" else "Entrada Cliente"
                desc_fin = "Pagamento Pedreiro" if tipo == "Pagamento (Saída)" else "Recebimento Cliente"
                supabase.table("custos").insert({
                    "id_obra": id_obra_atual, "descricao": desc_fin,
                    "valor": v_mov, "qtd": 1, "total": v_mov,
                    "etapa": etapa_fin, "data": str(dt_mov)
                }).execute()
                st.success("Sucesso!"); st.cache_data.clear(); st.rerun()

    # Cálculos e Históricos Separados
    pagos_mo = custos_f[custos_f['etapa'] == "Mão de Obra"] if not custos_f.empty else pd.DataFrame()
    recebido_cli = custos_f[custos_f['etapa'] == "Entrada Cliente"] if not custos_f.empty else pd.DataFrame()
    
    st.markdown("### 📊 Resumo")
    r1, r2 = st.columns(2)
    with r1:
        st.info("**Mão de Obra**")
        st.metric("Total Pago", formatar_moeda(pagos_mo['total'].sum() if not pagos_mo.empty else 0))
        st.metric("Saldo a Pagar", formatar_moeda(novo_orc_p - (pagos_mo['total'].sum() if not pagos_mo.empty else 0)))
    with r2:
        st.success("**Cliente**")
        st.metric("Total Recebido", formatar_moeda(recebido_cli['total'].sum() if not recebido_cli.empty else 0))
        st.metric("Saldo a Receber", formatar_moeda(novo_orc_c - (recebido_cli['total'].sum() if not recebido_cli.empty else 0)))

    st.markdown("---")
    ch1, ch2 = st.columns(2)
    with ch1:
        st.write("🔴 **Saídas (Pedreiro)**")
        st.dataframe(pagos_mo[['data', 'total']], hide_index=True, use_container_width=True,
                     column_config={"data": st.column_config.DateColumn(format="DD/MM/YYYY"), "total": st.column_config.NumberColumn(format="R$ %.2f")})
    with ch2:
        st.write("🟢 **Entradas (Cliente)**")
        st.dataframe(recebido_cli[['data', 'total']], hide_index=True, use_container_width=True,
                     column_config={"data": st.column_config.DateColumn(format="DD/MM/YYYY"), "total": st.column_config.NumberColumn(format="R$ %.2f")})