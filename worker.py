# worker.py
import app
from app import get_db_connection, get_now
import datetime
import time
import sys

def set_db_status(is_running, progress=0, total=0, mode="Čekám..."):
    """Zapíše aktuální stav workeru do sdílené tabulky v DB."""
    conn = None; db_pool = None
    try:
        conn, db_pool = get_db_connection()
        with conn.cursor() as c:
            c.execute("""
                UPDATE system_status 
                SET is_running = %s, progress = %s, total = %s, mode = %s, last_update = %s 
                WHERE id = 1
            """, (is_running, progress, total, mode, get_now()))
            conn.commit()
    except Exception as e:
        print(f"⚠️ Chyba při zápisu stavu do DB: {e}")
    finally:
        if conn and db_pool: 
            db_pool.putconn(conn)

if __name__ == "__main__":
    print(f"🚀 START WORKERU: {get_now().strftime('%d.%m.%Y %H:%M:%S')}")
    
    # 1. Označíme v DB, že začínáme
    set_db_status(True, 0, 0, "Inicializace...")
    
    try:
        # 2. Spustíme hlavní logiku z app.py 
        # !!! KLÍČOVÁ ZMĚNA: Předáváme funkci set_db_status jako hook
        app.monitor_job(status_hook=set_db_status)
        
        print("✅ HOTOVO: Kontrola úspěšně dokončena.")
    except Exception as e:
        print(f"❌ KRITICKÁ CHYBA: {e}")
        # Zapíšeme chybu do stavu, aby to uživatel viděl v UI
        set_db_status(False, 0, 0, f"Chyba: {str(e)[:40]}")
        sys.exit(1)
    finally:
        # 3. Označíme v DB, že jsme skončili (pokud se tak už nestalo uvnitř monitor_job)
        set_db_status(False, 0, 0, "Spí")
        print(f"🏁 KONEC WORKERU: {get_now().strftime('%H:%M:%S')}")
