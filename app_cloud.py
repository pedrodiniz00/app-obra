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
    if df is None or df.empty: return pd.DataFrame(columns=colunas)
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
    tabelas = ["obras", "custos", "cronograma", "tarefas", "materiais", "prestadores", "fornecedores"]
    for tbl in tabelas:
        df = run_query(tbl)
        if tbl == 'obras':
            df = garantir_colunas(df, ['id', 'nome', 'orcamento_pedreiro', 'orcamento_cliente', 'arquivada'])
        elif tbl == 'custos':
            df = garantir_colunas(df, ['id', 'id_obra', 'valor', 'total', 'descricao', 'data', 'etapa', 'fornecedor'])
            if not df.empty: df['data'] = pd.to_datetime(df['data']).dt.date
        elif tbl == 'cronograma':
            df = garantir_colunas(df, ['id', 'id_obra', 'etapa', 'porcentagem', 'planejada'])
        elif tbl == 'tarefas':
            df = garantir_colunas(df, ['id', 'id_obra', 'descricao', 'responsavel', 'status'], "texto")
        elif tbl in ['materiais', 'prestadores', 'fornecedores']:
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
id_obra_atual = 0
nome_obra = ""
orc_p_db = 0.0
orc_c_db = 0.0

# --- SIDEBAR ---
with st.sidebar:
    st.header("🏢 Obras")
    ver_arquivadas = st.checkbox("Ver Arquivadas")
    if not DB['obras'].empty:
        DB['obras']['arquivada'] = DB['obras']['arquivada'].apply(lambda x: str(x).lower() in ['true', '1', 't'])
        df_f = DB['obras'][DB['obras']['arquivada'] == ver_arquivadas]
        if not df_f.empty:
            opcoes = df_f.apply(lambda x: f"{int(x['id'])} - {x['nome']}", axis=1).tolist()
            selecao = st.selectbox("Selecione a Obra:", opcoes)
            id_obra_atual = int(selecao.split(" - ")[0])
            row_o = DB['obras'][DB['obras']['id'] == id_obra_atual].iloc[0]
            nome_obra = row_o['nome']
            orc_p_db = float(row_o.get('orcamento_pedreiro', 0) or 0)
            orc_c_db = float(row_o.get('orcamento_cliente', 0) or 0)
            status_arq = row_o['arquivada']
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

custos_f = DB['custos'][DB['custos']['id_obra'] == id_obra_atual] if not DB['custos'].empty else pd.DataFrame()
crono_f = DB['cronograma'][DB['cronograma']['id_obra'] == id_obra_atual] if not DB['cronograma'].empty else pd.DataFrame()
tarefas_f = DB['tarefas'][DB['tarefas']['id_obra'] == id_obra_atual] if not DB['tarefas'].empty else pd.DataFrame()

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
            p_lista = DB['prestadores']['nome'].tolist() if 'nome' in DB['prestadores'].columns else []
            desc = c2.selectbox("Prestador", p_lista) if p_lista else c2.text_input("Nome")
            forn_vinculo = ""
        else:
            m_lista = DB['materiais']['nome'].tolist() if 'nome' in DB['materiais'].columns else []
            desc = c2.selectbox("Material", m_lista) if m_lista else c2.text_input("Descrição")
            f_lista = DB['fornecedores']['nome'].tolist() if 'nome' in DB['fornecedores'].columns else []
            forn_vinculo = c3.selectbox("Fornecedor", ["-"] + f_lista)
        valor = st.number_input("Valor Unitário (R$)", 0.0, format="%.2f")
        qtd = st.number_input("Qtd", 1.0, step=0.1)
        dt_in = st.date_input("Data", format="DD/MM/YYYY")
        if st.form_submit_button("Salvar"):
            supabase.table("custos").insert({"id_obra": id_obra_atual, "descricao": desc, "valor": valor, "qtd": qtd, "total": valor*qtd, "etapa": etapa_fin, "data": str(dt_in), "fornecedor": forn_vinculo if forn_vinculo != "-" else ""}).execute()
            st.success("Salvo!"); st.cache_data.clear()

