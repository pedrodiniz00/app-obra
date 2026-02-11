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
        st.error("❌ Erro: Configure o arquivo .streamlit/secrets.toml com as chaves do Supabase.")
        st.stop()

supabase = init_connection()

# --- DEFINIÇÃO DO PADRÃO CONSTRUTIVO (BASEADO NA PLANILHA) ---
TEMPLATE_ETAPAS = [
    ("1. Planejamento e Preliminares", 5000.0, [
        "Projetos e Aprovações", "Limpeza do Terreno", "Ligação Provisória (Água/Luz)", "Barracão e Tapumes"
    ]),
    ("2. Infraestrutura (Fundação)", 15000.0, [
        "Gabarito e Marcação", "Escavação", "Concretagem Sapatas/Estacas", "Vigas Baldrame", 
        "Impermeabilização", "Passagem de tubulação de esgoto", "Passagem de tubulação de alimentação de energia"
    ]),
    ("3. Supraestrutura (Estrutura)", 25000.0, [
        "Pilares", "Vigas", "Lajes", "Escadas"
    ]),
    ("3. Supraestrutura e Alvenaria", 20000.0, [
        "Marcação dasParedes", "Locação Caixinhas (conferencia de altura e alinhamento)", 
        "Conferencia dos pontos hidráulicos e esgoto (altura dos mesmos)", "Impermeabilização das 3 fiadas", 
        "Embuço", "Impermeabilização dos Banheiros"
    ]),
    ("4. Alvenaria e Vedação", 12000.0, [
        "Levantamento de Paredes", "Vergas e Contravergas", "Chapisco e Emboço"
    ]),
    ("4. Cobertura", 10000.0, [
        "Montagem da Lage", "Passagem e Conferencia dos Conduites", "Estrutura Telhado", "Telhamento", "Calhas e Rufos"
    ]),
    ("5. Instalações", 10000.0, [
        "Conferir medidas de saida de esgoto do vaso", "Ralo dentro e fora do boxe", 
        "Conferir medida do desnível para o chuveiro", "Conferir novamente pontos de esgoto e aguá das pias(alturas)"
    ]),
    ("6. Instalações", 15000.0, [
        "Tubulação Água/Esgoto", "Eletrodutos e Caixinhas", "Fiação e Cabos", "Tubulação Gás/Ar"
    ]),
    ("7. Acabamentos", 30000.0, [
        "Contrapiso", "Reboco/Gesso", "Revestimentos (Piso/Parede)", "Louças e Metais", 
        "Esquadrias (Portas/Janelas)", "Conferir alinhamento dos pisos", 
        "Conferir alinhamento dos pisos nas varandas em todos os cantos", "Conferir largura do desnível dos banheiros"
    ]),
    ("8. Área Externa e Finalização", 5000.0, [
        "Muros e Calçadas", "Pintura Interna/Externa", "Elétrica Final (Tomadas/Luz)", "Limpeza Pós-Obra"
    ])
]

# --- FUNÇÕES AUXILIARES ---
def extrair_numero_etapa(texto):
    try:
        match = re.match(r"(\d+)", str(texto))
        return int(match.group(1)) if match else 9999
    except: return 9999

def run_query(table_name):
    """Busca dados do Supabase e converte para DataFrame"""
    try:
        response = supabase.table(table_name).select("*").execute()
        df = pd.DataFrame(response.data)
        return df if not df.empty else pd.DataFrame()
    except:
        return pd.DataFrame()

@st.cache_data(ttl=2) 
def carregar_tudo():
    dados = {}
    tabelas = ["obras", "custos", "cronograma", "materiais", "fornecedores", "pontos_criticos", "tarefas"]
    
    for tbl in tabelas:
        dados[tbl] = run_query(tbl)
            
    # Converte números
    if not dados['custos'].empty:
        for c in ['valor', 'total', 'qtd']:
            dados['custos'][c] = pd.to_numeric(dados['custos'][c], errors='coerce').fillna(0.0)
    if not dados['cronograma'].empty:
        dados['cronograma']['orcamento'] = pd.to_numeric(dados['cronograma']['orcamento'], errors='coerce').fillna(0.0)

    return dados

# --- LOGIN ---
if "password_correct" not in st.session_state: st.session_state["password_correct"] = False
if not st.session_state["password_correct"]:
    c1, c2, c3 = st.columns([1,2,1])
    with c2:
        st.title("🔒 Acesso Restrito")
        pwd = st.text_input("Senha de Acesso", type="password")
        if st.button("Entrar"):
            if pwd == st.secrets["acesso"]["senha_admin"]:
                st.session_state["password_correct"] = True
                st.rerun()
    st.stop()

# --- INTERFACE ---
st.title("🏗️ Gestor Multi-Obras (SQL)")
DB = carregar_tudo()

