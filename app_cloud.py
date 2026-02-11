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

# --- DEFINIÇÃO DO PADRÃO CONSTRUTIVO ---
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
    """Busca dados com tratamento de erro (Blindagem)"""
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
        df = run_query(tbl)
        
        # --- PROTEÇÃO CONTRA COLUNAS FALTANTES ---
        if tbl == 'custos':
            if 'subetapa' not in df.columns: df['subetapa'] = ""
            if 'classe' not in df.columns: df['classe'] = "Material"
            if df.empty:
                df = pd.DataFrame(columns=['id', 'id_obra', 'classe', 'subetapa', 'valor', 'total', 'qtd', 'descricao', 'data', 'etapa', 'fornecedor', 'unidade'])

        if tbl == 'obras':
            if 'orcamento_pedreiro' not in df.columns: df['orcamento_pedreiro'] = 0.0
            if 'status' not in df.columns: df['status'] = 'Ativa'
            if df.empty:
                df = pd.DataFrame(columns=['id', 'nome', 'orcamento_pedreiro', 'status', 'endereco'])

        # Preenchimento de Nulos
        if not df.empty:
            cols_num = df.select_dtypes(include=[np.number]).columns
            df[cols_num] = df[cols_num].fillna(0)
            cols_obj = df.select_dtypes(include=['object']).columns
            df[cols_obj] = df[cols_obj].fillna("")
        
        dados[tbl] = df
            
    if not dados['custos'].empty:
        for c in ['valor', 'total', 'qtd']:
            if c in dados['custos'].columns:
                dados['custos'][c] = pd.to_numeric(dados['custos'][c], errors='coerce').fillna(0.0)
            
    if not dados['cronograma'].empty:
        dados['cronograma']['orcamento'] = pd.to_numeric(dados['cronograma']['orcamento'], errors='coerce').fillna(0.0)
        dados['cronograma']['porcentagem'] = pd.to_numeric(dados['cronograma']['porcentagem'], errors='coerce').fillna(0)

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

# --- SIDEBAR (COM PROTEÇÃO) ---
with st.sidebar:
    st.header("🏢 Obra Ativa")
    
    id_obra_atual = 0
    nome_obra_atual = "Sem Obra"
    status_obra = "Ativa"

    if DB['obras'].empty:
        st.warning("Nenhuma obra cadastrada.")
    else:
        opcoes = DB['obras'].apply(lambda x: f"{x['id']} - {x['nome']}", axis=1).tolist()
        selecao = st.selectbox("Selecione:", opcoes)
        
        try:
            temp_id = int(selecao.split(" - ")[0])
            # VERIFICAÇÃO: O ID ainda existe no banco?
            if temp_id in DB['obras']['id'].values:
                id_obra_atual = temp_id
                nome_obra_atual = selecao.split(" - ")[1]
                status_obra = DB['obras'][DB['obras']['id'] == id_obra_atual].iloc[0]['status']
            else:
                st.error("Obra não encontrada. Selecione outra.")
        except:
            id_obra_atual = 0

    BLOQUEADO = status_obra in ["Concluída", "Paralisada"]

    with st.expander("➕ Nova Obra", expanded=(DB['obras'].empty)):
        with st.form("new_obra", clear_on_submit=True):
            n_nome = st.text_input("Nome da Obra")
            n_end = st.text_input("Endereço")
            if st.form_submit_button("Criar Obra"):
                res = supabase.table("obras").insert({"nome": n_nome, "endereco": n_end, "status": "Ativa", "orcamento_pedreiro": 0}).execute()
                new_id = res.data[0]['id']
                
                lista_crono = [{"id_obra": new_id, "etapa": str(e), "status": "Pendente", "orcamento": float(o), "porcentagem": 0} for e, o, _ in TEMPLATE_ETAPAS]
                supabase.table("cronograma").insert(lista_crono).execute()
                
                lista_subs = []
                for e, _, subs in TEMPLATE_ETAPAS:
                    for s in subs: lista_subs.append({"id_obra": new_id, "etapa_pai": str(e), "descricao": str(s), "feito": "FALSE"})
                supabase.table("pontos_criticos").insert(lista_subs).execute()
                
                st.success("Obra criada com sucesso!"); st.cache_data.clear(); time.sleep(1); st.rerun()

    if id_obra_atual > 0:
        st.write("---")
        st.write("**Situação da Obra:**")
        
        lista_status = ["Ativa", "Concluída", "Paralisada"]
        try: idx_status = lista_status.index(status_obra)
        except: idx_status = 0
            
        novo_status = st.selectbox("Mudar Status:", lista_status, index=idx_status, label_visibility="collapsed")
        
        if novo_status != status_obra:
            supabase.table("obras").update({"status": novo_status}).eq("id", id_obra_atual).execute()
            st.toast(f"Status alterado para {novo_status}!")
            time.sleep(1)
            st.cache_data.clear()
            st.rerun()

        if novo_status == "Ativa": st.info("🚧 OBRA EM ANDAMENTO")
        elif novo_status == "Concluída": st.success("✅ OBRA CONCLUÍDA (Bloqueada)")
        elif novo_status == "Paralisada": st.warning("⏸️ OBRA PARALISADA (Bloqueada)")
            
        if BLOQUEADO: st.error("🔒 MODO LEITURA: Edições bloqueadas.")
            
        st.write("---")
        
        if not BLOQUEADO:
            if st.button("🗑️ Excluir Obra Atual", type="primary"):
                supabase.table("custos").delete().eq("id_obra", id_obra_atual).execute()
                supabase.table("cronograma").delete().eq("id_obra", id_obra_atual).execute()
                supabase.table("pontos_criticos").delete().eq("id_obra", id_obra_atual).execute()
                supabase.table("obras").delete().eq("id", id_obra_atual).execute()
                st.success("Excluído!"); st.cache_data.clear(); time.sleep(1); st.rerun()
        else:
            st.caption("🚫 Ative a obra para excluir.")

    if st.button("🔄 Atualizar Dados"): st.cache_data.clear(); st.rerun()

