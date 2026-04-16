"""
CENTRÁLNÍ APLIKAČNÍ SERVER A WEBOVÉ ROZHRANÍ - RASPBERRY PI
-----------------------------------------------------------
Tento skript běží na centrální jednotce (Raspberry Pi) jako hlavní mozek systému.
Kombinuje v sobě backendový webový server (Flask), klienta pro zprávovou 
sběrnici (MQTT) a přímé ovládání hardwaru (IR diody, lokální procesy).
Řídí kompletní stavový model, vizualizaci pro personál a integraci s IoT prvky.
"""

# ==========================================
# 1. IMPORT POTŘEBNÝCH KNIHOVEN
# ==========================================
import requests                  # Pro odesílání synchronních HTTP GET požadavků (REST API) na externí server
from flask import Flask, render_template, jsonify, request # Webový framework pro tvorbu API a servírování HTML
import paho.mqtt.client as mqtt  # Klient pro asynchronní komunikaci se zprávovou sběrnicí MQTT
import threading                 # Podpora pro běh funkcí ve vedlejších vláknech (multithreading)
import time                      # Časové funkce pro prodlevy a měření časovačů (SOS alarm)
import subprocess                # Modul pro spouštění nízkoúrovňových linuxových příkazů (espeak, ir-ctl)
import datetime                  # Pro formátování reálného času do logovacích souborů
import os                        # Přístup k souborovému systému (ověřování existence souborů)

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
# ikonku pro frontend (FontAwesome), typ akce a případné další parametry (např. IR kód).

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
    {"id": 4, "label": "DOMŮ", "icon": "fa-house", "color": "secondary", "type": "back"}
]

# Podmenu pro ovládání konkrétní spotřební elektroniky přes infračervený signál (IR)
MENU_TV_CONTROLS = [{"id": 0, "label": "ZAP/VYP", "icon": "fa-power-off", "color": "danger", "type": "ir", "device": "tv", "code": "power"}, {"id": 1, "label": "PROGRAM +", "icon": "fa-arrow-up", "color": "info", "type": "ir", "device": "tv", "code": "ch_up"}, {"id": 2, "label": "PROGRAM -", "icon": "fa-arrow-down", "color": "info", "type": "ir", "device": "tv", "code": "ch_down"}, {"id": 3, "label": "HLASITOST +", "icon": "fa-volume-high", "color": "secondary", "type": "ir", "device": "tv", "code": "vol_up"}, {"id": 4, "label": "HLASITOST -", "icon": "fa-volume-low", "color": "secondary", "type": "ir", "device": "tv", "code": "vol_down"}, {"id": 5, "label": "NAHORU", "icon": "fa-chevron-up", "color": "primary", "type": "ir", "device": "tv", "code": "up"}, {"id": 6, "label": "DOLŮ", "icon": "fa-chevron-down", "color": "primary", "type": "ir", "device": "tv", "code": "down"}, {"id": 7, "label": "DOLEVA", "icon": "fa-chevron-left", "color": "primary", "type": "ir", "device": "tv", "code": "left"}, {"id": 8, "label": "DOPRAVA", "icon": "fa-chevron-right", "color": "primary", "type": "ir", "device": "tv", "code": "right"}, {"id": 9, "label": "OK", "icon": "fa-circle-check", "color": "success", "type": "ir", "device": "tv", "code": "ok"}, {"id": 10, "label": "TV ZPĚT", "icon": "fa-rotate-left", "color": "warning", "type": "ir", "device": "tv", "code": "tv_back"}, {"id": 11, "label": "TV DOMŮ", "icon": "fa-house", "color": "warning", "type": "ir", "device": "tv", "code": "tv_home"}, {"id": 12, "label": "SEZNAM", "icon": "fa-list", "color": "info", "type": "ir", "device": "tv", "code": "guide"}, {"id": 13, "label": "ZPĚT", "icon": "fa-arrow-left", "color": "secondary", "type": "back"}]
MENU_AC_CONTROLS = [{"id": 0, "label": "ZAPNOUT", "icon": "fa-power-off", "color": "success", "type": "ir", "device": "ac", "code": "power_on"}, {"id": 1, "label": "VYPNOUT", "icon": "fa-power-off", "color": "danger", "type": "ir", "device": "ac", "code": "power_off"}, {"id": 2, "label": "TEPLOTA +", "icon": "fa-temperature-arrow-up", "color": "warning", "type": "ir", "device": "ac", "code": "temp_up"}, {"id": 3, "label": "TEPLOTA -", "icon": "fa-temperature-arrow-down", "color": "info", "type": "ir", "device": "ac", "code": "temp_down"}, {"id": 4, "label": "ZPĚT", "icon": "fa-arrow-left", "color": "secondary", "type": "back"}]
MENU_RADIO_CONTROLS = [{"id": 0, "label": "ZAP/VYP", "icon": "fa-power-off", "color": "danger", "type": "ir", "device": "radio", "code": "power"}, {"id": 1, "label": "STANICE +", "icon": "fa-arrow-up", "color": "info", "type": "ir", "device": "radio", "code": "ch_up"}, {"id": 2, "label": "STANICE -", "icon": "fa-arrow-down", "color": "info", "type": "ir", "device": "radio", "code": "ch_down"}, {"id": 3, "label": "HLASITOST +", "icon": "fa-volume-high", "color": "secondary", "type": "ir", "device": "radio", "code": "vol_up"}, {"id": 4, "label": "HLASITOST -", "icon": "fa-volume-low", "color": "secondary", "type": "ir", "device": "radio", "code": "vol_down"}, {"id": 5, "label": "ZPĚT", "icon": "fa-arrow-left", "color": "secondary", "type": "back"}]
MENU_LED_CONTROLS = [{"id": 0, "label": "ZAP/VYP", "icon": "fa-power-off", "color": "danger", "type": "ir", "device": "led", "code": "power"}, {"id": 1, "label": "ČERVENÁ", "icon": "fa-palette", "color": "danger", "type": "ir", "device": "led", "code": "color_red"}, {"id": 2, "label": "ZELENÁ", "icon": "fa-palette", "color": "success", "type": "ir", "device": "led", "code": "color_green"}, {"id": 3, "label": "MODRÁ", "icon": "fa-palette", "color": "info", "type": "ir", "device": "led", "code": "color_blue"}, {"id": 4, "label": "ZPĚT", "icon": "fa-arrow-left", "color": "secondary", "type": "back"}]

