
import streamlit as st
import psycopg2
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import json
import smtplib
import hashlib
import time
import random  # Pro náhodné pauzy
import datetime
from urllib.parse import urlparse, parse_qs
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from apscheduler.schedulers.background import BackgroundScheduler

# --- KONFIGURACE UI ---
st.set_page_config(page_title="Infosoud Monitor", page_icon="⚖️", layout="wide")

import os  # <--- TOTO JE DŮLEŽITÉ, PŘIDEJTE TO NA ÚPLNÝ ZAČÁTEK SOUBORU K OSTATNÍM IMPORTŮM

# ... (ostatní importy nechte, jak jsou) ...

# --- 🔐 NAČTENÍ TAJNÝCH ÚDAJŮ (SECRETS) ---
# Funkce, která zkusí najít heslo v souboru, a když tam není, koukne do Railway Variables
def get_secret(key):
    # 1. Zkusíme st.secrets (pro lokální běh nebo Streamlit Cloud)
    if key in st.secrets:
        return st.secrets[key]
    # 2. Zkusíme systémové proměnné (pro Railway)
    return os.getenv(key)

try:
    # Načítáme pomocí naší chytré funkce
    DB_URI = get_secret("SUPABASE_DB_URL")
    
    SUPER_ADMIN_USER = get_secret("SUPER_ADMIN_USER")
    SUPER_ADMIN_PASS = get_secret("SUPER_ADMIN_PASS")
    SUPER_ADMIN_EMAIL = get_secret("SUPER_ADMIN_EMAIL")
    
    SMTP_SERVER = "smtp.gmail.com" # Pokud máte Seznam, změňte na smtp.seznam.cz
    SMTP_PORT = 587
    SMTP_EMAIL = get_secret("SMTP_EMAIL")
    SMTP_PASSWORD = get_secret("SMTP_PASSWORD")

    # Kontrola, jestli se to povedlo (jestli není něco None)
    if not DB_URI or not SMTP_EMAIL or not SMTP_PASSWORD:
        st.error("Chybí některá klíčová hesla! Zkontrolujte nastavení Variables na Railway.")
        st.stop()

except Exception as e:
    st.error(f"Chyba při načítání konfigurace: {e}")
    st.stop()