# --- FILTROS SEGUROS ---
if id_obra_atual == 0:
    st.info("👈 Crie ou selecione uma obra no menu lateral para começar.")
    st.stop()

custos_f = DB['custos'][DB['custos']['id_obra'] == id_obra_atual] if not DB['custos'].empty else pd.DataFrame(columns=['id', 'classe', 'total', 'data', 'descricao'])
crono_f = DB['cronograma'][DB['cronograma']['id_obra'] == id_obra_atual] if not DB['cronograma'].empty else pd.DataFrame()
tarefas_f = DB['tarefas'][DB['tarefas']['id_obra'] == id_obra_atual] if not DB['tarefas'].empty else pd.DataFrame()
pontos_f = DB['pontos_criticos'][DB['pontos_criticos']['id_obra'] == id_obra_atual] if not DB['pontos_criticos'].empty else pd.DataFrame()

# --- ABAS (VOLTAMOS PARA 6 ABAS) ---
t1, t2, t3, t4, t5, t6 = st.tabs(["📝 Lançar Custos", "📅 Cronograma", "✅ Tarefas", "📦 Cadastros", "📊 Histórico", "📈 Dashboards"])

# 1. LANÇAR
with t1:
    st.subheader(f"Financeiro - {nome_obra_atual}")
    if BLOQUEADO: st.info(f"🔒 Esta obra está {status_obra}. Para lançar custos, altere o status para 'Ativa'.")
    else:
        if "reset_lanc" not in st.session_state: st.session_state.reset_lanc = 0
        c_sel1, c_sel2, c_sel3, c_sel4 = st.columns(4)
        lista_mat = [""] + (DB['materiais'].apply(lambda x: f"{x['id']} - {x['nome']}", axis=1).tolist() if not DB['materiais'].empty else [])
        sel_mat = c_sel1.selectbox("Produto/Serviço", lista_mat, key=f"mat_{st.session_state.reset_lanc}")
        lista_forn = ["-"] + (DB['fornecedores']['nome'].tolist() if not DB['fornecedores'].empty else [])
        sel_forn = c_sel2.selectbox("Fornecedor", lista_forn, key=f"forn_{st.session_state.reset_lanc}")
        etapas_disp = ["Geral"]
        if not crono_f.empty:
            df_temp = crono_f.copy()
            df_temp['sid'] = df_temp['etapa'].apply(extrair_numero_etapa)
            etapas_disp = df_temp.sort_values('sid')['etapa'].tolist()
        sel_etapa = c_sel3.selectbox("Etapa", etapas_disp, key=f"etapa_{st.session_state.reset_lanc}")
        subs_disp = ["Geral"]
        if not pontos_f.empty and sel_etapa:
            subs_da_etapa = pontos_f[pontos_f['etapa_pai'] == sel_etapa]['descricao'].tolist()
            subs_disp += subs_da_etapa
        sel_subetapa = c_sel4.selectbox("Sub-etapa", subs_disp, key=f"sub_{st.session_state.reset_lanc}")

        nome, un, val = "", "un", 0.0
        if sel_mat:
            cod = int(sel_mat.split(" - ")[0])
            item = DB['materiais'][DB['materiais']['id'] == cod].iloc[0]
            nome, un, val = item['nome'], item['unidade'], float(item['preco_ref'])

        with st.form("lancar", clear_on_submit=True):
            st.markdown("---")
            c1,c2,c3,c4 = st.columns([1, 2, 1, 1])
            data = c1.date_input("Data do Gasto")
            c2.text_input("Item Selecionado", nome, disabled=True)
            valor = c3.number_input("Valor Unitário (R$)", value=val)
            qtd = c4.number_input("Quantidade", 1.0)
            
            if st.form_submit_button("💾 Salvar Lançamento"):
                if not sel_mat: st.error("Selecione um item da lista.")
                else:
                    supabase.table("custos").insert({
                        "id_obra": id_obra_atual, "data": str(data), "descricao": nome,
                        "qtd": qtd, "unidade": un, "valor": valor, "total": valor*qtd,
                        "classe": "Material", "etapa": sel_etapa, "subetapa": sel_subetapa,
                        "fornecedor": sel_forn
                    }).execute()
                    st.success("Salvo!"); st.session_state.reset_lanc += 1; st.cache_data.clear(); time.sleep(0.5); st.rerun()

