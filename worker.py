# worker.py
import app # Tvůj původní soubor

def run_headless_monitor():
    print("--- START AUTOMATICKÉ KONTROLY ---")
    # Zde zavoláme přímo funkci, která stahuje data
    # DŮLEŽITÉ: Funkce monitor_job nesmí obsahovat 'st.' příkazy!
    app.monitor_job() 
    print("--- KONTROLA DOKONČENA ---")

if __name__ == "__main__":
    run_headless_monitor()
