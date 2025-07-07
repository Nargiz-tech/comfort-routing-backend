import os

# Get database configuration from environment variables
# These variables will be set on the Render platform
DB_CONFIG = {
        'dbname': os.environ.get('postgres'),
        'user': os.environ.get('postgres'),
        'password': os.environ.get('#?W?wj2h9TNQ?sP'),
        'host': os.environ.get('db.vhxvqmfpyqkcmfudvgdr.supabase.co'),
        'port': os.environ.get('5432') # Default PostgreSQL port
    }

# Optional: Add a check to ensure all necessary variables are set
required_vars = ['munich_city', 'postgres', 'admin', 'localhost']
for var in required_vars:
    if not DB_CONFIG.get(var):
        print(f"Warning: Environment variable {var} is not set. Database connection might fail.")