# --- KOMPLETNÍ DATABÁZE SOUDŮ ---
SOUDY_MAPA = {
    "NS": "Nejvyšší soud", "NSJIMBM": "Nejvyšší soud", "NSS": "Nejvyšší správní soud",
    "VSPHAAB": "Vrchní soud v Praze", "VSOL": "Vrchní soud v Olomouci",
    "MSPHAAB": "Městský soud v Praze", 
    "OSPHA01": "Obvodní soud pro Prahu 1",
    "OSPHA02": "Obvodní soud pro Prahu 2",
    "OSPHA03": "Obvodní soud pro Prahu 3",
    "OSPHA04": "Obvodní soud pro Prahu 4",
    "OSPHA05": "Obvodní soud pro Prahu 5",
    "OSPHA06": "Obvodní soud pro Prahu 6",
    "OSPHA07": "Obvodní soud pro Prahu 7",
    "OSPHA08": "Obvodní soud pro Prahu 8",
    "OSPHA09": "Obvodní soud pro Prahu 9",
    "OSPHA10": "Obvodní soud pro Prahu 10",
    "KSSTCAB": "Krajský soud v Praze", "OSBN": "Okresní soud v Benešově", "OSBE": "Okresní soud v Berouně",
    "OSKL": "Okresní soud v Kladně", "OSKO": "Okresní soud v Kolíně", "OSKH": "Okresní soud v Kutné Hoře",
    "OSME": "Okresní soud v Mělníku", "OSMB": "Okresní soud v Mladé Boleslavi", "OSNB": "Okresní soud v Nymburce",
    "OSSTCPY": "Okresní soud Praha-východ", "OSSTCZA": "Okresní soud Praha-západ", "OSPB": "Okresní soud v Příbrami",
    "OSRA": "Okresní soud v Rakovníku", "KSCB": "Krajský soud v Českých Budějovicích", "KSCBTAB": "KS Č. Budějovice - pobočka Tábor",
    "OSCB": "Okresní soud v Českých Budějovicích", "OSCK": "Okresní soud v Českém Krumlově", "OSJH": "Okresní soud v Jindřichově Hradci",
    "OSPE": "Okresní soud v Pelhřimově", "OSPI": "Okresní soud v Písku", "OSPT": "Okresní soud v Prachaticích",
    "OSST": "Okresní soud ve Strakonicích", "OSTA": "Okresní soud v Táboře", "KSPL": "Krajský soud v Plzni",
    "KSPLKV": "KS Plzeň - pobočka Karlovy Vary", "OSDO": "Okresní soud v Domažlicích", "OSCH": "Okresní soud v Chebu",
    "OSKV": "Okresní soud v Karlových Varech", "OSKT": "Okresní soud v Klatovech", "OSPM": "Okresní soud Plzeň-město",
    "OSPJ": "Okresní soud Plzeň-jih", "OSPS": "Okresní soud Plzeň-sever", "OSRO": "Okresní soud v Rokycanech",
    "OSSO": "Okresní soud v Sokolově", "OSTC": "Okresní soud v Tachově", "KSUL": "Krajský soud v Ústí nad Labem",
    "KSULLBC": "KS Ústí n.L. - pobočka Liberec", "OSCL": "Okresní soud v České Lípě", "OSDC": "Okresní soud v Děčíně",
    "OSCV": "Okresní soud v Chomutově", "OSJN": "Okresní soud v Jablonci nad Nisou", "OSLI": "Okresní soud v Liberci",
    "OSLT": "Okresní soud v Litoměřicích", "OSLN": "Okresní soud v Lounech", "OSMO": "Okresní soud v Mostě",
    "OSTP": "Okresní soud v Teplicích", "OSUL": "Okresní soud v Ústí nad Labem", "KSHK": "Krajský soud v Hradci Králové",
    "KSHKPCE": "KS Hradec Králové - pobočka Pardubice", "OSHKB": "Okresní soud v Havlíčkově Brodě", "OSHK": "Okresní soud v Hradci Králové",
    "OSCHR": "Okresní soud v Chrudimi", "OSJC": "Okresní soud v Jičíně", "OSNA": "Okresní soud v Náchodě",
    "OSPA": "Okresní soud v Pardubicích", "OSRK": "Okresní soud v Rychnově nad Kněžnou", "OSSE": "Okresní soud v Semilech",
    "OSTR": "Okresní soud ve Svitavách", "OSTU": "Okresní soud v Trutnově", "OSUO": "Okresní soud v Ústí nad Orlicí",
    "KSBR": "Krajský soud v Brně", "KSBRJI": "KS Brno - pobočka Jihlava", "KSBRZL": "KS Brno - pobočka Zlín",
    "MSBR": "Městský soud v Brně", "OSBK": "Okresní soud v Blansku", "OSBO": "Okresní soud Brno-venkov",
    "OSBV": "Okresní soud v Břeclavi", "OSHO": "Okresní soud v Hodoníně", "OSJI": "Okresní soud v Jihlavě",
    "OSKM": "Okresní soud v Kroměříži", "OSPV": "Okresní soud v Prostějově", "OSTRB": "Okresní soud v Třebíči",
    "OSUH": "Okresní soud v Uherském Hradišti", "OSVY": "Okresní soud ve Vyškově", "OSZL": "Okresní soud ve Zlíně",
    "OSZN": "Okresní soud ve Znojmě", "OSZR": "Okresní soud ve Žďáru nad Sázavou", "KSOS": "Krajský soud v Ostravě",
    "KSOSOL": "KS Ostrava - pobočka Olomouc", "OSBR": "Okresní soud v Bruntále", "OSFM": "Okresní soud ve Frýdku-Místku",
    "OSJE": "Okresní soud v Jeseníku", "OSKA": "Okresní soud v Karviné", "OSNJ": "Okresní soud v Novém Jičíně",
    "OSOL": "Okresní soud v Olomouci", "OSOP": "Okresní soud v Opavě", "OSOS": "Okresní soud v Ostravě",
    "OSPR": "Okresní soud v Přerově", "OSSU": "Okresní soud v Šumperku", "OSVS": "Okresní soud ve Vsetíně"
}

# -------------------------------------------------------------------------
# 1. DATABÁZE (PostgreSQL / Supabase)
# -------------------------------------------------------------------------

def get_connection():
    """Vytvoří připojení k Supabase databázi."""
    return psycopg2.connect(DB_URI)

