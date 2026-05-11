"""
CENTRÁLNÍ APLIKAČNÍ SERVER A WEBOVÉ ROZHRANÍ - RASPBERRY PI
-----------------------------------------------------------
Tento skript běží na centrální jednotce (Raspberry Pi) jako hlavní mozek systému.
Kombinuje v sobě backendový webový server (Flask), klienta pro zprávovou 
sběrnici (MQTT) a přímé ovládání hardwaru (IR diody, lokální procesy).

Nová verze obsahuje hybridní vrstvu pro IR vysílání (Kaskádové načítání), 
která inteligentně upřednostňuje čisté protokoly před RAW daty.
"""

# ==========================================
# 1. IMPORT POTŘEBNÝCH KNIHOVEN A MODULŮ
# ==========================================
# Flask: Webový framework pro vytvoření API a zobrazení HTML stránky (index.html)
from flask import Flask, render_template, jsonify, request 
# Paho MQTT: Knihovna pro naslouchání zprávám z joysticku (z ESP32)
import paho.mqtt.client as mqtt  
# Requests: Modul pro odesílání HTTP požadavků (ovládání domácnosti Benetronic a sesterny)
import requests                  
# Threading: Umožňuje běh více věcí najednou (např. web běží, zatímco se odesílá HTTP dotaz nebo se čeká na animaci)
import threading                 
# Time: Práce s časem (časovače pro 2minutový SOS poplach, pauzy u IR vysílání a UI animace)
import time                      
# Subprocess: Slouží ke spouštění linuxových příkazů přímo z Pythonu (čtení textu espeak, infračervené ir-ctl)
import subprocess                
# Datetime: Získání aktuálního data a času pro zapisování do logovacího souboru
import datetime                  
# OS: Práce se souborovým systémem Linuxu (hlavně ověřování, zda existuje .txt soubor s IR kódem)
import os                        
# Urllib: NOVÉ - Knihovna pro bezpečné zakódování textu do URL adresy (převede mezery a háčky, aby to web pochopil)
import urllib.parse              

# Inicializace samotné webové aplikace do proměnné 'app'
app = Flask(__name__)

# ==========================================
# 2. DEFINICE STROMOVÉHO MENU (Uživatelské rozhraní)
# ==========================================
# Menu je definováno jako seznam slovníků. Každý slovník představuje jedno tlačítko na obrazovce.
# - 'id': Pořadí tlačítka
# - 'label': Nápis na tlačítku
# - 'icon': Třída ikonky z knihovny FontAwesome (např. fa-tv)
# - 'color': Barva tlačítka (bootstrap třídy nebo naše vlastní led-barvy z CSS)
# - 'type': Typ akce, která se stane po stisknutí (ir, zigbee, sos, submenu, http_get, atd.)

# Kořenové menu - základní požadavky pacienta
MENU_HOME = [
    {"id": 0, "label": "MÁM ŽÍZEŇ", "icon": "fa-glass-water", "color": "primary", "type": "req"},
    {"id": 1, "label": "MÁM HLAD", "icon": "fa-utensils", "color": "warning", "type": "req"},
    {"id": 2, "label": "SVĚTLO", "icon": "fa-lightbulb", "color": "success", "type": "zigbee"},
    # Typ 'sos' vyvolá vizuální poplach (blikání obrazovky na sesterně a HTTP požadavek do cloudu)
    {"id": 3, "label": "POMOC", "icon": "fa-hand-holding-medical", "color": "danger", "type": "sos"},
    {"id": 4, "label": "ZRUŠIT", "icon": "fa-rotate-left", "color": "secondary", "type": "cancel"}
]

# Rozcestník pro výběr konkrétního hardwaru (typuje do podmenu)
MENU_DEVICES = [
    {"id": 0, "label": "TELEVIZE", "icon": "fa-tv", "color": "secondary", "type": "submenu", "target": "tv_controls"},
    {"id": 1, "label": "KLIMATIZACE", "icon": "fa-snowflake", "color": "info", "type": "submenu", "target": "ac_controls"},
    {"id": 2, "label": "RÁDIO", "icon": "fa-radio", "color": "primary", "type": "submenu", "target": "radio_controls"},
    {"id": 3, "label": "LED PÁSKY", "icon": "fa-lightbulb", "color": "warning", "type": "submenu", "target": "led_controls"},
    # Napojení na domácnost klienta
    {"id": 4, "label": "DOMÁCNOST KLIENTA", "icon": "fa-house-user", "color": "success", "type": "submenu", "target": "client_controls"},
    {"id": 5, "label": "DOMŮ", "icon": "fa-house", "color": "secondary", "type": "back"}
]