MENUS = {"home": MENU_HOME, "devices": MENU_DEVICES, "tv_controls": MENU_TV_CONTROLS, "ac_controls": MENU_AC_CONTROLS, "radio_controls": MENU_RADIO_CONTROLS, "led_controls": MENU_LED_CONTROLS}

# Databáze podporovaných značek pro "kobercový nálet" infračervených povelů
AVAILABLE_TV_BRANDS = ["tcl", "sony", "lg", "panasonic", "gogen"]
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
    "tts_enabled": False         # Příznak, zda je na Raspberry Pi zapnuto čtení obrazovky (Text-To-Speech)
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
    print(f"Zapsáno: {action}")

def speak_text(text):
    """
    Vygeneruje syntetický hlasový výstup (přečtení textu) přímo z Raspberry Pi.
    Využívá utilitu 'espeak'. Kvůli zamezení přeřvávání slov (např. při rychlém
    posunu v menu) nejprve tvrdě ukončí probíhající proces čtení.
    """
    if system_state.get("tts_enabled", False):
        try:
            # killall okamžitě umlčí předchozí asynchronní slovo
            subprocess.run(["killall", "espeak"], stderr=subprocess.DEVNULL)
            # Spuštění nového vlákna pro přečtení slova (česká výslovnost '-v cs')
            subprocess.Popen(["espeak", "-v", "cs", text], stderr=subprocess.DEVNULL)
        except Exception as e:
            print(f"Chyba TTS: {e}")

def send_http_request(url):
    """
    Odešle asynchronní HTTP GET dotaz na nadřazený dohledový server.
    Obsahuje ochranný timeout pro zabránění zamrznutí lokální sítě.
    """
    if "DOPLNIT" in url: return # Ochrana při nevyplněných URL
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
            # Aktualizace vizuálního odznáčku stavu připojení ESP32 (Sleep/Ready)
            system_state["connection"] = payload
            if payload == "READY": log_activity("Ovladač se připojil.")
        elif topic == "joystick/command":
            # Přijat konkrétní směr pohybu páčkou od pacienta
            process_command(payload)
    except Exception as e: print(e)

