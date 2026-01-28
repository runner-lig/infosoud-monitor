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
import pytz
import os
import math
from urllib.parse import urlparse, parse_qs
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from apscheduler.schedulers.background import BackgroundScheduler
import extra_streamlit_components as stx
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- KONFIGURACE UI ---
try:
    st.set_page_config(page_title="Infosoud Monitor", page_icon="⚖️", layout="wide")
except:
    pass # Ignorujeme, pokud běžíme jako worker v headless režimu

# --- 🕰️ NASTAVENÍ ČASOVÉHO PÁSMA (CZECHIA) ---
def get_now():
    tz = pytz.timezone('Europe/Prague')
    return datetime.datetime.now(tz)

# --- 🔄 GLOBÁLNÍ STAV SCHEDULERU (PRO RUČNÍ START V SEŠNĚ) ---
if not hasattr(st, "monitor_status"):
    st.monitor_status = {
        "running": False,
        "progress": 0,
        "total": 0,
        "mode": "Neznámý",
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
        
        c.execute('''CREATE TABLE IF NOT EXISTS system_logs
                     (id SERIAL PRIMARY KEY,
                      start_time TIMESTAMP,
                      end_time TIMESTAMP,
                      mode TEXT,
                      processed_count INTEGER)''')
        
        # --- TABULKA PRO STAV SYSTÉMU (MOST MEZI WORKEREM A UI) ---
        c.execute('''CREATE TABLE IF NOT EXISTS system_status
                     (id INTEGER PRIMARY KEY,
                      is_running BOOLEAN,
                      progress INTEGER,
                      total INTEGER,
                      mode TEXT,
                      last_update TIMESTAMP)''')
        
        c.execute("INSERT INTO system_status (id, is_running, progress, total, mode) SELECT 1, False, 0, 0, 'Spí' WHERE NOT EXISTS (SELECT 1 FROM system_status WHERE id = 1)")
                     
        conn.commit()
    except Exception as e:
        st.error(f"Chyba při inicializaci DB: {e}")
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

# --- LOGOVÁNÍ A ÚDRŽBA ---

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
                  (get_now(), user, akce, popis))
        conn.commit()
    except Exception as e:
        print(f"Chyba logování: {e}")
    finally:
        if conn and db_pool: db_pool.putconn(conn)

def get_historie(dny=14):
    conn = None; db_pool = None
    try:
        datum_limit = get_now() - datetime.timedelta(days=dny)
        conn, db_pool = get_db_connection()
        df = pd.read_sql_query("SELECT datum, uzivatel, akce, popis FROM historie WHERE datum > %s ORDER BY datum DESC", 
                                 conn, params=(datum_limit,))
        return df
    except Exception:
        return pd.DataFrame()
    finally:
        if conn and db_pool: db_pool.putconn(conn)

def get_system_logs(dny=3):
    conn = None; db_pool = None
    try:
        datum_limit = get_now() - datetime.timedelta(days=dny)
        conn, db_pool = get_db_connection()
        df = pd.read_sql_query("SELECT start_time, end_time, mode, processed_count FROM system_logs WHERE start_time > %s ORDER BY start_time DESC", 
                                 conn, params=(datum_limit,))
        return df
    except Exception:
        return pd.DataFrame()
    finally:
        if conn and db_pool: db_pool.putconn(conn)

def vycistit_stare_logy(dny=30):
    """Smaže systémové logy a historii starší než stanovený počet dní."""
    conn = None; db_pool = None
    try:
        limit = get_now() - datetime.timedelta(days=dny)
        conn, db_pool = get_db_connection()
        c = conn.cursor()
        c.execute("DELETE FROM system_logs WHERE start_time < %s", (limit,))
        c.execute("DELETE FROM historie WHERE datum < %s", (limit,))
        conn.commit()
        print(f"Sweep 🧹: Smazány záznamy starší než {dny} dní.")
    except Exception as e:
        print(f"Chyba při úklidu DB: {e}")
    finally:
        if conn and db_pool: db_pool.putconn(conn)

# -------------------------------------------------------------------------
# 2. LOGIKA ODESÍLÁNÍ
# -------------------------------------------------------------------------

def odeslat_email_notifikaci(nazev, udalost, znacka):
    if not SMTP_EMAIL or "novy.email" in SMTP_EMAIL: return

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

USER_AGENTS = ["Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"]