# --- PODMENU PRO INFRAČERVENÁ ZAŘÍZENÍ (IR) ---
# Tlačítka obsahují parametry 'device' (složka přístroje) a 'code' (název txt souboru)
MENU_TV_CONTROLS = [
    {"id": 0, "label": "ZAP/VYP", "icon": "fa-power-off", "color": "danger", "type": "ir", "device": "tv", "code": "power"},
    {"id": 1, "label": "PROGRAM +", "icon": "fa-arrow-up", "color": "info", "type": "ir", "device": "tv", "code": "ch_up"},
    {"id": 2, "label": "PROGRAM -", "icon": "fa-arrow-down", "color": "info", "type": "ir", "device": "tv", "code": "ch_down"},
    {"id": 3, "label": "HLASITOST +", "icon": "fa-volume-high", "color": "secondary", "type": "ir", "device": "tv", "code": "vol_up"},
    {"id": 4, "label": "HLASITOST -", "icon": "fa-volume-low", "color": "secondary", "type": "ir", "device": "tv", "code": "vol_down"},
    {"id": 5, "label": "NAHORU", "icon": "fa-chevron-up", "color": "primary", "type": "ir", "device": "tv", "code": "up"},
    {"id": 6, "label": "DOLŮ", "icon": "fa-chevron-down", "color": "primary", "type": "ir", "device": "tv", "code": "down"},
    {"id": 7, "label": "DOLEVA", "icon": "fa-chevron-left", "color": "primary", "type": "ir", "device": "tv", "code": "left"},
    {"id": 8, "label": "DOPRAVA", "icon": "fa-chevron-right", "color": "primary", "type": "ir", "device": "tv", "code": "right"},
    {"id": 9, "label": "OK", "icon": "fa-circle-check", "color": "success", "type": "ir", "device": "tv", "code": "ok"},
    {"id": 10, "label": "TV ZPĚT", "icon": "fa-rotate-left", "color": "warning", "type": "ir", "device": "tv", "code": "tv_back"},
    {"id": 11, "label": "TV DOMŮ", "icon": "fa-house", "color": "warning", "type": "ir", "device": "tv", "code": "tv_home"},
    {"id": 12, "label": "SEZNAM", "icon": "fa-list", "color": "info", "type": "ir", "device": "tv", "code": "guide"},
    {"id": 13, "label": "ZPĚT", "icon": "fa-arrow-left", "color": "secondary", "type": "back"}
]

MENU_AC_CONTROLS = [
    {"id": 0, "label": "ZAPNOUT", "icon": "fa-power-off", "color": "success", "type": "ir", "device": "ac", "code": "power_on"},
    {"id": 1, "label": "VYPNOUT", "icon": "fa-power-off", "color": "danger", "type": "ir", "device": "ac", "code": "power_off"},
    {"id": 2, "label": "TEPLOTA +", "icon": "fa-temperature-arrow-up", "color": "warning", "type": "ir", "device": "ac", "code": "temp_up"},
    {"id": 3, "label": "TEPLOTA -", "icon": "fa-temperature-arrow-down", "color": "info", "type": "ir", "device": "ac", "code": "temp_down"},
    {"id": 4, "label": "ZPĚT", "icon": "fa-arrow-left", "color": "secondary", "type": "back"}
]

MENU_RADIO_CONTROLS = [
    {"id": 0, "label": "ZAP/VYP", "icon": "fa-power-off", "color": "danger", "type": "ir", "device": "radio", "code": "power"},
    {"id": 1, "label": "STANICE +", "icon": "fa-arrow-up", "color": "info", "type": "ir", "device": "radio", "code": "ch_up"},
    {"id": 2, "label": "STANICE -", "icon": "fa-arrow-down", "color": "info", "type": "ir", "device": "radio", "code": "ch_down"},
    {"id": 3, "label": "HLASITOST +", "icon": "fa-volume-high", "color": "secondary", "type": "ir", "device": "radio", "code": "vol_up"},
    {"id": 4, "label": "HLASITOST -", "icon": "fa-volume-low", "color": "secondary", "type": "ir", "device": "radio", "code": "vol_down"},
    {"id": 5, "label": "ZPĚT", "icon": "fa-arrow-left", "color": "secondary", "type": "back"}
]

