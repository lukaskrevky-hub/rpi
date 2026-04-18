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
# 1. IMPORT POTŘEBNÝCH KNIHOVEN
# ==========================================
from flask import Flask, render_template, jsonify, request # Webový framework pro tvorbu API a servírování HTML
import paho.mqtt.client as mqtt  # Klient pro asynchronní komunikaci se zprávovou sběrnicí MQTT
import requests                  # Pro odesílání synchronních HTTP GET požadavků (REST API) na externí server
import threading                 # Podpora pro běh funkcí ve vedlejších vláknech (multithreading)
import time                      # Časové funkce pro prodlevy a měření časovačů (SOS alarm)
import subprocess                # Modul pro spouštění nízkoúrovňových linuxových příkazů (espeak, ir-ctl)
import datetime                  # Pro formátování reálného času do logovacích souborů
import os                        # Přístup k souborovému systému (ověřování existence IR souborů)

app = Flask(__name__)

# ==========================================
# 2. EXTERNÍ INTEGRACE A KONFIGURACE
# ==========================================
# Tyto adresy slouží pro komunikaci se vzdáleným dohledovým serverem.
# Systém na ně odesílá asynchronní HTTP požadavky v případě nouze (SOS).
URL_SOS_ON = "http://DOPLNIT_URL_OD_VEDOUCIHO/sos_zvoni.txt?stav=1"
URL_SOS_OFF = "http://DOPLNIT_URL_OD_VEDOUCIHO/sos_zvoni.txt?stav=0"

# ==========================================
# 3. DEFINICE STROMOVÉHO MENU
# ==========================================
# Menu je definováno jako seznam slovníků. Každá položka nese sémantický význam,
# ikonku pro frontend (FontAwesome), typ akce a případné další parametry.

MENU_HOME = [
    {"id": 0, "label": "MÁM ŽÍZEŇ", "icon": "fa-glass-water", "color": "primary", "type": "req"},
    {"id": 1, "label": "MÁM HLAD", "icon": "fa-utensils", "color": "warning", "type": "req"},
    {"id": 2, "label": "SVĚTLO", "icon": "fa-lightbulb", "color": "success", "type": "zigbee"},
    {"id": 3, "label": "ZVONEK", "icon": "fa-bell", "color": "info", "type": "zigbee_bell"},
    {"id": 4, "label": "POMOC", "icon": "fa-hand-holding-medical", "color": "danger", "type": "sos"},
    {"id": 5, "label": "ZRUŠIT", "icon": "fa-rotate-left", "color": "secondary", "type": "cancel"}
]

MENU_DEVICES = [
    {"id": 0, "label": "TELEVIZE", "icon": "fa-tv", "color": "secondary", "type": "submenu", "target": "tv_controls"},
    {"id": 1, "label": "KLIMATIZACE", "icon": "fa-snowflake", "color": "info", "type": "submenu", "target": "ac_controls"},
    {"id": 2, "label": "RÁDIO", "icon": "fa-radio", "color": "primary", "type": "submenu", "target": "radio_controls"},
    {"id": 3, "label": "LED PÁSKY", "icon": "fa-lightbulb", "color": "warning", "type": "submenu", "target": "led_controls"},
    {"id": 4, "label": "DOMÁCNOST KLIENTA", "icon": "fa-house-user", "color": "success", "type": "submenu", "target": "client_controls"},
    {"id": 5, "label": "DOMŮ", "icon": "fa-house", "color": "secondary", "type": "back"}
]

# Podmenu pro ovládání konkrétní spotřební elektroniky přes infračervený signál (IR)
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

MENU_CLIENT_CONTROLS = [
    {"id": 0, "label": "LAMPA", "icon": "fa-lightbulb", "color": "warning", "type": "http_get", "url": "https://iot.benetronic.com/mymodule/z6r64fcYSf/EfR4/jirka@benetronic.com/HODNOTA/100/0"},
    {"id": 1, "label": "PROGRAM +", "icon": "fa-arrow-up", "color": "info", "type": "http_get", "url": "https://iot.benetronic.com/mymodule/E9zNtHbVM3/BX9c/jirka@benetronic.com/HODNOTA/100/0"},
    {"id": 2, "label": "PROGRAM -", "icon": "fa-arrow-down", "color": "info", "type": "http_get", "url": "https://iot.benetronic.com/mymodule/mRHBXuNKd6/Bwuz/jirka@benetronic.com/HODNOTA/100/0"},
    {"id": 3, "label": "ZPĚT", "icon": "fa-arrow-left", "color": "secondary", "type": "back"}
]

# Propojovací slovník pro snadnou navigaci mezi podmenu
MENUS = {
    "home": MENU_HOME, "devices": MENU_DEVICES,
    "tv_controls": MENU_TV_CONTROLS, "ac_controls": MENU_AC_CONTROLS,
    "radio_controls": MENU_RADIO_CONTROLS, "led_controls": MENU_LED_CONTROLS
}