# 2. CRONOGRAMA
with t2:
    with st.expander("⚙️ Gerenciar Estrutura (Editar / Resetar)"):
        if BLOQUEADO: st.warning("🔒 Desbloqueie a obra para editar a estrutura.")
        else:
            col_reset, col_renum = st.columns(2)
            if col_reset.button("🔄 Aplicar Padrão da Planilha", type="primary"):
                supabase.table("pontos_criticos").delete().eq("id_obra", id_obra_atual).execute()
                supabase.table("cronograma").delete().eq("id_obra", id_obra_atual).execute()
                lista_crono = [{"id_obra": id_obra_atual, "etapa": str(e), "status": "Pendente", "orcamento": float(o), "porcentagem": 0} for e, o, _ in TEMPLATE_ETAPAS]
                supabase.table("cronograma").insert(lista_crono).execute()
                lista_subs = []
                for e, _, subs in TEMPLATE_ETAPAS:
                    for s in subs: lista_subs.append({"id_obra": id_obra_atual, "etapa_pai": str(e), "descricao": str(s), "feito": "FALSE"})
                supabase.table("pontos_criticos").insert(lista_subs).execute()
                st.success("Atualizado!"); st.cache_data.clear(); time.sleep(1); st.rerun()
            if col_renum.button("🔢 Renumerar Automaticamente (1, 2, 3...)"):
                if not crono_f.empty:
                    df_t = crono_f.copy()
                    df_t['sid'] = df_t['etapa'].apply(extrair_numero_etapa)
                    seq = 1
                    for _, r in df_t.sort_values('sid').iterrows():
                        old = r['etapa']
                        clean = old.split('.',1)[1].strip() if '.' in old else old
                        new = f"{seq}. {clean}"
                        if new != old:
                            supabase.table("cronograma").update({"etapa": new}).eq("id", int(r['id'])).execute()
                            supabase.table("pontos_criticos").update({"etapa_pai": new}).eq("id_obra", id_obra_atual).eq("etapa_pai", old).execute()
                            supabase.table("custos").update({"etapa": new}).eq("id_obra", id_obra_atual).eq("etapa", old).execute()
                        seq += 1
                    st.success("Renumerado!"); st.cache_data.clear(); st.rerun()

            st.markdown("---")
            st.markdown("### 2. Editor Manual")
            if not crono_f.empty:
                st.write("**Etapas Principais:**")
                df_crono_edit = st.data_editor(crono_f[['id', 'etapa', 'orcamento']], key="editor_crono", hide_index=True, column_config={"orcamento": st.column_config.NumberColumn("Orçamento Meta (R$)", min_value=0.0, format="R$ %.2f")})
                if st.button("💾 Salvar Etapas"):
                    for index, row in df_crono_edit.iterrows():
                        val_orcamento = row['orcamento']
                        if val_orcamento is None or pd.isna(val_orcamento) or str(val_orcamento).strip() == "": val_orcamento = 0.0
                        else: val_orcamento = float(val_orcamento)
                        supabase.table("cronograma").update({"etapa": row['etapa'], "orcamento": val_orcamento}).eq("id", int(row['id'])).execute()
                    st.success("Salvo!"); st.cache_data.clear(); time.sleep(0.5); st.rerun()
            if not pontos_f.empty:
                st.write("**Sub-tarefas (Checklist):**")
                df_pontos_edit = st.data_editor(pontos_f[['id', 'etapa_pai', 'descricao']], key="editor_pontos", hide_index=True)
                if st.button("💾 Salvar Sub-tarefas"):
                    for index, row in df_pontos_edit.iterrows():
                        supabase.table("pontos_criticos").update({"descricao": row['descricao'], "etapa_pai": row['etapa_pai']}).eq("id", int(row['id'])).execute()
                    st.success("Salvo!"); st.cache_data.clear(); time.sleep(0.5); st.rerun()

    st.markdown("---")
    if not crono_f.empty:
        crono_f['sid'] = crono_f['etapa'].apply(extrair_numero_etapa)
        for _, row in crono_f.sort_values("sid").iterrows():
            with st.expander(f"📌 {row['etapa']} ({row['porcentagem']}%) | Meta: R$ {float(row['orcamento']):,.2f}"):
                col_s, col_chk = st.columns([0.4, 0.6])
                with col_s:
                    nv = st.slider("Progresso", 0, 100, int(row['porcentagem']), key=f"s_{row['id']}", disabled=BLOQUEADO)
                    if nv != int(row['porcentagem']):
                        supabase.table("cronograma").update({"porcentagem": nv}).eq("id", int(row['id'])).execute()
                        st.cache_data.clear(); st.rerun()
                with col_chk:
                    subs = pontos_f[pontos_f['etapa_pai'] == row['etapa']]
                    for _, sub in subs.iterrows():
                        chk = st.checkbox(sub['descricao'], value=(sub['feito']=="TRUE"), key=f"ck_{sub['id']}", disabled=BLOQUEADO)
                        if chk != (sub['feito']=="TRUE"):
                            supabase.table("pontos_criticos").update({"feito": "TRUE" if chk else "FALSE"}).eq("id", int(sub['id'])).execute()
                            st.cache_data.clear(); st.rerun()
                    if not BLOQUEADO:
                        c_add1, c_add2 = st.columns([0.8, 0.2])
                        ns = c_add1.text_input("Nova Sub-tarefa", key=f"ns_{row['id']}")
                        if c_add2.button("Add", key=f"bns_{row['id']}"):
                            supabase.table("pontos_criticos").insert({"id_obra": id_obra_atual, "etapa_pai": row['etapa'], "descricao": ns}).execute()
                            st.cache_data.clear(); st.rerun()