def process_command(cmd):
    """Namapuje hardwarové pohyby (UP/DOWN/LEFT/RIGHT) na funkce v uživatelském rozhraní."""
    if cmd == "UP": go_back()                   
    elif cmd == "RIGHT": move_selection(1)      
    elif cmd == "LEFT": move_selection(-1)      
    elif cmd in ["DOWN", "SELECT"]: trigger_action() 

def move_selection(direction):
    """
    Posouvá aktivní výběr (kurzor) po položkách menu horizontálně.
    Využívá logiku zbytků po dělení (modulo) pro vytvoření nekonečné "kruhové" rotace.
    """
    menu_len = len(system_state["current_menu"])
    system_state["selected_index"] = (system_state["selected_index"] + direction) % menu_len
    
    # Po přesunu na novou kartu nahlas přečte její název, pokud je TTS zapnuto
    item = system_state["current_menu"][system_state["selected_index"]]
    speak_text(item["label"])

def go_back():
    """
    Logika pro navigaci ZPĚT (pohyb páčkou NAHORU).
    Buď vynoří uživatele z hlubšího podmenu, nebo přepne hlavní sekci (Služby <-> Zařízení).
    """
    if len(system_state["menu_history"]) > 0:
        # Vynoření z podmenu (vyzvednutí předchozího stavu z LIFO zásobníku)
        prev_state = system_state["menu_history"].pop()
        system_state["current_menu"] = prev_state["menu"]
        system_state["selected_index"] = prev_state["index"]
        system_state["message"] = prev_state["message"]
    else:
        # Přepínání hlavních kořenových kategorií (Global Toggle)
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
    
    # Přečtení nově aktivní karty po návratu
    item = system_state["current_menu"][system_state["selected_index"]]
    speak_text(item["label"])

def trigger_action():
    """
    Hlavní výkonná funkce spuštěná při potvrzení položky (pohyb DOLŮ).
    Rozhoduje o spuštění hardwarové, softwarové nebo síťové akce.
    """
    idx = system_state["selected_index"]
    item = system_state["current_menu"][idx]
    system_state["last_action"] = time.time() # Spustí zelenou flash animaci na frontendu
    
    # 1. Navigace do hlubšího podmenu
    if item.get("type") == "submenu":
        # Uložení aktuálního stavu do zásobníku (historie) pro bezpečný návrat
        system_state["menu_history"].append({
            "menu": system_state["current_menu"],
            "index": system_state["selected_index"],
            "message": system_state["message"]
        })
        system_state["message"] = f"Menu: {item['label']}"
        target_menu = item["target"]
        system_state["current_menu"] = MENUS[target_menu]
        system_state["selected_index"] = 0 
        
        # Přečte hned první položku v právě otevřeném podmenu
        new_item = system_state["current_menu"][0]
        speak_text(new_item["label"])
        
    # 2. Hardcodované navigační prvky
    elif item.get("type") == "back": go_back()
    elif item.get("type") == "cancel": system_state["message"] = "Připraveno"

    # 3. Běžné sémantické asistenční požadavky
    elif item.get("type") == "req":
        system_state["message"] = f"Vybráno: {item['label']}"

    # 4. Krizový SOS Poplach (Rozsvítí obrazovku na rudo a zašle zprávu do internetu)
    elif item.get("type") == "sos":
        system_state["message"] = "POPLACH: " + item['label']
        system_state["sos_active"] = True
        system_state["sos_timer"] = time.time()
        # Odeslání HTTP požadavku probíhá ve vedlejším vlákně, aby nezaseklo vykreslování
        threading.Thread(target=send_http_request, args=(URL_SOS_ON,)).start()

    # 5. Lokální IoT integrace protokolu Zigbee (Odeslání přes zprostředkovatele)
    elif item.get("type") == "zigbee":
        try: mqtt_client.publish("zigbee2mqtt/zasuvka/set", '{"state": "TOGGLE"}')
        except: pass
        system_state["message"] = "Připraveno"

    elif item.get("type") == "zigbee_bell":
        try: mqtt_client.publish("zigbee2mqtt/zvonek/set", '{"state": "ON"}')
        except: pass
        system_state["message"] = "Připraveno"

    # 6. Infračervené ovládání starších zařízení (Strategie "Kobercový nálet")
    elif item.get("type") == "ir":
        code_file = item['code']
        device_type = item.get('device', 'tv') 
        
        # Nastavení správného kontextu pro iteraci značek a informační zprávy
        if device_type == "tv": brands = AVAILABLE_TV_BRANDS; system_state["message"] = f"TV: {item['label']}"
        elif device_type == "ac": brands = AVAILABLE_AC_BRANDS; system_state["message"] = f"KLÍMA: {item['label']}"
        elif device_type == "radio": brands = AVAILABLE_RADIO_BRANDS; system_state["message"] = f"RÁDIO: {item['label']}"
        elif device_type == "led": brands = AVAILABLE_LED_BRANDS; system_state["message"] = f"LED: {item['label']}"
        else: brands = []
        
        # Algoritmus iteruje přes všechny dostupné značky daného spotřebiče a odešle
        # příslušný RAW signál za sebou všem. Odpadá tak nutnost nastavovat konkrétní typ TV v menu.
        for brand in brands:
            path = f"/home/lukas/rpi/ir_codes/{device_type}/{brand}/{code_file}.txt"
            if not os.path.exists(path): continue
            try: 
                # Spustí kernel-space linuxovou utilitu pro absolutně přesné vyslání RAW signálu
                subprocess.run(["ir-ctl", "-d", "/dev/lirc0", "--send", path], check=True)
                # Nutná ochranná prodleva pro oddělení signálů v prostoru (prevence interferencí)
                time.sleep(0.3) 
            except Exception as e: print(e)