# 2. ABA CRONOGRAMA (ALTERAÇÃO SOLICITADA: PESOS HIERÁRQUICOS)
with tabs[1]:
    st.subheader("📅 Cronograma: Pesos Hierárquicos")
    if not crono_f.empty:
        crono_f['pai'] = crono_f['etapa'].apply(lambda x: x.split(' | ')[0] if ' | ' in x else x)
        crono_f['sub'] = crono_f['etapa'].apply(lambda x: x.split(' | ')[1] if ' | ' in x else "")
        etapas_uniques = sorted(crono_f['pai'].unique())
        
        # PESO ETAPA PAI EM RELAÇÃO À OBRA (Soma = 100%)
        cols_pai = st.columns(len(etapas_uniques))
        pesos_pai = {}
        for idx, pai in enumerate(etapas_uniques):
            pesos_pai[pai] = cols_pai[idx].number_input(f"{pai} (% Obra)", 0, 100, 10, key=f"wp_{pai}")
        
        prog_total = 0
        st.divider()
        
        for i, pai in enumerate(etapas_uniques, 1):
            subset = crono_f[crono_f['pai'] == pai].sort_values(by='sub')
            
            # Cálculo progresso Etapa Pai: (Executado % * Peso da Sub na Etapa)
            soma_pesos_sub = subset['planejada'].sum()
            prog_pai = sum((r['porcentagem']/100)*(r['planejada']/soma_pesos_sub) for _,r in subset.iterrows()) if soma_pesos_sub>0 else 0
            
            # Acúmulo no Total: Progresso Pai * Peso do Pai na Obra
            prog_total += (prog_pai * (pesos_pai[pai]/100))
            
            with st.expander(f"📁 {pai} — Progresso: {prog_pai*100:.1f}% (Peso: {pesos_pai[pai]}%)"):
                for j, (_, row) in enumerate(subset.iterrows(), 1):
                    with st.container(border=True):
                        # Linha 1: Descrição
                        r1c1, r1c2, r1c3, r1c4 = st.columns([0.4, 8.0, 0.7, 0.7])
                        r1c1.write(f"**{i}.{j}**")
                        nv_sub = r1c2.text_input("Ativ", row['sub'], key=f"n_{row['id']}", label_visibility="collapsed")
                        
                        if r1c3.button("💾", key=f"s_{row['id']}"):
                            supabase.table("cronograma").update({
                                "etapa": f"{pai} | {nv_sub}", 
                                "planejada": st.session_state[f"pl_{row['id']}"], 
                                "porcentagem": st.session_state[f"ex_{row['id']}"]
                            }).eq("id", row['id']).execute()
                            st.cache_data.clear(); st.rerun()
                        if r1c4.button("🗑️", key=f"d_{row['id']}"):
                            supabase.table("cronograma").delete().eq("id", row['id']).execute()
                            st.cache_data.clear(); st.rerun()
                        
                        # Linha 2: Pesos e Execução
                        r2c1, r2c2, r2c3, r2c4 = st.columns([0.4, 2.0, 2.0, 5.0])
                        # planejado = Peso da Sub na Etapa Pai
                        st.session_state[f"pl_{row['id']}"] = r2c2.number_input("Peso na Etapa (%)", 0, 100, int(row.get('planejada', 0)), key=f"pi_{row['id']}")
                        # porcentagem = Executado Real da Sub
                        st.session_state[f"ex_{row['id']}"] = r2c3.number_input("Executado (%)", 0, 100, int(row['porcentagem']), key=f"ei_{row['id']}")
                        
                        status_txt = "✅ Concluída" if st.session_state[f"ex_{row['id']}"] >= 100 else "🚧 Em Andamento"
                        r2c4.write(f"**Status:** {status_txt}")
        
        st.divider()
        st.metric("🏗️ PROGRESSO TOTAL DA OBRA", f"{prog_total*100:.2f}%")
        st.progress(min(prog_total, 1.0))

# 3. ABA TAREFAS
with tabs[2]:
    st.subheader("📋 Gestão de Tarefas")
    with st.form("f_t", clear_on_submit=True):
        c1, c2 = st.columns(2); nt, rp = c1.text_input("Tarefa"), c2.text_input("Responsável")
        if st.form_submit_button("Adicionar"):
            supabase.table("tarefas").insert({"id_obra": id_obra_atual, "descricao": nt, "responsavel": rp, "status": "Pendente"}).execute()
            st.cache_data.clear(); st.rerun()
    v_c = st.toggle("Ver Concluídas")
    df_v = tarefas_f[tarefas_f['status'] == ("Concluída" if v_c else "Pendente")]
    if not df_v.empty:
        df_edit = st.data_editor(df_v[['id', 'descricao', 'responsavel', 'status']], key=f"et_{v_c}", hide_index=True, use_container_width=True)
        if st.button("💾 Salvar Tarefas"):
            for _, r in df_edit.iterrows(): supabase.table("tarefas").update({"descricao": r['descricao'], "responsavel": r['responsavel'], "status": r['status']}).eq("id", r['id']).execute()
            st.cache_data.clear(); st.rerun()

# 4. ABA HISTÓRICO
with tabs[3]:
    st.subheader("📊 Histórico de Custos")
    st.dataframe(custos_f[['data', 'descricao', 'fornecedor', 'total', 'etapa']], use_container_width=True)