def make_hash(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_hash(password, hashed_text):
    if make_hash(password) == hashed_text:
        return True
    return False

@st.cache_resource
def init_db():
    """Inicializace tabulek v PostgreSQL."""
    conn = get_connection()
    c = conn.cursor()
    
    # Tabulka případů (používáme SERIAL místo AUTOINCREMENT a BOOLEAN místo 0/1)
    c.execute('''CREATE TABLE IF NOT EXISTS pripady
                 (id SERIAL PRIMARY KEY,
                  oznaceni TEXT,
                  url TEXT,
                  params_json TEXT,
                  pocet_udalosti INTEGER,
                  posledni_udalost TEXT,
                  ma_zmenu BOOLEAN,
                  posledni_kontrola TIMESTAMP,
                  realny_nazev_soudu TEXT)''')
    
    # Tabulka uživatelů
    c.execute('''CREATE TABLE IF NOT EXISTS uzivatele
                 (id SERIAL PRIMARY KEY,
                  username TEXT UNIQUE,
                  password TEXT,
                  email TEXT,
                  role TEXT)''')

    # Historie
    c.execute('''CREATE TABLE IF NOT EXISTS historie
                 (id SERIAL PRIMARY KEY,
                  datum TIMESTAMP,
                  uzivatel TEXT,
                  akce TEXT,
                  popis TEXT)''')
                 
    conn.commit()
    conn.close()

# Zavoláme inicializaci při startu (nevadí, pokud tabulky už existují)
try:
    init_db()
except Exception as e:
    st.error(f"Chyba při připojení k databázi: {e}")
    st.stop()

# --- SPRÁVA UŽIVATELŮ ---

def create_user(username, password, email, role):
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute("INSERT INTO uzivatele (username, password, email, role) VALUES (%s, %s, %s, %s)", 
                  (username, make_hash(password), email, role))
        conn.commit()
        conn.close()
        log_do_historie("Vytvoření uživatele", f"Vytvořen uživatel '{username}' ({role})")
        return True
    except psycopg2.IntegrityError:
        return False
    except Exception as e:
        print(f"Chyba DB: {e}")
        return False

def delete_user(username):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM uzivatele WHERE username=%s", (username,))
    conn.commit()
    conn.close()
    log_do_historie("Smazání uživatele", f"Smazán uživatel '{username}'")

def get_all_users():
    conn = get_connection()
    # Pandas read_sql vyžaduje connection object
    df = pd.read_sql_query("SELECT username, email, role FROM uzivatele", conn)
    conn.close()
    return df

def verify_login(username, password):
    if username == SUPER_ADMIN_USER and password == SUPER_ADMIN_PASS:
        return "Super Admin"
    
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT password, role FROM uzivatele WHERE username=%s", (username,))
    data = c.fetchone()
    conn.close()
    
    if data:
        stored_hash, role = data
        if check_hash(password, stored_hash):
            return role
    return None

# --- LOGOVÁNÍ ---

def log_do_historie(akce, popis):
    if 'current_user' in st.session_state:
        user = st.session_state['current_user']
    else:
        user = "🤖 Systém (Robot)"
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute("INSERT INTO historie (datum, uzivatel, akce, popis) VALUES (%s, %s, %s, %s)", 
                  (datetime.datetime.now(), user, akce, popis))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Chyba logování: {e}")

def get_historie(dny=14):
    datum_limit = datetime.datetime.now() - datetime.timedelta(days=dny)
    conn = get_connection()
    df = pd.read_sql_query("SELECT datum, uzivatel, akce, popis FROM historie WHERE datum > %s ORDER BY datum DESC", 
                             conn, params=(datum_limit,))
    conn.close()
    return df

# -------------------------------------------------------------------------
# 2. LOGIKA ODESÍLÁNÍ
# -------------------------------------------------------------------------

def odeslat_email_notifikaci(nazev, udalost, znacka):
    if "novy.email" in SMTP_EMAIL: return

    # 1. Získat emaily z DB
    try:
        conn = get_connection()
        df_users = pd.read_sql_query("SELECT email FROM uzivatele WHERE email IS NOT NULL AND email != ''", conn)
        conn.close()
        prijemci = df_users['email'].tolist()
    except:
        prijemci = []
    
    # 2. Přidat Super Admina
    if SUPER_ADMIN_EMAIL and "@" in SUPER_ADMIN_EMAIL:
        prijemci.append(SUPER_ADMIN_EMAIL)
    
    prijemci = list(set(prijemci)) 

    if not prijemci: return

    msg = MIMEMultipart()
    msg['From'] = SMTP_EMAIL
    msg['Subject'] = f"🚨 Změna ve spisu: {nazev}"
    msg.attach(MIMEText(f"Novinka u {nazev} ({znacka}):\n\n{udalost}\n\n--\nInfosoud Monitor", 'plain'))

    try:
        s = smtplib.SMTP(SMTP_SERVER, int(SMTP_PORT))
        s.starttls(); s.login(SMTP_EMAIL, SMTP_PASSWORD)
        for p in prijemci:
            del msg['To']; msg['To'] = p; s.sendmail(SMTP_EMAIL, p, msg.as_string())
        s.quit()
        log_do_historie("Odeslání notifikace", f"Odesláno na {len(prijemci)} adres.")
    except Exception as e: print(f"Chyba emailu: {e}")

# -------------------------------------------------------------------------
# 3. PARSOVÁNÍ A SCRAPING
# -------------------------------------------------------------------------

def parsuj_url(url):
    try:
        p = parse_qs(urlparse(url).query)
        soud = p.get('org', [''])[0] or p.get('krajOrg', [None])[0]
        typ = p.get('typSoudu', ['os'])[0]
        if not soud and typ == 'ns': soud = 'NS'
        if soud and soud.upper().startswith(('KS','MS')): typ = 'ks'
        return {"typ": typ, "soud": soud, "senat": p.get('cisloSenatu',[None])[0], 
                "druh": p.get('druhVec',[None])[0].upper() if p.get('druhVec') else None, 
                "cislo": p.get('bcVec',[p.get('cislo',[None])[0]])[0], "rocnik": p.get('rocnik',[None])[0]}
    except: return None

# --- PŘIDAT TENTO SEZNAM NAD FUNKCI NEBO DO NI ---
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0"
]

