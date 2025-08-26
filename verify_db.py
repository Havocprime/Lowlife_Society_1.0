from src.core.settings import SETTINGS
import sqlite3

print("DB path:", SETTINGS.db_path)
con = sqlite3.connect(SETTINGS.db_path)
cur = con.cursor()
tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")]
print("tables:", tables)
