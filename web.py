"""
ASISTENČNÍ HUB - BACKEND APLIKACE
---------------------------------
Tento skript slouží jako hlavní řídící uzel (backend) pro asistenční systém ovládaný joystickem.
Zajišťuje komunikaci mezi hardwarovým ovladačem (přes MQTT), uživatelským rozhraním (přes Flask API),
chytrou domácností (přes Zigbee2MQTT) a infračervenými zařízeními (přes systémový LIRC/ir-ctl).

Modul je koncipován jako stavový automat, který na základě vstupů mění svůj vnitřní model
a poskytuje jej přes REST API asynchronnímu frontendu (polling).
Rok: 2026
"""

# --- IMPORTY KNIHOVEN ---
from flask import Flask, render_template, jsonify, request
import paho.mqtt.client as mqtt  # Zajišťuje asynchronní komunikaci přes protokol MQTT
import threading                 # Umožňuje běh MQTT klienta v odděleném vlákně nezávisle na webovém serveru
import time                      # Slouží pro časování (např. nezbytné prodlevy při sekvenčním vysílání IR kódů)
import subprocess                # Umožňuje volání systémových příkazů OS Linux (zde pro obsluhu IR vysílače)
import datetime                  # Práce s reálným časem pro účely přesného logování událostí
import os                        # Přidáno pro ověřování fyzické existence nahraných IR souborů

# Inicializace instance webového serveru Flask
app = Flask(__name__)

# ==========================================
# 1. DEFINICE STROMOVÉHO MENU A UŽIVATELSKÉHO ROZHRANÍ
# ==========================================

# Hlavní obrazovka 1: Běžné požadavky (Výchozí stav)
MENU_HOME = [
    {"id": 0, "label": "MÁM ŽÍZEŇ", "icon": "fa-glass-water", "color": "primary", "type": "req"},
    {"id": 1, "label": "MÁM HLAD", "icon": "fa-utensils", "color": "warning", "type": "req"},
    {"id": 2, "label": "SVĚTLO", "icon": "fa-lightbulb", "color": "success", "type": "zigbee"},
    {"id": 3, "label": "ZVONEK", "icon": "fa-bell", "color": "info", "type": "zigbee_bell"},
    {"id": 4, "label": "POMOC", "icon": "fa-hand-holding-medical", "color": "danger", "type": "req"},
    {"id": 5, "label": "ZRUŠIT", "icon": "fa-rotate-left", "color": "secondary", "type": "cancel"} # Vyřešení/Zrušení alarmu
]

# Hlavní obrazovka 2: Výběr zařízení (Dostupné po stisknutí páčky NAHORU)
MENU_DEVICES = [
    {"id": 0, "label": "TELEVIZE", "icon": "fa-tv", "color": "secondary", "type": "submenu", "target": "tv_controls"},
    {"id": 1, "label": "KLIMATIZACE", "icon": "fa-snowflake", "color": "info", "type": "submenu", "target": "ac_controls"},
    {"id": 2, "label": "RÁDIO", "icon": "fa-radio", "color": "primary", "type": "submenu", "target": "radio_controls"},
    {"id": 3, "label": "LED PÁSKY", "icon": "fa-lightbulb", "color": "warning", "type": "submenu", "target": "led_controls"},
    {"id": 4, "label": "DOMŮ", "icon": "fa-house", "color": "secondary", "type": "back"}
]

# Podmenu: Ovládání Televize
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
    {"id": 12, "label": "SEZNAM KANÁLŮ", "icon": "fa-list", "color": "info", "type": "ir", "device": "tv", "code": "guide"},
    {"id": 13, "label": "ZPĚT", "icon": "fa-arrow-left", "color": "secondary", "type": "back"}
]

# Podmenu: Ovládání Klimatizace (Rozděleno na Zapnout a Vypnout)
MENU_AC_CONTROLS = [
    {"id": 0, "label": "ZAPNOUT", "icon": "fa-power-off", "color": "success", "type": "ir", "device": "ac", "code": "power_on"},
    {"id": 1, "label": "VYPNOUT", "icon": "fa-power-off", "color": "danger", "type": "ir", "device": "ac", "code": "power_off"},
    {"id": 2, "label": "TEPLOTA +", "icon": "fa-temperature-arrow-up", "color": "warning", "type": "ir", "device": "ac", "code": "temp_up"},
    {"id": 3, "label": "TEPLOTA -", "icon": "fa-temperature-arrow-down", "color": "info", "type": "ir", "device": "ac", "code": "temp_down"},
    {"id": 4, "label": "ZPĚT", "icon": "fa-arrow-left", "color": "secondary", "type": "back"}
]