def stahni_data_z_infosoudu(params):
    url = "https://infosoud.justice.cz/InfoSoud/public/search.do"
    
    # Parametry pro Infosoud
    req_params = {
        'type': 'spzn', 'typSoudu': params['typ'], 'krajOrg': 'VSECHNY_KRAJE',
        'org': params['soud'], 'cisloSenatu': params['senat'], 'druhVec': params['druh'],
        'bcVec': params['cislo'], 'rocnik': params['rocnik'], 'spamQuestion': '23', 'agendaNc': 'CIVIL'
    }
    
    # --- MASKOVÁNÍ (Simulace prohlížeče) ---
    # Vybereme náhodný prohlížeč
    agent = random.choice(USER_AGENTS)
    
    # Nastavíme hlavičky tak, jak je posílá opravdový Chrome/Firefox
    headers = {
        "User-Agent": agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "cs,en-US;q=0.7,en;q=0.3",
        "Referer": "https://infosoud.justice.cz/InfoSoud/public/search.do",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1"
    }
    
    try:
        # Použijeme headers v dotazu
        r = requests.get(url, params=req_params, headers=headers, timeout=10)
        
        # Kontrola, zda nás nepřesměrovali na Captchu (ochranu)
        if "recaptcha" in r.text.lower() or "spam" in r.text.lower():
            print("⚠️ POZOR: Infosoud vrátil podezření na robota (Captcha).")
            return None

        soup = BeautifulSoup(r.text, 'html.parser')
        
        if "Řízení nebylo nalezeno" in soup.text: 
            return None
            
        udalosti = []
        for row in soup.find_all('tr'):
            cols = row.find_all('td')
            # Hledáme řádky, kde druhý sloupec je datum (DD.MM.RRRR)
            if len(cols) >= 2 and re.match(r'^\d{2}\.\d{2}\.\d{4}$', cols[1].get_text(strip=True)):
                text = cols[0].find('a').get_text(strip=True) if cols[0].find('a') else cols[0].get_text(strip=True)
                datum = cols[1].get_text(strip=True)
                udalosti.append(f"{datum} - {text}")
        return udalosti
        
    except Exception as e:
        print(f"Chyba při stahování: {e}")
        return None