# 3. TAREFAS
with t3:
    if BLOQUEADO:
        st.info("🔒 Tarefas em modo leitura.")
        if not tarefas_f.empty:
            for _, t in tarefas_f.iterrows(): st.write(f"- {t['descricao']} ({t['responsavel']}) - {t['status']}")
    else:
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
    if BLOQUEADO: st.info("🔒 Cadastros bloqueados nesta obra.")
    else:
        st_cad1, st_cad2 = st.tabs(["➕ Adicionar Novos", "📋 Visualizar Cadastros"])
        with st_cad1:
            st.subheader("📥 Importar Lista de Materiais (CSV/Excel)")
            uploaded_file = st.file_uploader("Escolha o arquivo CSV ou Excel", type=["csv", "xlsx"])
            if uploaded_file:
                try:
                    if uploaded_file.name.endswith('.csv'): df_import = pd.read_csv(uploaded_file)
                    else: df_import = pd.read_excel(uploaded_file)
                    col_name = df_import.columns[0]
                    df_import = df_import.rename(columns={col_name: 'nome'})
                    if 'unidade' not in df_import.columns: df_import['unidade'] = 'un'
                    if 'preco_ref' not in df_import.columns: df_import['preco_ref'] = 0.0
                    df_import = df_import[df_import['nome'].astype(str).str.strip() != '']
                    df_import = df_import.replace({np.nan: None})
                    st.write(f"Encontrados {len(df_import)} itens. Exemplo:")
                    st.dataframe(df_import.head(3))
                    if st.button("Confirmar Importação em Massa"):
                        dados_para_enviar = df_import[['nome', 'unidade', 'preco_ref']].to_dict(orient='records')
                        for i in range(0, len(dados_para_enviar), 100):
                            chunk = dados_para_enviar[i:i+100]
                            supabase.table("materiais").insert(chunk).execute()
                        st.success("Materiais importados com sucesso!"); time.sleep(1); st.rerun()
                except Exception as e: st.error(f"Erro ao ler arquivo: {e}")
            st.markdown("---")
            c1, c2 = st.columns(2)
            with c1:
                st.write("🧱 **Cadastrar Material Manualmente**")
                with st.form("nm"):
                    n = st.text_input("Nome")
                    u = st.selectbox("Unidade", ["un","m","m²","m³","kg","sc"])
                    p = st.number_input("Preço Ref", 0.0)
                    if st.form_submit_button("Salvar Material"):
                        supabase.table("materiais").insert({"nome": n, "unidade": u, "preco_ref": p}).execute()
                        st.success("OK"); st.cache_data.clear(); st.rerun()
            with c2:
                st.write("🚚 **Cadastrar Fornecedor**")
                with st.form("nf"):
                    n = st.text_input("Nome")
                    t = st.text_input("Tel")
                    if st.form_submit_button("Salvar Fornecedor"):
                        supabase.table("fornecedores").insert({"nome": n, "telefone": t}).execute()
                        st.success("OK"); st.cache_data.clear(); st.rerun()
        with st_cad2:
            st.subheader("📦 Estoque de Materiais Cadastrados")
            if not DB['materiais'].empty:
                busca = st.text_input("🔍 Buscar Material", placeholder="Digite para filtrar (ex: Cimento)")
                df_mat = DB['materiais']
                if busca: df_mat = df_mat[df_mat['nome'].str.contains(busca, case=False, na=False)]
                st.dataframe(df_mat[['id', 'nome', 'unidade', 'preco_ref']], use_container_width=True, hide_index=True)
                st.caption(f"Total de itens: {len(df_mat)}")
            else: st.info("Nenhum material cadastrado ainda.")
            st.markdown("---")
            st.subheader("🚚 Lista de Fornecedores")
            if not DB['fornecedores'].empty: st.dataframe(DB['fornecedores'], use_container_width=True, hide_index=True)
            else: st.info("Nenhum fornecedor cadastrado.")

