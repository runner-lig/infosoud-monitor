import streamlit as st
import psycopg2
from psycopg2 import pool
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import json
import smtplib
import hashlib
import time
import random
import datetime
import os
import math
from urllib.parse import urlparse, parse_qs
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from apscheduler.schedulers.background import BackgroundScheduler
import extra_streamlit_components as stx
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- KONFIGURACE UI ---
st.set_page_config(page_title="Infosoud Monitor", page_icon="⚖️", layout="wide")

# --- 🔄 GLOBÁLNÍ STAV SCHEDULERU ---
if not hasattr(st, "monitor_status"):
    st.monitor_status = {
        "running": False,
        "progress": 0,
        "total": 0,
        "mode": "Neznámý", # Zda běží denní nebo noční
        "start_time": None,
        "last_finished": None
    }

# --- 🔐 NAČTENÍ TAJNÝCH ÚDAJŮ (SECRETS) ---
def get_secret(key):
    value = os.getenv(key)
    if value is not None:
        return value
    try:
        if hasattr(st, "secrets") and key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return None

try:
    DB_URI = get_secret("SUPABASE_DB_URL")
    SUPER_ADMIN_USER = get_secret("SUPER_ADMIN_USER")
    SUPER_ADMIN_PASS = get_secret("SUPER_ADMIN_PASS")
    SUPER_ADMIN_EMAIL = get_secret("SUPER_ADMIN_EMAIL")
    
    SMTP_SERVER = "smtp.gmail.com"
    SMTP_PORT = 587
    SMTP_EMAIL = get_secret("SMTP_EMAIL")
    SMTP_PASSWORD = get_secret("SMTP_PASSWORD")

    if not DB_URI or not SMTP_EMAIL:
        st.error("Chybí klíčová nastavení (DB_URI nebo EMAIL). Zkontrolujte Variables.")
        st.stop()

except Exception as e:
    st.error(f"Kritická chyba konfigurace: {e}")
    st.stop()

# --- 🏗️ DATABÁZOVÝ POOL ---
@st.cache_resource
def init_connection_pool():
    try:
        return psycopg2.pool.SimpleConnectionPool(1, 10, dsn=DB_URI)
    except Exception as e:
        st.error(f"Nepodařilo se vytvořit DB Pool: {e}")
        return None

def get_db_connection():
    db_pool = init_connection_pool()
    if db_pool:
        return db_pool.getconn(), db_pool
    else:
        raise Exception("DB Pool není inicializován.")

# --- 🍪 SPRÁVCE COOKIES ---
def get_cookie_manager():
    return stx.CookieManager(key="cookie_mgr")

cookie_manager = get_cookie_manager()

