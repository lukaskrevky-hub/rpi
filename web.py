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
# Nový systém podporuje vnořování. Typ "submenu" nás přesměruje do jiného seznamu.
# Typ "back" nás vrátí o úroveň výš.

MENU_HOME = [
    {"id": 0, "label": "MÁM ŽÍZEŇ", "icon": "fa-glass-water", "color": "primary", "type": "req"},
    {"id": 1, "label": "MÁM HLAD", "icon": "fa-utensils", "color": "warning", "type": "req"},
    {"id": 2, "label": "SVĚTLO", "icon": "fa-lightbulb", "color": "success", "type": "zigbee"},
    {"id": 3, "label": "ZVONEK", "icon": "fa-bell", "color": "info", "type": "zigbee_bell"},
    {"id": 4, "label": "POMOC", "icon": "fa-hand-holding-medical", "color": "danger", "type": "req"},
    # Přímý vstup do sekce televize - už žádný výběr značek
    {"id": 5, "label": "TELEVIZE", "icon": "fa-tv", "color": "secondary", "type": "submenu", "target": "tv_controls"}
]

# Podmenu: Samotný univerzální dálkový ovladač
MENU_TV_CONTROLS = [
    {"id": 0, "label": "ZAP/VYP", "icon": "fa-power-off", "color": "danger", "type": "ir", "code": "power"},
    {"id": 1, "label": "PROGRAM +", "icon": "fa-arrow-up", "color": "info", "type": "ir", "code": "ch_up"},
    {"id": 2, "label": "PROGRAM -", "icon": "fa-arrow-down", "color": "info", "type": "ir", "code": "ch_down"},
    {"id": 3, "label": "HLASITOST +", "icon": "fa-volume-high", "color": "secondary", "type": "ir", "code": "vol_up"},
    {"id": 4, "label": "HLASITOST -", "icon": "fa-volume-low", "color": "secondary", "type": "ir", "code": "vol_down"},
    {"id": 5, "label": "ZPĚT", "icon": "fa-arrow-left", "color": "secondary", "type": "back"}
]

# Slovník všech menu pro snadné přepínání podle jména
MENUS = {
    "home": MENU_HOME,
    "tv_controls": MENU_TV_CONTROLS
}

# Tyto značky systém prohledá a "vybombarduje" jejich kódy postupně
AVAILABLE_BRANDS = ["tcl", "sony", "samsung"]

# --- CENTRÁLNÍ STAV SYSTÉMU ---
system_state = {
    "current_menu": MENU_HOME,   # Aktuálně zobrazené menu
    "menu_history": [],          # PAMĚŤ (zásobník) pro návrat zpět
    "selected_index": 0,         # Pozice kurzoru (joysticku)
    "message": "Připraveno",     # Text v horní liště
    "connection": "SLEEP",       # Stav spojení Bluetooth
    "last_action": 0             # Čas poslední akce pro animaci probliknutí
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

# Mozek ovládání s NOVOU logikou stromu
def process_command(cmd):
    log_activity(f"Přijat příkaz od pacienta: {cmd}")
    
    # NAHORU = Návrat o úroveň výš (Zpět)
    if cmd == "UP": 
        go_back()
        
    # DOPRAVA = Další karta
    elif cmd == "RIGHT": 
        move_selection(1)
        
    # DOLEVA = Předchozí karta
    elif cmd == "LEFT": 
        move_selection(-1)
        
    # DOLŮ = Potvrzení / Vstup do podmenu
    elif cmd == "DOWN" or cmd == "SELECT": 
        trigger_action()

def move_selection(direction):
    menu_len = len(system_state["current_menu"])
    system_state["selected_index"] = (system_state["selected_index"] + direction) % menu_len

# Funkce pro NÁVRAT ZPĚT v historii stromu
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
    
    # 1. POHYB VE STROMU (Vstup do podmenu)
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

    # 5. IR VYSÍLÁNÍ (Televize) - KOBERCOVÝ NÁLET
    elif item.get("type") == "ir":
        code_file = item['code']
        system_state["message"] = f"TV: {item['label']}"
        
        # Postupně odešle kód pro VŠECHNY dostupné značky
        for brand in AVAILABLE_BRANDS:
            path = f"/home/lukas/rpi/ir_codes/{brand}/{code_file}.txt"
            print(f"IR Vysílání ({brand}): {path}")
            try: 
                subprocess.run(["ir-ctl", "-d", "/dev/lirc0", "--send", path])
                # Velmi důležitá pauza! Bez ní by systém poslal kódy příliš rychle
                # a mohly by se signály slít do jednoho nesrozumitelného.
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
