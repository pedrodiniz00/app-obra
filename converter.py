import json

# --- CONFIGURAÇÃO ---
# Troque pelo nome exato do arquivo que você baixou do Google
nome_do_arquivo = "banded-earth-486602-n1-3929774e6312" 
# --------------------

try:
    with open(nome_do_arquivo, 'r', encoding='utf-8') as f:
        dados = json.load(f)
        
    print("\n--- COPIE A PARTIR DAQUI ---\n")
    print("[gcp_service_account]")
    
    # O segredo: json.dumps formata a string perfeitamente para o TOML
    for chave, valor in dados.items():
        print(f'{chave} = {json.dumps(valor)}')
        
    print("\n--- ATÉ AQUI ---\n")
    
except FileNotFoundError:
    print(f"ERRO: Não encontrei o arquivo '{nome_do_arquivo}'. Verifique o nome!")
    