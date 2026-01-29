def odeslat_email_notifikaci(nazev, udalost, znacka, soud, url):
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

    # Získání aktuálního českého času pro patičku
    cas_odeslani = get_now().strftime("%d.%m.%Y %H:%M")

    msg = MIMEMultipart("alternative")
    msg['From'] = SMTP_EMAIL
    
    # --- ZDE JE VAŠE ZMĚNA ---
    # Předmět nyní obsahuje spisovou značku (např. "Změna ve spisu: 81 T 8 / 2020")
    msg['Subject'] = f"Změna ve spisu: {znacka}"

    # 1. Čistý text
    text_body = f"""
    {nazev}
    
    Soud: {soud}
    Spisová značka: {znacka}

    Nová událost:
    {udalost}

    Otevřít na Infosoudu:
    {url}
    
    --
    Infosoud Monitor (Odesláno: {cas_odeslani})
    """

    # 2. HTML verze
    html_body = f"""
    <html>
      <body>
        <h3>{nazev}</h3>
        
        <p>
           <b>Soud:</b> {soud}<br>
           <b>Spisová značka:</b> {znacka}
        </p>
        
        <div style="background-color: #f5f5f5; padding: 15px; border-left: 5px solid #d32f2f; margin: 15px 0;">
            <b>Nová událost:</b><br>
            {udalost}
        </div>
        
        <br>
        <a href="{url}" style="background-color: #d32f2f; color: white; padding: 10px 15px; text-decoration: none; border-radius: 5px; font-weight: bold;">
           👉 Otevřít na Infosoudu
        </a>
        
        <br><br>
        <hr style="border: 0; border-top: 1px solid #eee;">
        <small style="color: grey;">
            Infosoud Monitor • Odesláno: {cas_odeslani}
        </small>
      </body>
    </html>
    """

    part1 = MIMEText(text_body, "plain")
    part2 = MIMEText(html_body, "html")
    msg.attach(part1)
    msg.attach(part2)

    try:
        s = smtplib.SMTP(SMTP_SERVER, int(SMTP_PORT))
        s.starttls(); s.login(SMTP_EMAIL, SMTP_PASSWORD)
        for p in prijemci:
            del msg['To']; msg['To'] = p; s.sendmail(SMTP_EMAIL, p, msg.as_string())
        s.quit()
        log_do_historie("Odeslání notifikace", f"Odesláno na {len(prijemci)} adres.")
    except Exception as e: print(f"Chyba emailu: {e}")
