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
    pass 

# --- 🕰️ NASTAVENÍ ČASOVÉHO PÁSMA ---
def get_now():
    tz = pytz.timezone('Europe/Prague')
    return datetime.datetime.now(tz)

# --- 🔄 GLOBÁLNÍ STAV ---
if not hasattr(st, "monitor_status"):
    st.monitor_status = {"running": False, "progress": 0, "total": 0, "mode": "Neznámý", "last_finished": None}

# --- 🔐 NAČTENÍ TAJNÝCH ÚDAJŮ (SECRETS) ---
def get_secret(key):
    value = os.getenv(key)
    if value is not None: return value
    try:
        if hasattr(st, "secrets") and key in st.secrets: return st.secrets[key]
    except: pass
    return None

DB_URI = get_secret("SUPABASE_DB_URL")
SUPER_ADMIN_USER = get_secret("SUPER_ADMIN_USER")
SUPER_ADMIN_PASS = get_secret("SUPER_ADMIN_PASS")
SUPER_ADMIN_EMAIL = get_secret("SUPER_ADMIN_EMAIL")
SMTP_SERVER, SMTP_PORT = "smtp.gmail.com", 587
SMTP_EMAIL = get_secret("SMTP_EMAIL")
SMTP_PASSWORD = get_secret("SMTP_PASSWORD")

# --- 🏗️ DATABÁZOVÝ POOL ---
@st.cache_resource
def init_connection_pool():
    try:
        return psycopg2.pool.SimpleConnectionPool(1, 15, dsn=DB_URI)
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

# --- 1. INITIALIZACE DATABÁZE ---
def make_hash(password): return hashlib.sha256(str.encode(password)).hexdigest()
def check_hash(password, hashed_text): return make_hash(password) == hashed_text

