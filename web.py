"""
ASISTENČNÍ HUB - BACKEND APLIKACE
---------------------------------
Tento skript slouží jako hlavní řídící uzel (backend) pro asistenční systém ovládaný joystickem.
Zajišťuje komunikaci mezi hardwarovým ovladačem (přes MQTT), uživatelským rozhraním (přes Flask API),
chytrou domácností (přes Zigbee2MQTT) a infračervenými zařízeními (přes systémový LIRC/ir-ctl).
"""

# --- IMPORTY KNIHOVEN ---
from flask import Flask, render_template, jsonify, request
import paho.mqtt.client as mqtt  # Zajišťuje asynchronní komunikaci přes protokol MQTT
import threading                 # Umožňuje běh MQTT klienta v odděleném vlákně nezávisle na webovém serveru
import time                      # Slouží pro časování (např. nezbytné prodlevy při sekvenčním vysílání IR kódů)
import subprocess                # Umožňuje volání systémových příkazů OS Linux (zde pro obsluhu IR vysílače)
import datetime                  # Práce s reálným časem pro účely přesného logování událostí

# Inicializace instance webového serveru Flask
app = Flask(__name__)

# ==========================================
# 1. DEFINICE STROMOVÉHO MENU A UŽIVATELSKÉHO ROZHRANÍ
# ==========================================
# Následující datové struktury (seznamy slovníků) definují jednotlivé obrazovky uživatelského rozhraní.
# Každá položka obsahuje metadata pro frontend (ikona, barva) a funkční parametry (typ akce, cíl podmenu).

MENU_HOME = [
    {"id": 0, "label": "MÁM ŽÍZEŇ", "icon": "fa-glass-water", "color": "primary", "type": "req"},
    {"id": 1, "label": "MÁM HLAD", "icon": "fa-utensils", "color": "warning", "type": "req"},
    {"id": 2, "label": "SVĚTLO", "icon": "fa-lightbulb", "color": "success", "type": "zigbee"},
    {"id": 3, "label": "ZVONEK", "icon": "fa-bell", "color": "info", "type": "zigbee_bell"},
    {"id": 4, "label": "POMOC", "icon": "fa-hand-holding-medical", "color": "danger", "type": "req"},
    {"id": 5, "label": "TELEVIZE", "icon": "fa-tv", "color": "secondary", "type": "submenu", "target": "tv_controls"},
    {"id": 6, "label": "KLIMATIZACE", "icon": "fa-snowflake", "color": "info", "type": "submenu", "target": "ac_controls"},
    {"id": 7, "label": "RÁDIO", "icon": "fa-radio", "color": "primary", "type": "submenu", "target": "radio_controls"},
    {"id": 8, "label": "LED PÁSKY", "icon": "fa-lightbulb", "color": "warning", "type": "submenu", "target": "led_controls"}
]

# Podmenu: Ovládání Televize
MENU_TV_CONTROLS = [
    {"id": 0, "label": "ZAP/VYP", "icon": "fa-power-off", "color": "danger", "type": "ir", "device": "tv", "code": "power"},
    {"id": 1, "label": "PROGRAM +", "icon": "fa-arrow-up", "color": "info", "type": "ir", "device": "tv", "code": "ch_up"},
    {"id": 2, "label": "PROGRAM -", "icon": "fa-arrow-down", "color": "info", "type": "ir", "device": "tv", "code": "ch_down"},
    {"id": 3, "label": "HLASITOST +", "icon": "fa-volume-high", "color": "secondary", "type": "ir", "device": "tv", "code": "vol_up"},
    {"id": 4, "label": "HLASITOST -", "icon": "fa-volume-low", "color": "secondary", "type": "ir", "device": "tv", "code": "vol_down"},
    {"id": 5, "label": "ZPĚT", "icon": "fa-arrow-left", "color": "secondary", "type": "back"}
]