def pridej_pripad(url, oznaceni):
    p = parsuj_url(url)
    if not p or not p['soud']: return False, "Neplatná URL."
    data = stahni_data_z_infosoudu(p)
    if data is None: return False, "Spis nenalezen."
    
    spis_zn = f"{p.get('senat')} {p.get('druh')} {p.get('cislo')}/{p.get('rocnik')}"
    
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO pripady (oznaceni, url, params_json, pocet_udalosti, posledni_udalost, ma_zmenu, posledni_kontrola) VALUES (%s, %s, %s, %s, %s, %s, %s)",
              (oznaceni, url, json.dumps(p), len(data), data[-1] if data else "", False, datetime.datetime.now()))
    conn.commit()
    conn.close()
    
    log_do_historie("Přidání spisu", f"Přidán spis: {oznaceni} ({spis_zn})")
    return True, "OK"

def smaz_pripad(cid):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT oznaceni FROM pripady WHERE id=%s", (cid,))
    res = c.fetchone()
    nazev = res[0] if res else "Neznámý"
    c.execute("DELETE FROM pripady WHERE id=%s", (cid,))
    conn.commit()
    conn.close()
    log_do_historie("Smazání spisu", f"Uživatel smazal spis: {nazev}")

def resetuj_upozorneni(cid):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT oznaceni FROM pripady WHERE id=%s", (cid,))
    res = c.fetchone()
    nazev = res[0] if res else "Neznámý"
    c.execute("UPDATE pripady SET ma_zmenu = %s WHERE id=%s", (False, cid))
    conn.commit()
    conn.close()
    log_do_historie("Potvrzení změny", f"Viděl jsem: {nazev}")

def resetuj_vsechna_upozorneni():
    conn = get_connection()
    c = conn.cursor()
    # Tento SQL příkaz najde všechny řádky, kde je změna, a nastaví je na False
    c.execute("UPDATE pripady SET ma_zmenu = %s WHERE ma_zmenu = %s", (False, True))
    conn.commit()
    conn.close()
    log_do_historie("Hromadné potvrzení", "Uživatel označil všechny změny jako viděné.")

def prejmenuj_pripad(cid, novy_nazev):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE pripady SET oznaceni = %s WHERE id = %s", (novy_nazev, cid))
    conn.commit()
    conn.close()
    log_do_historie("Přejmenování", f"Spis ID {cid} přejmenován na '{novy_nazev}'")

# --- SCHEDULER (POZADÍ) ---
@st.cache_resource
def start_scheduler():
    scheduler = BackgroundScheduler()
    # Interval 60 minut je OK
    scheduler.add_job(monitor_job, 'interval', minutes=60)
    scheduler.start()
    return scheduler

def monitor_job(status_placeholder=None, progress_bar=None):
    # Vytvoříme nové spojení pro vlákno
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT id, params_json, pocet_udalosti, oznaceni FROM pripady")
        rows = c.fetchall()
    except Exception as e:
        print(f"Chyba připojení scheduleru: {e}")
        return

    celkem = len(rows)
    print(f"--- KONTROLA ({datetime.datetime.now()}) - Počet spisů: {celkem} ---")
    
    for i, row in enumerate(rows):
        # --- AKTUALIZACE PRŮBĚHU (NOVÉ) ---
        if status_placeholder and progress_bar:
            aktualni_cislo = i + 1
            procenta = int((aktualni_cislo / celkem) * 100)
            status_placeholder.write(f"⏳ Kontroluji spis **{aktualni_cislo} / {celkem}**: _{row[3]}_")
            progress_bar.progress(procenta)
        # ----------------------------------

        cid, params_str, old_cnt, name = row
        p = json.loads(params_str)
        
        # 1. Zpomalovač proti zablokování
        time.sleep(random.uniform(0.1, 0.8))
        
        new_data = stahni_data_z_infosoudu(p)
        
        if new_data is not None:
            now = datetime.datetime.now()
            
            if len(new_data) > old_cnt:
                # Změna nalezena!
                c.execute("UPDATE pripady SET pocet_udalosti=%s, posledni_udalost=%s, ma_zmenu=%s, posledni_kontrola=%s WHERE id=%s", 
                          (len(new_data), new_data[-1], True, now, cid))
                conn.commit()
                
                try:
                    c.execute("INSERT INTO historie (datum, uzivatel, akce, popis) VALUES (%s, %s, %s, %s)",
                              (now, "🤖 Systém (Robot)", "Nová událost", f"Změna u {name}"))
                    conn.commit()
                except: pass
                
                spis_zn = f"{p.get('senat')} {p.get('druh')} {p.get('cislo')}/{p.get('rocnik')}"
                odeslat_email_notifikaci(name, new_data[-1], spis_zn)
                
            else:
                # Beze změny
                c.execute("UPDATE pripady SET posledni_kontrola=%s WHERE id=%s", (now, cid))
                conn.commit()
    
    conn.close()