MENU_LED_CONTROLS = [
    {"id": 0, "label": "ZAPNOUT", "icon": "fa-power-off", "color": "success", "type": "ir", "device": "led", "code": "power_on"},
    {"id": 1, "label": "VYPNOUT", "icon": "fa-power-off", "color": "danger", "type": "ir", "device": "led", "code": "power_off"},
    {"id": 2, "label": "JAS +", "icon": "fa-sun", "color": "warning", "type": "ir", "device": "led", "code": "bright_up"},
    {"id": 3, "label": "JAS -", "icon": "fa-moon", "color": "secondary", "type": "ir", "device": "led", "code": "bright_down"},
    {"id": 4, "label": "ČERVENÁ", "icon": "fa-palette", "color": "led-red", "type": "ir", "device": "led", "code": "color_red"},
    {"id": 5, "label": "ZELENÁ", "icon": "fa-palette", "color": "led-green", "type": "ir", "device": "led", "code": "color_green"},
    {"id": 6, "label": "MODRÁ", "icon": "fa-palette", "color": "led-blue", "type": "ir", "device": "led", "code": "color_blue"},
    {"id": 7, "label": "BÍLÁ", "icon": "fa-palette", "color": "led-white", "type": "ir", "device": "led", "code": "color_white"},
    {"id": 8, "label": "ŽLUTÁ", "icon": "fa-palette", "color": "led-yellow", "type": "ir", "device": "led", "code": "color_yellow"},
    {"id": 9, "label": "ORANŽOVÁ", "icon": "fa-palette", "color": "led-orange", "type": "ir", "device": "led", "code": "color_orange"},
    {"id": 10, "label": "RŮŽOVÁ", "icon": "fa-palette", "color": "led-pink", "type": "ir", "device": "led", "code": "color_pink"},
    {"id": 11, "label": "FIALOVÁ", "icon": "fa-palette", "color": "led-purple", "type": "ir", "device": "led", "code": "color_purple"},
    {"id": 12, "label": "SVĚTLE MODRÁ", "icon": "fa-palette", "color": "led-lightblue", "type": "ir", "device": "led", "code": "color_lightblue"},
    {"id": 13, "label": "EFEKT: BLIKÁNÍ", "icon": "fa-bolt", "color": "led-effect", "type": "ir", "device": "led", "code": "effect_flash"},
    {"id": 14, "label": "EFEKT: STROBOSKOP", "icon": "fa-wave-square", "color": "led-effect", "type": "ir", "device": "led", "code": "effect_strobe"},
    {"id": 15, "label": "EFEKT: PROLÍNÁNÍ", "icon": "fa-circle-half-stroke", "color": "led-effect", "type": "ir", "device": "led", "code": "effect_fade"},
    {"id": 16, "label": "EFEKT: PLYNULE", "icon": "fa-wand-magic-sparkles", "color": "led-effect", "type": "ir", "device": "led", "code": "effect_smooth"},
    {"id": 17, "label": "ZPĚT", "icon": "fa-arrow-left", "color": "secondary", "type": "back"}
]

# --- PODMENU PRO DOMÁCNOST KLIENTA (BENETRONIC) ---
# Tato sekce obsahuje přímé HTTP odkazy poskytnuté klientem. Akce typu "http_get" zavolá danou URL.
MENU_CLIENT_CONTROLS = [
    {"id": 0, "label": "LAMPA", "icon": "fa-lightbulb", "color": "warning", "type": "http_get", "url": "https://iot.benetronic.com/mymodule/z6r64fcYSf/EfR4/jirka@benetronic.com/HODNOTA/100/0"},
    {"id": 1, "label": "PROGRAM +", "icon": "fa-arrow-up", "color": "info", "type": "http_get", "url": "https://iot.benetronic.com/mymodule/E9zNtHbVM3/BX9c/jirka@benetronic.com/HODNOTA/100/0"},
    {"id": 2, "label": "PROGRAM -", "icon": "fa-arrow-down", "color": "info", "type": "http_get", "url": "https://iot.benetronic.com/mymodule/mRHBXuNKd6/Bwuz/jirka@benetronic.com/HODNOTA/100/0"},
    {"id": 3, "label": "ZPĚT", "icon": "fa-arrow-left", "color": "secondary", "type": "back"}
]

# Propojovací slovník (Dictionary) pro snadnou navigaci.
# Slouží k tomu, aby systém věděl, jaké pole tlačítek má načíst, když uživatel klikne na submenu.
MENUS = {
    "home": MENU_HOME, "devices": MENU_DEVICES,
    "tv_controls": MENU_TV_CONTROLS, "ac_controls": MENU_AC_CONTROLS,
    "radio_controls": MENU_RADIO_CONTROLS, "led_controls": MENU_LED_CONTROLS,
    "client_controls": MENU_CLIENT_CONTROLS
}

