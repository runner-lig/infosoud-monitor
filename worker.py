# worker.py
import app
from app import get_db_connection, get_now
import datetime
import time

def set_db_status(is_running, progress=0, total=0, mode="Čekám..."):
    """Zapíše aktuální stav workeru do sdílené tabulky v DB."""
    conn = None; db_pool = None
    try:
        conn, db_pool = get_db_connection()
        c = conn.cursor()
        c.execute("""
            UPDATE system_status 
            SET is_running = %s, progress = %s, total = %s, mode = %s, last_update = %s 
            WHERE id = 1
        """, (is_running, progress, total, mode, get_now()))
        conn.commit()
    except Exception as e:
        print(f"Chyba při zápisu stavu do DB: {e}")
    finally:
        if conn and db_pool: db_pool.putconn(conn)

if __name__ == "__main__":
    print("🚀 START: Plánovaná kontrola přes Heroku Scheduler")
    
    # 1. Označíme v DB, že začínáme
    set_db_status(True, 0, 0, "Inicializace...")
    
    try:
        # 2. Spustíme hlavní logiku z app.py
        # Poznámka: monitor_job by nyní měl ideálně volat set_db_status průběžně
        app.monitor_job()
        print("✅ HOTOVO: Kontrola úspěšně dokončena.")
    except Exception as e:
        print(f"❌ KRITICKÁ CHYBA: {e}")
    finally:
        # 3. Označíme v DB, že jsme skončili
        set_db_status(False, 0, 0, "Dokončeno / Spí")