start_scheduler()

# -------------------------------------------------------------------------
# 4. FRONTEND
# -------------------------------------------------------------------------

if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
    st.session_state['current_user'] = None
    st.session_state['user_role'] = None

if not st.session_state['logged_in']:
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.title("🔐 Infosoud Monitor")
        with st.form("login_form"):
            username = st.text_input("Uživatelské jméno")
            password = st.text_input("Heslo", type="password")
            submitted = st.form_submit_button("Přihlásit se")
            
            if submitted:
                role = verify_login(username, password)
                if role:
                    st.session_state['logged_in'] = True
                    st.session_state['current_user'] = username
                    st.session_state['user_role'] = role
                    st.success(f"Vítejte, {username} ({role})")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("Chybné jméno nebo heslo.")
    st.stop()

# --- HLAVNÍ APLIKACE ---

st.title("⚖️ Monitor Soudních Spisů")

with st.sidebar:
    st.write(f"👤 **{st.session_state['current_user']}**")
    st.caption(f"Role: {st.session_state['user_role']}")
    if st.button("Odhlásit se"):
        st.session_state['logged_in'] = False
        st.rerun()
    st.markdown("---")

menu_options = ["📊 Přehled kauz", "📜 Auditní historie"]
if st.session_state['user_role'] in ["Super Admin", "Administrátor"]:
    menu_options.append("👥 Správa uživatelů")

selected_page = st.sidebar.radio("Menu", menu_options)
st.sidebar.markdown("---")

# -------------------------------------------------------------------------
# STRÁNKA: SPRÁVA UŽIVATELŮ
# -------------------------------------------------------------------------
if selected_page == "👥 Správa uživatelů":
    st.header("👥 Správa uživatelů")
    current_role = st.session_state['user_role']
    
    with st.expander("➕ Vytvořit nového uživatele", expanded=True):
        c1, c2, c3, c4 = st.columns([2,2,2,1])
        new_user = c1.text_input("Jméno")
        new_pass = c2.text_input("Heslo", type="password")
        new_email = c3.text_input("E-mail pro notifikace")
        
        roles_available = ["Uživatel"]
        if current_role == "Super Admin": roles_available.append("Administrátor")
        new_role = c1.selectbox("Role", roles_available)
        
        if c4.button("Vytvořit"):
            if new_user and new_pass and new_email:
                if create_user(new_user, new_pass, new_email, new_role):
                    st.success(f"Uživatel {new_user} vytvořen.")
                    time.sleep(1); st.rerun()
                else: st.error("Uživatel již existuje.")
            else: st.warning("Vyplňte jméno, heslo i e-mail.")

    st.subheader("Seznam uživatelů")
    users_df = get_all_users()
    if not users_df.empty:
        for index, row in users_df.iterrows():
            if row['username'] == SUPER_ADMIN_USER: continue
            if current_role == "Administrátor" and row['role'] == "Administrátor": continue

            with st.container(border=True):
                c_info, c_del = st.columns([5, 1])
                c_info.markdown(f"**{row['username']}** `({row['role']})` - 📧 {row['email']}")
                can_delete = False
                if current_role == "Super Admin": can_delete = True
                elif current_role == "Administrátor" and row['role'] == "Uživatel": can_delete = True
                
                if can_delete:
                    if c_del.button("Smazat", key=f"del_user_{row['username']}"):
                        delete_user(row['username']); st.rerun()