# Podmenu: Ovládání Rádia
MENU_RADIO_CONTROLS = [
    {"id": 0, "label": "ZAP/VYP", "icon": "fa-power-off", "color": "danger", "type": "ir", "device": "radio", "code": "power"},
    {"id": 1, "label": "STANICE +", "icon": "fa-arrow-up", "color": "info", "type": "ir", "device": "radio", "code": "ch_up"},
    {"id": 2, "label": "STANICE -", "icon": "fa-arrow-down", "color": "info", "type": "ir", "device": "radio", "code": "ch_down"},
    {"id": 3, "label": "HLASITOST +", "icon": "fa-volume-high", "color": "secondary", "type": "ir", "device": "radio", "code": "vol_up"},
    {"id": 4, "label": "HLASITOST -", "icon": "fa-volume-low", "color": "secondary", "type": "ir", "device": "radio", "code": "vol_down"},
    {"id": 5, "label": "ZPĚT", "icon": "fa-arrow-left", "color": "secondary", "type": "back"}
]

# Podmenu: Ovládání LED pásků
MENU_LED_CONTROLS = [
    {"id": 0, "label": "ZAP/VYP", "icon": "fa-power-off", "color": "danger", "type": "ir", "device": "led", "code": "power"},
    {"id": 1, "label": "ČERVENÁ", "icon": "fa-palette", "color": "danger", "type": "ir", "device": "led", "code": "color_red"},
    {"id": 2, "label": "ZELENÁ", "icon": "fa-palette", "color": "success", "type": "ir", "device": "led", "code": "color_green"},
    {"id": 3, "label": "MODRÁ", "icon": "fa-palette", "color": "info", "type": "ir", "device": "led", "code": "color_blue"},
    {"id": 4, "label": "ZPĚT", "icon": "fa-arrow-left", "color": "secondary", "type": "back"}
]

# Centrální registr všech menu pro dynamické přepínání (Routing) na základě parametru "target"
MENUS = {
    "home": MENU_HOME,
    "devices": MENU_DEVICES,
    "tv_controls": MENU_TV_CONTROLS,
    "ac_controls": MENU_AC_CONTROLS,
    "radio_controls": MENU_RADIO_CONTROLS,
    "led_controls": MENU_LED_CONTROLS
}

# Konfigurační seznamy podporovaných značek pro sekvenční vysílání IR kódů (tzv. "kobercový nálet")
AVAILABLE_TV_BRANDS = ["tcl", "sony", "lg", "panasonic", "gogen"]
AVAILABLE_AC_BRANDS = ["toshiba", "mitsubishi"]
AVAILABLE_RADIO_BRANDS = ["auna", "onkyo"]
AVAILABLE_LED_BRANDS = ["generic_rgb"]

# ==========================================
# 2. STAVOVÝ MODEL SYSTÉMU (State Management)
# ==========================================
# Globální slovník uchovávající aktuální stav celého systému. 
# Webový frontend tento stav vyčítá každých 300 ms a podle něj reaguje.
system_state = {
    "mode": "home",              # Značí aktuální hlavní obrazovku (home = Požadavky, devices = Výběr zařízení)
    "current_menu": MENU_HOME,   # Reference na pole s aktuálně zobrazovaným menu
    "menu_history": [],          # LIFO zásobník (stack) pro implementaci funkce "Krok zpět" v podmenu
    "selected_index": 0,         # Index aktuálně zvýrazněné položky (pozice kurzoru joysticku)
    "message": "Připraveno",     # Textový stavový výstup pro horní informační panel
    "connection": "SLEEP",       # Stav připojení BLE/MQTT ovladače (SLEEP, CONNECTING, READY)
    "last_action": 0             # Časové razítko (timestamp) poslední akce pro spuštění UI animací
}

# ==========================================
# 3. LOGOVACÍ SYSTÉM
# ==========================================
def log_activity(action):
    """
    Zaznamená specifikovanou událost do textového logovacího souboru s aktuálním časovým razítkem.
    Zajišťuje auditní stopu chování systému a interakcí pacienta.
    """
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open("/home/lukas/rpi/aktivita_systemu.log", "a") as f:
            f.write(f"[{timestamp}] - {action}\n")
    except IOError as e:
        pass # Ignorování chyby, pokud logovací soubor není dostupný (zabrání pádu aplikace)
    print(f"Zapsáno do logu: [{timestamp}] - {action}")

