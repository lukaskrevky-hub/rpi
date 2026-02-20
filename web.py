from flask import Flask, render_template, jsonify, request
import paho.mqtt.client as mqtt
import threading   # <--- TADY CHYBĚL TENTO ŘÁDEK
import time
import subprocess

app = Flask(__name__)

# --- DEFINICE MENU ---
MENU_HOME = [
    {"id": 0, "label": "MÁM ŽÍZEŇ", "icon": "fa-glass-water", "color": "primary", "type": "req"},
    {"id": 1, "label": "MÁM HLAD", "icon": "fa-utensils", "color": "warning", "type": "req"},
    {"id": 2, "label": "SVĚTLO", "icon": "fa-lightbulb", "color": "success", "type": "zigbee"},
    {"id": 3, "label": "POMOC", "icon": "fa-hand-holding-medical", "color": "danger", "type": "req"}
]

# MENU TELEVIZE (Kódy jsou názvy souborů bez přípony)
MENU_TV = [
    {"id": 0, "label": "ZAP/VYP", "icon": "fa-power-off", "color": "danger", "type": "ir", "code": "power"},
    {"id": 1, "label": "PROGRAM +", "icon": "fa-arrow-up", "color": "info", "type": "ir", "code": "ch_up"},
    {"id": 2, "label": "PROGRAM -", "icon": "fa-arrow-down", "color": "info", "type": "ir", "code": "ch_down"},
    {"id": 3, "label": "HLASITOST +", "icon": "fa-volume-high", "color": "secondary", "type": "ir", "code": "vol_up"},
    {"id": 4, "label": "HLASITOST -", "icon": "fa-volume-low", "color": "secondary", "type": "ir", "code": "vol_down"}
]

# Seznam podporovaných značek (musí odpovídat složkám v /home/lukas/rpi/ir_codes/)
AVAILABLE_BRANDS = ["samsung", "lg", "sony", "philips", "panasonic"]

# --- STAV SYSTÉMU ---
system_state = {
    "mode": "home",          # 'home' nebo 'tv'
    "current_menu": MENU_HOME,
    "selected_index": 0,
    "message": "Připraveno",
    "connection": "SLEEP",
    "tv_brand": "samsung"    # Výchozí značka
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
    # Jednoduchá logika bez časovačů
    if cmd == "RIGHT": toggle_mode()
    elif cmd == "DOWN": move_selection(1)
    elif cmd == "UP" or cmd == "LEFT": move_selection(-1)
    elif cmd == "SELECT": trigger_action()

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
    
    if item["type"] != "ir":
        system_state["message"] = f"Vybráno: {item['label']}"
    
    # Zigbee
    if item.get("type") == "zigbee":
        try: mqtt_client.publish("zigbee2mqtt/zasuvka/set", '{"state": "TOGGLE"}')
        except: pass

    # IR OVLÁDÁNÍ
    if item.get("type") == "ir":
        brand = system_state['tv_brand']
        code_file = item['code']
        path = f"/home/lukas/rpi/ir_codes/{brand}/{code_file}.txt"
        print(f"IR Vysílání: {path}")
        try:
            subprocess.run(["ir-ctl", "-d", "/dev/lirc0", "--send", path])
        except Exception as e:
            print(f"Chyba IR: {e}")

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
    # Posíláme seznam značek do šablony
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
    # Tady nám to padalo, protože chyběl "import threading" nahoře
    threading.Thread(target=start_mqtt, daemon=True).start()
    app.run(host='0.0.0.0', port=5000, debug=False)
