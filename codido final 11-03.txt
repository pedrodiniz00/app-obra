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
    {"pai": "7. Acabamentos", "sub": "Pisos/Revestimentos"},
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
    st.info("👈 Por favor, selecione uma obra na barra lateral.")
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

# 2. ABA CRONOGRAMA (LÓGICA DE PESOS HIERÁRQUICOS)
with tabs[1]:
    st.subheader("📅 Cronograma: Pesos de Etapa e Subetapa")
    
    if not crono_f.empty:
        crono_f['pai'] = crono_f['etapa'].apply(lambda x: x.split(' | ')[0] if ' | ' in x else x)
        crono_f['sub'] = crono_f['etapa'].apply(lambda x: x.split(' | ')[1] if ' | ' in x else "")
        
        # 1. Configurar Pesos das Etapas Pai (Soma = 100% da Obra)
        etapas_uniques = sorted(crono_f['pai'].unique())
        st.info("📌 **Passo 1:** Defina quanto cada Etapa Pai vale no total de 100% da obra.")
        cols_pai = st.columns(len(etapas_uniques))
        pesos_pai = {}
        soma_pai = 0
        for idx, pai in enumerate(etapas_uniques):
            p_val = cols_pai[idx].number_input(f"{pai} (%)", 0, 100, 10, key=f"wp_{pai}")
            pesos_pai[pai] = p_val
            soma_pai += p_val
        
        if soma_pai != 100:
            st.warning(f"⚠️ A soma das etapas pai é **{soma_pai}%**. Ajuste para 100%.")

        # Cálculo do Progresso Real
        progresso_total_acumulado = 0
        
        st.divider()

        # 2. Renderização das Pastas e Subetapas
        for i, pai in enumerate(etapas_uniques, 1):
            subset = crono_f[crono_f['pai'] == pai].sort_values(by='sub')
            
            # Cálculo do progresso da Etapa Pai baseado no peso das subetapas
            soma_pesos_sub = subset['planejada'].sum()
            progresso_da_etapa_pai = 0
            if soma_pesos_sub > 0:
                # Cada sub contribui com (executado/100) * (peso_da_sub / soma_pesos_sub)
                for _, sub_row in subset.iterrows():
                    contribuicao_sub = (sub_row['porcentagem'] / 100) * (sub_row['planejada'] / soma_pesos_sub)
                    progresso_da_etapa_pai += contribuicao_sub
            
            # Progresso total da obra: progresso_pai * (peso_do_pai_no_total / 100)
            progresso_total_acumulado += (progresso_da_etapa_pai * (pesos_pai[pai] / 100))

            # Interface da Pasta
            c_f, c_e, c_d = st.columns([6, 1, 1])
            with c_f: 
                exp = st.expander(f"📁 {pai} — Concluído: {progresso_da_etapa_pai*100:.1f}% (Vale {pesos_pai[pai]}% da obra)")
            
            with c_e:
                with st.popover("✏️"):
                    nv = st.text_input("Renomear Pasta", value=pai, key=f"ren_{i}")
                    if st.button("OK", key=f"bren_{i}"):
                        for _, r in subset.iterrows():
                            supabase.table("cronograma").update({"etapa": f"{nv} | {r['sub']}"}).eq("id", r['id']).execute()
                        st.cache_data.clear(); st.rerun()
            with c_d:
                if st.button("🗑️", key=f"del_{i}"):
                    supabase.table("cronograma").delete().eq("id_obra", id_obra_atual).ilike("etapa", f"{pai}%").execute()
                    st.cache_data.clear(); st.rerun()
            
            with exp:
                st.caption(f"💡 Defina abaixo o peso de cada subetapa em relação à etapa {pai} (Soma deve ser 100%).")
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
                        # Aqui P% representa o peso da subetapa em relação ao PAI
                        nv_p = r2c2.number_input("Peso na Etapa (%)", 0, 100, int(row.get('planejada', 0)), key=f"pl_{row['id']}")
                        # Aqui E% representa o quanto daquela subetapa foi feito (0-100)
                        nv_e = r2c3.number_input("Executado (%)", 0, 100, int(row['porcentagem']), key=f"ex_{row['id']}")
                        status_txt = "✅ Concluída" if nv_e >= 100 else "🚧 Em Andamento"
                        r2c4.write(f"**Status:** {status_txt}")

        # Métrica Geral no rodapé/topo
        st.divider()
        st.metric("🏗️ PROGRESSO TOTAL DA CONSTRUÇÃO", f"{progresso_total_acumulado*100:.2f}%")
        st.progress(min(progresso_total_acumulado, 1.0))

# 3. ABA TAREFAS
with tabs[2]:
    st.subheader("📋 Gestão de Tarefas")
    with st.form("f_t", clear_on_submit=True):
        c1, c2 = st.columns(2); nt, rp = c1.text_input("Tarefa"), c2.text_input("Responsável")
        if st.form_submit_button("Adicionar"):
            supabase.table("tarefas").insert({"id_obra": id_obra_atual, "descricao": nt, "responsavel": rp, "status": "Pendente"}).execute()
            st.success("Tarefa adicionada!"); st.cache_data.clear()
    v_c = st.toggle("Ver Concluídas")
    df_v = tarefas_f[tarefas_f['status'] == ("Concluída" if v_c else "Pendente")]
    if not df_v.empty:
        df_edit = st.data_editor(df_v[['id', 'descricao', 'responsavel', 'status']], key=f"et_{v_c}", hide_index=True, use_container_width=True, 
                                 column_config={"status": st.column_config.SelectboxColumn("Status", options=["Pendente", "Em Andamento", "Concluída"])})
        if st.button("💾 Salvar Alterações"):
            for _, r in df_edit.iterrows():
                supabase.table("tarefas").update({"descricao": r['descricao'], "responsavel": r['responsavel'], "status": r['status']}).eq("id", r['id']).execute()
            st.cache_data.clear(); st.rerun()

