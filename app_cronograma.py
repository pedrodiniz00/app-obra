import streamlit as st
import pandas as pd
from datetime import datetime
from supabase import create_client, Client

# --- 1. CONFIGURAÇÃO DA INTERFACE (UI) ---
st.set_page_config(
    page_title="Cronograma Pro | Gestão de Obras",
    page_icon="📅",
    layout="wide"
)

# Estilo CSS para deixar o app com cara de software profissional
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stMetric { 
        background-color: white; 
        padding: 20px; 
        border-radius: 15px; 
        box-shadow: 0 4px 12px rgba(0,0,0,0.05);
    }
    .etapa-container {
        background-color: white;
        padding: 20px;
        border-radius: 10px;
        margin-bottom: 20px;
        border-left: 6px solid #007bff;
    }
    </style>
""", unsafe_allow_html=True)

# --- 2. CONEXÃO COM O SUPABASE ---
# COLOQUE SUAS CHAVES AQUI:
URL = "SUA_URL_DO_SUPABASE"
KEY = "SUA_CHAVE_ANON_DO_SUPABASE"

@st.cache_resource
def conectar_banco():
    return create_client(URL, KEY)

supabase = conectar_banco()

# --- 3. FUNÇÕES DE BUSCA DE DADOS ---
def listar_obras():
    res = supabase.table("obras").select("id, nome").execute()
    return pd.DataFrame(res.data)

def carregar_cronograma(id_obra):
    res = supabase.table("cronograma").select("*").eq("id_obra", id_obra).execute()
    df = pd.DataFrame(res.data)
    if not df.empty:
        # Tratamento de colunas para evitar erros
        df['pai'] = df['etapa'].apply(lambda x: x.split(' | ')[0] if ' | ' in x else x)
        df['sub'] = df['etapa'].apply(lambda x: x.split(' | ')[1] if ' | ' in x else "")
        return df
    return pd.DataFrame()

# --- 4. BARRA LATERAL (NAVEGAÇÃO) ---
with st.sidebar:
    st.title("🏗️ CronogramaPro")
    st.caption("Versão 1.0 - Aplicativo Independente")
    
    df_obras = listar_obras()
    if not df_obras.empty:
        obra_selecionada = st.selectbox("Selecione a Obra", df_obras['nome'].tolist())
        id_obra_atual = df_obras[df_obras['nome'] == obra_selecionada]['id'].iloc[0]
    else:
        st.warning("Cadastre uma obra no Supabase primeiro.")
        st.stop()

    st.divider()
    menu = st.radio("Menu", ["📊 Dashboard", "📅 Planejamento", "⚙️ Configurações"])

# --- 5. LÓGICA DO DASHBOARD ---
if menu == "📊 Dashboard":
    st.title(f"Painel da Obra: {obra_selecionada}")
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Progresso Total", "45%", "Em dia")
    c2.metric("Etapas Concluídas", "3/8")
    c3.metric("Prazo Restante", "120 dias")

# --- 6. LÓGICA DO CRONOGRAMA (PLANEJAMENTO) ---
elif menu == "📅 Planejamento":
    st.title("Detalhamento do Cronograma")
    
    df = carregar_cronograma(id_obra_atual)
    
    if df.empty:
        st.info("Nenhuma etapa cadastrada. Clique no botão abaixo para criar a primeira.")
    else:
        # Ordenação por Etapa Pai
        etapas_pai = sorted(df['pai'].unique(), 
                            key=lambda x: df[df['pai'] == x]['ordem_pai'].iloc[0] if 'ordem_pai' in df.columns else 0)

        for i, pai in enumerate(etapas_pai):
            subset = df[df['pai'] == pai].sort_values('ordem_sub' if 'ordem_sub' in df.columns else 'sub')
            
            # Cálculo de progresso da pasta
            peso_pai = subset['planejada_pai'].iloc[0] if 'planejada_pai' in subset.columns else 10
            prog_etapa = subset['porcentagem'].mean() # Simplificado para o exemplo

            with st.container():
                st.markdown(f"""
                <div class="etapa-container">
                    <h3>📁 {pai} <span style='float:right; color:#007bff;'>{prog_etapa:.1f}%</span></h3>
                </div>
                """, unsafe_allow_html=True)
                
                with st.expander("Ver atividades", expanded=True):
                    for _, row in subset.iterrows():
                        col1, col2, col3, col4 = st.columns([4, 4, 2, 1])
                        
                        # Nome e Datas
                        col1.text_input("Atividade", row['sub'], key=f"n_{row['id']}")
                        
                        # Datas formato BR
                        d_ini = datetime.strptime(row['data_inicio'], '%Y-%m-%d').date() if row.get('data_inicio') else datetime.now().date()
                        d_fim = datetime.strptime(row['data_fim'], '%Y-%m-%d').date() if row.get('data_fim') else datetime.now().date()
                        col2.date_input("Prazo", [d_ini, d_fim], format="DD/MM/YYYY", key=f"d_{row['id']}")
                        
                        # Execução
                        col3.slider("Execução", 0, 100, int(row['porcentagem']), key=f"e_{row['id']}")
                        
                        if col4.button("💾", key=f"s_{row['id']}"):
                            # Aqui você adiciona a lógica de UPDATE no Supabase
                            st.success("Salvo!")

    st.divider()
    with st.popover("📁 Criar Nova Pasta (Etapa Pai)"):
        nova_pasta = st.text_input("Nome da Etapa (ex: Alvenaria)")
        if st.button("Confirmar"):
            # Lógica de INSERT no Supabase
            st.rerun()

# --- 7. RODAPÉ ---
st.markdown("---")
st.caption("ObraPro - Sistema de Gestão Independente")