# --- SIDEBAR ---
with st.sidebar:
    st.header("🏢 Obra Ativa")
    
    # SELETOR DE OBRAS
    if DB['obras'].empty:
        st.warning("Nenhuma obra cadastrada.")
        opcoes = []
        id_obra_atual = 0
        nome_obra_atual = "Sem Obra"
        status_obra = ""
    else:
        opcoes = DB['obras'].apply(lambda x: f"{x['id']} - {x['nome']}", axis=1).tolist()
        selecao = st.selectbox("Selecione:", opcoes)
        try:
            id_obra_atual = int(selecao.split(" - ")[0])
            nome_obra_atual = selecao.split(" - ")[1]
            status_obra = DB['obras'][DB['obras']['id'] == id_obra_atual].iloc[0]['status']
        except:
            id_obra_atual = 0
            nome_obra_atual = "Erro"
            status_obra = ""

    # NOVA OBRA
    with st.expander("➕ Nova Obra", expanded=(DB['obras'].empty)):
        with st.form("new_obra", clear_on_submit=True):
            n_nome = st.text_input("Nome da Obra")
            n_end = st.text_input("Endereço")
            if st.form_submit_button("Criar Obra"):
                # 1. Cria a Obra
                res = supabase.table("obras").insert({"nome": n_nome, "endereco": n_end, "status": "Ativa"}).execute()
                new_id = res.data[0]['id']
                
                # 2. Gera Cronograma Padrão
                lista_crono = [{"id_obra": new_id, "etapa": str(e), "status": "Pendente", "orcamento": float(o), "porcentagem": 0} for e, o, _ in TEMPLATE_ETAPAS]
                supabase.table("cronograma").insert(lista_crono).execute()
                
                # 3. Gera Checklist Padrão
                lista_subs = []
                for e, _, subs in TEMPLATE_ETAPAS:
                    for s in subs: lista_subs.append({"id_obra": new_id, "etapa_pai": str(e), "descricao": str(s), "feito": "FALSE"})
                supabase.table("pontos_criticos").insert(lista_subs).execute()
                
                st.success("Obra criada com sucesso!"); st.cache_data.clear(); time.sleep(1); st.rerun()

    if id_obra_atual > 0:
        if status_obra == "Concluída": st.success("✅ OBRA CONCLUÍDA")
        else: st.info("🚧 EM ANDAMENTO")
        
        if st.button("🗑️ Excluir Obra Atual", type="primary"):
            supabase.table("custos").delete().eq("id_obra", id_obra_atual).execute()
            supabase.table("cronograma").delete().eq("id_obra", id_obra_atual).execute()
            supabase.table("pontos_criticos").delete().eq("id_obra", id_obra_atual).execute()
            supabase.table("obras").delete().eq("id", id_obra_atual).execute()
            st.success("Excluído!"); st.cache_data.clear(); time.sleep(1); st.rerun()

    if st.button("🔄 Atualizar Dados"): st.cache_data.clear(); st.rerun()

# --- FILTROS ---
if id_obra_atual == 0:
    st.info("👈 Crie ou selecione uma obra no menu lateral para começar.")
    st.stop()

custos_f = DB['custos'][DB['custos']['id_obra'] == id_obra_atual] if not DB['custos'].empty else pd.DataFrame()
crono_f = DB['cronograma'][DB['cronograma']['id_obra'] == id_obra_atual] if not DB['cronograma'].empty else pd.DataFrame()
tarefas_f = DB['tarefas'][DB['tarefas']['id_obra'] == id_obra_atual] if not DB['tarefas'].empty else pd.DataFrame()
pontos_f = DB['pontos_criticos'][DB['pontos_criticos']['id_obra'] == id_obra_atual] if not DB['pontos_criticos'].empty else pd.DataFrame()

# --- ABAS ---
t1, t2, t3, t4, t5, t6, t7 = st.tabs(["📝 Lançar Custos", "📅 Cronograma", "✅ Tarefas", "📦 Cadastros", "📊 Histórico", "📈 Dashboards", "⚙️ Ajustes"])