def stahni_data_z_infosoudu(params):
    url = "https://infosoud.justice.cz/InfoSoud/public/search.do"
    req_params = {
        'type': 'spzn', 'typSoudu': params['typ'], 'krajOrg': 'VSECHNY_KRAJE',
        'org': params['soud'], 'cisloSenatu': params['senat'], 'druhVec': params['druh'],
        'bcVec': params['cislo'], 'rocnik': params['rocnik'], 'spamQuestion': '23', 'agendaNc': 'CIVIL'
    }
    
    try:
        r = requests.get(url, params=req_params, headers={"User-Agent": random.choice(USER_AGENTS)}, timeout=10)
        if "recaptcha" in r.text.lower(): return None
        soup = BeautifulSoup(r.text, 'html.parser')
        
        udalosti = []
        for row in soup.find_all('tr'):
            cols = row.find_all('td')
            if len(cols) >= 2 and re.match(r'^\d{2}\.\d{2}\.\d{4}$', cols[1].get_text(strip=True)):
                text = cols[0].get_text(strip=True)
                udalosti.append(f"{cols[1].get_text(strip=True)} - {text}")
        return udalosti
    except:
        return None

def pridej_pripad(url, oznaceni):
    p = parsuj_url(url)
    if not p or not p['soud']: return False, "Neplatná URL."
    data = stahni_data_z_infosoudu(p)
    if data is None: return False, "Spis nenalezen."
    
    conn = None; db_pool = None
    try:
        conn, db_pool = get_db_connection(); c = conn.cursor()
        c.execute("INSERT INTO pripady (oznaceni, url, params_json, pocet_udalosti, posledni_udalost, ma_zmenu, posledni_kontrola) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                  (oznaceni, url, json.dumps(p), len(data), data[-1] if data else "", False, get_now()))
        conn.commit()
        return True, "OK"
    except:
        if conn: conn.rollback()
        return False, "Chyba DB"
    finally:
        if conn and db_pool: db_pool.putconn(conn)

def smaz_pripad(cid):
    conn = None; db_pool = None
    try:
        conn, db_pool = get_db_connection(); c = conn.cursor()
        c.execute("DELETE FROM pripady WHERE id=%s", (cid,))
        conn.commit()
    finally:
        if conn and db_pool: db_pool.putconn(conn)

def resetuj_upozorneni(cid):
    conn = None; db_pool = None
    try:
        conn, db_pool = get_db_connection(); c = conn.cursor()
        c.execute("UPDATE pripady SET ma_zmenu = %s WHERE id=%s", (False, cid))
        conn.commit()
    finally:
        if conn and db_pool: db_pool.putconn(conn)

def resetuj_vsechna_upozorneni():
    conn = None; db_pool = None
    try:
        conn, db_pool = get_db_connection(); c = conn.cursor()
        c.execute("UPDATE pripady SET ma_zmenu = %s WHERE ma_zmenu = %s", (False, True))
        conn.commit()
    finally:
        if conn and db_pool: db_pool.putconn(conn)

def prejmenuj_pripad(cid, novy_nazev):
    conn = None; db_pool = None
    try:
        conn, db_pool = get_db_connection(); c = conn.cursor()
        c.execute("UPDATE pripady SET oznaceni = %s WHERE id = %s", (novy_nazev, cid))
        conn.commit()
    finally:
        if conn and db_pool: db_pool.putconn(conn)

# --- SCHEDULER POMOCNÍCI ---

def zkontroluj_jeden_pripad(row):
    cid, params_str, old_cnt, name, _ = row
    conn = None; db_pool = None
    try:
        p = json.loads(params_str)
        time.sleep(random.uniform(1.0, 3.0))
        new_data = stahni_data_z_infosoudu(p)
        if new_data is not None:
            now = get_now()
            conn, db_pool = get_db_connection(); c = conn.cursor()
            if len(new_data) > old_cnt:
                c.execute("UPDATE pripady SET pocet_udalosti=%s, posledni_udalost=%s, ma_zmenu=%s, posledni_kontrola=%s WHERE id=%s", 
                          (len(new_data), new_data[-1], True, now, cid))
                conn.commit()
                spis_zn = f"{p.get('senat')} {p.get('druh')} {p.get('cislo')} / {p.get('rocnik')}"
                odeslat_email_notifikaci(name, new_data[-1], spis_zn)
            else:
                c.execute("UPDATE pripady SET posledni_kontrola=%s WHERE id=%s", (now, cid))
                conn.commit()
            return True
    except: pass
    finally:
        if conn and db_pool: db_pool.putconn(conn)
    return False

def je_pripad_skonceny(text_udalosti):
    if not text_udalosti: return False
    txt = text_udalosti.lower()
    return any(x in txt for x in ["skončení", "pravomoc", "vyřízeno"])

# --- 4. MONITOR JOB (HLAVNÍ MOTOR S MOSTY) ---

def monitor_job():
    def update_status_all(key, value):
        if hasattr(st, "monitor_status"):
            st.monitor_status[key] = value
        try:
            conn_upd, pool_upd = get_db_connection()
            c_upd = conn_upd.cursor()
            if key == "running": c_upd.execute("UPDATE system_status SET is_running = %s, last_update = %s WHERE id = 1", (value, get_now()))
            elif key == "progress": c_upd.execute("UPDATE system_status SET progress = %s, last_update = %s WHERE id = 1", (value, get_now()))
            elif key == "total": c_upd.execute("UPDATE system_status SET total = %s, last_update = %s WHERE id = 1", (value, get_now()))
            elif key == "mode": c_upd.execute("UPDATE system_status SET mode = %s, last_update = %s WHERE id = 1", (value, get_now()))
            conn_upd.commit(); pool_upd.putconn(conn_upd)
        except: pass

    if hasattr(st, "monitor_status") and st.monitor_status.get("running"): return

    start_ts = get_now()
    update_status_all("running", True); update_status_all("progress", 0); update_status_all("mode", "Inicializace...")
    
    conn = None; db_pool = None
    try:
        conn, db_pool = get_db_connection(); c = conn.cursor()
        c.execute("SELECT id, params_json, pocet_udalosti, oznaceni, posledni_udalost FROM pripady")
        all_rows = c.fetchall(); db_pool.putconn(conn); conn = None 
        
        aktualni_hodina = get_now().hour
        aktivni_pripady = [r for r in all_rows if not je_pripad_skonceny(r[4])]
        skoncene_pripady = [r for r in all_rows if je_pripad_skonceny(r[4])]
        
        if aktualni_hodina == 2: 
            target_rows = skoncene_pripady; rezim_text = "🌙 NOČNÍ KONTROLA (ARCHIV)"
        else:
            target_rows = aktivni_pripady; rezim_text = "☀️ DENNÍ KONTROLA (AKTIVNÍ)"
            
        update_status_all("total", len(target_rows)); update_status_all("mode", rezim_text)
        print(f"--- START {rezim_text} ({len(target_rows)} spisů) ---")
        
        dokonceno = 0
        if target_rows:
            with ThreadPoolExecutor(max_workers=3) as executor:
                futures = [executor.submit(zkontroluj_jeden_pripad, row) for row in target_rows]
                for future in as_completed(futures):
                    dokonceno += 1
                    update_status_all("progress", dokonceno)
                    if dokonceno % 10 == 0: print(f"⏳ Průběh: {dokonceno}/{len(target_rows)}")
            
        end_ts = get_now()
        conn, db_pool = get_db_connection(); c = conn.cursor()
        c.execute("INSERT INTO system_logs (start_time, end_time, mode, processed_count) VALUES (%s, %s, %s, %s)", (start_ts, end_ts, rezim_text, dokonceno))
        conn.commit(); print("--- KONEC ---")
        vycistit_stare_logy(30)
                    
    except Exception as e:
        print(f"❌ Chyba: {e}")
    finally:
        update_status_all("running", False); update_status_all("mode", "Spí")
        if conn and db_pool: db_pool.putconn(conn)

# --- 5. UI FRAGMENT (POLOVÁNÍ DATABÁZE) ---

@st.fragment(run_every=5)
def render_status():
    st.markdown("### 🤖 Automatická kontrola")
    try:
        conn, db_pool = get_db_connection(); c = conn.cursor()
        c.execute("SELECT is_running, progress, total, mode FROM system_status WHERE id = 1")
        db_state = c.fetchone(); db_pool.putconn(conn)
        
        if db_state and db_state[0]:
            is_run, prog, tot, mode = db_state
            st.info(f"{mode}")
            st.progress(int((prog / tot) * 100) if tot > 0 else 0)
            st.caption(f"Zpracováno: **{prog} / {tot}**")
        else:
            st.caption("✅ Systém je v pohotovosti (start ve :40)")
    except:
        st.caption("⏳ Načítám stav...")

# -------------------------------------------------------------------------
# 6. FRONTEND A PŘIHLÁŠENÍ
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
                    st.session_state['logged_in'], st.session_state['current_user'], st.session_state['user_role'] = True, cookie_user, role
                    st.rerun()
        except: pass

if not st.session_state['logged_in']:
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.title("🔐 Infosoud Monitor")
        with st.form("login_form"):
            username = st.text_input("Uživatelské jméno")
            password = st.text_input("Heslo", type="password")
            if st.form_submit_button("Přihlásit se"):
                role = verify_login(username, password)
                if role:
                    st.session_state['logged_in'], st.session_state['current_user'], st.session_state['user_role'] = True, username, role
                    cookie_manager.set("infosoud_user", username, expires_at=datetime.datetime.now() + datetime.timedelta(days=7))
                    st.rerun()
                else: st.error("Chybné jméno nebo heslo.")
    st.stop()

# --- HLAVNÍ APLIKACE ---

st.title("⚖️ Monitor Soudních Spisů")

with st.sidebar:
    st.write(f"👤 **{st.session_state['current_user']}** ({st.session_state['user_role']})")
    if st.button("Odhlásit se"):
        cookie_manager.delete("infosoud_user")
        st.session_state['logged_in'] = False; st.rerun()
    st.markdown("---")
    render_status() # Voláme globálně definovaný fragment
    st.markdown("---")
    st.header("➕ Přidat nový spis")
    nazev_val = st.text_input("Název kauzy", key="input_nazev")
    url_val = st.text_input("URL z Infosoudu", key="input_url")
    if st.button("Sledovat", use_container_width=True):
        ok, msg = pridej_pripad(url_val, nazev_val)
        if ok: st.success("Přidáno!"); time.sleep(1); st.rerun()
        else: st.error(msg)

menu_options = ["📊 Přehled kauz", "📜 Auditní historie", "🤖 Logy kontrol"]
if st.session_state['user_role'] in ["Super Admin", "Administrátor"]: menu_options.append("👥 Správa uživatelů")
selected_page = st.sidebar.radio("Menu", menu_options)

# -------------------------------------------------------------------------
# STRÁNKY (ZKRÁCENÉ LOGY/AUDIT PRO PŘEHLEDNOST)
# -------------------------------------------------------------------------

    
    ITEMS_PER_PAGE = 50
    if 'page' not in st.session_state:
        st.session_state['page'] = 1

    # --- FUNKCE PRO NAČÍTÁNÍ DAT ---
    def get_zmeny_all():
        conn = None; db_pool = None
        try:
            conn, db_pool = get_db_connection()
            return pd.read_sql_query("SELECT * FROM pripady WHERE ma_zmenu = TRUE ORDER BY id DESC", conn)
        except: return pd.DataFrame()
        finally: 
            if conn and db_pool: db_pool.putconn(conn)

    def get_all_green_cases_raw():
        conn = None; db_pool = None
        try:
            conn, db_pool = get_db_connection()
            return pd.read_sql_query("SELECT * FROM pripady WHERE ma_zmenu = FALSE ORDER BY id DESC", conn)
        except: return pd.DataFrame()
        finally: 
            if conn and db_pool: db_pool.putconn(conn)

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
# STRÁNKA: LOGY KONTROL
# -------------------------------------------------------------------------
elif selected_page == "🤖 Logy kontrol":
    st.header("🤖 Historie automatických kontrol (poslední 3 dny)")
    
    df_logs = get_system_logs(dny=3)
    
    if not df_logs.empty:
        # Převod na hezčí formát
        df_logs['start_time'] = pd.to_datetime(df_logs['start_time']).dt.strftime("%d.%m.%Y %H:%M")
        # Výpočet trvání
        df_logs['trvani'] = (pd.to_datetime(df_logs['end_time']) - pd.to_datetime(df_logs['start_time'], format="%d.%m.%Y %H:%M")).dt.total_seconds().apply(lambda x: f"{int(x // 60)} min {int(x % 60)} s")
        
        # Sloupec "Ikona" podle režimu
        def get_icon(mode_text):
            if "NOČNÍ" in str(mode_text): return "🌙"
            if "DENNÍ" in str(mode_text): return "☀️"
            return "❓"
            
        df_logs['ikona'] = df_logs['mode'].apply(get_icon)
        
        # Zobrazíme jen to podstatné
        df_display = df_logs[['start_time', 'ikona', 'mode', 'processed_count', 'trvani']].copy()
        df_display.columns = ["Začátek", "", "Režim", "Zkontrolováno spisů", "Doba trvání"]
        
        st.dataframe(df_display, use_container_width=True, hide_index=True)
    else:
        st.info("Zatím neproběhla žádná kontrola (nebo je databáze prázdná).")

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

elif selected_page == "👥 Správa uživatelů":
    t.header("👥 Správa uživatelů")
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

# start_scheduler() # DEAKTIVOVÁNO - POUŽÍVÁME HEROKU SCHEDULER