# 4. ABA HISTÓRICO
with tabs[3]:
    st.subheader("📊 Histórico de Custos")
    st.dataframe(custos_f[['data', 'descricao', 'fornecedor', 'total', 'etapa']], use_container_width=True, 
                 column_config={"total": st.column_config.NumberColumn(format="R$ %.2f"), "data": st.column_config.DateColumn(format="DD/MM/YYYY")})

# 5. ABA DASHBOARD
with tabs[4]:
    st.subheader("📈 Resumo Financeiro")
    tg = custos_f['total'].sum() if not custos_f.empty else 0
    c1, c2, c3 = st.columns(3); c1.metric("Orçado", formatar_moeda(orc_c_db)); c2.metric("Gasto", formatar_moeda(tg)); c3.metric("Saldo", formatar_moeda(orc_c_db - tg))
    if not custos_f.empty: st.bar_chart(custos_f.groupby('etapa')['total'].sum())

# 6. ABA PAGAMENTOS
with tabs[5]:
    st.subheader("💰 Gestão de Pagamentos")
    with st.expander("⚙️ Definir Orçamentos", expanded=False):
        c_orc1, c_orc2, c_orc3 = st.columns([2, 2, 1]); nv_c = c_orc1.number_input("Cliente", value=orc_c_db, format="%.2f"); nv_p = c_orc2.number_input("Pedreiro", value=orc_p_db, format="%.2f")
        if c_orc3.button("Salvar Orçamentos"):
            supabase.table("obras").update({"orcamento_cliente": nv_c, "orcamento_pedreiro": nv_p}).eq("id", id_obra_atual).execute()
            st.cache_data.clear(); st.rerun()
    p_m = custos_f[custos_f['etapa'] == "Mão de Obra"].copy() if not custos_f.empty else pd.DataFrame()
    r_cl = custos_f[custos_f['etapa'] == "Entrada Cliente"].copy() if not custos_f.empty else pd.DataFrame()
    res1, res2 = st.columns(2); res1.metric("Saldo Pedreiro", formatar_moeda(orc_p_db - p_m['total'].sum() if not p_m.empty else orc_p_db)); res2.metric("Saldo Cliente", formatar_moeda(orc_c_db - r_cl['total'].sum() if not r_cl.empty else orc_c_db))
    with st.form("f_p", clear_on_submit=True):
        cp1, cp2, cp3, cp4 = st.columns(4); tp = cp1.selectbox("Tipo", ["Saída (Pedreiro)", "Entrada (Cliente)"]); p_list_p = DB['prestadores']['nome'].tolist() if 'nome' in DB['prestadores'].columns else []; p_sel = cp2.selectbox("Quem?", p_list_p) if (tp == "Saída (Pedreiro)" and p_list_p) else cp2.text_input("Ref"); v_l = cp3.number_input("R$", 0.0); d_l = cp4.date_input("Data")
        if st.form_submit_button("Lançar"):
            supabase.table("custos").insert({"id_obra": id_obra_atual, "descricao": f"Pgto: {p_sel}" if "Saída" in tp else tp, "total": v_l, "etapa": "Mão de Obra" if "Saída" in tp else "Entrada Cliente", "data": str(d_l)}).execute()
            st.cache_data.clear(); st.rerun()

# 7. ABA CADASTRO
with tabs[6]:
    st.subheader("📦 Central de Cadastros")
    s_m, s_f = st.tabs(["Materiais", "Fornecedores"])
    with s_m:
        with st.form("a_m", clear_on_submit=True):
            nm = st.text_input("Nome Material")
            if st.form_submit_button("Salvar Material"):
                supabase.table("materiais").insert({"nome": nm}).execute(); st.cache_data.clear()
        if not DB['materiais'].empty: st.data_editor(DB['materiais'][['id', 'nome']], use_container_width=True, hide_index=True)
    with s_f:
        with st.form("a_f", clear_on_submit=True):
            f1, f2, f3 = st.columns(3); fn, ft, fc = f1.text_input("Loja"), f2.text_input("Fone"), f3.selectbox("Tipo", ["Materiais", "Elétrica", "Hidráulica", "Outros"])
            if st.form_submit_button("Salvar Fornecedor"):
                supabase.table("fornecedores").insert({"nome": fn, "telefone": ft, "categoria": fc}).execute(); st.cache_data.clear()

# 8. ABA PRESTADORES
with tabs[7]:
    st.subheader("👷 Prestadores de Serviço")
    with st.form("a_pre", clear_on_submit=True):
        np, ep = st.columns(2)
        if st.form_submit_button("Cadastrar Profissional"):
            supabase.table("prestadores").insert({"nome": np.text_input("Nome"), "especialidade": ep.text_input("Especialidade")}).execute(); st.cache_data.clear()
    if not DB['prestadores'].empty: st.data_editor(DB['prestadores'][['id', 'nome', 'especialidade']], use_container_width=True, hide_index=True)