# 1. LANÇAR
with t1:
    st.subheader(f"Financeiro - {nome_obra_atual}")
    
    # Selectboxes Dinâmicos
    if "reset_lanc" not in st.session_state: st.session_state.reset_lanc = 0
    
    lista_mat = [""] + (DB['materiais'].apply(lambda x: f"{x['id']} - {x['nome']}", axis=1).tolist() if not DB['materiais'].empty else [])
    sel_mat = st.selectbox("Produto/Serviço", lista_mat, key=f"mat_{st.session_state.reset_lanc}")
    
    lista_forn = ["-"] + (DB['fornecedores']['nome'].tolist() if not DB['fornecedores'].empty else [])
    sel_forn = st.selectbox("Fornecedor", lista_forn, key=f"forn_{st.session_state.reset_lanc}")
    
    # Preenchimento automático
    nome, un, val = "", "un", 0.0
    if sel_mat:
        cod = int(sel_mat.split(" - ")[0])
        item = DB['materiais'][DB['materiais']['id'] == cod].iloc[0]
        nome, un, val = item['nome'], item['unidade'], float(item['preco_ref'])

    with st.form("lancar", clear_on_submit=True):
        c1,c2,c3 = st.columns(3)
        data = c1.date_input("Data")
        c2.text_input("Item", nome, disabled=True)
        valor = c3.number_input("Valor Unitário (R$)", value=val)
        c4,c5 = st.columns(2)
        qtd = c4.number_input("Quantidade", 1.0)
        
        # Etapas ordenadas
        etapas_disp = ["Geral"]
        if not crono_f.empty:
            df_temp = crono_f.copy()
            df_temp['sid'] = df_temp['etapa'].apply(extrair_numero_etapa)
            etapas_disp = df_temp.sort_values('sid')['etapa'].tolist()
        etapa = c5.selectbox("Etapa", etapas_disp)
        
        if st.form_submit_button("💾 Salvar Lançamento"):
            if not sel_mat: st.error("Selecione um item da lista.")
            else:
                supabase.table("custos").insert({
                    "id_obra": id_obra_atual, "data": str(data), "descricao": nome,
                    "qtd": qtd, "unidade": un, "valor": valor, "total": valor*qtd,
                    "classe": "Material", "etapa": etapa, "fornecedor": sel_forn
                }).execute()
                st.success("Salvo!"); st.session_state.reset_lanc += 1; st.cache_data.clear(); time.sleep(0.5); st.rerun()

# 2. CRONOGRAMA
with t2:
    if not crono_f.empty:
        crono_f['sid'] = crono_f['etapa'].apply(extrair_numero_etapa)
        for _, row in crono_f.sort_values("sid").iterrows():
            with st.expander(f"📌 {row['etapa']} ({row['porcentagem']}%) | Meta: R$ {float(row['orcamento']):,.2f}"):
                col_s, col_chk = st.columns([0.4, 0.6])
                
                with col_s:
                    nv = st.slider("Progresso", 0, 100, int(row['porcentagem']), key=f"s_{row['id']}")
                    if nv != int(row['porcentagem']):
                        supabase.table("cronograma").update({"porcentagem": nv}).eq("id", int(row['id'])).execute()
                        st.cache_data.clear(); st.rerun()
                
                with col_chk:
                    subs = pontos_f[pontos_f['etapa_pai'] == row['etapa']]
                    for _, sub in subs.iterrows():
                        chk = st.checkbox(sub['descricao'], value=(sub['feito']=="TRUE"), key=f"ck_{sub['id']}")
                        if chk != (sub['feito']=="TRUE"):
                            supabase.table("pontos_criticos").update({"feito": "TRUE" if chk else "FALSE"}).eq("id", int(sub['id'])).execute()
                            st.cache_data.clear(); st.rerun()
                    
                    # Botão rápido para adicionar sub-tarefa pontual
                    c_add1, c_add2 = st.columns([0.8, 0.2])
                    ns = c_add1.text_input("Nova Sub-tarefa", key=f"ns_{row['id']}")
                    if c_add2.button("Add", key=f"bns_{row['id']}"):
                        supabase.table("pontos_criticos").insert({"id_obra": id_obra_atual, "etapa_pai": row['etapa'], "descricao": ns}).execute()
                        st.cache_data.clear(); st.rerun()

# 3. TAREFAS
with t3:
    with st.form("nt"):
        d = st.text_input("Tarefa")
        r = st.text_input("Responsável")
        if st.form_submit_button("Adicionar"):
            supabase.table("tarefas").insert({"id_obra": id_obra_atual, "descricao": d, "responsavel": r, "status": "Pendente"}).execute()
            st.cache_data.clear(); st.rerun()
    
    if not tarefas_f.empty:
        for _, t in tarefas_f.iterrows():
            if t['status'] != 'Concluída':
                c1, c2 = st.columns([0.05, 0.95])
                if c1.checkbox("", key=f"t_{t['id']}"):
                    supabase.table("tarefas").update({"status": "Concluída"}).eq("id", int(t['id'])).execute()
                    st.cache_data.clear(); st.rerun()
                c2.write(f"{t['descricao']} ({t['responsavel']})")

