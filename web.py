from flask import Flask, render_template, jsonify, request
import paho.mqtt.client as mqtt
import threading
import time
import subprocess

app = Flask(__name__)

# --- DEFINICE MENU ---
MENU_HOME = [
    {"id": 0, "label": "MÁM ŽÍZEŇ", "icon": "fa-glass-water", "color": "primary", "type": "req"},
    {"id": 1, "label": "MÁM HLAD", "icon": "fa-utensils", "color": "warning", "type": "req"},
    {"id": 2, "label": "SVĚTLO", "icon": "fa-lightbulb", "color": "success", "type": "zigbee"},
    {"id": 3, "label": "POMOC", "icon": "fa-hand-holding-medical", "color": "danger", "type": "req"},
    {"id": 4, "label": "ZRUŠIT", "icon": "fa-rotate-left", "color": "secondary", "type": "cancel"}
]

MENU_TV = [
    {"id": 0, "label": "ZAP/VYP", "icon": "fa-power-off", "color": "danger", "type": "ir", "code": "power"},
    {"id": 1, "label": "PROGRAM +", "icon": "fa-arrow-up", "color": "info", "type": "ir", "code": "ch_up"},
    {"id": 2, "label": "PROGRAM -", "icon": "fa-arrow-down", "color": "info", "type": "ir", "code": "ch_down"},
    {"id": 3, "label": "HLASITOST +", "icon": "fa-volume-high", "color": "secondary", "type": "ir", "code": "vol_up"},
    {"id": 4, "label": "HLASITOST -", "icon": "fa-volume-low", "color": "secondary", "type": "ir", "code": "vol_down"}
]

AVAILABLE_BRANDS = ["tcl", "sony", "samsung"]

# --- STAV SYSTÉMU ---
system_state = {
    "mode": "home",          # 'home' nebo 'tv'
    "current_menu": MENU_HOME,
    "selected_index": 0,
    "message": "Připraveno",
    "connection": "SLEEP",
    "tv_brand": "tcl",
    "last_action": 0         # Čas poslední akce pro vizuální probliknutí v HTML
}

# --- MQTT LOGIKA ---
def on_message(client, userdata, msg):
    try:
        topic = msg.topic
        payload = msg.payload.decode()
        if topic == "joystick/status":
            system_state["connection"] = payload
        elif topic == "joystick/command":
            process_command(payload)
    except Exception as e: print(e)

def process_command(cmd):
    # 1. NAHORU = Přepnutí režimu (TV/Home)
    if cmd == "UP": 
        toggle_mode()
        
    # 2. DOPRAVA = Posun vpřed
    elif cmd == "RIGHT": 
        move_selection(1)
        
    # 3. DOLEVA = Posun vzad
    elif cmd == "LEFT": 
        move_selection(-1)
        
    # 4. DOLŮ = POTVRZENÍ
    elif cmd == "DOWN" or cmd == "SELECT": 
        trigger_action()

def move_selection(direction):
    menu_len = len(system_state["current_menu"])
    system_state["selected_index"] = (system_state["selected_index"] + direction) % menu_len

def toggle_mode():
    if system_state["mode"] == "home":
        system_state["mode"] = "tv"
        system_state["current_menu"] = MENU_TV
        system_state["message"] = f"Režim: TV ({system_state['tv_brand'].upper()})"
    else:
        system_state["mode"] = "home"
        system_state["current_menu"] = MENU_HOME
        system_state["message"] = "Režim: POŽADAVKY"
    system_state["selected_index"] = 0

def trigger_action():
    idx = system_state["selected_index"]
    item = system_state["current_menu"][idx]
    
    # Zaznamenáme čas akce pro animaci probliknutí v HTML
    system_state["last_action"] = time.time()
    
    # --- REŽIM 1: BĚŽNÉ POŽADAVKY ---
    if system_state["mode"] == "home":
        if item.get("type") == "cancel":
            system_state["message"] = "Připraveno"  # Pacient akci zrušil
            
        elif item.get("type") == "zigbee":
            # Pokud to bylo světlo (Zigbee), pouze ho sepneme, 
            # ale zprávu v horní liště NEMĚNÍME (necháme ji tak, jak je).
            try: mqtt_client.publish("zigbee2mqtt/zasuvka/set", '{"state": "TOGGLE"}')
            except: pass
            
        else:
            # Všechny ostatní požadavky (MÁM ŽÍZEŇ, HLAD, POMOC) vypíšeme
            system_state["message"] = f"Vybráno: {item['label']}"

    # --- REŽIM 2: U TELEVIZE ---
    elif system_state["mode"] == "tv":
        if item.get("type") == "ir":
            brand = system_state['tv_brand']
            code_file = item['code']
            path = f"/home/lukas/rpi/ir_codes/{brand}/{code_file}.txt"
            print(f"IR Vysílání: {path}")
            try: subprocess.run(["ir-ctl", "-d", "/dev/lirc0", "--send", path])
            except Exception as e: print(f"Chyba IR: {e}")

# --- START ---
mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
mqtt_client.on_message = on_message

def start_mqtt():
    while True:
        try:
            mqtt_client.connect("localhost", 1883, 60)
            mqtt_client.subscribe("joystick/#")
            mqtt_client.loop_forever()
        except: time.sleep(5)

# --- ROUTES ---
@app.route('/')
def index():
    return render_template('index.html', brands=AVAILABLE_BRANDS, current_brand=system_state["tv_brand"])

@app.route('/api/status')
def get_status():
    return jsonify(system_state)

@app.route('/api/click/<int:index>', methods=['POST'])
def web_click(index):
    system_state["selected_index"] = index
    trigger_action()
    return jsonify({"status": "ok"})

@app.route('/api/reset', methods=['POST'])
def reset_message():
    system_state["message"] = "Připraveno"
    return jsonify({"status": "reset"})

@app.route('/api/set_brand/<brand>', methods=['POST'])
def set_brand(brand):
    if brand in AVAILABLE_BRANDS:
        system_state["tv_brand"] = brand
        if system_state["mode"] == "tv":
            system_state["message"] = f"Režim: TV ({brand.upper()})"
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    threading.Thread(target=start_mqtt, daemon=True).start()
    app.run(host='0.0.0.0', port=5000, debug=False)
