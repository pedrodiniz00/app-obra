import os

# Conteúdo do arquivo de senhas
conteudo = """
[acesso]
senha_admin = "1234"

[supabase]
url = "COLE_SUA_URL_DO_SUPABASE_AQUI"
key = "COLE_SUA_KEY_ANON_PUBLIC_AQUI"
"""

# 1. Cria a pasta .streamlit (se não existir)
pasta = ".streamlit"
if not os.path.exists(pasta):
    os.makedirs(pasta)
    print(f"✅ Pasta '{pasta}' criada com sucesso!")
else:
    print(f"ℹ️ Pasta '{pasta}' já existia.")

# 2. Cria o arquivo secrets.toml dentro dela
caminho_arquivo = os.path.join(pasta, "secrets.toml")
with open(caminho_arquivo, "w", encoding="utf-8") as f:
    f.write(conteudo)

print(f"✅ Arquivo '{caminho_arquivo}' criado!")
print("⚠️ AGORA ABRA ESSE ARQUIVO E COLE SUAS CHAVES DO SUPABASE!")