# --- KOMPLETNÍ DATABÁZE SOUDŮ ---
SOUDY_MAPA = {
    "NS": "Nejvyšší soud", "NSJIMBM": "Nejvyšší soud", "NSS": "Nejvyšší správní soud",
    "VSPHAAB": "Vrchní soud v Praze", "VSOL": "Vrchní soud v Olomouci",
    "MSPHAAB": "Městský soud v Praze", 
    "OSPHA01": "Obvodní soud pro Prahu 1", "OSPHA02": "Obvodní soud pro Prahu 2",
    "OSPHA03": "Obvodní soud pro Prahu 3", "OSPHA04": "Obvodní soud pro Prahu 4",
    "OSPHA05": "Obvodní soud pro Prahu 5", "OSPHA06": "Obvodní soud pro Prahu 6",
    "OSPHA07": "Obvodní soud pro Prahu 7", "OSPHA08": "Obvodní soud pro Prahu 8",
    "OSPHA09": "Obvodní soud pro Prahu 9", "OSPHA10": "Obvodní soud pro Prahu 10",
    "KSSTCAB": "Krajský soud v Praze", "OSSTCBN": "Okresní soud v Benešově", "OSBE": "Okresní soud v Berouně",
    "OSSTCKL": "Okresní soud v Kladně", "OSSTCKO": "Okresní soud v Kolíně", "OSKH": "Okresní soud v Kutné Hoře",
    "OSME": "Okresní soud v Mělníku", "OSSTCMB": "Okresní soud v Mladé Boleslavi", "OSSTCNB": "Okresní soud v Nymburce",
    "OSSTCPY": "Okresní soud Praha-východ", "OSSTCPZ": "Okresní soud Praha-západ", "OSPB": "Okresní soud v Příbrami",
    "OSSTCRA": "Okresní soud v Rakovníku", "KSJICCB": "Krajský soud v Českých Budějovicích", "KSCBTAB": "KS Č. Budějovice - pobočka Tábor",
    "OSJICCB": "Okresní soud v Českých Budějovicích", "OSCK": "Okresní soud v Českém Krumlově", "OSJH": "Okresní soud v Jindřichově Hradci",
    "OSJICPE": "Okresní soud v Pelhřimově", "OSJICPI": "Okresní soud v Písku", "OSPT": "Okresní soud v Prachaticích",
    "OSST": "Okresní soud ve Strakonicích", "OSJICTA": "Okresní soud v Táboře", "KSZPCPM": "Krajský soud Plzeň",
    "KSPLKV": "KS Plzeň - pobočka Karlovy Vary", "OSZPCDO": "Okresní soud v Domažlicích", "OSZPCCH": "Okresní soud v Chebu",
    "OSKV": "Okresní soud v Karlových Varech", "OSZPCKV": "Okresní soud v Klatovech", "OSZPCPM": "Okresní soud Plzeň-město",
    "OSPJ": "Okresní soud Plzeň-jih", "OSZPCPS": "Okresní soud Plzeň-sever", "OSZPCRO": "Okresní soud v Rokycanech",
    "OSZPCSO": "Okresní soud v Sokolově", "OSZPCTC": "Okresní soud v Tachově", "KSSCEUL": "Krajský soud v Ústí nad Labem",
    "KSULLBC": "KS Ústí n.L. - pobočka Liberec", "OSCL": "Okresní soud v České Lípě", "OSSCEDC": "Okresní soud v Děčíně",
    "OSSCECV": "Okresní soud v Chomutově", "OSSCEJN": "Okresní soud v Jablonci nad Nisou", "OSSCELB": "Okresní soud v Liberci",
    "OSLT": "Okresní soud v Litoměřicích", "OSSCELN": "Okresní soud v Lounech", "OSSCEMO": "Okresní soud v Mostě",
    "OSSCETP": "Okresní soud v Teplicích", "OSSCEUL": "Okresní soud v Ústí nad Labem", "KSVYCHK": "Krajský soud v Hradci Králové",
    "KSHKPCE": "KS Hradec Králové - pobočka Pardubice", "OSVYCHB": "Okresní soud v Havlíčkově Brodě", "OSVYCHK": "Okresní soud v Hradci Králové",
    "OSCHR": "Okresní soud v Chrudimi", "OSJC": "Okresní soud v Jičíně", "OSNA": "Okresní soud v Náchodě",
    "OSVYCPA": "Okresní soud v Pardubicích", "OSVYCRK": "Okresní soud v Rychnově nad Kněžnou", "OSSE": "Okresní soud v Semilech",
    "OSVYCSY": "Okresní soud ve Svitavách", "OSTU": "Okresní soud v Trutnově", "OSUO": "Okresní soud v Ústí nad Orlicí",
    "KSJIMBM": "Krajský soud v Brně", "KSBRJI": "KS Brno - pobočka Jihlava", "KSBRZL": "KS Brno - pobočka Zlín",
    "OSJIMBM": "Městský soud v Brně", "OSBK": "Okresní soud v Blansku", "OSBO": "Okresní soud Brno-venkov",
    "OSJIMBV": "Okresní soud v Břeclavi", "OSHO": "Okresní soud v Hodoníně", "OSJI": "Okresní soud v Jihlavě",
    "OSKM": "Okresní soud v Kroměříži", "OSJIMPV": "Okresní soud v Prostějově", "OSTRB": "Okresní soud v Třebíči",
    "OSJIMUH": "Okresní soud v Uherském Hradišti", "OSJIMVY": "Okresní soud ve Vyškově", "OSJIMZL": "Okresní soud ve Zlíně",
    "OSJIMZN": "Okresní soud ve Znojmě", "OSJIMZR": "Okresní soud ve Žďáru nad Sázavou", "KSSEMOS": "Krajský soud v Ostravě",
    "KSOSOL": "KS Ostrava - pobočka Olomouc", "OSBR": "Okresní soud v Bruntále", "OSSEMFM": "Okresní soud ve Frýdku-Místku",
    "OSJE": "Okresní soud v Jeseníku", "OSSEMKA": "Okresní soud v Karviné", "OSNJ": "Okresní soud v Novém Jičíně",
    "OSSEMOC": "Okresní soud v Olomouci", "OSSEMOP": "Okresní soud v Opavě", "OSSEMOS": "Okresní soud v Ostravě",
    "OSSEMPR": "Okresní soud v Přerově", "OSSEMSU": "Okresní soud v Šumperku", "OSSEMVS": "Okresní soud ve Vsetíně"
}

