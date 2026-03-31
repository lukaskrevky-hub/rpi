# IMPORTY KNIHOVEN
from flask import Flask, render_template, jsonify, request
import paho.mqtt.client as mqtt
import threading
import time
import subprocess
import datetime

# Vytvoření instance webové aplikace
app = Flask(__name__)

# --- DEFINICE STROMOVÉHO MENU ---

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

# Podmenu 1: TV (Ověř, že "device" je "tv")
MENU_TV_CONTROLS = [
    {"id": 0, "label": "ZAP/VYP", "icon": "fa-power-off", "color": "danger", "type": "ir", "device": "tv", "code": "power"},
    {"id": 1, "label": "PROGRAM +", "icon": "fa-arrow-up", "color": "info", "type": "ir", "device": "tv", "code": "ch_up"},
    {"id": 2, "label": "PROGRAM -", "icon": "fa-arrow-down", "color": "info", "type": "ir", "device": "tv", "code": "ch_down"},
    {"id": 3, "label": "HLASITOST +", "icon": "fa-volume-high", "color": "secondary", "type": "ir", "device": "tv", "code": "vol_up"},
    {"id": 4, "label": "HLASITOST -", "icon": "fa-volume-low", "color": "secondary", "type": "ir", "device": "tv", "code": "vol_down"},
    {"id": 5, "label": "ZPĚT", "icon": "fa-arrow-left", "color": "secondary", "type": "back"}
]

# Podmenu 2: KLIMATIZACE (Ověř, že "device" je "ac")
MENU_AC_CONTROLS = [
    {"id": 0, "label": "ZAP/VYP", "icon": "fa-power-off", "color": "danger", "type": "ir", "device": "ac", "code": "power"},
    {"id": 1, "label": "TEPLOTA +", "icon": "fa-temperature-arrow-up", "color": "warning", "type": "ir", "device": "ac", "code": "temp_up"},
    {"id": 2, "label": "TEPLOTA -", "icon": "fa-temperature-arrow-down", "color": "info", "type": "ir", "device": "ac", "code": "temp_down"},
    {"id": 3, "label": "ZPĚT", "icon": "fa-arrow-left", "color": "secondary", "type": "back"}
]

# Podmenu 3: RÁDIO
MENU_RADIO_CONTROLS = [
    {"id": 0, "label": "ZAP/VYP", "icon": "fa-power-off", "color": "danger", "type": "ir", "device": "radio", "code": "power"},
    {"id": 1, "label": "STANICE +", "icon": "fa-arrow-up", "color": "info", "type": "ir", "device": "radio", "code": "ch_up"},
    {"id": 2, "label": "STANICE -", "icon": "fa-arrow-down", "color": "info", "type": "ir", "device": "radio", "code": "ch_down"},
    {"id": 3, "label": "HLASITOST +", "icon": "fa-volume-high", "color": "secondary", "type": "ir", "device": "radio", "code": "vol_up"},
    {"id": 4, "label": "HLASITOST -", "icon": "fa-volume-low", "color": "secondary", "type": "ir", "device": "radio", "code": "vol_down"},
    {"id": 5, "label": "ZPĚT", "icon": "fa-arrow-left", "color": "secondary", "type": "back"}
]

# Podmenu 4: LED PÁSKY
MENU_LED_CONTROLS = [
    {"id": 0, "label": "ZAP/VYP", "icon": "fa-power-off", "color": "danger", "type": "ir", "device": "led", "code": "power"},
    {"id": 1, "label": "ČERVENÁ", "icon": "fa-palette", "color": "danger", "type": "ir", "device": "led", "code": "color_red"},
    {"id": 2, "label": "ZELENÁ", "icon": "fa-palette", "color": "success", "type": "ir", "device": "led", "code": "color_green"},
    {"id": 3, "label": "MODRÁ", "icon": "fa-palette", "color": "info", "type": "ir", "device": "led", "code": "color_blue"},
    {"id": 4, "label": "ZPĚT", "icon": "fa-arrow-left", "color": "secondary", "type": "back"}
]

# Slovník všech menu
MENUS = {
    "home": MENU_HOME,
    "tv_controls": MENU_TV_CONTROLS,
    "ac_controls": MENU_AC_CONTROLS,
    "radio_controls": MENU_RADIO_CONTROLS,
    "led_controls": MENU_LED_CONTROLS
}

# Samostatné seznamy pro "kobercový nálet"
AVAILABLE_TV_BRANDS = ["tcl", "sony", "samsung"]
AVAILABLE_AC_BRANDS = ["lg", "daikin", "samsung", "panasonic"]
AVAILABLE_RADIO_BRANDS = ["sony", "philips"]
AVAILABLE_LED_BRANDS = ["generic_rgb"]

# --- CENTRÁLNÍ STAV SYSTÉMU ---
system_state = {
    "current_menu": MENU_HOME,
    "menu_history": [],
    "selected_index": 0,
    "message": "Připraveno",
    "connection": "SLEEP",
    "last_action": 0
}

