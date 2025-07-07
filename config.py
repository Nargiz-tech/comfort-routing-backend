import os

DB_CONFIG = {
    'dbname': os.environ.get('DB_NAME'),
    'user': os.environ.get('DB_USER'),
    'password': os.environ.get('DB_PASSWORD'), # <-- Пароль читается из переменной окружения
    'host': os.environ.get('DB_HOST'),
    'port': os.environ.get('DB_PORT', '5432')
}

# Optional: Add a check to ensure all necessary variables are set
required_vars = ['DB_NAME', 'DB_USER', 'DB_PASSWORD', 'DB_HOST']
for var in required_vars:
    if not DB_CONFIG.get(var):
        print(f"Warning: Environment variable {var} is not set. Database connection might fail.")