@st.cache_resource
def init_db():
    conn = None; db_pool = None
    try:
        conn, db_pool = get_db_connection()
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS pripady (id SERIAL PRIMARY KEY, oznaceni TEXT, url TEXT, params_json TEXT, pocet_udalosti INTEGER, posledni_udalost TEXT, ma_zmenu BOOLEAN, posledni_kontrola TIMESTAMP, realny_nazev_soudu TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS uzivatele (id SERIAL PRIMARY KEY, username TEXT UNIQUE, password TEXT, email TEXT, role TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS historie (id SERIAL PRIMARY KEY, datum TIMESTAMP, uzivatel TEXT, akce TEXT, popis TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS system_logs (id SERIAL PRIMARY KEY, start_time TIMESTAMP, end_time TIMESTAMP, mode TEXT, processed_count INTEGER)")
        c.execute("CREATE TABLE IF NOT EXISTS system_status (id INTEGER PRIMARY KEY, is_running BOOLEAN, progress INTEGER, total INTEGER, mode TEXT, last_update TIMESTAMP)")
        c.execute("INSERT INTO system_status (id, is_running, progress, total, mode) SELECT 1, False, 0, 0, 'Spí' WHERE NOT EXISTS (SELECT 1 FROM system_status WHERE id = 1)")
        conn.commit()
    except Exception as e:
        st.error(f"Chyba DB Init: {e}")
    finally:
        if conn and db_pool: db_pool.putconn(conn)

init_db()

# --- SPRÁVA UŽIVATELŮ A LOGY ---
def create_user(username, password, email, role):
    conn = None; db_pool = None
    try:
        conn, db_pool = get_db_connection(); c = conn.cursor()
        c.execute("INSERT INTO uzivatele (username, password, email, role) VALUES (%s, %s, %s, %s)", (username, make_hash(password), email, role))
        conn.commit(); log_do_historie("Vytvoření uživatele", f"Vytvořen uživatel '{username}'")
        return True
    except: return False
    finally:
        if conn and db_pool: db_pool.putconn(conn)

def delete_user(username):
    conn = None; db_pool = None
    try:
        conn, db_pool = get_db_connection(); c = conn.cursor()
        c.execute("DELETE FROM uzivatele WHERE username=%s", (username,))
        conn.commit(); log_do_historie("Smazání uživatele", f"Smazán '{username}'")
    finally:
        if conn and db_pool: db_pool.putconn(conn)

def get_all_users():
    conn = None; db_pool = None
    try:
        conn, db_pool = get_db_connection()
        return pd.read_sql_query("SELECT username, email, role FROM uzivatele", conn)
    except: return pd.DataFrame()
    finally:
        if conn and db_pool: db_pool.putconn(conn)

def verify_login(username, password):
    if username == SUPER_ADMIN_USER and password == SUPER_ADMIN_PASS: return "Super Admin"
    conn = None; db_pool = None
    try:
        conn, db_pool = get_db_connection(); c = conn.cursor()
        c.execute("SELECT password, role FROM uzivatele WHERE username=%s", (username,))
        data = c.fetchone()
        if data and check_hash(password, data[0]): return data[1]
    except: pass
    finally:
        if conn and db_pool: db_pool.putconn(conn)
    return None

def log_do_historie(akce, popis):
    user = st.session_state.get('current_user', "🤖 Systém (Robot)")
    conn = None; db_pool = None
    try:
        conn, db_pool = get_db_connection(); c = conn.cursor()
        c.execute("INSERT INTO historie (datum, uzivatel, akce, popis) VALUES (%s, %s, %s, %s)", (get_now(), user, akce, popis))
        conn.commit()
    except: pass
    finally:
        if conn and db_pool: db_pool.putconn(conn)

def get_system_logs(dny=3):
    conn = None; db_pool = None
    try:
        conn, db_pool = get_db_connection()
        return pd.read_sql_query("SELECT start_time, end_time, mode, processed_count FROM system_logs WHERE start_time > %s ORDER BY start_time DESC", conn, params=(get_now() - datetime.timedelta(days=dny),))
    except: return pd.DataFrame()
    finally:
        if conn and db_pool: db_pool.putconn(conn)

def vycistit_stare_logy(dny=30):
    conn = None; db_pool = None
    try:
        conn, db_pool = get_db_connection(); c = conn.cursor()
        limit = get_now() - datetime.timedelta(days=dny)
        c.execute("DELETE FROM system_logs WHERE start_time < %s", (limit,))
        c.execute("DELETE FROM historie WHERE datum < %s", (limit,))
        conn.commit()
    except: pass
    finally:
        if conn and db_pool: db_pool.putconn(conn)

# --- 2. NOTIFIKACE A SCRAPING ---
def odeslat_email_notifikaci(nazev, udalost, znacka):
    if not SMTP_EMAIL or "novy.email" in SMTP_EMAIL: return
    conn = None; db_pool = None; prijemci = []
    try:
        conn, db_pool = get_db_connection()
        df_users = pd.read_sql_query("SELECT email FROM uzivatele WHERE email IS NOT NULL AND email != ''", conn)
        prijemci = df_users['email'].tolist()
    finally:
        if conn and db_pool: db_pool.putconn(conn)
    if SUPER_ADMIN_EMAIL: prijemci.append(SUPER_ADMIN_EMAIL)
    prijemci = list(set(prijemci))
    if not prijemci: return
    msg = MIMEMultipart()
    msg['From'] = SMTP_EMAIL
    msg['Subject'] = f"🚨 Změna ve spisu: {nazev}"
    msg.attach(MIMEText(f"Novinka u {nazev} ({znacka}):\n\n{udalost}\n\nInfosoud Monitor", 'plain'))
    try:
        s = smtplib.SMTP(SMTP_SERVER, SMTP_PORT); s.starttls(); s.login(SMTP_EMAIL, SMTP_PASSWORD)
        for p in prijemci: s.sendmail(SMTP_EMAIL, p, msg.as_string())
        s.quit()
    except: pass

def stahni_data_z_infosoudu(params):
    url = "https://infosoud.justice.cz/InfoSoud/public/search.do"
    req_params = {'type': 'spzn', 'typSoudu': params['typ'], 'krajOrg': 'VSECHNY_KRAJE', 'org': params['soud'], 'cisloSenatu': params['senat'], 'druhVec': params['druh'], 'bcVec': params['cislo'], 'rocnik': params['rocnik'], 'spamQuestion': '23', 'agendaNc': 'CIVIL'}
    try:
        r = requests.get(url, params=req_params, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if "recaptcha" in r.text.lower(): return None
        soup = BeautifulSoup(r.text, 'html.parser')
        udalosti = []
        for row in soup.find_all('tr'):
            cols = row.find_all('td')
            if len(cols) >= 2 and re.match(r'^\d{2}\.\d{2}\.\d{4}$', cols[1].get_text(strip=True)):
                udalosti.append(f"{cols[1].get_text(strip=True)} - {cols[0].get_text(strip=True)}")
        return udalosti
    except: return None

def pridej_pripad(url, oznaceni):
    p = urlparse(url) # Placeholder pro parsování
    conn = None; db_pool = None
    try:
        conn, db_pool = get_db_connection(); c = conn.cursor()
        c.execute("INSERT INTO pripady (oznaceni, url, ma_zmenu, posledni_kontrola) VALUES (%s, %s, %s, %s)", (oznaceni, url, False, get_now()))
        conn.commit(); return True
    except: return False
    finally:
        if conn and db_pool: db_pool.putconn(conn)

def resetuj_upozorneni(cid):
    conn = None; db_pool = None
    try:
        conn, db_pool = get_db_connection(); c = conn.cursor()
        c.execute("UPDATE pripady SET ma_zmenu = False WHERE id=%s", (cid,)); conn.commit()
    finally:
        if conn and db_pool: db_pool.putconn(conn)

def zkontroluj_jeden_pripad(row):
    cid, params_str, old_cnt, name, _ = row
    conn = None; db_pool = None
    try:
        p = json.loads(params_str); time.sleep(random.uniform(1.0, 3.0))
        new_data = stahni_data_z_infosoudu(p)
        if new_data is not None:
            conn, db_pool = get_db_connection(); c = conn.cursor()
            if len(new_data) > old_cnt:
                c.execute("UPDATE pripady SET pocet_udalosti=%s, posledni_udalost=%s, ma_zmenu=True, posledni_kontrola=%s WHERE id=%s", (len(new_data), new_data[-1], get_now(), cid))
                conn.commit(); odeslat_email_notifikaci(name, new_data[-1], "Změna")
            else:
                c.execute("UPDATE pripady SET posledni_kontrola=%s WHERE id=%s", (get_now(), cid))
                conn.commit()
            return True
    finally:
        if conn: db_pool.putconn(conn)
    return False

# --- 4. MONITOR JOB (FIXED SQL BRIDGE) ---
def monitor_job():
    def update_status_all(key, value):
        if hasattr(st, "monitor_status"): st.monitor_status[key] = value
        try:
            conn_upd, pool_upd = get_db_connection(); c_upd = conn_upd.cursor()
            if key == "running": c_upd.execute("UPDATE system_status SET is_running=%s, last_update=%s WHERE id=1", (value, get_now()))
            elif key == "progress": c_upd.execute("UPDATE system_status SET progress=%s, last_update=%s WHERE id=1", (value, get_now()))
            elif key == "total": c_upd.execute("UPDATE system_status SET total=%s, last_update=%s WHERE id=1", (value, get_now()))
            elif key == "mode": c_upd.execute("UPDATE system_status SET mode=%s, last_update=%s WHERE id=1", (value, get_now()))
            conn_upd.commit(); pool_upd.putconn(conn_upd)
        except: pass

    update_status_all("running", True); update_status_all("progress", 0)
    try:
        conn, pool = get_db_connection(); c = conn.cursor()
        c.execute("SELECT id, params_json, pocet_udalosti, oznaceni, posledni_udalost FROM pripady")
        rows = c.fetchall(); pool.putconn(conn)
        target_rows = [r for r in rows if "skončení" not in str(r[4]).lower()]
        update_status_all("total", len(target_rows))
        rezim_text = "🌙 NOČNÍ KONTROLA" if get_now().hour == 2 else "☀️ DENNÍ KONTROLA"
        update_status_all("mode", rezim_text)
        
        dokonceno = 0
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(zkontroluj_jeden_pripad, r) for r in target_rows]
            for f in as_completed(futures):
                dokonceno += 1; update_status_all("progress", dokonceno)
        
        conn, pool = get_db_connection(); c = conn.cursor()
        c.execute("INSERT INTO system_logs (start_time, end_time, mode, processed_count) VALUES (%s, %s, %s, %s)", (get_now(), get_now(), rezim_text, dokonceno))
        conn.commit(); pool.putconn(conn)
        vycistit_stare_logy(30)
    finally:
        update_status_all("running", False); update_status_all("mode", "Spí")

# --- 5. UI FRAGMENT ---
@st.fragment(run_every=5)
def render_status():
    try:
        conn, pool = get_db_connection(); c = conn.cursor()
        c.execute("SELECT is_running, progress, total, mode FROM system_status WHERE id=1")
        res = c.fetchone(); pool.putconn(conn)
        if res and res[0]:
            st.info(f"🤖 {res[3]}")
            st.progress(int((res[1]/res[2])*100) if res[2]>0 else 0)
            st.caption(f"Zpracováno: **{res[1]} / {res[2]}**")
        else:
            st.caption("✅ Systém je v pohotovosti")
    except: pass

# --- 6. FRONTEND ---
if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
if not st.session_state['logged_in']:
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.title("🔐 Infosoud Monitor")
        with st.form("login_form"):
            user = st.text_input("Uživatel"); passw = st.text_input("Heslo", type="password")
            if st.form_submit_button("Přihlásit"):
                role = verify_login(user, passw)
                if role:
                    st.session_state['logged_in'], st.session_state['current_user'], st.session_state['user_role'] = True, user, role
                    st.rerun()
    st.stop()

st.title("⚖️ Monitor Soudních Spisů")

with st.sidebar:
    st.write(f"👤 **{st.session_state['current_user']}**")
    if st.button("Odhlásit"): st.session_state['logged_in'] = False; st.rerun()
    st.markdown("---")
    render_status()
    st.markdown("---")
    st.header("➕ Přidat nový spis")
    n_nazev = st.text_input("Název kauzy")
    n_url = st.text_input("URL")
    if st.button("Sledovat"):
        if pridej_pripad(n_url, n_nazev): st.success("Přidáno!"); time.sleep(1); st.rerun()

menu = ["📊 Přehled kauz", "📜 Auditní historie", "🤖 Logy kontrol", "👥 Správa uživatelů"]
choice = st.sidebar.radio("Menu", menu)

if choice == "📊 Přehled kauz":
    ITEMS_PER_PAGE = 50
    if 'page' not in st.session_state: st.session_state['page'] = 1
    
    conn, pool = get_db_connection()
    df_zmeny = pd.read_sql_query("SELECT * FROM pripady WHERE ma_zmenu = TRUE ORDER BY id DESC", conn)
    df_all = pd.read_sql_query("SELECT * FROM pripady WHERE ma_zmenu = FALSE ORDER BY id DESC", conn)
    pool.putconn(conn)

    if not df_zmeny.empty:
        st.subheader(f"🚨 Změny ({len(df_zmeny)})")
        for idx, row in df_zmeny.iterrows():
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([2, 3, 4, 1])
                c1.markdown(f"### {row['oznaceni']}\n🚨 **NOVÉ**")
                c2.write(f"🏛️ {row['realny_nazev_soudu']}")
                c3.write(f"📅 **{row['posledni_udalost']}**")
                if c4.button("👁️", key=f"v_{row['id']}"): resetuj_upozorneni(row['id']); st.rerun()

    st.markdown("---")
    st.subheader(f"✅ Archiv ({len(df_all)})")
    start = (st.session_state['page'] - 1) * ITEMS_PER_PAGE
    for idx, row in df_all.iloc[start:start+ITEMS_PER_PAGE].iterrows():
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([2, 3, 4, 1])
            c1.markdown(f"**{row['oznaceni']}**")
            c2.caption(f"🏛️ {row['realny_nazev_soudu']}")
            c3.write(f"{row['posledni_udalost']}")
            if c4.button("🗑️", key=f"d_{row['id']}"): st.write("Smazáno"); st.rerun()

elif choice == "🤖 Logy kontrol":
    st.dataframe(get_system_logs(), use_container_width=True, hide_index=True)
elif choice == "👥 Správa uživatelů":
    st.header("👥 Správa uživatelů")
    st.dataframe(get_all_users(), use_container_width=True)