# --- DATABÁZE PODPOROVANÝCH ZNAČEK PRO IR ALGORITMUS KOBERCOVÉHO NÁLETU ---
# Systém postupně odešle kód pro všechny značky v těchto seznamech.
AVAILABLE_TV_BRANDS = ["tcl", "sony", "lg", "panasonic", "gogen", "samsung"]
AVAILABLE_AC_BRANDS = ["toshiba", "mitsubishi"]
AVAILABLE_RADIO_BRANDS = ["auna", "onkyo"]
AVAILABLE_LED_BRANDS = ["generic_rgb"]

# ==========================================
# 3. GLOBÁLNÍ STAVOVÝ MODEL SYSTÉMU (State)
# ==========================================
# Tento slovník drží aktuální stav celé aplikace. Frontend (přes AJAX v prohlížeči) 
# si tento stav pravidelně stahuje (3x za vteřinu) a podle něj mění to, co uživatel vidí.
system_state = {
    "mode": "home",              # Zda jsme v režimu HOME (Požadavky) nebo DEVICES (Ovládání elektroniky)
    "current_menu": MENU_HOME,   # Aktuálně vykreslované pole tlačítek na obrazovce
    "menu_history": [],          # LIFO zásobník (paměť) pro navigaci "Zpět"
    "selected_index": 0,         # Index (pořadí) karty, na které je aktuálně kurzor (vybrána joystickem)
    "message": "Připraveno",     # Informační zpráva zobrazená v horní liště (např. "MÁM HLAD")
    "active_alert": False,       # NOVÉ: Pokud je True, brání přepsání výstražné zprávy při pohybu v menu
    "active_requests": [],       # NOVÉ: Paměť pro více požadavků najednou (např. HLAD + ŽÍZEŇ)
    "connection": "SLEEP",       # Stav spojení s ESP32 ovladačem (READY, CONNECTING, SLEEP)
    "last_action": 0,            # Časové razítko poslední akce (slouží pro spuštění zelené flash animace karty)
    "sos_active": False,         # Logická hodnota (Zda obrazovka bliká červeně)
    "sos_timer": 0,              # Přesný čas, kdy byl SOS poplach spuštěn (slouží k samovypnutí po 2 minutách)
    "tts_enabled": False         # Logická hodnota (Zda Raspberry Pi čte text pomocí espeak)
}