# -------------------------------------------------------------------------
# STRÁNKA: PŘEHLED KAUZ
# -------------------------------------------------------------------------
elif selected_page == "📊 Přehled kauz":
    
    # --- 1. FUNKCE PRO NAČÍTÁNÍ DAT S PAMĚTÍ ---
    @st.cache_data(ttl=300)
    def get_pripady_data():
        conn = get_connection()
        df_result = pd.read_sql_query("SELECT * FROM pripady ORDER BY posledni_kontrola DESC", conn)
        conn.close()
        return df_result

    # --- 2. SIDEBAR ---
    with st.sidebar:
        st.header("➕ Přidat nový spis")
        
        def zpracuj_pridani():
            url = st.session_state.input_url
            nazev = st.session_state.input_nazev
            ok, msg = pridej_pripad(url, nazev)
            if ok:
                st.session_state['vysledek_akce'] = ("success", msg)
                st.session_state.input_url = ""
                st.session_state.input_nazev = ""
                st.cache_data.clear()
            else:
                st.session_state['vysledek_akce'] = ("error", msg)

        st.text_input("Název kauzy", key="input_nazev")
        st.text_input("URL z Infosoudu", key="input_url")
        st.button("Sledovat případ", on_click=zpracuj_pridani)
        
        if 'vysledek_akce' in st.session_state:
            typ, text = st.session_state['vysledek_akce']
            if typ == 'success': st.success(text)
            else: st.error(text)
            del st.session_state['vysledek_akce']
        
        st.divider()
        if st.button("🔄 Ruční kontrola"):
            st.write("---")
            status_text = st.empty()
            my_bar = st.progress(0)
            monitor_job(status_placeholder=status_text, progress_bar=my_bar)
            st.cache_data.clear() 
            status_text.success("✅ Hotovo! Vše zkontrolováno.")
            my_bar.progress(100)
            time.sleep(2)
            st.rerun()
            
        st.divider()
        if st.button("🧪 SIMULACE ZMĚNY + E-MAIL"):
             conn = get_connection()
             try:
                 df_test = pd.read_sql_query("SELECT * FROM pripady ORDER BY id ASC LIMIT 2", conn)
                 if not df_test.empty:
                     c = conn.cursor()
                     ids = tuple(df_test['id'].tolist())
                     if len(ids) == 1: ids = f"({ids[0]})"
                     c.execute(f"UPDATE pripady SET ma_zmenu=TRUE WHERE id IN {ids}")
                     conn.commit()
                     c.close()
                     st.toast("Odesílám notifikace...")
                     log_do_historie("Simulace", "Spuštěna simulace změny")
                     for i, row in df_test.iterrows():
                         try: p=json.loads(row['params_json']); znacka=f"{p.get('senat')} {p.get('druh')} {p.get('cislo')}/{p.get('rocnik')}"
                         except: znacka="Test"
                         odeslat_email_notifikaci(row['oznaceni'], "🔔 TESTOVACÍ SIMULACE ZMĚNY", znacka)
                     st.cache_data.clear()
                     st.success("Hotovo."); time.sleep(2); st.rerun()
                 else: st.warning("Žádné spisy.")
             finally:
                 conn.close()

    # --- 3. HLAVNÍ VÝPIS KAUZ ---
    df = get_pripady_data()
    
    if df.empty:
        st.info("Zatím nesledujete žádné spisy. Přidejte první vlevo.")
    else:
        df_zmeny = df[df['ma_zmenu'] == True]
        df_ostatni = df[df['ma_zmenu'] == False]

        # Callback funkce
        def akce_videl_jsem(id_spisu):
            resetuj_upozorneni(id_spisu)
            st.cache_data.clear() 

        def akce_smazat(id_spisu):
            smaz_pripad(id_spisu)
            st.cache_data.clear()
            
        def akce_videl_jsem_vse():
            resetuj_vsechna_upozorneni()
            st.cache_data.clear()

        # --- A) ČERVENÁ SEKCE (ZMĚNY) ---
        if not df_zmeny.empty:
            col_head, col_btn = st.columns([3, 1])
            with col_head: st.subheader("🚨 Případy se změnou ve spise")
            with col_btn: st.button("👁️ Viděl jsem vše", on_click=akce_videl_jsem_vse, type="primary", use_container_width=True)

            for index, row in df_zmeny.iterrows():
                try:
                    p = json.loads(row['params_json'])
                    spisova_znacka = f"{p.get('senat')} {p.get('druh')} {p.get('cislo')}/{p.get('rocnik')}"
                    kod_soudu = p.get('soud')
                    nazev_soudu = SOUDY_MAPA.get(kod_soudu, kod_soudu)
                    formatted_time = pd.to_datetime(row['posledni_kontrola']).strftime("%d. %m. %Y %H:%M")
                except:
                    spisova_znacka = "?"; nazev_soudu = "?"; formatted_time = ""

                with st.container(border=True):
                    c1, c2, c3, c4 = st.columns([2, 3, 4, 1])
                    with c1:
                        st.markdown(f"### {row['oznaceni']}")
                        st.error("🚨 **NOVÁ UDÁLOST**") 
                    with c2:
                        st.markdown(f"📂 **{spisova_znacka}**")
                        st.markdown(f"🏛️ {nazev_soudu}")
                    with c3:
                        st.write(f"📅 **{row['posledni_udalost']}**")
                        st.caption(f"Kontrolováno: {formatted_time}")
                    with c4:
                        # Tlačítka akcí
                        st.link_button("Otevřít", row['url'])
                        
                        # NOVÉ: Tlačítko EDITOVAT (vyskakovací okénko)
                        with st.popover("✏️", help="Upravit název"):
                            novy_nazev = st.text_input("Název kauzy", value=row['oznaceni'], key=f"edit_red_{row['id']}")
                            if st.button("Uložit", key=f"save_red_{row['id']}"):
                                prejmenuj_pripad(row['id'], novy_nazev)
                                st.cache_data.clear()
                                st.rerun()

                        st.button("👁️ Viděl", key=f"seen_{row['id']}", on_click=akce_videl_jsem, args=(row['id'],))
                        st.button("🗑️", key=f"del_{row['id']}", help="Smazat", on_click=akce_smazat, args=(row['id'],))

        # --- B) ZELENÁ SEKCE (BEZ ZMĚN) ---
        if not df_ostatni.empty:
            if not df_zmeny.empty: st.markdown("---") 
            st.subheader("✅ Případy beze změn")
            for index, row in df_ostatni.iterrows():
                try:
                    p = json.loads(row['params_json'])
                    spisova_znacka = f"{p.get('senat')} {p.get('druh')} {p.get('cislo')}/{p.get('rocnik')}"
                    kod_soudu = p.get('soud')
                    nazev_soudu = SOUDY_MAPA.get(kod_soudu, kod_soudu)
                    formatted_time = pd.to_datetime(row['posledni_kontrola']).strftime("%d. %m. %Y %H:%M")
                except:
                    spisova_znacka = "?"; nazev_soudu = "?"; formatted_time = ""

                with st.container(border=True):
                    c1, c2, c3, c4 = st.columns([2, 3, 4, 1])
                    with c1:
                        st.markdown(f"**{row['oznaceni']}**")
                        st.caption("✅ Bez změn")
                    with c2:
                        st.markdown(f"📂 **{spisova_znacka}**")
                        st.caption(f"🏛️ {nazev_soudu}")
                    with c3:
                        st.write(f"📅 **{row['posledni_udalost']}**")
                        st.caption(f"Kontrolováno: {formatted_time}")
                    with c4:
                        st.link_button("Otevřít", row['url'])
                        
                        # NOVÉ: Tlačítko EDITOVAT (vyskakovací okénko)
                        with st.popover("✏️", help="Upravit název"):
                            novy_nazev = st.text_input("Název kauzy", value=row['oznaceni'], key=f"edit_green_{row['id']}")
                            if st.button("Uložit", key=f"save_green_{row['id']}"):
                                prejmenuj_pripad(row['id'], novy_nazev)
                                st.cache_data.clear()
                                st.rerun()
                                
                        st.button("🗑️", key=f"del_{row['id']}", help="Smazat", on_click=akce_smazat, args=(row['id'],))

# -------------------------------------------------------------------------
# STRÁNKA: AUDITNÍ HISTORIE
# -------------------------------------------------------------------------
elif selected_page == "📜 Auditní historie":
    st.header("📜 Kdo co dělal")
    df_h = get_historie()
    if not df_h.empty:
        df_h['datum'] = pd.to_datetime(df_h['datum']).dt.strftime("%d.%m.%Y %H:%M")
        df_h.columns = ["Kdy", "Kdo", "Co se stalo", "Detail"]
        st.dataframe(df_h, use_container_width=True, hide_index=True)
    else: st.info("Prázdno.")