# -------------------------------------------------------------------------
# 1. INITIALIZACE DATABÁZE
# -------------------------------------------------------------------------

def make_hash(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_hash(password, hashed_text):
    if make_hash(password) == hashed_text:
        return True
    return False

@st.cache_resource
def init_db():
    conn = None; db_pool = None
    try:
        conn, db_pool = get_db_connection()
        c = conn.cursor()
        
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
        
        c.execute('''CREATE TABLE IF NOT EXISTS uzivatele
                     (id SERIAL PRIMARY KEY,
                      username TEXT UNIQUE,
                      password TEXT,
                      email TEXT,
                      role TEXT)''')

        c.execute('''CREATE TABLE IF NOT EXISTS historie
                     (id SERIAL PRIMARY KEY,
                      datum TIMESTAMP,
                      uzivatel TEXT,
                      akce TEXT,
                      popis TEXT)''')
                     
        conn.commit()
    except Exception as e:
        st.error(f"Chyba při inicializaci DB: {e}")
        st.stop()
    finally:
        if conn and db_pool: db_pool.putconn(conn)

init_db()

# --- SPRÁVA UŽIVATELŮ ---

def create_user(username, password, email, role):
    conn = None; db_pool = None
    try:
        conn, db_pool = get_db_connection()
        c = conn.cursor()
        c.execute("INSERT INTO uzivatele (username, password, email, role) VALUES (%s, %s, %s, %s)", 
                  (username, make_hash(password), email, role))
        conn.commit()
        log_do_historie("Vytvoření uživatele", f"Vytvořen uživatel '{username}' ({role})")
        return True
    except psycopg2.IntegrityError:
        if conn: conn.rollback()
        return False
    except Exception as e:
        print(f"Chyba DB: {e}")
        if conn: conn.rollback()
        return False
    finally:
        if conn and db_pool: db_pool.putconn(conn)

def delete_user(username):
    conn = None; db_pool = None
    try:
        conn, db_pool = get_db_connection()
        c = conn.cursor()
        c.execute("DELETE FROM uzivatele WHERE username=%s", (username,))
        conn.commit()
        log_do_historie("Smazání uživatele", f"Smazán uživatel '{username}'")
    except Exception as e:
        print(f"Chyba: {e}")
    finally:
        if conn and db_pool: db_pool.putconn(conn)

def get_all_users():
    conn = None; db_pool = None
    try:
        conn, db_pool = get_db_connection()
        df = pd.read_sql_query("SELECT username, email, role FROM uzivatele", conn)
        return df
    except Exception:
        return pd.DataFrame()
    finally:
        if conn and db_pool: db_pool.putconn(conn)

def verify_login(username, password):
    if username == SUPER_ADMIN_USER and password == SUPER_ADMIN_PASS:
        return "Super Admin"
    
    conn = None; db_pool = None
    role = None
    try:
        conn, db_pool = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT password, role FROM uzivatele WHERE username=%s", (username,))
        data = c.fetchone()
        
        if data:
            stored_hash, db_role = data
            if check_hash(password, stored_hash):
                role = db_role
    except Exception:
        pass
    finally:
        if conn and db_pool: db_pool.putconn(conn)
    
    return role

def get_user_role(username):
    if username == SUPER_ADMIN_USER: return "Super Admin"
    conn = None; db_pool = None; role = None
    try:
        conn, db_pool = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT role FROM uzivatele WHERE username=%s", (username,))
        data = c.fetchone()
        if data: role = data[0]
    except: pass
    finally: 
        if conn and db_pool: db_pool.putconn(conn)
    return role

# --- LOGOVÁNÍ ---

def log_do_historie(akce, popis):
    if 'current_user' in st.session_state:
        user = st.session_state['current_user']
    else:
        user = "🤖 Systém (Robot)"
    
    conn = None; db_pool = None
    try:
        conn, db_pool = get_db_connection()
        c = conn.cursor()
        c.execute("INSERT INTO historie (datum, uzivatel, akce, popis) VALUES (%s, %s, %s, %s)", 
                  (datetime.datetime.now(), user, akce, popis))
        conn.commit()
    except Exception as e:
        print(f"Chyba logování: {e}")
    finally:
        if conn and db_pool: db_pool.putconn(conn)

def get_historie(dny=14):
    conn = None; db_pool = None
    try:
        datum_limit = datetime.datetime.now() - datetime.timedelta(days=dny)
        conn, db_pool = get_db_connection()
        df = pd.read_sql_query("SELECT datum, uzivatel, akce, popis FROM historie WHERE datum > %s ORDER BY datum DESC", 
                                 conn, params=(datum_limit,))
        return df
    except Exception:
        return pd.DataFrame()
    finally:
        if conn and db_pool: db_pool.putconn(conn)

# -------------------------------------------------------------------------
# 2. LOGIKA ODESÍLÁNÍ
# -------------------------------------------------------------------------

def odeslat_email_notifikaci(nazev, udalost, znacka):
    if "novy.email" in SMTP_EMAIL: return

    conn = None; db_pool = None; prijemci = []
    try:
        conn, db_pool = get_db_connection()
        df_users = pd.read_sql_query("SELECT email FROM uzivatele WHERE email IS NOT NULL AND email != ''", conn)
        prijemci = df_users['email'].tolist()
    except: prijemci = []
    finally:
        if conn and db_pool: db_pool.putconn(conn)
    
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

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0"
]

