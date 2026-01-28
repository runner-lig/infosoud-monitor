# worker.py
import app
import os

if __name__ == "__main__":
    print("🚀 Startuji plánovanou kontrolu spisů (headless režim)...")
    try:
        # Spustíme přímo funkci z tvého app.py
        app.monitor_job()
        print("✅ Kontrola úspěšně dokončena.")
    except Exception as e:
        print(f"❌ Došlo k chybě během kontroly: {e}")
