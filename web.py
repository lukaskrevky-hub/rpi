from flask import Flask, render_template, jsonify, request
import paho.mqtt.client as mqtt
import threading
import time
import subprocess
import sys

app = Flask(__name__)

# --- GLOBÁLNÍ STAV ---
system_state = {
    "selected_index": 0,
    "message": "Startuji...",
    "connection": "SLEEP",  # Výchozí stav
    "last_action": 0
}

# --- DEFINICE MENU ---
MENU_ITEMS = [
    {"id": 0, "label": "MÁM ŽÍZEŇ", "icon": "fa-glass-water", "color": "primary", "speech": "Mám žízeň, prosím vodu."},
    {"id": 1, "label": "MÁM HLAD", "icon": "fa-utensils", "color": "warning", "speech": "Mám hlad."},
    {"id": 2, "label": "SVĚTLO", "icon": "fa-lightbulb", "color": "success", "speech": "Přepínám světlo.", "type": "zigbee"},
    {"id": 3, "label": "POMOC", "icon": "fa-hand-holding-medical", "color": "danger", "speech": "Prosím, pojďte sem, potřebuji pomoc!"}
]

# --- MQTT CALLBACKY ---
def on_connect(client, userdata, flags, rc, properties=None):
    print(f"MQTT Připojeno s kódem {rc}")
    # Odebíráme všechna témata začínající na joystick/
    client.subscribe("joystick/#")

def on_message(client, userdata, msg):
    global system_state
    try:
        topic = msg.topic
        payload = msg.payload.decode()
        
        # --- DEBUG VÝPIS (Uvidíte v logu služby) ---
        print(f"DEBUG MQTT: Téma='{topic}' Data='{payload}'")

        # 1. Změna stavu připojení (z ble_bridge.py)
        if topic == "joystick/status":
            system_state["connection"] = payload
            
        # 2. Příkazy z joysticku
        elif topic == "joystick/command":
            if payload == "UP" or payload == "LEFT":
                system_state["selected_index"] = (system_state["selected_index"] - 1) % len(MENU_ITEMS)
            elif payload == "DOWN" or payload == "RIGHT":
                system_state["selected_index"] = (system_state["selected_index"] + 1) % len(MENU_ITEMS)
            elif payload == "SELECT":
                trigger_action(system_state["selected_index"])
                
    except Exception as e:
        print(f"Chyba při zpracování MQTT zprávy: {e}")

# --- FUNKCE AKCÍ ---
def trigger_action(index):
    item = MENU_ITEMS[index]
    system_state["message"] = f"Akce: {item['label']}"
    system_state["last_action"] = time.time()
    
    print(f"SPUSTENI AKCE: {item['label']}")
    
    # Hlasový výstup v novém vlákně (neblokuje web)
    threading.Thread(target=speak, args=(item['speech'],)).start()

def speak(text):
    try:
        # Používá espeak-ng pro český hlas
        subprocess.run(['espeak-ng', '-v', 'cs', text])
    except Exception as e:
        print(f"Chyba TTS: {e}")

# --- MQTT VLÁKNO ---
def start_mqtt_thread():
    # Používáme CallbackAPIVersion.VERSION2 pro novější Paho knihovnu
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message
    
    while True:
        try:
            print("Připojuji se k MQTT brokeru...")
            client.connect("localhost", 1883, 60)
            print(">>> MQTT VLÁKNO BĚŽÍ A ČEKÁ NA ZPRÁVY <<<")
            client.loop_forever()
        except Exception as e:
            print(f"Chyba připojení MQTT (zkusím za 5s): {e}")
            time.sleep(5)

# --- FLASK WEBOVÉ CESTY ---
@app.route('/')
def index():
    return render_template('index.html', menu=MENU_ITEMS)

@app.route('/api/status')
def get_status():
    # Tuto adresu volá JavaScript každých 300ms
    return jsonify(system_state)

@app.route('/api/click/<int:item_id>', methods=['POST'])
def web_click(item_id):
    trigger_action(item_id)
    return jsonify({"status": "ok"})

# --- HLAVNÍ SPOUŠTĚČ ---
if __name__ == '__main__':
    # 1. Nastartovat MQTT na pozadí
    mqtt_thread = threading.Thread(target=start_mqtt_thread, daemon=True)
    mqtt_thread.start()
    
    # 2. Spustit Web Server
    print("Spouštím Flask server na portu 5000...")
    app.run(host='0.0.0.0', port=5000, debug=False)