# Databáze podporovaných značek pro infračervených povelů
AVAILABLE_TV_BRANDS = ["tcl", "sony", "lg", "panasonic", "gogen", "samsung"]
AVAILABLE_AC_BRANDS = ["toshiba", "mitsubishi"]
AVAILABLE_RADIO_BRANDS = ["auna", "onkyo"]
AVAILABLE_LED_BRANDS = ["generic_rgb"]

# ==========================================
# 4. GLOBÁLNÍ STAVOVÝ MODEL SYSTÉMU (State)
# ==========================================
# Tento slovník drží aktuální stav celé aplikace. Frontend (AJAX) 
# si tento stav pravidelně stahuje a podle něj překresluje obrazovku.
system_state = {
    "mode": "home",              # Aktuální hlavní režim (home / devices)
    "current_menu": MENU_HOME,   # Zrovna vykreslované menu na displeji
    "menu_history": [],          # LIFO zásobník pro navigaci "Zpět" (Zanořování)
    "selected_index": 0,         # Index karty, na které je aktuálně kurzor (joystick)
    "message": "Připraveno",     # Informační zpráva zobrazená v horní liště
    "connection": "SLEEP",       # Stav spojení s ESP32 ovladačem
    "last_action": 0,            # Časové razítko poslední provedené akce (pro animace)
    "sos_active": False,         # Zda je aktivní 2minutový poplach
    "sos_timer": 0,              # Unix timestamp spuštění poplachu
    "tts_enabled": False         # Příznak, zda je zapnuto čtení obrazovky (Text-To-Speech)
}