# Podmenu: Ovládání Klimatizace
MENU_AC_CONTROLS = [
    {"id": 0, "label": "ZAP/VYP", "icon": "fa-power-off", "color": "danger", "type": "ir", "device": "ac", "code": "power"},
    {"id": 1, "label": "TEPLOTA +", "icon": "fa-temperature-arrow-up", "color": "warning", "type": "ir", "device": "ac", "code": "temp_up"},
    {"id": 2, "label": "TEPLOTA -", "icon": "fa-temperature-arrow-down", "color": "info", "type": "ir", "device": "ac", "code": "temp_down"},
    {"id": 3, "label": "ZPĚT", "icon": "fa-arrow-left", "color": "secondary", "type": "back"}
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

# Centrální registr všech menu pro dynamické přepínání na základě parametru "target"
MENUS = {
    "home": MENU_HOME,
    "tv_controls": MENU_TV_CONTROLS,
    "ac_controls": MENU_AC_CONTROLS,
    "radio_controls": MENU_RADIO_CONTROLS,
    "led_controls": MENU_LED_CONTROLS
}

# Konfigurační seznamy podporovaných značek pro sekvenční vysílání IR kódů (tzv. "kobercový nálet")
AVAILABLE_TV_BRANDS = ["tcl", "sony", "samsung"]
AVAILABLE_AC_BRANDS = ["lg", "daikin", "samsung", "panasonic"]
AVAILABLE_RADIO_BRANDS = ["sony", "philips"]
AVAILABLE_LED_BRANDS = ["generic_rgb"]

# ==========================================
# 2. STAVOVÝ MODEL SYSTÉMU (State Management)
# ==========================================
# Globální slovník uchovávající aktuální stav celého systému. 
# Webový frontend tento stav pravidelně vyčítá (polling) a podle něj aktualizuje UI.
system_state = {
    "current_menu": MENU_HOME,   # Reference na aktuálně zobrazované menu
    "menu_history": [],          # LIFO zásobník (stack) pro implementaci funkce "Krok zpět"
    "selected_index": 0,         # Index aktuálně zvýrazněné položky (pro vizualizaci kurzoru)
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
    Slouží pro diagnostiku systému a monitorování aktivity uživatele/pacienta.
    
    Args:
        action (str): Popis události, která má být zaznamenána.
    """
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open("/home/lukas/rpi/aktivita_systemu.log", "a") as f:
            f.write(f"[{timestamp}] - {action}\n")
    except IOError as e:
        print(f"Chyba při zápisu do logu: {e}")
    print(f"Zapsáno do logu: [{timestamp}] - {action}")

# ==========================================
# 4. OBSLUHA MQTT PROTOKOLU (Příjem povelů)
# ==========================================
def on_message(client, userdata, msg):
    """
    Callback funkce volaná automaticky při přijetí nové zprávy z MQTT brokeru.
    Filtruje zprávy podle topicu a předává je k dalšímu zpracování.
    """
    try:
        topic = msg.topic
        payload = msg.payload.decode()
        
        # Zpracování stavu připojení hardwarového ovladače
        if topic == "joystick/status":
            system_state["connection"] = payload
            if payload == "READY":
                log_activity("Ovladač se úspěšně připojil.")
                
        # Zpracování směrových povelů z joysticku
        elif topic == "joystick/command":
            process_command(payload)
    except Exception as e: 
        print(f"Chyba při zpracování MQTT zprávy: {e}")

def process_command(cmd):
    """
    Vyhodnocuje povely přijaté z joysticku a mapuje je na odpovídající navigační funkce.
    """
    log_activity(f"Přijat příkaz od pacienta: {cmd}")
    
    if cmd == "UP": 
        go_back()                   # Návrat v hierarchii stromu o úroveň výš
    elif cmd == "RIGHT": 
        move_selection(1)           # Krok vpřed v lineárním menu
    elif cmd == "LEFT": 
        move_selection(-1)          # Krok vzad v lineárním menu
    elif cmd in ["DOWN", "SELECT"]: 
        trigger_action()            # Potvrzení výběru (vstup do podmenu nebo spuštění akce)

def move_selection(direction):
    """
    Zajišťuje cyklický posun kurzoru v aktuálním menu.
    Používá operátor modulo pro zajištění rotace (z poslední položky na první a naopak).
    """
    menu_len = len(system_state["current_menu"])
    system_state["selected_index"] = (system_state["selected_index"] + direction) % menu_len

def go_back():
    """
    Implementuje funkci "Zpět" pomocí výběru z historie stromu.
    Pokud je historie prázdná, uživatel se nachází v hlavním kořenovém menu.
    """
    if len(system_state["menu_history"]) > 0:
        prev_state = system_state["menu_history"].pop()
        system_state["current_menu"] = prev_state["menu"]
        system_state["selected_index"] = prev_state["index"]
        system_state["message"] = prev_state["message"]
    else:
        system_state["message"] = "Jste v hlavním menu"

# ==========================================
# 5. VÝKONNÁ LOGIKA (Zpracování potvrzených akcí)
# ==========================================
def trigger_action():
    """
    Hlavní výkonná funkce systému. Přečte parametry aktuálně vybrané položky a na
    základě jejího 'type' provede příslušnou systémovou nebo hardwarovou akci.
    """
    idx = system_state["selected_index"]
    item = system_state["current_menu"][idx]
    
    # Aktualizace časového razítka pro spuštění vizuální odezvy v prohlížeči
    system_state["last_action"] = time.time()
    
    # --- POHYB VE STROMU (Navigace) ---
    if item.get("type") == "submenu":
        # Uložení současného stavu do historie před přechodem do hlubší úrovně
        system_state["menu_history"].append({
            "menu": system_state["current_menu"],
            "index": system_state["selected_index"],
            "message": system_state["message"]
        })
        system_state["message"] = f"Menu: {item['label']}"
        target_menu = item["target"]
        system_state["current_menu"] = MENUS[target_menu]
        system_state["selected_index"] = 0  # Reset kurzoru pro nové podmenu
        
    elif item.get("type") == "back":
        go_back()

    # --- BĚŽNÉ POŽADAVKY (Asistence) ---
    elif item.get("type") == "req":
        system_state["message"] = f"Vybráno: {item['label']}"
        
    # --- CHYTRÁ DOMÁCNOST (Zigbee) ---
    elif item.get("type") == "zigbee":
        try: 
            mqtt_client.publish("zigbee2mqtt/zasuvka/set", '{"state": "TOGGLE"}')
            system_state["message"] = "Světlo přepnuto"
        except Exception as e: 
            print(f"Chyba Zigbee (světlo): {e}")

    elif item.get("type") == "zigbee_bell":
        try: 
            mqtt_client.publish("zigbee2mqtt/zvonek/set", '{"state": "ON"}')
            system_state["message"] = "Zvonek aktivován!"
        except Exception as e: 
            print(f"Chyba Zigbee (zvonek): {e}")

    # --- INFRAČERVENÉ OVLÁDÁNÍ (Sekvenční vysílání) ---
    elif item.get("type") == "ir":
        code_file = item['code']
        device_type = item.get('device', 'tv') # Identifikátor podadresáře (tv, ac, radio, led)
        
        # Mapování typu zařízení na příslušný list podporovaných značek
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
        
        # Algoritmus "kobercového náletu": Iterace přes všechny relevantní značky
        # a postupné odeslání IR kódu s definovanou prodlevou proti zahlcení přijímače.
        for brand in brands:
            path = f"/home/lukas/rpi/ir_codes/{device_type}/{brand}/{code_file}.txt"
            print(f"IR Vysílání ({device_type.upper()} - {brand}): {path}")
            try: 
                # Synchronní blokující volání systémového procesu lirc/ir-ctl
                subprocess.run(["ir-ctl", "-d", "/dev/lirc0", "--send", path], check=True)
                time.sleep(0.3) # Kritická pauza pro spolehlivé přečtení kódu koncovým zařízením
            except subprocess.CalledProcessError as e:
                print(f"Chyba při exekuci ir-ctl ({brand}): {e}")
            except FileNotFoundError:
                print(f"Soubor s IR kódem nenalezen: {path}")

# ==========================================
# 6. INICIALIZACE MQTT KLIENTA NA POZADÍ
# ==========================================
mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
mqtt_client.on_message = on_message

def start_mqtt():
    """
    Udržuje permanentní spojení s lokálním MQTT brokerem.
    Funkce běží v nekonečné smyčce ve vyhrazeném vlákně.
    """
    while True:
        try:
            mqtt_client.connect("localhost", 1883, 60)
            mqtt_client.subscribe("joystick/#")
            mqtt_client.loop_forever()
        except Exception as e:
            print(f"Ztráta spojení s MQTT brokerem. Pokus o obnovu za 5s. ({e})")
            time.sleep(5)

# ==========================================
# 7. FLASK REST API (Komunikační rozhraní pro frontend)
# ==========================================
@app.route('/')
def index():
    """Vykreslí výchozí HTML šablonu uživatelského rozhraní."""
    return render_template('index.html')

@app.route('/api/status')
def get_status():
    """Endpoint pro polling frontendu. Vrací serializovaný stavový model v JSON formátu."""
    return jsonify(system_state)

@app.route('/api/click/<int:index>', methods=['POST'])
def web_click(index):
    """
    Umožňuje ovládání systému přes dotykový displej nebo myš.
    Simuluje chování mechanického joysticku posunutím kurzoru na specifikovaný index a potvrzením.
    """
    if 0 <= index < len(system_state["current_menu"]):
        system_state["selected_index"] = index
        trigger_action()
    return jsonify({"status": "ok"})

@app.route('/api/reset', methods=['POST'])
def reset_message():
    """Endpoint vyhrazený pro personál. Resetuje alarmové hlášení na výchozí stav."""
    system_state["message"] = "Připraveno"
    return jsonify({"status": "reset"})

# ==========================================
# 8. HLAVNÍ SPOUŠTĚCÍ BLOK (Entry Point)
# ==========================================
if __name__ == '__main__':
    log_activity("--- SYSTÉM NASTARTOVÁN ---")
    
    # Start MQTT klienta jako "daemon thread" (ukončí se automaticky při vypnutí hlavního programu)
    threading.Thread(target=start_mqtt, daemon=True).start()
    
    # Spuštění produkčního/vývojového web serveru (přístupné ze všech IP adres v lokální síti)
    app.run(host='0.0.0.0', port=5000, debug=False)