# ==========================================
# 7. INICIALIZACE MQTT KLIENTA
# ==========================================
mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
mqtt_client.on_message = on_mqtt_message

def on_connect(client, userdata, flags, reason_code, properties):
    # Přihlášení k odběru všech dat směřujících z/do ovladače pod příslušným tématem
    client.subscribe("joystick/#")
mqtt_client.on_connect = on_connect

def start_mqtt():
    """Funkce běžící v samostatném vlákně zajišťující permanentní síťové naslouchání."""
    while True:
        try:
            mqtt_client.connect("localhost", 1883, 60)
            mqtt_client.loop_forever()
        except: time.sleep(5)

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
    Hlavní synchronizační endpoint pro AJAX Polling. 
    Zároveň automaticky utne běžící SOS poplach po uplynutí 120 vteřin.
    """
    if system_state.get("sos_active") and (time.time() - system_state.get("sos_timer", 0) > 120):
        system_state["sos_active"] = False
        system_state["message"] = "Připraveno"
        threading.Thread(target=send_http_request, args=(URL_SOS_OFF,)).start()
    return jsonify(system_state)

@app.route('/api/click/<int:index>', methods=['POST'])
def web_click(index):
    """Endpoint umožňující ovládat položky menu manuálně pomocí dotyku či myši."""
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
    """Endpoint pro vyvolání vzdálené aktualizace (OTA) mikrokontroléru ESP32."""
    mqtt_client.publish("joystick/ota", "START")
    system_state["message"] = "Povel k aktualizaci odeslán."
    return jsonify({"status": "ota_started"})

@app.route('/api/tts_toggle', methods=['POST'])
def toggle_tts():
    """Přepíná globální proměnnou, která povoluje/zakazuje zvukový výstup (espeak)."""
    system_state["tts_enabled"] = not system_state.get("tts_enabled", False)
    
    if system_state["tts_enabled"]:
        speak_text("Hlasový asistent zapnut")
    else:
        # Umlčení probíhajícího monologu při vypnutí
        subprocess.run(["killall", "espeak"], stderr=subprocess.DEVNULL)
    return jsonify({"status": "ok", "tts_enabled": system_state["tts_enabled"]})

# ==========================================
# 9. VSTUPNÍ BOD APLIKACE
# ==========================================
if __name__ == '__main__':
    # Start MQTT klienta jako Daemona (vlákno se ukončí spolu s programem)
    threading.Thread(target=start_mqtt, daemon=True).start()
    # Start webového serveru (0.0.0.0 povoluje přístup odkudkoliv ze sítě či P2P tunelu)
    app.run(host='0.0.0.0', port=5000, debug=False)