def stahni_data_z_infosoudu(params):
    url = "https://infosoud.justice.cz/InfoSoud/public/search.do"
    req_params = {
        'type': 'spzn', 'typSoudu': params['typ'], 'krajOrg': 'VSECHNY_KRAJE',
        'org': params['soud'], 'cisloSenatu': params['senat'], 'druhVec': params['druh'],
        'bcVec': params['cislo'], 'rocnik': params['rocnik'], 'spamQuestion': '23', 'agendaNc': 'CIVIL'
    }
    
    agent = random.choice(USER_AGENTS)
    headers = {
        "User-Agent": agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "cs,en-US;q=0.7,en;q=0.3",
        "Referer": "https://infosoud.justice.cz/InfoSoud/public/search.do",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1"
    }
    
    try:
        r = requests.get(url, params=req_params, headers=headers, timeout=10)
        if "recaptcha" in r.text.lower() or "spam" in r.text.lower():
            print("⚠️ POZOR: Infosoud vrátil podezření na robota (Captcha).")
            return None

        soup = BeautifulSoup(r.text, 'html.parser')
        
        if "Řízení nebylo nalezeno" in soup.text: 
            return None
            
        udalosti = []
        for row in soup.find_all('tr'):
            cols = row.find_all('td')
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
    
    # Formátování s mezerami pro log
    spis_zn = f"{p.get('senat')} {p.get('druh')} {p.get('cislo')} / {p.get('rocnik')}"
    
    conn = None; db_pool = None
    try:
        conn, db_pool = get_db_connection()
        c = conn.cursor()
        c.execute("INSERT INTO pripady (oznaceni, url, params_json, pocet_udalosti, posledni_udalost, ma_zmenu, posledni_kontrola) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                  (oznaceni, url, json.dumps(p), len(data), data[-1] if data else "", False, datetime.datetime.now()))
        conn.commit()
        log_do_historie("Přidání spisu", f"Přidán spis: {oznaceni} ({spis_zn})")
        return True, "OK"
    except Exception as e:
        if conn: conn.rollback()
        return False, f"Chyba DB: {e}"
    finally:
        if conn and db_pool: db_pool.putconn(conn)

def smaz_pripad(cid):
    conn = None; db_pool = None
    try:
        conn, db_pool = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT oznaceni FROM pripady WHERE id=%s", (cid,))
        res = c.fetchone()
        nazev = res[0] if res else "Neznámý"
        c.execute("DELETE FROM pripady WHERE id=%s", (cid,))
        conn.commit()
        log_do_historie("Smazání spisu", f"Uživatel smazal spis: {nazev}")
    except Exception as e:
        print(f"Chyba při mazání: {e}")
    finally:
        if conn and db_pool: db_pool.putconn(conn)

def resetuj_upozorneni(cid):
    conn = None; db_pool = None
    try:
        conn, db_pool = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT oznaceni FROM pripady WHERE id=%s", (cid,))
        res = c.fetchone()
        nazev = res[0] if res else "Neznámý"
        c.execute("UPDATE pripady SET ma_zmenu = %s WHERE id=%s", (False, cid))
        conn.commit()
        log_do_historie("Potvrzení změny", f"Viděl jsem: {nazev}")
    except Exception as e:
        print(f"Chyba: {e}")
    finally:
        if conn and db_pool: db_pool.putconn(conn)

def resetuj_vsechna_upozorneni():
    conn = None; db_pool = None
    try:
        conn, db_pool = get_db_connection()
        c = conn.cursor()
        c.execute("UPDATE pripady SET ma_zmenu = %s WHERE ma_zmenu = %s", (False, True))
        conn.commit()
        log_do_historie("Hromadné potvrzení", "Uživatel označil všechny změny jako viděné.")
    except Exception as e:
        print(f"Chyba: {e}")
    finally:
        if conn and db_pool: db_pool.putconn(conn)

def prejmenuj_pripad(cid, novy_nazev):
    conn = None; db_pool = None
    try:
        conn, db_pool = get_db_connection()
        c = conn.cursor()
        c.execute("UPDATE pripady SET oznaceni = %s WHERE id = %s", (novy_nazev, cid))
        conn.commit()
        log_do_historie("Přejmenování", f"Spis ID {cid} přejmenován na '{novy_nazev}'")
    except Exception as e:
        print(f"Chyba: {e}")
    finally:
        if conn and db_pool: db_pool.putconn(conn)

# --- SCHEDULER (POZADÍ - CHYTRÝ REŽIM DEN/NOC) ---
@st.cache_resource
def start_scheduler():
    scheduler = BackgroundScheduler()
    # Interval 60 minut
    scheduler.add_job(monitor_job, 'interval', minutes=60)
    scheduler.start()
    return scheduler

# Worker funkce - přijímá i posledni_udalost, ale nepoužívá ji pro kontrolu
def zkontroluj_jeden_pripad(row):
    cid, params_str, old_cnt, name, _ = row  # Unpack 5 hodnot (posledni je last_event)
    
    conn = None; db_pool = None
    try:
        p = json.loads(params_str)
        
        # BEZPEČNOSTNÍ PAUZA (1-3s)
        time.sleep(random.uniform(1.0, 3.0))
        
        new_data = stahni_data_z_infosoudu(p)
        
        if new_data is not None:
            now = datetime.datetime.now()
            
            conn, db_pool = get_db_connection()
            c = conn.cursor()
            
            if len(new_data) > old_cnt:
                # ZMĚNA!
                c.execute("UPDATE pripady SET pocet_udalosti=%s, posledni_udalost=%s, ma_zmenu=%s, posledni_kontrola=%s WHERE id=%s", 
                          (len(new_data), new_data[-1], True, now, cid))
                conn.commit()
                
                try:
                    c.execute("INSERT INTO historie (datum, uzivatel, akce, popis) VALUES (%s, %s, %s, %s)",
                              (now, "🤖 Systém (Robot)", "Nová událost", f"Změna u {name}"))
                    conn.commit()
                except: pass
                
                # E-mail
                spis_zn = f"{p.get('senat')} {p.get('druh')} {p.get('cislo')} / {p.get('rocnik')}"
                odeslat_email_notifikaci(name, new_data[-1], spis_zn)
                
            else:
                # BEZ ZMĚNY
                c.execute("UPDATE pripady SET posledni_kontrola=%s WHERE id=%s", (now, cid))
                conn.commit()
            return True
            
    except Exception as e:
        print(f"Chyba u případu ID {cid}: {e}")
        return False
    finally:
        if conn and db_pool: db_pool.putconn(conn)

# Pomocná funkce pro detekci "skončených" případů
def je_pripad_skonceny(text_udalosti):
    if not text_udalosti: return False
    txt = text_udalosti.lower()
    return "skončení věci" in txt or "pravomoc" in txt or "vyřízeno" in txt

def monitor_job():
    if st.monitor_status.get("running", False):
        return

    # START
    st.monitor_status["running"] = True
    st.monitor_status["start_time"] = datetime.datetime.now()
    st.monitor_status["progress"] = 0
    
    conn = None; db_pool = None
    try:
        conn, db_pool = get_db_connection()
        c = conn.cursor()
        # Načteme i poslední událost pro filtraci
        c.execute("SELECT id, params_json, pocet_udalosti, oznaceni, posledni_udalost FROM pripady")
        all_rows = c.fetchall()
        db_pool.putconn(conn); conn = None 
        
        # --- FILTRACE (DEN vs NOC) ---
        aktualni_hodina = datetime.datetime.now().hour
        
        # Rozdělení na aktivní a skončené
        aktivni_pripady = []
        skoncene_pripady = []
        
        for r in all_rows:
            last_event_text = r[4] # Index 4 je posledni_udalost
            if je_pripad_skonceny(last_event_text):
                skoncene_pripady.append(r)
            else:
                aktivni_pripady.append(r)
        
        # Logika výběru
        target_rows = []
        rezim_text = ""
        
        if aktualni_hodina == 2: # 02:00 - 02:59
            target_rows = skoncene_pripady
            rezim_text = "🌙 NOČNÍ KONTROLA (ARCHIV)"
        else:
            target_rows = aktivni_pripady
            rezim_text = "☀️ DENNÍ KONTROLA (AKTIVNÍ)"
            
        st.monitor_status["total"] = len(target_rows)
        st.monitor_status["mode"] = rezim_text
        
        print(f"--- START {rezim_text} ({datetime.datetime.now()}) - Počet: {len(target_rows)} ---")
        
        # --- BEZPEČNÁ PARALELIZACE (Max 3 vlákna) ---
        dokonceno = 0
        if target_rows:
            with ThreadPoolExecutor(max_workers=3) as executor:
                futures = [executor.submit(zkontroluj_jeden_pripad, row) for row in target_rows]
                for future in as_completed(futures):
                    dokonceno += 1
                    st.monitor_status["progress"] = dokonceno
            
        print(f"--- KONEC KONTROLY ---")
                    
    except Exception as e:
        print(f"Chyba scheduleru: {e}")
    finally:
        st.monitor_status["running"] = False
        st.monitor_status["last_finished"] = datetime.datetime.now()
        if conn and db_pool: db_pool.putconn(conn)

start_scheduler()

# -------------------------------------------------------------------------
# 4. FRONTEND A PŘIHLÁŠENÍ (ANTI-FLICKER)
# -------------------------------------------------------------------------

if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
    st.session_state['current_user'] = None
    st.session_state['user_role'] = None

if not st.session_state['logged_in']:
    if 'prevent_relogin' not in st.session_state:
        try:
            cookie_user = cookie_manager.get(cookie="infosoud_user")
            if cookie_user:
                role = get_user_role(cookie_user)
                if role:
                    st.session_state['logged_in'] = True
                    st.session_state['current_user'] = cookie_user
                    st.session_state['user_role'] = role
                    st.rerun()
            else:
                 time.sleep(0.2)
                 cookie_user = cookie_manager.get(cookie="infosoud_user")
                 if cookie_user: st.rerun()
        except: pass

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
                    cookie_manager.set("infosoud_user", username, expires_at=datetime.datetime.now() + datetime.timedelta(days=7))
                    if 'prevent_relogin' in st.session_state: del st.session_state['prevent_relogin']
                    st.success(f"Vítejte, {username} ({role})")
                    time.sleep(1); st.rerun()
                else:
                    st.error("Chybné jméno nebo heslo.")
    st.stop()

# --- HLAVNÍ APLIKACE ---

st.title("⚖️ Monitor Soudních Spisů")

with st.sidebar:
    st.write(f"👤 **{st.session_state['current_user']}**")
    st.caption(f"Role: {st.session_state['user_role']}")
    
    if st.button("Odhlásit se"):
        cookie_manager.delete("infosoud_user")
        st.session_state['logged_in'] = False
        st.session_state['prevent_relogin'] = True
        time.sleep(0.5); st.rerun()
        
    st.markdown("---")
    
    # --- INFO O AUTOMATICKÉ KONTROLE ---
    st.markdown("### 🤖 Automatická kontrola")
    if st.monitor_status["running"]:
        total = st.monitor_status["total"]
        done = st.monitor_status["progress"]
        mode = st.monitor_status.get("mode", "Běží...")
        
        remaining = total - done
        eta_seconds = remaining * 0.8 
        eta_min = int(eta_seconds // 60)
        
        st.info(f"{mode}")
        st.progress(int((done / total) * 100) if total > 0 else 0)
        st.caption(f"Zpracováno: **{done} / {total}**")
        st.caption(f"Zbývá cca: **{eta_min} min**")
    else:
        last_time = st.monitor_status["last_finished"]
        if last_time:
            st.caption(f"Poslední kontrola: {last_time.strftime('%H:%M')}")
        else:
            st.caption("Čekám na spuštění...")
            
    st.markdown("---")

    # --- PŘIDÁNÍ SPISU (BEZ TLAČÍTKA RUČNÍ KONTROLY) ---
    st.header("➕ Přidat nový spis")
    
    if st.session_state.get('smazat_vstupy'):
        st.session_state.input_url = ""
        st.session_state.input_nazev = ""
        st.session_state.smazat_vstupy = False 
    
    st.text_input("Název kauzy", key="input_nazev")
    st.text_input("URL z Infosoudu", key="input_url")
    
    if st.button("Sledovat", use_container_width=True):
        with st.spinner("⏳ Přidávám případ..."):
            zacatek = time.time()
            url_val = st.session_state.input_url
            nazev_val = st.session_state.input_nazev
            ok, msg = pridej_pripad(url_val, nazev_val)
            trvani = time.time() - zacatek
            if trvani < 5: time.sleep(5 - trvani)
            
            if ok:
                st.cache_data.clear()
                st.session_state['vysledek_akce'] = ("success", msg)
                st.session_state['smazat_vstupy'] = True
            else:
                st.session_state['vysledek_akce'] = ("error", msg)
        if ok: st.rerun()

    if 'vysledek_akce' in st.session_state:
        typ, text = st.session_state['vysledek_akce']
        if typ == 'success': st.success(text)
        else: st.error(text)
        del st.session_state['vysledek_akce']
        
    st.divider()

    # --- HLAVNÍ VÝPIS KAUZ ---
    df_zmeny = get_zmeny_all()

    c_search_input, c_search_btn = st.columns([4, 1])
    with c_search_input:
        search_query_input = st.text_input("Hledat v archivu (Název, značka, soud, text)", 
                                           label_visibility="collapsed", 
                                           placeholder="🔍 Hledat v archivu... (např. 20 C 70 / 2014)")
    with c_search_btn:
        search_clicked = st.button("🔍 Hledat", use_container_width=True)

    if 'last_search' not in st.session_state: st.session_state['last_search'] = ""
    if search_clicked or search_query_input != st.session_state['last_search']:
        st.session_state['page'] = 1
        st.session_state['last_search'] = search_query_input
        if search_clicked: st.rerun()

    active_search_query = st.session_state['last_search']
    df_all_green = get_all_green_cases_raw()
    
    if not df_all_green.empty and active_search_query:
        q_lower = active_search_query.lower()
        q_no_space = q_lower.replace(" ", "")
        
        def filter_row(row):
            if q_lower in str(row['oznaceni']).lower(): return True
            if q_lower in str(row['realny_nazev_soudu']).lower(): return True
            if q_lower in str(row['posledni_udalost']).lower(): return True
            try:
                p = json.loads(row['params_json'])
                znacka = f"{p.get('senat')}{p.get('druh')}{p.get('cislo')}/{p.get('rocnik')}".lower()
                if q_no_space in znacka: return True
            except: pass
            return False

        mask = df_all_green.apply(filter_row, axis=1)
        df_filtered = df_all_green[mask]
    else:
        df_filtered = df_all_green

    total_green = len(df_filtered)
    total_pages = math.ceil(total_green / ITEMS_PER_PAGE)
    if total_pages < 1: total_pages = 1
    
    start_idx = (st.session_state['page'] - 1) * ITEMS_PER_PAGE
    end_idx = start_idx + ITEMS_PER_PAGE
    df_ostatni = df_filtered.iloc[start_idx:end_idx]

    def akce_videl_jsem(id_spisu): resetuj_upozorneni(id_spisu)
    def akce_smazat(id_spisu): smaz_pripad(id_spisu)
    def akce_videl_jsem_vse(): resetuj_vsechna_upozorneni()

    # --- A) ČERVENÁ SEKCE ---
    if not df_zmeny.empty:
        col_head, col_btn = st.columns([3, 1])
        with col_head: st.subheader(f"🚨 Případy se změnou ({len(df_zmeny)})")
        with col_btn: st.button("👁️ Viděl jsem vše", on_click=akce_videl_jsem_vse, type="primary", use_container_width=True)

        for index, row in df_zmeny.iterrows():
            try:
                p = json.loads(row['params_json'])
                spisova_znacka = f"{p.get('senat')} {p.get('druh')} {p.get('cislo')} / {p.get('rocnik')}"
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
                    st.link_button("Otevřít", row['url'])
                    with st.popover("✏️", help="Upravit název"):
                        novy_nazev = st.text_input("Název", value=row['oznaceni'], key=f"edit_red_{row['id']}")
                        if st.button("Uložit", key=f"save_red_{row['id']}"):
                            prejmenuj_pripad(row['id'], novy_nazev); st.rerun()
                    st.button("👁️ Viděl", key=f"seen_{row['id']}", on_click=akce_videl_jsem, args=(row['id'],))
                    with st.popover("🗑️", help="Odstranit"):
                        st.write("Opravdu smazat?")
                        if st.button("Ano", key=f"confirm_del_red_{row['id']}", type="primary"):
                            akce_smazat(row['id']); st.rerun()

    # --- B) ZELENÁ SEKCE ---
    if not df_zmeny.empty: st.markdown("---")
    
    if active_search_query:
        st.subheader(f"🔍 Výsledky hledání: '{active_search_query}' (Nalezeno: {total_green})")
    else:
        st.subheader(f"✅ Případy beze změn (Celkem: {total_green})")
    
    if df_ostatni.empty:
        st.info("Žádné případy nenalezeny.")
    else:
        for index, row in df_ostatni.iterrows():
            try:
                p = json.loads(row['params_json'])
                spisova_znacka = f"{p.get('senat')} {p.get('druh')} {p.get('cislo')} / {p.get('rocnik')}"
                kod_soudu = p.get('soud')
                nazev_soudu = SOUDY_MAPA.get(kod_soudu, kod_soudu)
                formatted_time = pd.to_datetime(row['posledni_kontrola']).strftime("%d. %m. %Y %H:%M")
            except:
                spisova_znacka = "?"; nazev_soudu = "?"; formatted_time = ""

            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([2, 3, 4, 1])
                with c1:
                    st.markdown(f"**{row['oznaceni']}**")
                    st.caption("✅ Bez změny")
                with c2:
                    st.markdown(f"📂 **{spisova_znacka}**")
                    st.caption(f"🏛️ {nazev_soudu}")
                with c3:
                    st.write(f"📅 **{row['posledni_udalost']}**")
                    st.caption(f"Kontrolováno: {formatted_time}")
                with c4:
                    st.link_button("Otevřít", row['url'])
                    with st.popover("✏️", help="Upravit název"):
                        novy_nazev = st.text_input("Název", value=row['oznaceni'], key=f"edit_green_{row['id']}")
                        if st.button("Uložit", key=f"save_green_{row['id']}"):
                            prejmenuj_pripad(row['id'], novy_nazev); st.rerun()
                    with st.popover("🗑️", help="Odstranit"):
                        st.write("Opravdu smazat?")
                        if st.button("Ano", key=f"confirm_del_green_{row['id']}", type="primary"):
                            akce_smazat(row['id']); st.rerun()

    if total_pages > 1:
        st.markdown("---")
        c_prev, c_info, c_next = st.columns([1, 2, 1])
        with c_prev:
            if st.session_state['page'] > 1:
                if st.button("⬅️ Předchozí"):
                    st.session_state['page'] -= 1; st.rerun()
        with c_info:
            st.markdown(f"<div style='text-align: center'>Strana <b>{st.session_state['page']}</b> z {total_pages}</div>", unsafe_allow_html=True)
        with c_next:
            if st.session_state['page'] < total_pages:
                if st.button("Další ➡️"):
                    st.session_state['page'] += 1; st.rerun()

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