# 5. HISTORICO
with t5:
    if not custos_f.empty:
        df_edit = custos_f.copy()
        # Garante colunas de texto para evitar KeyError
        if 'subetapa' not in df_edit.columns: df_edit['subetapa'] = ""
        
        # Converte data com segurança
        df_edit['data'] = pd.to_datetime(df_edit['data'], errors='coerce').dt.date
        
        config_colunas = {
            "valor": st.column_config.NumberColumn("Valor Unit.", format="R$ %.2f"),
            "total": st.column_config.NumberColumn("Total", format="R$ %.2f"),
            "qtd": st.column_config.NumberColumn("Qtd", format="%.2f"),
            "data": st.column_config.DateColumn("Data", format="DD/MM/YYYY")
        }
        
        colunas_visiveis = ["data", "descricao", "qtd", "valor", "total", "etapa", "subetapa"]
        colunas_reais = [c for c in colunas_visiveis if c in df_edit.columns]

        if BLOQUEADO:
            st.dataframe(df_edit[colunas_reais], use_container_width=True, hide_index=True, column_config=config_colunas)
        else:
            df_edit.insert(0, "Excluir", False)
            res = st.data_editor(df_edit[["Excluir"] + colunas_reais], hide_index=True, use_container_width=True, column_config=config_colunas)
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
        df_c['dt'] = pd.to_datetime(df_c['data'], errors='coerce')
        df_c = df_c.dropna(subset=['dt'])
        df_c['mes'] = df_c['dt'].dt.strftime('%Y-%m')
        c1, c2 = st.columns(2)
        c1.markdown("### 📅 Gastos Mensais")
        c1.bar_chart(df_c.groupby('mes')['total'].sum())
        c2.markdown("### 🧱 Curva ABC (Top Materiais)")
        top = df_c.groupby('descricao')['total'].sum().sort_values(ascending=False).head(10)
        c2.bar_chart(top)