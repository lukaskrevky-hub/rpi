from flask import Flask, render_template, jsonify, request
import paho.mqtt.client as mqtt
import time
import subprocess

app = Flask(__name__)

# --- DEFINICE MENU ---

# 1. HLAVNÍ MENU (Domácí)
MENU_HOME = [
    {"id": 0, "label": "MÁM ŽÍZEŇ", "icon": "fa-glass-water", "color": "primary", "type": "req"},
    {"id": 1, "label": "MÁM HLAD", "icon": "fa-utensils", "color": "warning", "type": "req"},
    {"id": 2, "label": "SVĚTLO", "icon": "fa-lightbulb", "color": "success", "type": "zigbee"},
    {"id": 3, "label": "POMOC", "icon": "fa-hand-holding-medical", "color": "danger", "type": "req"}
]

# 2. MENU TELEVIZE (IR Kódy)
# Soubory jako 'tv_power.txt' musí existovat ve složce /home/lukas/rpi/ir_codes/
MENU_TV = [
    {"id": 0, "label": "ZAP/VYP", "icon": "fa-power-off", "color": "danger", "type": "ir", "code": "tv_power"},
    {"id": 1, "label": "PROGRAM +", "icon": "fa-arrow-up", "color": "info", "type": "ir", "code": "tv_ch_up"},
    {"id": 2, "label": "PROGRAM -", "icon": "fa-arrow-down", "color": "info", "type": "ir", "code": "tv_ch_down"},
    {"id": 3, "label": "HLASITOST +", "icon": "fa-volume-high", "color": "secondary", "type": "ir", "code": "tv_vol_up"},
    {"id": 4, "label": "HLASITOST -", "icon": "fa-volume-low", "color": "secondary", "type": "ir", "code": "tv_vol_down"}
]

# --- STAV SYSTÉMU ---
system_state = {
    "mode": "home",          # Aktuální režim: 'home' nebo 'tv'
    "current_menu": MENU_HOME, # Aktuálně zobrazené položky
    "selected_index": 0,
    "message": "Připraveno",
    "connection": "SLEEP",
    "last_action": None,
    "right_hold_start": 0    # Časovač pro detekci dlouhého stisku
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

    except Exception as e:
        print(f"Chyba MQTT: {e}")

def process_command(cmd):
    # 1. DETEKCE DLOUHÉHO STISKU (DOPRAVA)
    if cmd == "RIGHT":
        # Začínáme měřit čas
        if system_state["right_hold_start"] == 0:
            system_state["right_hold_start"] = time.time()
            
    elif cmd == "CENTER":
        # Páčka puštěna -> vyhodnotíme délku stisku
        if system_state["right_hold_start"] > 0:
            duration = time.time() - system_state["right_hold_start"]
            system_state["right_hold_start"] = 0 # Reset
            
            if duration > 1.5:
                # DLOUHÝ STISK (> 1.5s) -> PŘEPNOUT REŽIM
                toggle_mode()
            else:
                # KRÁTKÝ STISK -> POSUNOUT V MENU (Stejně jako DOWN)
                move_selection(1)
    
    # 2. BĚŽNÁ NAVIGACE
    elif cmd == "DOWN":
        move_selection(1)
        system_state["right_hold_start"] = 0 # Pro jistotu reset
        
    elif cmd == "UP" or cmd == "LEFT":
        move_selection(-1)
        system_state["right_hold_start"] = 0

    # 3. POTVRZENÍ
    elif cmd == "SELECT":
        trigger_action()
        system_state["right_hold_start"] = 0

def move_selection(direction):
    menu_len = len(system_state["current_menu"])
    system_state["selected_index"] = (system_state["selected_index"] + direction) % menu_len

def toggle_mode():
    if system_state["mode"] == "home":
        system_state["mode"] = "tv"
        system_state["current_menu"] = MENU_TV
        system_state["message"] = "Režim: OVLÁDÁNÍ TV"
    else:
        system_state["mode"] = "home"
        system_state["current_menu"] = MENU_HOME
        system_state["message"] = "Režim: POŽADAVKY"
    
    # Resetujeme výběr na první položku
    system_state["selected_index"] = 0

def trigger_action():
    idx = system_state["selected_index"]
    menu = system_state["current_menu"]
    item = menu[idx]
    
    # Nastavíme zprávu (pokud to není IR, tam chceme nechat zprávu o režimu)
    if item["type"] != "ir":
        system_state["message"] = f"Vybráno: {item['label']}"
    
    # --- AKCE ---
    
    # 1. Zigbee (Světlo)
    if item.get("type") == "zigbee":
        try:
            mqtt_client.publish("zigbee2mqtt/zasuvka/set", '{"state": "TOGGLE"}')
        except: pass

    # 2. IR (Televize)
    if item.get("type") == "ir":
        print(f"IR Vysílání: {item['code']}")
        try:
            # Předpokládá cestu /home/lukas/rpi/ir_codes/tv_power.txt
            # -d /dev/lirc0 určuje zařízení (může být i defaultní, ale lepší specifikovat)
            subprocess.run(["ir-ctl", "-d", "/dev/lirc0", "--send", f"/home/lukas/rpi/ir_codes/{item['code']}.txt"])
        except Exception as e:
            print(f"Chyba IR: {e}")

# --- START SERVERU ---
mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
mqtt_client.on_message = on_message

def start_mqtt():
    while True:
        try:
            mqtt_client.connect("localhost", 1883, 60)
            mqtt_client.subscribe("joystick/#")
            mqtt_client.loop_forever()
        except: time.sleep(5)

# --- FLASK ENDPOINTY ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status')
def get_status():
    return jsonify(system_state)

@app.route('/api/click/<int:index>', methods=['POST'])
def web_click(index):
    # Pro manuální kliknutí myší
    system_state["selected_index"] = index
    trigger_action()
    return jsonify({"status": "ok"})

@app.route('/api/reset', methods=['POST'])
def reset_message():
    system_state["message"] = "Připraveno"
    return jsonify({"status": "reset"})

if __name__ == '__main__':
    threading.Thread(target=start_mqtt, daemon=True).start()
    app.run(host='0.0.0.0', port=5000, debug=False)
