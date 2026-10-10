import os

# Keep a developer's local .env (which may set FOXPROFILE_API_TOKEN) from turning
# on auth in tests. load_dotenv() never overrides a variable that already exists,
# and this runs before any test module imports src.core.config.
os.environ["FOXPROFILE_API_TOKEN"] = ""