# --- FUNKCE PRO ZÁPIS DO DENÍČKU ---
def log_activity(action):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open("/home/lukas/rpi/aktivita_systemu.log", "a") as f:
        f.write(f"[{timestamp}] - {action}\n")
    print(f"Zapsáno do logu: [{timestamp}] - {action}")

# --- MQTT LOGIKA ---
def on_message(client, userdata, msg):
    try:
        topic = msg.topic
        payload = msg.payload.decode()
        if topic == "joystick/status":
            system_state["connection"] = payload
            if payload == "READY":
                log_activity("Ovladač se úspěšně připojil.")
                
        elif topic == "joystick/command":
            process_command(payload)
    except Exception as e: print(e)

# Mozek ovládání s logikou stromu
def process_command(cmd):
    log_activity(f"Přijat příkaz od pacienta: {cmd}")
    
    if cmd == "UP": go_back()
    elif cmd == "RIGHT": move_selection(1)
    elif cmd == "LEFT": move_selection(-1)
    elif cmd == "DOWN" or cmd == "SELECT": trigger_action()

def move_selection(direction):
    menu_len = len(system_state["current_menu"])
    system_state["selected_index"] = (system_state["selected_index"] + direction) % menu_len

def go_back():
    if len(system_state["menu_history"]) > 0:
        prev_state = system_state["menu_history"].pop()
        system_state["current_menu"] = prev_state["menu"]
        system_state["selected_index"] = prev_state["index"]
        system_state["message"] = prev_state["message"]
    else:
        system_state["message"] = "Jste v hlavním menu"

# --- VYKONÁNÍ AKCE ---
def trigger_action():
    idx = system_state["selected_index"]
    item = system_state["current_menu"][idx]
    
    system_state["last_action"] = time.time()
    
    # 1. POHYB VE STROMU
    if item.get("type") == "submenu":
        system_state["menu_history"].append({
            "menu": system_state["current_menu"],
            "index": system_state["selected_index"],
            "message": system_state["message"]
        })
        system_state["message"] = f"Menu: {item['label']}"
        target_menu = item["target"]
        system_state["current_menu"] = MENUS[target_menu]
        system_state["selected_index"] = 0
        
    # 2. TLAČÍTKO ZPĚT
    elif item.get("type") == "back":
        go_back()

    # 3. ZÁKLADNÍ POŽADAVKY
    elif item.get("type") == "req":
        system_state["message"] = f"Vybráno: {item['label']}"
        
    # 4. ZIGBEE OVLÁDÁNÍ
    elif item.get("type") == "zigbee":
        try: mqtt_client.publish("zigbee2mqtt/zasuvka/set", '{"state": "TOGGLE"}')
        except: pass
        system_state["message"] = "Světlo přepnuto"

    elif item.get("type") == "zigbee_bell":
        try: mqtt_client.publish("zigbee2mqtt/zvonek/set", '{"state": "ON"}')
        except: pass
        system_state["message"] = "Zvonek aktivován!"

    # 5. IR VYSÍLÁNÍ (Televize i Klimatizace) - KOBERCOVÝ NÁLET
    elif item.get("type") == "ir":
        code_file = item['code']
        device_type = item.get('device', 'tv') # "tv", "ac", "radio" nebo "led"
        
        # Přiřadíme seznam značek a nastavíme zprávu pro UI
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
        
        # Cesta se nyní skládá velmi čistě pomocí "device_type" (tv/ac/radio/led)
        for brand in brands:
            path = f"/home/lukas/rpi/ir_codes/{device_type}/{brand}/{code_file}.txt"
            print(f"IR Vysílání ({device_type.upper()} - {brand}): {path}")
            try: 
                subprocess.run(["ir-ctl", "-d", "/dev/lirc0", "--send", path])
                time.sleep(0.3) 
            except Exception as e: 
                print(f"Chyba IR ({brand}): {e}")

# --- START SLUŽEB NA POZADÍ ---
mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
mqtt_client.on_message = on_message

def start_mqtt():
    while True:
        try:
            mqtt_client.connect("localhost", 1883, 60)
            mqtt_client.subscribe("joystick/#")
            mqtt_client.loop_forever()
        except: time.sleep(5)

# --- FLASK API ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status')
def get_status():
    return jsonify(system_state)

@app.route('/api/click/<int:index>', methods=['POST'])
def web_click(index):
    if 0 <= index < len(system_state["current_menu"]):
        system_state["selected_index"] = index
        trigger_action()
    return jsonify({"status": "ok"})

@app.route('/api/reset', methods=['POST'])
def reset_message():
    system_state["message"] = "Připraveno"
    return jsonify({"status": "reset"})

# --- SPUŠTĚNÍ CELÉ APLIKACE ---
if __name__ == '__main__':
    log_activity("--- SYSTÉM NASTARTOVÁN ---")
    threading.Thread(target=start_mqtt, daemon=True).start()
    app.run(host='0.0.0.0', port=5000, debug=False)