# ==========================================
# 4. OBSLUHA MQTT PROTOKOLU (Příjem povelů z HW)
# ==========================================
def on_message(client, userdata, msg):
    """Callback funkce volaná při přijetí zprávy od MQTT brokera z hardwarového ovladače."""
    try:
        topic = msg.topic
        payload = msg.payload.decode()
        
        # Zpracování stavu připojení ovladače (Heartbeat/Status)
        if topic == "joystick/status":
            system_state["connection"] = payload
            if payload == "READY": log_activity("Ovladač se úspěšně připojil.")
                
        # Zpracování samotných směrových povelů
        elif topic == "joystick/command":
            process_command(payload)
    except Exception as e: print(e)

def process_command(cmd):
    """Vyhodnocuje povely přijaté z joysticku a mapuje je na logické navigační funkce UI."""
    log_activity(f"Přijat příkaz od pacienta: {cmd}")
    
    if cmd == "UP": go_back()                   # Akce NAHORU: Krok zpět nebo přepnutí režimu obrazovky
    elif cmd == "RIGHT": move_selection(1)      # Akce DOPRAVA: Další položka
    elif cmd == "LEFT": move_selection(-1)      # Akce DOLEVA: Předchozí položka
    elif cmd in ["DOWN", "SELECT"]: trigger_action() # Akce DOLŮ/SELECT: Potvrzení výběru

def move_selection(direction):
    """
    Zajišťuje cyklický posun kurzoru v aktuálním menu.
    Operátor modulo (%) zaručuje rotaci z poslední karty zpět na první.
    """
    menu_len = len(system_state["current_menu"])
    system_state["selected_index"] = (system_state["selected_index"] + direction) % menu_len

def go_back():
    """
    Strukturální navigační logika (Ošetřuje pohyb joysticku NAHORU).
    1. Nachází-li se uživatel v hlubokém podmenu (zásobník není prázdný), funkce provede návrat ('pop') o úroveň výš.
    2. Je-li historie prázdná (uživatel je na hlavní obrazovce), slouží jako pákový přepínač 
       mezi obrazovkou "Běžné požadavky" a "Výběr zařízení".
    """
    if len(system_state["menu_history"]) > 0:
        # Extrahování předchozího stavu ze zásobníku (LIFO)
        prev_state = system_state["menu_history"].pop()
        system_state["current_menu"] = prev_state["menu"]
        system_state["selected_index"] = prev_state["index"]
        system_state["message"] = prev_state["message"]
    else:
        # PŘEPÍNÁNÍ HLAVNÍCH REŽIMŮ (Zajišťuje čisté a nepřehlcené rozhraní)
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