# ==========================================
# 4. POMOCNÉ SERVISNÍ FUNKCE
# ==========================================
def log_activity(action):
    """Zápis systémových událostí do trvalého txt souboru. Dobré pro ladění a historii."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        # Soubor se otevře v režimu "a" (append - připojit na konec), aby se nepřemazala stará data
        with open("/home/lukas/rpi/aktivita_systemu.log", "a") as f:
            f.write(f"[{timestamp}] - {action}\n")
    except IOError: 
        pass # Pokud nejde zapsat (např. práva), chybu ignoruje
    print(f"Zapsáno do logu: [{timestamp}] - {action}")

def speak_text(text):
    """
    Vygeneruje syntetický hlasový výstup (přečtení textu) přímo z reproduktorů Raspberry Pi.
    """
    # Provede se pouze, pokud je čtení v systému zapnuto (přepíná se v horní liště webu)
    if system_state.get("tts_enabled", False):
        upraveny_text = text.replace("ZAP/VYP", "Zapnout vypnout") \
                            .replace("/", " ") \
                            .replace("+", " plus") \
                            .replace("-", " mínus")
        try:
            #  Ukončení probíhajícího procesu espeak (při rychlém přepínání karet)
            subprocess.run(["killall", "espeak"], stderr=subprocess.DEVNULL)
            # Zpomalení řeči
            subprocess.Popen(["espeak", "-v", "cs+f2", "-s", "140", upraveny_text], stderr=subprocess.DEVNULL)
        except Exception as e: 
            print(e)

def send_http_request(url):
    """
    Odešle HTTP GET dotaz (slouží pro domácnost Benetronic a vzdálenou sesternu).
    Běží vždy v novém vlákně, aby čekání na odpověď serveru nezablokovalo webové rozhraní.
    """
    if "DOPLNIT" in url: return # Ochrana před chybou
    try: 
        # Timeout 3 sekundy zajišťuje, že systém nespadne, pokud cílový server neodpovídá
        requests.get(url, timeout=3)
    except: 
        pass

# ==========================================
# 5. LOGIKA OVLÁDÁNÍ A ZPRACOVÁNÍ POVELŮ (Z Joysticku)
# ==========================================
def on_mqtt_message(client, userdata, msg):
    """Tato funkce se spustí automaticky POKAŽDÉ, když do RPi dorazí data od ESP32 ovladače."""
    try:
        topic = msg.topic # V jakém tématu zpráva přišla
        payload = msg.payload.decode() # Přeložení surových dat na text (např. "UP")
        
        # Ošetření stavu Bluetooth spojení
        if topic == "joystick/status":
            system_state["connection"] = payload
            if payload == "READY": log_activity("Ovladač se úspěšně připojil.")
            
        # Ošetření povelu (Pohyb joysticku)
        elif topic == "joystick/command":
            process_command(payload)
    except Exception as e: 
        print(e)

def process_command(cmd):
    """Přeloží hardwarové směry (UP/DOWN/LEFT/RIGHT) na navigaci po obrazovce."""
    log_activity(f"Přijat příkaz od pacienta: {cmd}")
    
    if cmd == "UP": go_back()                   # Nahoru = Krok zpět bez probliknutí karty
    elif cmd == "RIGHT": move_selection(1)      # Doprava = Posun o 1 kartu dál
    elif cmd == "LEFT": move_selection(-1)      # Doleva = Posun o 1 kartu zpět
    elif cmd in ["DOWN", "SELECT"]: trigger_action() # Dolů (nebo fyzické stisknutí tlačítka) = Potvrdit volbu

def move_selection(direction):
    """
    Posouvá kurzor na obrazovce.
    Využívá operátor modulo (%) k tzv. 'rotaci' (když přejedu na konec, skočí to zase na začátek).
    """
    menu_len = len(system_state["current_menu"])
    system_state["selected_index"] = (system_state["selected_index"] + direction) % menu_len
    
    # Najde slovník aktuálně vybrané karty a přečte ji nahlas
    item = system_state["current_menu"][system_state["selected_index"]]
    speak_text(item["label"])

def go_back(delayed=False):
    """
    Logika pro navigaci ZPĚT.
    Zjišťuje, jestli je uživatel v podmenu (pamatuje si historii), nebo na hlavní obrazovce.
    Parametr delayed=True, čekání na dokončení animace.
    """
    def switch_logic():
        # Pokud je požadavek zpožděný, chvíli vlákno uspíme
        if delayed:
            time.sleep(0.4) 

        # Je něco v historii? (uživatel v podmenu např. TV)
        if len(system_state["menu_history"]) > 0:
            # Vrátíme se do stavu před zanořením
            prev_state = system_state["menu_history"].pop()
            system_state["current_menu"] = prev_state["menu"]
            system_state["selected_index"] = prev_state["index"]
            
            # Zprávu o historii přepíšeme pouze tehdy, když zrovna nesvítí poplach / požadavek
            if not system_state.get("active_alert"):
                system_state["message"] = prev_state["message"]
        else:
            # Nejsme v historii. Jsme na kořenové obrazovce.
            # Směr nahoru přepíná mezi Požadavky (HOME) a Elektronikou (DEVICES)
            if system_state["mode"] == "home":
                system_state["mode"] = "devices"
                system_state["current_menu"] = MENU_DEVICES
                system_state["selected_index"] = 0
                
                # Ochrana proti smazání poplachu při přepnutí režimu
                if not system_state.get("active_alert"):
                    system_state["message"] = "Režim: ZAŘÍZENÍ"
            else:
                system_state["mode"] = "home"
                system_state["current_menu"] = MENU_HOME
                system_state["selected_index"] = 0
                
                # Ochrana proti smazání poplachu
                if not system_state.get("active_alert"):
                    system_state["message"] = "Připraveno"
                
        # Po změně nabídky přečteme vybranou položku
        item = system_state["current_menu"][system_state["selected_index"]]
        speak_text(item["label"])

    # Spustíme logiku přepnutí buď hned, nebo skrytě na pozadí, aby web nezamrzl
    if delayed:
        threading.Thread(target=switch_logic).start()
    else:
        switch_logic()

def trigger_action():
    """
    NEJDŮLEŽITĚJŠÍ FUNKCE WEBU. Spustí se při potvrzení položky.
    Vyhledá typ karty (type) a podle toho vykoná danou akci.
    """
    # Získání dat o aktuálně vybrané kartě
    idx = system_state["selected_index"]
    item = system_state["current_menu"][idx]
    
    # Uloží se přesný čas stisku (frontend díky tomu problikne kartu zeleně)
    system_state["last_action"] = time.time()
    
    # --- 1. ZANOŘENÍ DO PODMENU ---
    if item.get("type") == "submenu":
        # Uložíme současný stav do historie
        system_state["menu_history"].append({
            "menu": system_state["current_menu"], "index": system_state["selected_index"], "message": system_state["message"]
        })
        
        # FUNKCE PRO ZPOŽDĚNÝ PŘECHOD:
        # Aby frontend stihl přehrát animaci na vybrané kartě ještě předtím, 
        # než se menu kompletně přepne na např. ovladač TV, provedeme samotné přepnutí 
        # ve vedlejším vlákně s malým zpožděním.
        def delayed_submenu_switch():
            time.sleep(0.4) 
            
            # Pokud je aktivní poplach/požadavek, nepřepisujeme ho názvem menu
            if not system_state.get("active_alert"):
                system_state["message"] = f"Menu: {item['label']}"
                
            system_state["current_menu"] = MENUS[item["target"]]
            system_state["selected_index"] = 0 
            speak_text(system_state["current_menu"][0]["label"])
            
        threading.Thread(target=delayed_submenu_switch).start()
        
    # --- 2. OBYČEJNÉ NÁPISY A ZPĚT ---
    elif item.get("type") == "back": go_back(delayed=True) # Zde posílání True, čekání na animaci
    elif item.get("type") == "cancel": 
        # Zrušení poplachu i běžných požadavků ze strany pacienta ("ZRUŠIT")
        system_state["active_alert"] = False
        system_state["sos_active"] = False
        system_state["active_requests"] = [] # Vymaže celý seznam požadavků
        system_state["message"] = "Připraveno"
        
    elif item.get("type") == "req": 
        # U požadavků uzamkneme lištu nastavením active_alert = True
        system_state["active_alert"] = True
        
        # Přidáme aktuální požadavek do seznamu, pokud tam ještě není
        if item['label'] not in system_state["active_requests"]:
            system_state["active_requests"].append(item['label'])
            
        # Složení textu ze všech aktivních požadavků (např. "MÁM ŽÍZEŇ + MÁM HLAD")
        spojeny_text = " + ".join(system_state["active_requests"])
        
        # Pokud už běží SOS, zachováme slovo POPLACH, jinak dáme Vybráno
        if system_state["sos_active"]:
            system_state["message"] = f"POPLACH: {spojeny_text}"
        else:
            system_state["message"] = f"Vybráno: {spojeny_text}"
    
    # --- 3. KRIZOVÝ SOS POPLACH (Vizuální lokální poplach + Sesterna chytrepomucky.cz) ---
    elif item.get("type") == "sos":
        # Uzamknutí lišty pro SOS
        system_state["active_alert"] = True     
        system_state["sos_active"] = True       # Rozbliká prohlížeč červeně
        system_state["sos_timer"] = time.time() # Začne měřit 120 vteřin
        
        # Přidání POMOC do seznamu požadavků na první místo, pokud tam není
        if item['label'] not in system_state["active_requests"]:
            system_state["active_requests"].insert(0, item['label'])
            
        # Složení textu i se všemi předchozími volbami
        spojeny_text = " + ".join(system_state["active_requests"])
        system_state["message"] = f"POPLACH: {spojeny_text}"
        
        # Odeslání kritické hlášky na vzdálený dohledový server
        # Funkce urllib.parse.quote() se postará o to, aby se mezery a háčky bezpečně přepsaly do webového formátu (např. %20)
        encoded_msg = urllib.parse.quote("Pacient potřebuje pomoc")
        url = f"https://chytrepomucky.cz/smarthome/klient16drv651vd6sJwer95d/api.php?zvonek=1&hlaska={encoded_msg}&kontext=Pokoj%2012"
        threading.Thread(target=send_http_request, args=(url,)).start()
        
    # --- 4. ZIGBEE LOKÁLNÍ CHYTRÁ DOMÁCNOST ---
    elif item.get("type") == "zigbee":
        try: mqtt_client.publish("zigbee2mqtt/zasuvka/set", '{"state": "TOGGLE"}')
        except: pass
        
        # Zpráva o připravenosti jen tehdy, když nevisí poplach/požadavek
        if not system_state.get("active_alert"):
            system_state["message"] = "Připraveno"

    # --- 5. EXTERNÍ HTTP POŽADAVKY (Benetronic) ---
    elif item.get("type") == "http_get":
        url = item.get("url") # Vyčte konkrétní adresu z definice menu
        # Nastaveno na "Připraveno", pouze pokud není aktivní poplach.
        if not system_state.get("active_alert"):
            system_state["message"] = "Připraveno" 
        # Okamžitě odešle dotaz na pozadí, aniž by zamrznul systém
        threading.Thread(target=send_http_request, args=(url,)).start()

    # --- 6. HYBRIDNÍ IR OVLÁDÁNÍ (Kaskádové vysílání) ---
    elif item.get("type") == "ir":
        code_file = item['code']
        device_type = item.get('device', 'tv') 
        
        # Rozhodovací strom: Zjistí, které zařízení bude pro vysílání procházet
        # Kontrola if not active_alert pro ochranu výstražné zprávy v liště
        if device_type == "tv": 
            brands = AVAILABLE_TV_BRANDS
            if not system_state.get("active_alert"): system_state["message"] = f"TV: {item['label']}"
        elif device_type == "ac": 
            brands = AVAILABLE_AC_BRANDS
            if not system_state.get("active_alert"): system_state["message"] = f"KLÍMA: {item['label']}"
        elif device_type == "radio": 
            brands = AVAILABLE_RADIO_BRANDS
            if not system_state.get("active_alert"): system_state["message"] = f"RÁDIO: {item['label']}"
        elif device_type == "led": 
            brands = AVAILABLE_LED_BRANDS
            if not system_state.get("active_alert"): system_state["message"] = f"LED: {item['label']}"
        else: brands = []
        
        # Algoritmus iteruje přes všechny definované značky
        for brand in brands:
            # Přesné systémové cesty v Linuxu pro oba druhy datových záznamů
            proto_path = f"/home/lukas/rpi/ir_codes/protokoly/{device_type}/{brand}/{code_file}.txt"
            raw_path = f"/home/lukas/rpi/ir_codes/raw_data/{device_type}/{brand}/{code_file}.txt"

            # --- METODA A: ČISTÝ PROTOKOL (vyšší priorita) ---
            if os.path.exists(proto_path):
                try:
                    with open(proto_path, "r") as f:
                        content = f.read().strip()
                    
                    # Logika parsování: Soubor musí vypadat např. jako "PROTOCOL:necx SCANCODE:0x70702"
                    if "PROTOCOL:" in content and "SCANCODE:" in content:
                        parts = content.split()
                        protocol = parts[0].split(":")[1]
                        scancode = parts[1].split(":")[1]
                        ir_arg = f"{protocol}:{scancode}"
                    else:
                        ir_arg = content 
                        
                    print(f"IR Vysílání PROTOKOL ({device_type.upper()} - {brand.upper()}): {ir_arg}")
                    # Příkaz ir-ctl -S vygeneruje signál matematicky se strojovou přesností jádra Linuxu
                    subprocess.run(["ir-ctl", "-d", "/dev/lirc0", "-S", ir_arg], check=True)
                    time.sleep(0.3) # Pauza mezi pakety pro zamezení interference
                    
                    # Příkaz 'continue' zajistí, že pokud se vyslal čistý protokol,
                    # skript přeskočí metodu B a jde na další značku televize.
                    continue 
                except Exception as e:
                    print(f"Chyba u protokolu: {e}")

            # --- METODA B: RAW DATA (Fallback / Záchranná síť) ---
            # Kód se spustí POUZE, pokud selže Metoda A, hlavně pro multipakety klimatizací.
            if os.path.exists(raw_path):
                print(f"IR Vysílání RAW ({device_type.upper()} - {brand.upper()}): {raw_path}")
                try: 
                    # Příkaz ir-ctl --send odešle surové RAW data
                    subprocess.run(["ir-ctl", "-d", "/dev/lirc0", "--send", raw_path], check=True)
                    time.sleep(0.3) 
                except Exception as e: print(e)

# ==========================================
# 6. INICIALIZACE MQTT KLIENTA PRO ESP32
# ==========================================
# Vytvoření komunikačního uzlu
mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
# Spojení funkce 'on_mqtt_message' s událostí příchozí zprávy
mqtt_client.on_message = on_mqtt_message

def on_connect(client, userdata, flags, reason_code, properties):
    # Ihned po nastartování brokeru se systém přihlásí k odběru na vše v sekci 'joystick'
    client.subscribe("joystick/#")
mqtt_client.on_connect = on_connect

def start_mqtt():
    """Funkce běžící odděleně od webu na pozadí. Pokud spadne sběrnice, zkusí se za 5 vteřin obnovit."""
    while True:
        try:
            mqtt_client.connect("localhost", 1883, 60)
            mqtt_client.loop_forever() # Drží připojení otevřené (Nekonečná smyčka)
        except Exception as e: time.sleep(5)

# ==========================================
# 7. WEBOVÉ API (FLASK ENDPOINTY - Rozhraní pro JavaScript)
# ==========================================
@app.route('/')
def index():
    """Základní cesta. Po zadání IP do prohlížeče pošle grafický vzhled (HTML)."""
    return render_template('index.html')

@app.route('/api/status')
def get_status():
    """
    AJAX endpoint, aktualizuje 3x za vteřinu aktuální stav
    """
    # Logika pro automatické ukončení vizuálního SOS alarmu po 120 vteřinách
    if system_state.get("sos_active") and (time.time() - system_state.get("sos_timer", 0) > 120):
        system_state["sos_active"] = False
        
        # Po vypršení času uvolní lištu a smaže seznam požadavků
        system_state["active_alert"] = False 
        system_state["active_requests"] = [] 
        system_state["message"] = "Připraveno"
        
    return jsonify(system_state) # Odešle slovník zkonvertovaný do formátu JSON

@app.route('/api/click/<int:index>', methods=['POST'])
def web_click(index):
    """Pomocná funkce, pokud na displej u postele ťukne někdo prstem místo joysticku."""
    if 0 <= index < len(system_state["current_menu"]):
        system_state["selected_index"] = index
        trigger_action() # Umělé vyvolání stisknutí tlačítka
    return jsonify({"status": "ok"})

@app.route('/api/reset', methods=['POST'])
def reset_message():
    """Vypnutí SOS poplachu a chybových zpráv na obrazovce tlačítkem 'VYŘÍZENO'."""
    system_state["sos_active"] = False
    
    # Uvolnění lišty sestrou (zmáčknutím VYŘÍZENO) a smazání fronty
    system_state["active_alert"] = False 
    system_state["active_requests"] = [] 
    system_state["message"] = "Připraveno"
    
    # Odeslání informace na sesternu (chytrepomucky.cz), že je poplach zrušen
    url = "https://chytrepomucky.cz/smarthome/klient16drv651vd6sJwer95d/api.php?zvonek=0&hlaska=Vyrizeno&kontext=Pokoj%2012"
    threading.Thread(target=send_http_request, args=(url,)).start()
    
    return jsonify({"status": "reset"})

@app.route('/api/ota', methods=['POST'])
def trigger_ota():
    """Skrz MQTT pošle signál, že si má ESP32 ovladač sám sobě updatovat kód přes WiFi."""
    mqtt_client.publish("joystick/ota", "START")
    
    # Ochrana před přepsáním aktivního poplachu textem o aktualizaci
    if not system_state.get("active_alert"):
        system_state["message"] = "Povel k aktualizaci odeslán."
    return jsonify({"status": "ota_started"})

@app.route('/api/tts_toggle', methods=['POST'])
def toggle_tts():
    """Zapínání a vypínání hlasového čtení z reproduktoru."""
    # Prohodí True za False a naopak (Negace aktuálního stavu)
    system_state["tts_enabled"] = not system_state.get("tts_enabled", False)
    if system_state["tts_enabled"]: 
        speak_text("Hlasový asistent zapnut")
    else: 
        # Zastaví espeak pomocí příkazu killall
        subprocess.run(["killall", "espeak"], stderr=subprocess.DEVNULL)
    return jsonify({"status": "ok", "tts_enabled": system_state["tts_enabled"]})

# ==========================================
# 8. VSTUPNÍ BOD APLIKACE (Zaváděcí skript)
# ==========================================
# Tento blok se spustí pouze, když se skript spustí napřímo příkazem python web.py
if __name__ == '__main__':
    log_activity("--- SYSTÉM NASTARTOVÁN ---")
    
    # 1. Start MQTT klienta jako procesu na pozadí, vlákno se ukončí, pokud spadne hlavní web
    threading.Thread(target=start_mqtt, daemon=True).start()
    
    # 2. Start samotného webového serveru
    # host='0.0.0.0' webová stránka je přístupná všem zařízením na lokální síti
    app.run(host='0.0.0.0', port=5000, debug=False)