# 4. CADASTROS
with t4:
    c1, c2 = st.columns(2)
    with c1:
        st.write("🧱 **Materiais**")
        with st.form("nm"):
            n = st.text_input("Nome")
            u = st.selectbox("Unidade", ["un","m","m²","m³","kg","sc"])
            p = st.number_input("Preço Ref", 0.0)
            if st.form_submit_button("Salvar Material"):
                supabase.table("materiais").insert({"nome": n, "unidade": u, "preco_ref": p}).execute()
                st.success("OK"); st.cache_data.clear(); st.rerun()
    
    with c2:
        st.write("🚚 **Fornecedores**")
        with st.form("nf"):
            n = st.text_input("Nome")
            t = st.text_input("Tel")
            if st.form_submit_button("Salvar Fornecedor"):
                supabase.table("fornecedores").insert({"nome": n, "telefone": t}).execute()
                st.success("OK"); st.cache_data.clear(); st.rerun()

# 5. HISTORICO
with t5:
    if not custos_f.empty:
        df_edit = custos_f.copy()
        df_edit.insert(0, "Excluir", False)
        res = st.data_editor(df_edit[["Excluir", "data", "descricao", "qtd", "valor", "total", "etapa"]], hide_index=True, use_container_width=True)
        
        if res["Excluir"].any():
            if st.button("Confirmar Exclusão"):
                ids = custos_f.loc[res[res["Excluir"]].index, "id"].tolist()
                for i in ids: supabase.table("custos").delete().eq("id", int(i)).execute()
                st.success("Apagado!"); st.cache_data.clear(); st.rerun()

# 6. DASHBOARDS
with t6:
    if custos_f.empty: st.info("Sem dados.")
    else:
        df_c = custos_f.copy()
        df_c['dt'] = pd.to_datetime(df_c['data'])
        df_c['mes'] = df_c['dt'].dt.strftime('%Y-%m')
        
        c1, c2 = st.columns(2)
        c1.markdown("### 📅 Gastos Mensais")
        c1.bar_chart(df_c.groupby('mes')['total'].sum())
        
        c2.markdown("### 🧱 Curva ABC (Top Materiais)")
        top = df_c.groupby('descricao')['total'].sum().sort_values(ascending=False).head(10)
        c2.bar_chart(top)

# 7. AJUSTES (NOVA ABA)
with t7:
    st.header("⚙️ Ajustes da Obra")
    
    st.markdown("### 1. Atualizar Estrutura")
    st.warning("⚠️ CUIDADO: O botão abaixo apaga todas as etapas atuais e recria baseada na nova planilha.")
    if st.button("🔄 Aplicar Novo Padrão (Planilha) nesta Obra"):
        # 1. Limpa cronograma e checklist atuais desta obra
        supabase.table("pontos_criticos").delete().eq("id_obra", id_obra_atual).execute()
        supabase.table("cronograma").delete().eq("id_obra", id_obra_atual).execute()
        
        # 2. Recria Cronograma
        lista_crono = [{"id_obra": id_obra_atual, "etapa": str(e), "status": "Pendente", "orcamento": float(o), "porcentagem": 0} for e, o, _ in TEMPLATE_ETAPAS]
        supabase.table("cronograma").insert(lista_crono).execute()
        
        # 3. Recria Checklist
        lista_subs = []
        for e, _, subs in TEMPLATE_ETAPAS:
            for s in subs: lista_subs.append({"id_obra": id_obra_atual, "etapa_pai": str(e), "descricao": str(s), "feito": "FALSE"})
        supabase.table("pontos_criticos").insert(lista_subs).execute()
        
        st.success("Estrutura atualizada com sucesso!"); st.cache_data.clear(); time.sleep(1); st.rerun()
        
    st.markdown("---")
    st.markdown("### 2. Editor Manual de Etapas")
    if not crono_f.empty:
        # Edição do Cronograma
        st.write("Edite nomes e orçamentos abaixo:")
        df_crono_edit = st.data_editor(crono_f[['id', 'etapa', 'orcamento']], key="editor_crono", hide_index=True)
        
        if st.button("💾 Salvar Alterações nas Etapas"):
            # Compara e salva alterações
            for index, row in df_crono_edit.iterrows():
                # Atualiza no banco
                supabase.table("cronograma").update({
                    "etapa": row['etapa'],
                    "orcamento": row['orcamento']
                }).eq("id", int(row['id'])).execute()
            st.success("Salvo!"); st.cache_data.clear(); time.sleep(0.5); st.rerun()
            
    st.markdown("---")
    st.markdown("### 3. Editor Manual de Sub-Etapas (Checklist)")
    if not pontos_f.empty:
        st.write("Edite descrições das sub-tarefas:")
        df_pontos_edit = st.data_editor(pontos_f[['id', 'etapa_pai', 'descricao']], key="editor_pontos", hide_index=True)
        
        if st.button("💾 Salvar Alterações nas Sub-Etapas"):
            for index, row in df_pontos_edit.iterrows():
                supabase.table("pontos_criticos").update({
                    "descricao": row['descricao'],
                    "etapa_pai": row['etapa_pai']
                }).eq("id", int(row['id'])).execute()
            st.success("Salvo!"); st.cache_data.clear(); time.sleep(0.5); st.rerun()