# ==========================================
# 5. VÝKONNÁ LOGIKA (Zpracování potvrzených akcí)
# ==========================================
def trigger_action():
    """
    Hlavní výkonná funkce (Spouštěč). Rozhoduje o akci na základě typu (type) aktuálně vybrané položky.
    """
    idx = system_state["selected_index"]
    item = system_state["current_menu"][idx]
    
    # Aktualizace timestampu pro spuštění vizuální haptické odezvy na webu (probliknutí)
    system_state["last_action"] = time.time()
    
    # 1. NAVIGACE DO HLUBŠÍ ÚROVNĚ (Podmenu)
    if item.get("type") == "submenu":
        # Uložení současného stavu do zásobníku před ponorem
        system_state["menu_history"].append({
            "menu": system_state["current_menu"],
            "index": system_state["selected_index"],
            "message": system_state["message"]
        })
        system_state["message"] = f"Menu: {item['label']}"
        target_menu = item["target"]
        system_state["current_menu"] = MENUS[target_menu]
        system_state["selected_index"] = 0 # Reset kurzoru pro novou obrazovku
        
    # 2. TLAČÍTKO ZPĚT / DOMŮ (Softwarová alternativa pohybu páčky nahoru)
    elif item.get("type") == "back":
        go_back()

    # 3. TLAČÍTKO ZRUŠIT (Funkce pro ošetřovatele: vyřešení stavu nouze/požadavku)
    elif item.get("type") == "cancel":
        system_state["message"] = "Připraveno"

    # 4. BĚŽNÉ POŽADAVKY (Žízeň, Hlad, Pomoc...)
    elif item.get("type") == "req":
        system_state["message"] = f"Vybráno: {item['label']}"
        
    # 5. OVLÁDÁNÍ CHYTRÉ DOMÁCNOSTI (Zigbee2MQTT)
    elif item.get("type") == "zigbee":
        try: mqtt_client.publish("zigbee2mqtt/zasuvka/set", '{"state": "TOGGLE"}')
        except: pass
        system_state["message"] = "Světlo přepnuto"

    elif item.get("type") == "zigbee_bell":
        try: mqtt_client.publish("zigbee2mqtt/zvonek/set", '{"state": "ON"}')
        except: pass
        system_state["message"] = "Zvonek aktivován!"

    # 6. INFRAČERVENÉ OVLÁDÁNÍ - SEKVENČNÍ VYSÍLÁNÍ (tzv. "Kobercový nálet")
    elif item.get("type") == "ir":
        code_file = item['code']
        device_type = item.get('device', 'tv') # Identifikátor kořenového adresáře kódů (tv, ac, radio, led)
        
        # Mapování dynamických textů a polí značek podle vybraného typu HW
        if device_type == "tv":
            brands = AVAILABLE_TV_BRANDS
            system_state["message"] = f"TV: {item['label']}"
        elif device_type == "ac":
            brands = AVAILABLE_AC_BRANDS
            system_state["message"] = f"KLÍMA: {item['label']}"
        elif device_type == "radio":
            brands = AVAILABLE_RADIO_BRANDS
            system_state["message"] = f"RÁDIO: {item['label']}"
        elif device_type == "led":
            brands = AVAILABLE_LED_BRANDS
            system_state["message"] = f"LED: {item['label']}"
        else:
            brands = []
        
        # Iterace přes seznam podporovaných značek. Algoritmus odešle daný příkaz postupně
        # pro všechny značky v definované kategorii s nutnou pauzou proti zarušení IR spektra.
        for brand in brands:
            path = f"/home/lukas/rpi/ir_codes/{device_type}/{brand}/{code_file}.txt"
            
            # --- BEZPEČNOSTNÍ POJISTKA ---
            # Zkontroluje, zda soubor s kódem na disku opravdu existuje.
            # Tím se zabrání zbytečným pádům programu u nekompletně nahraných ovladačů
            # a přeskočí se značky, které pro dané tlačítko nemají nahraný soubor.
            if not os.path.exists(path):
                print(f"VAROVÁNÍ: IR Soubor nenalezen (přeskakuji) - {path}")
                continue
                
            print(f"IR Vysílání ({device_type.upper()} - {brand}): {path}")
            try: 
                # Synchronní exekuce subprocesu LIRC pro odeslání infračerveného signálu
                subprocess.run(["ir-ctl", "-d", "/dev/lirc0", "--send", path], check=True)
                time.sleep(0.3) # Ochranná prodleva pro spolehlivé přečtení kódu přijímačem
            except Exception as e: print(e)

# ==========================================
# 6. INICIALIZACE MQTT KLIENTA NA POZADÍ
# ==========================================
mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
mqtt_client.on_message = on_message

def start_mqtt():
    """Udržuje trvalé spojení s lokálním MQTT brokerem ve vyhrazeném vlákně (Daemon Thread)."""
    while True:
        try:
            mqtt_client.connect("localhost", 1883, 60)
            mqtt_client.subscribe("joystick/#")
            mqtt_client.loop_forever()
        except: time.sleep(5) # Automatický pokus o obnovu při výpadku služby

# ==========================================
# 7. FLASK REST API (Komunikační rozhraní pro frontend)
# ==========================================
@app.route('/')
def index():
    """Servíruje hlavní HTML šablonu (Single Page Application)."""
    return render_template('index.html')

@app.route('/api/status')
def get_status():
    """Endpoint pro kontinuální polling. Vrací serializovaný globální stavový model do JS klienta."""
    return jsonify(system_state)

@app.route('/api/click/<int:index>', methods=['POST'])
def web_click(index):
    """API endpoint pro dotykové/manuální ovládání UI pečovatelem (obchází HW joystick)."""
    if 0 <= index < len(system_state["current_menu"]):
        system_state["selected_index"] = index
        trigger_action()
    return jsonify({"status": "ok"})

@app.route('/api/reset', methods=['POST'])
def reset_message():
    """API endpoint pro manuální vyřešení/zrušení poplachu přes UI rozhraní."""
    system_state["message"] = "Připraveno"
    return jsonify({"status": "reset"})

# ==========================================
# 8. HLAVNÍ SPOUŠTĚCÍ BLOK (Entry Point)
# ==========================================
if __name__ == '__main__':
    log_activity("--- SYSTÉM NASTARTOVÁN ---")
    
    # Start dedikovaného vlákna pro příjem MQTT zpráv z hardwaru
    threading.Thread(target=start_mqtt, daemon=True).start()
    
    # Spuštění webového serveru naslouchajícího na všech lokálních IP adresách sítě (0.0.0.0)
    app.run(host='0.0.0.0', port=5000, debug=False)