# 5. ABA DASHBOARD
with tabs[4]:
    st.subheader("📈 Resumo Financeiro")
    tg = custos_f['total'].sum() if not custos_f.empty else 0
    c1, c2, c3 = st.columns(3); c1.metric("Orçado", formatar_moeda(orc_c_db)); c2.metric("Gasto", formatar_moeda(tg)); c3.metric("Saldo", formatar_moeda(orc_c_db - tg))

# 6. ABA PAGAMENTOS (MANUTENÇÃO INTEGRAL)
with tabs[5]:
    st.subheader("💰 Pagamentos e Entradas")
    with st.expander("⚙️ Configurar Orçamentos"):
        co1, co2, co3 = st.columns([2, 2, 1])
        nv_c, nv_p = co1.number_input("Cliente", value=orc_c_db), co2.number_input("Pedreiro", value=orc_p_db)
        if co3.button("Salvar Orçamentos"):
            supabase.table("obras").update({"orcamento_cliente": nv_c, "orcamento_pedreiro": nv_p}).eq("id", id_obra_atual).execute()
            st.cache_data.clear(); st.rerun()

    with st.form("f_pg", clear_on_submit=True):
        cp1, cp2, cp3, cp4 = st.columns(4)
        tp = cp1.selectbox("Tipo", ["Saída (Pagto Pedreiro)", "Entrada (Aporte Cliente)"])
        p_lista = DB['prestadores']['nome'].tolist() if 'nome' in DB['prestadores'].columns else []
        if tp == "Saída (Pagto Pedreiro)":
            rf = cp2.selectbox("Referência (Prestador)", ["-"] + p_lista)
        else:
            rf = cp2.text_input("Referência")
        vl, dt = cp3.number_input("Valor R$", 0.0), cp4.date_input("Data")
        if st.form_submit_button("Lançar"):
            desc_f = f"Ref: {rf}" if rf != "-" else "Pagamento"
            etp = "Mão de Obra" if "Saída" in tp else "Entrada Cliente"
            supabase.table("custos").insert({"id_obra": id_obra_atual, "descricao": desc_f, "total": vl, "etapa": etp, "data": str(dt)}).execute()
            st.cache_data.clear(); st.rerun()

    st.divider()
    cl1, cl2 = st.columns(2)
    with cl1:
        st.error("🔴 Pagamentos (Saídas)")
        df_s = custos_f[custos_f['etapa'] == "Mão de Obra"].copy()
        if not df_s.empty:
            st.dataframe(df_s[['data', 'descricao', 'total']].sort_values('data', ascending=False), use_container_width=True, hide_index=True)
            st.metric("Total Pago", formatar_moeda(df_s['total'].sum()))
    with cl2:
        st.success("🟢 Entradas (Cliente)")
        df_e = custos_f[custos_f['etapa'] == "Entrada Cliente"].copy()
        if not df_e.empty:
            st.dataframe(df_e[['data', 'descricao', 'total']].sort_values('data', ascending=False), use_container_width=True, hide_index=True)
            st.metric("Total Recebido", formatar_moeda(df_e['total'].sum()))

# 7. ABA CADASTRO
with tabs[6]:
    st.subheader("📦 Cadastros")
    s1, s2 = st.tabs(["Materiais", "Fornecedores"])
    with s1:
        with st.form("a_m"):
            nm = st.text_input("Material")
            if st.form_submit_button("Salvar Material"):
                supabase.table("materials").insert({"nome": nm}).execute(); st.cache_data.clear()
        if not DB['materiais'].empty: st.data_editor(DB['materiais'][['id', 'nome']], use_container_width=True, hide_index=True)
    with s2:
        with st.form("a_f"):
            f1, f2, f3 = st.columns(3); fn, ft, fc = f1.text_input("Loja"), f2.text_input("Fone"), f3.selectbox("Tipo", ["Materiais", "Outros"])
            if st.form_submit_button("Salvar Fornecedor"):
                supabase.table("fornecedores").insert({"nome": fn, "telefone": ft, "categoria": fc}).execute(); st.cache_data.clear()
        if not DB['fornecedores'].empty: st.data_editor(DB['fornecedores'], use_container_width=True, hide_index=True)

# 8. ABA PRESTADORES
with tabs[7]:
    st.subheader("👷 Prestadores")
    with st.form("a_p"):
        n, e = st.columns(2); nv, ev = n.text_input("Nome"), e.text_input("Especialidade")
        if st.form_submit_button("Cadastrar"):
            supabase.table("prestadores").insert({"nome": nv, "especialidade": ev}).execute(); st.cache_data.clear()
    if not DB['prestadores'].empty: st.data_editor(DB['prestadores'], use_container_width=True, hide_index=True)