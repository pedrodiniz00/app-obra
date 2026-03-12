import streamlit as st
import pandas as pd
from datetime import datetime
from supabase import create_client, Client

# --- 1. CONFIGURAÇÃO E CONEXÃO ---
st.set_page_config(page_title="ObraPro | Cronograma Independente", layout="wide", page_icon="📅")

# Substitua pelas suas credenciais reais do Passo 3
URL = "https://lvuqxofjcuehpztwewns.supabase.co"
KEY = "sb_publishable_00qWWZO5j_T52RJFx8TBmg_peOk31Dh"

@st.cache_resource
def init_connection():
    return create_client(URL, KEY)

supabase = init_connection()

# --- 2. ESTILIZAÇÃO (UI) ---
st.markdown("""
    <style>
    .main { background-color: #f4f7f6; }
    .stButton>button { width: 100%; border-radius: 5px; }
    .etapa-card { background-color: white; padding: 20px; border-radius: 12px; border-left: 8px solid #007bff; margin-bottom: 15px; }
    </style>
""", unsafe_allow_html=True)

# --- 3. FUNÇÕES DE BANCO DE DADOS ---
def carregar_obras():
    res = supabase.table("obras").select("*").execute()
    return pd.DataFrame(res.data)

def carregar_cronograma(id_obra):
    res = supabase.table("cronograma").select("*").eq("id_obra", id_obra).execute()
    df = pd.DataFrame(res.data)
    if not df.empty:
        df['pai'] = df['etapa'].apply(lambda x: x.split(' | ')[0] if ' | ' in x else x)
        df['sub'] = df['etapa'].apply(lambda x: x.split(' | ')[1] if ' | ' in x else "")
        return df
    return df

# --- 4. INTERFACE LATERAL ---
with st.sidebar:
    st.title("🏗️ ObraPro")
    st.caption("Gestão de Cronograma Profissional")
    
    df_obras = carregar_obras()
    if not df_obras.empty:
        obra_sel = st.selectbox("Selecione a Obra", df_obras['nome'].tolist())
        id_obra_atual = df_obras[df_obras['nome'] == obra_sel]['id'].iloc[0]
    else:
        st.error("Nenhuma obra encontrada no banco.")
        st.stop()
    
    st.divider()
    menu = st.radio("Navegação", ["📊 Dashboard", "📅 Cronograma Detalhado"])

# --- 5. MÓDULO: DASHBOARD ---
if menu == "📊 Dashboard":
    st.title(f"Dashboard: {obra_sel}")
    c1, c2, c3 = st.columns(3)
    
    df = carregar_cronograma(id_obra_atual)
    if not df.empty:
        prog_medio = df['porcentagem'].mean()
        c1.metric("Progresso Médio", f"{prog_medio:.1f}%")
        c2.metric("Atividades Totais", len(df))
        c3.metric("Status", "Em Andamento", delta="Obra Ativa")
    else:
        st.info("Nenhum dado para exibir no Dashboard.")

# --- 6. MÓDULO: CRONOGRAMA ---
elif menu == "📅 Cronograma Detalhado":
    st.title(f"Planejamento: {obra_sel}")
    
    df = carregar_cronograma(id_obra_atual)
    
    if not df.empty:
        # Ordenação das Etapas Pai
        etapas_pai = sorted(df['pai'].unique(), 
                            key=lambda x: df[df['pai'] == x]['ordem_pai'].iloc[0] if 'ordem_pai' in df.columns else 0)

        for i, pai in enumerate(etapas_pai):
            subset = df[df['pai'] == pai].sort_values('ordem_sub')
            
            # Cálculo de progresso da etapa (Peso Pai)
            peso_pai = subset['planejada_pai'].iloc[0] if 'planejada_pai' in subset.columns else 10
            
            with st.container():
                st.markdown(f"### 📁 {pai} (Peso: {peso_pai}%)")
                
                for _, row in subset.iterrows():
                    with st.expander(f"🔹 {row['sub']} | Status: {row['porcentagem']}%", expanded=False):
                        # Layout de Edição
                        c1, c2, c3 = st.columns([4, 4, 1])
                        
                        # Campos de data e progresso
                        d_ini = datetime.strptime(row['data_inicio'], '%Y-%m-%d').date() if row.get('data_inicio') else datetime.now().date()
                        d_fim = datetime.strptime(row['data_fim'], '%Y-%m-%d').date() if row.get('data_fim') else datetime.now().date()
                        
                        novas_datas = c1.date_input("Prazo", [d_ini, d_fim], format="DD/MM/YYYY", key=f"d_{row['id']}")
                        novo_prog = c2.slider("Executado (%)", 0, 100, int(row['porcentagem']), key=f"p_{row['id']}")
                        
                        # Botão de Salvar
                        if c3.button("💾", key=f"s_{row['id']}"):
                            d_start = novas_datas[0].strftime('%Y-%m-%d') if len(novas_datas) > 0 else None
                            d_end = novas_datas[1].strftime('%Y-%m-%d') if len(novas_datas) > 1 else None
                            
                            supabase.table("cronograma").update({
                                "porcentagem": novo_prog,
                                "data_inicio": d_start,
                                "data_fim": d_end
                            }).eq("id", row['id']).execute()
                            st.cache_data.clear()
                            st.success("Salvo!")
                            st.rerun()

                # Botão para adicionar nova subetapa dentro desta pasta
                with st.popover(f"➕ Nova Atividade em {pai}"):
                    nova_ativ = st.text_input("Nome da Atividade", key=f"new_{i}")
                    if st.button("Criar Atividade", key=f"btn_{i}"):
                        if nova_ativ:
                            supabase.table("cronograma").insert({
                                "id_obra": id_obra_atual,
                                "etapa": f"{pai} | {nova_ativ}",
                                "porcentagem": 0,
                                "planejada_pai": peso_pai
                            }).execute()
                            st.cache_data.clear()
                            st.rerun()
                st.divider()

    # Opção Global: Criar nova pasta
    st.markdown("---")
    with st.popover("📁 Criar Nova Pasta Principal"):
        n_pasta = st.text_input("Ex: Acabamento, Pintura...")
        if st.button("Criar Pasta"):
            if n_pasta:
                supabase.table("cronograma").insert({
                    "id_obra": id_obra_atual,
                    "etapa": f"{n_pasta} | Início",
                    "porcentagem": 0
                }).execute()
                st.cache_data.clear()
                st.rerun()