# ==========================================
# 5. POMOCNÉ SERVISNÍ FUNKCE
# ==========================================
def log_activity(action):
    """Zápis systémových událostí do trvalého logovacího souboru pro diagnostiku."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open("/home/lukas/rpi/aktivita_systemu.log", "a") as f:
            f.write(f"[{timestamp}] - {action}\n")
    except IOError: pass
    print(f"Zapsáno do logu: [{timestamp}] - {action}")

def speak_text(text):
    """
    Vygeneruje syntetický hlasový výstup (přečtení textu) přímo z Raspberry Pi.
    Využívá utilitu 'espeak'. Nejprve tvrdě ukončí probíhající proces čtení,
    aby nedocházelo k překrývání slov při rychlém posunu v menu.
    """
    if system_state.get("tts_enabled", False):
        try:
            subprocess.run(["killall", "espeak"], stderr=subprocess.DEVNULL)
            subprocess.Popen(["espeak", "-v", "cs", text], stderr=subprocess.DEVNULL)
        except Exception as e: print(e)

def send_http_request(url):
    """
    Odešle asynchronní HTTP GET dotaz na nadřazený dohledový server.
    Obsahuje ochranný timeout pro zabránění zamrznutí lokální sítě.
    """
    if "DOPLNIT" in url: return 
    try: requests.get(url, timeout=3)
    except: pass

# ==========================================
# 6. LOGIKA OVLÁDÁNÍ A ZPRACOVÁNÍ POVELŮ
# ==========================================
def on_mqtt_message(client, userdata, msg):
    """Callback funkce volaná při jakémkoliv příchozím paketu přes MQTT sběrnici."""
    try:
        topic = msg.topic
        payload = msg.payload.decode()
        if topic == "joystick/status":
            system_state["connection"] = payload
            if payload == "READY": log_activity("Ovladač se úspěšně připojil.")
        elif topic == "joystick/command":
            process_command(payload)
    except Exception as e: print(e)

def process_command(cmd):
    """Namapuje hardwarové pohyby (UP/DOWN/LEFT/RIGHT) na funkce v uživatelském rozhraní."""
    log_activity(f"Přijat příkaz od pacienta: {cmd}")
    if cmd == "UP": go_back()                   
    elif cmd == "RIGHT": move_selection(1)      
    elif cmd == "LEFT": move_selection(-1)      
    elif cmd in ["DOWN", "SELECT"]: trigger_action() 

def move_selection(direction):
    """
    Posouvá aktivní výběr (kurzor) po položkách menu horizontálně.
    Využívá logiku zbytků po dělení (modulo) pro vytvoření nekonečné 'kruhové' rotace.
    """
    menu_len = len(system_state["current_menu"])
    system_state["selected_index"] = (system_state["selected_index"] + direction) % menu_len
    item = system_state["current_menu"][system_state["selected_index"]]
    speak_text(item["label"])

def go_back():
    """
    Logika pro navigaci ZPĚT. Buď vynoří uživatele z hlubšího podmenu (LIFO zásobník),
    nebo přepne hlavní sekci (Služby <-> Zařízení).
    """
    if len(system_state["menu_history"]) > 0:
        prev_state = system_state["menu_history"].pop()
        system_state["current_menu"] = prev_state["menu"]
        system_state["selected_index"] = prev_state["index"]
        system_state["message"] = prev_state["message"]
    else:
        if system_state["mode"] == "home":
            system_state["mode"] = "devices"
            system_state["current_menu"] = MENU_DEVICES
            system_state["selected_index"] = 0
            system_state["message"] = "Režim: ZAŘÍZENÍ"
        else:
            system_state["mode"] = "home"
            system_state["current_menu"] = MENU_HOME
            system_state["selected_index"] = 0
            system_state["message"] = "Připraveno"
    item = system_state["current_menu"][system_state["selected_index"]]
    speak_text(item["label"])

def trigger_action():
    """
    Hlavní výkonná funkce spuštěná při potvrzení položky.
    Rozhoduje o spuštění hardwarové, softwarové nebo síťové akce.
    """
    idx = system_state["selected_index"]
    item = system_state["current_menu"][idx]
    system_state["last_action"] = time.time()
    
    # 1. Navigace do hlubšího podmenu
    if item.get("type") == "submenu":
        system_state["menu_history"].append({
            "menu": system_state["current_menu"], "index": system_state["selected_index"], "message": system_state["message"]
        })
        system_state["message"] = f"Menu: {item['label']}"
        system_state["current_menu"] = MENUS[item["target"]]
        system_state["selected_index"] = 0 
        speak_text(system_state["current_menu"][0]["label"])
        
    # 2. Hardcodované navigační prvky a asistenční požadavky
    elif item.get("type") == "back": go_back()
    elif item.get("type") == "cancel": system_state["message"] = "Připraveno"
    elif item.get("type") == "req": system_state["message"] = f"Vybráno: {item['label']}"
    
    # 3. Krizový SOS Poplach (HTTP požadavek na vzdálený server)
    elif item.get("type") == "sos":
        system_state["message"] = "POPLACH: " + item['label']
        system_state["sos_active"] = True
        system_state["sos_timer"] = time.time()
        threading.Thread(target=send_http_request, args=(URL_SOS_ON,)).start()
        
    # 4. Lokální IoT integrace protokolu Zigbee
    elif item.get("type") == "zigbee":
        try: mqtt_client.publish("zigbee2mqtt/zasuvka/set", '{"state": "TOGGLE"}')
        except: pass
        system_state["message"] = "Připraveno"
    elif item.get("type") == "zigbee_bell":
        try: mqtt_client.publish("zigbee2mqtt/zvonek/set", '{"state": "ON"}')
        except: pass
        system_state["message"] = "Připraveno"

    # ==========================================
    # 5. HYBRIDNÍ IR OVLÁDÁNÍ (Kaskádové načítání: Protokoly -> RAW data)
    # ==========================================
    elif item.get("type") == "ir":
        code_file = item['code']
        device_type = item.get('device', 'tv') 
        
        # Nastavení správného kontextu pro iteraci značek
        if device_type == "tv": brands = AVAILABLE_TV_BRANDS; system_state["message"] = f"TV: {item['label']}"
        elif device_type == "ac": brands = AVAILABLE_AC_BRANDS; system_state["message"] = f"KLÍMA: {item['label']}"
        elif device_type == "radio": brands = AVAILABLE_RADIO_BRANDS; system_state["message"] = f"RÁDIO: {item['label']}"
        elif device_type == "led": brands = AVAILABLE_LED_BRANDS; system_state["message"] = f"LED: {item['label']}"
        else: brands = []
        
        # Algoritmus iteruje přes všechny dostupné značky daného spotřebiče
        for brand in brands:
            # Definování cest k oběma typům souborů v filesystému Linuxu
            proto_path = f"/home/lukas/rpi/ir_codes/protokoly/{device_type}/{brand}/{code_file}.txt"
            raw_path = f"/home/lukas/rpi/ir_codes/raw_data/{device_type}/{brand}/{code_file}.txt"

            # --- METODA A: ČISTÝ PROTOKOL (Nejvyšší priorita) ---
            # Podívá se do složky 'protokoly'. Pokud soubor existuje, preferuje ho.
            if os.path.exists(proto_path):
                try:
                    with open(proto_path, "r") as f:
                        content = f.read().strip()
                    
                    # Extrakce dat z formátu "PROTOCOL:nec SCANCODE:0x877C10EF"
                    if "PROTOCOL:" in content and "SCANCODE:" in content:
                        parts = content.split()
                        protocol = parts[0].split(":")[1]
                        scancode = parts[1].split(":")[1]
                        ir_arg = f"{protocol}:{scancode}"
                    else:
                        ir_arg = content # Podpora, pokud tam uživatel napíše rovnou "nec:0x877C10EF"
                        
                    print(f"IR Vysílání PROTOKOL ({device_type.upper()} - {brand.upper()}): {ir_arg}")
                    # Volání s parametrem -S pro čistý Scancode
                    subprocess.run(["ir-ctl", "-d", "/dev/lirc0", "-S", ir_arg], check=True)
                    time.sleep(0.3)
                    
                    # PŘESKOČENÍ RAW DAT: Příkaz 'continue' zajistí, že se záložní RAW data budou ignorovat
                    continue 
                except Exception as e:
                    print(f"Chyba u protokolu: {e}")

            # --- METODA B: RAW DATA (Záložní plán / Fallback) ---
            # Pokud se kód nedostal k 'continue' (soubor protokolu neexistuje), sáhne po starých RAW datech.
            if os.path.exists(raw_path):
                print(f"IR Vysílání RAW ({device_type.upper()} - {brand.upper()}): {raw_path}")
                try: 
                    # Volání s parametrem --send pro vyslání surových pulzů
                    subprocess.run(["ir-ctl", "-d", "/dev/lirc0", "--send", raw_path], check=True)
                    time.sleep(0.3) 
                except Exception as e: print(e)

# ==========================================
# 7. INICIALIZACE MQTT KLIENTA
# ==========================================
mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
mqtt_client.on_message = on_mqtt_message

def on_connect(client, userdata, flags, reason_code, properties):
    # Přihlášení k odběru všech dat směřujících z/do ovladače
    client.subscribe("joystick/#")
mqtt_client.on_connect = on_connect

def start_mqtt():
    """Funkce běžící v samostatném vlákně zajišťující permanentní síťové naslouchání."""
    while True:
        try:
            mqtt_client.connect("localhost", 1883, 60)
            mqtt_client.loop_forever()
        except Exception as e: time.sleep(5)

# ==========================================
# 8. WEBOVÉ API (FLASK ENDPOINTY)
# ==========================================
@app.route('/')
def index():
    """Servíruje primární HTML šablonu uživatelského rozhraní."""
    return render_template('index.html')

@app.route('/api/status')
def get_status():
    """
    Hlavní synchronizační endpoint pro AJAX Polling klienta. 
    Zároveň automaticky utne běžící SOS poplach po uplynutí 120 vteřin.
    """
    if system_state.get("sos_active") and (time.time() - system_state.get("sos_timer", 0) > 120):
        system_state["sos_active"] = False
        system_state["message"] = "Připraveno"
        threading.Thread(target=send_http_request, args=(URL_SOS_OFF,)).start()
    return jsonify(system_state)

@app.route('/api/click/<int:index>', methods=['POST'])
def web_click(index):
    """Endpoint umožňující ovládat položky menu manuálně pomocí dotyku či myši na obrazovce."""
    if 0 <= index < len(system_state["current_menu"]):
        system_state["selected_index"] = index
        trigger_action()
    return jsonify({"status": "ok"})

@app.route('/api/reset', methods=['POST'])
def reset_message():
    """Zrušení výstražné hlášky a storno SOS poplachu tlačítkem 'VYŘÍZENO'."""
    system_state["sos_active"] = False
    system_state["message"] = "Připraveno"
    threading.Thread(target=send_http_request, args=(URL_SOS_OFF,)).start()
    return jsonify({"status": "reset"})

@app.route('/api/ota', methods=['POST'])
def trigger_ota():
    """Endpoint pro vyvolání vzdálené aktualizace (OTA) mikrokontroléru ESP32 přes Bluetooth."""
    mqtt_client.publish("joystick/ota", "START")
    system_state["message"] = "Povel k aktualizaci odeslán."
    return jsonify({"status": "ota_started"})

@app.route('/api/tts_toggle', methods=['POST'])
def toggle_tts():
    """Přepíná globální proměnnou, která povoluje/zakazuje zvukový výstup (espeak)."""
    system_state["tts_enabled"] = not system_state.get("tts_enabled", False)
    if system_state["tts_enabled"]: speak_text("Hlasový asistent zapnut")
    else: subprocess.run(["killall", "espeak"], stderr=subprocess.DEVNULL)
    return jsonify({"status": "ok", "tts_enabled": system_state["tts_enabled"]})

# ==========================================
# 9. VSTUPNÍ BOD APLIKACE
# ==========================================
if __name__ == '__main__':
    log_activity("--- SYSTÉM NASTARTOVÁN ---")
    # Start MQTT klienta jako Daemona (vlákno se ukončí spolu s hlavním programem)
    threading.Thread(target=start_mqtt, daemon=True).start()
    # Start webového serveru (0.0.0.0 povoluje přístup odkudkoliv ze sítě či P2P tunelu)
    app.run(host='0.0.0.0', port=5000, debug=False)
