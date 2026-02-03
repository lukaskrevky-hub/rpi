from flask import Flask, render_template, jsonify, request
import paho.mqtt.client as mqtt
import threading
import time
import subprocess

app = Flask(__name__)

# --- STAV SYSTÉMU ---
# Toto jsou data, která sdílíme mezi Joystickem a Webem
system_state = {
    "selected_index": 0,  # Která ikona je vybraná joystickem
    "message": "Připraveno", # Hláška pro lištu
    "last_action": None
}

# --- DEFINICE MENU ---
# Ikony používají FontAwesome (součást Bootstrapu)
MENU_ITEMS = [
    {"id": 0, "label": "MÁM ŽÍZEŇ", "icon": "fa-glass-water", "color": "primary", "speech": "Mám žízeň, prosím vodu."},
    {"id": 1, "label": "MÁM HLAD", "icon": "fa-utensils", "color": "warning", "speech": "Mám hlad."},
    {"id": 2, "label": "SVĚTLO", "icon": "fa-lightbulb", "color": "success", "speech": "Přepínám světlo.", "type": "zigbee"},
    {"id": 3, "label": "POTŘEBUJI POMOC", "icon": "fa-hand-holding-medical", "color": "danger", "speech": "Prosím, pojďte sem, potřebuji pomoc!"}
]

# --- MQTT SETUP ---
def on_message(client, userdata, msg):
    command = msg.payload.decode()
    print(f"Joystick: {command}")
    
    # Logika ovládání menu joystickem
    if command == "UP" or command == "LEFT":
        system_state["selected_index"] = (system_state["selected_index"] - 1) % len(MENU_ITEMS)
    elif command == "DOWN" or command == "RIGHT":
        system_state["selected_index"] = (system_state["selected_index"] + 1) % len(MENU_ITEMS)
    elif command == "SELECT":
        trigger_action(system_state["selected_index"])

mqtt_client = mqtt.Client()
mqtt_client.on_message = on_message

def start_mqtt():
    try:
        mqtt_client.connect("localhost", 1883, 60)
        mqtt_client.subscribe("joystick/command")
        mqtt_client.loop_forever()
    except Exception as e:
        print(f"Chyba MQTT: {e}")

# --- FUNKCE AKCÍ ---
def trigger_action(index):
    item = MENU_ITEMS[index]
    system_state["message"] = f"Aktivováno: {item['label']}"
    system_state["last_action"] = time.time()
    
    # 1. Hlasový výstup (TTS)
    # Spouštíme v novém vlákně, aby to neblokovalo web
    threading.Thread(target=speak, args=(item['speech'],)).start()
    
    # 2. Zigbee / IoT Akce (Zde později doplníme kód pro zásuvku)
    if "type" in item and item["type"] == "zigbee":
        print(f"--> Odesílám Zigbee příkaz pro: {item['label']}")
        # Zde bude: mqtt_client.publish("zigbee2mqtt/zasuvka/set", '{"state":"TOGGLE"}')

def speak(text):
    subprocess.run(['espeak-ng', '-v', 'cs', text])

# --- FLASK WEBOVÉ CESTY (ROUTES) ---

@app.route('/')
def index():
    # Pošle prohlížeči soubor index.html a data o menu
    return render_template('index.html', menu=MENU_ITEMS)

@app.route('/api/status')
def get_status():
    # AJAX volá tuto adresu každých 500ms, aby zjistil, kde je joystick
    return jsonify(system_state)

@app.route('/api/click/<int:item_id>', methods=['POST'])
def web_click(item_id):
    # Když pečovatel klikne myší/prstem na webu
    trigger_action(item_id)
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    # Spuštění MQTT na pozadí
    threading.Thread(target=start_mqtt, daemon=True).start()
    # Spuštění Web Serveru (host='0.0.0.0' zpřístupní web v celé síti)
    app.run(host='0.0.0.0', port=5000, debug=False)
