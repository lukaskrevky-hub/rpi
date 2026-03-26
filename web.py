# IMPORTY KNIHOVEN
from flask import Flask, render_template, jsonify, request # Flask = framework pro tvorbu webového serveru
import paho.mqtt.client as mqtt # Knihovna pro naslouchání a posílání zpráv přes MQTT (komunikace s BLE Bridge a Zigbee)
import threading                # Umožňuje spouštět věci na pozadí (tzv. vlákna), aby se web nezasekl
import time                     # Práce s časem (pauzy, zaznamenávání času poslední akce)
import subprocess               # Umožňuje spouštět systémové příkazy Linuxu (potřebujeme pro IR vysílač ir-ctl)
import datetime                 # Knihovna pro práci s datem a časem (potřebná pro logování)

# Vytvoření instance webové aplikace
app = Flask(__name__)

# --- DEFINICE MENU (Karty) ---
# Tyto seznamy definují, jaké karty se zobrazí na obrazovce. 
# Obsahují ikony (z FontAwesome), barvy (z Bootstrapu) a hlavně "typ" akce.

MENU_HOME = [
    {"id": 0, "label": "MÁM ŽÍZEŇ", "icon": "fa-glass-water", "color": "primary", "type": "req"},
    {"id": 1, "label": "MÁM HLAD", "icon": "fa-utensils", "color": "warning", "type": "req"},
    {"id": 2, "label": "SVĚTLO", "icon": "fa-lightbulb", "color": "success", "type": "zigbee"},
    {"id": 3, "label": "ZVONEK", "icon": "fa-bell", "color": "info", "type": "zigbee_bell"},
    {"id": 4, "label": "POMOC", "icon": "fa-hand-holding-medical", "color": "danger", "type": "req"},
    {"id": 5, "label": "ZRUŠIT", "icon": "fa-rotate-left", "color": "secondary", "type": "cancel"}
]

MENU_TV = [
    # Typ 'ir' znamená, že při výběru se pošle infračervený signál. "code" odpovídá názvu .txt souboru z nahrávání.
    {"id": 0, "label": "ZAP/VYP", "icon": "fa-power-off", "color": "danger", "type": "ir", "code": "power"},
    {"id": 1, "label": "PROGRAM +", "icon": "fa-arrow-up", "color": "info", "type": "ir", "code": "ch_up"},
    {"id": 2, "label": "PROGRAM -", "icon": "fa-arrow-down", "color": "info", "type": "ir", "code": "ch_down"},
    {"id": 3, "label": "HLASITOST +", "icon": "fa-volume-high", "color": "secondary", "type": "ir", "code": "vol_up"},
    {"id": 4, "label": "HLASITOST -", "icon": "fa-volume-low", "color": "secondary", "type": "ir", "code": "vol_down"}
]

# Seznam podporovaných televizí (odpovídá složkám v /home/lukas/rpi/ir_codes/)
AVAILABLE_BRANDS = ["tcl", "sony", "samsung"]

# --- CENTRÁLNÍ STAV SYSTÉMU (Trezor paměti) ---
# Tento slovník (dict) si pamatuje aktuální situaci. Webová stránka (HTML/JS) se na něj 
# každých 300 milisekund ptá, aby věděla, co má vykreslit.
system_state = {
    "mode": "home",              # Aktuální režim obrazovky ('home' pro požadavky, 'tv' pro televizi)
    "current_menu": MENU_HOME,   # Které menu se má zrovna zobrazovat
    "selected_index": 0,         # Která karta je právě zvýrazněná (vybraná joystickem)
    "message": "Připraveno",     # Text, který svítí v horní liště (např. "Vybráno: MÁM ŽÍZEŇ")
    "connection": "SLEEP",       # Stav Bluetooth spojení (aktualizováno z ble_bridge)
    "tv_brand": "tcl",           # Jaká značka televize je aktuálně zvolená v roletce
    "last_action": 0             # Čas (timestamp) posledního potvrzení (spouští animaci probliknutí karty)
}

# --- FUNKCE PRO ZÁPIS DO DENÍČKU (LOGOVÁNÍ) ---
# Zapisuje veškerou aktivitu do souboru. Výborné pro test baterie i pro dlouhodobý dohled.
def log_activity(action):
    # Získání aktuálního data a času ve formátu "ROK-MĚSÍC-DEN HODINA:MINUTA:SEKUNDA"
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # Otevření souboru v režimu "a" (append - přidávání nakonec, nemaže stará data)
    with open("/home/lukas/rpi/aktivita_systemu.log", "a") as f:
        f.write(f"[{timestamp}] - {action}\n")
    print(f"Zapsáno do logu: [{timestamp}] - {action}")

# --- MQTT LOGIKA (Zpracování zpráv z Bluetooth) ---
# Funkce, která se zavolá automaticky POKAŽDÉ, když od ble_bridge přijde nějaká zpráva
def on_message(client, userdata, msg):
    try:
        topic = msg.topic
        payload = msg.payload.decode() # Převod z bytů na normální text (string)
        if topic == "joystick/status":
            # Přišla zpráva o stavu BT připojení (SLEEP, CONNECTING, READY)
            system_state["connection"] = payload
            # NOVÉ: Pokud se systém právě připojil, zaznamenáme to
            if payload == "READY":
                log_activity("Ovladač se úspěšně připojil.")
            
        elif topic == "joystick/command":
            # Přišel povel z joysticku (UP, DOWN, LEFT, RIGHT). Jdeme ho zpracovat.
            process_command(payload)
    except Exception as e: print(e)

# Mozek ovládání - překlad směrů páčky na konkrétní akce v menu
def process_command(cmd):
    # Zaznamenáme každý jednotlivý pohyb páčky do deníčku
    log_activity(f"Přijat příkaz od pacienta: {cmd}")
    
    # 1. NAHORU = Tlačítko pro přepnutí mezi obrazovkami (Zdravotní vs. Televize)
    if cmd == "UP": 
        toggle_mode()
        
    # 2. DOPRAVA = Posun zvýraznění na další kartu
    elif cmd == "RIGHT": 
        move_selection(1)
        
    # 3. DOLEVA = Posun zvýraznění na předchozí kartu
    elif cmd == "LEFT": 
        move_selection(-1)
        
    # 4. DOLŮ = Tlačítko pro "ENTER" / Potvrzení vybrané karty
    elif cmd == "DOWN" or cmd == "SELECT": 
        trigger_action()

# Matematika posunu kurzoru
def move_selection(direction):
    menu_len = len(system_state["current_menu"])
    # Zbytek po dělení (%) zajistí, že když přejedeme konec, kurzor přeskočí zpět na začátek (tzv. rotace)
    system_state["selected_index"] = (system_state["selected_index"] + direction) % menu_len

# Přepínání hlavní obrazovky
def toggle_mode():
    if system_state["mode"] == "home":
        # Pokud jsme byli doma, přepneme na TV
        system_state["mode"] = "tv"
        system_state["current_menu"] = MENU_TV
        system_state["message"] = f"Režim: TV ({system_state['tv_brand'].upper()})"
    else:
        # Pokud jsme byli u TV, přepneme domů
        system_state["mode"] = "home"
        system_state["current_menu"] = MENU_HOME
        system_state["message"] = "Režim: POŽADAVKY"
    # Při změně režimu kurzor vždy zresetujeme na první kartu (index 0)
    system_state["selected_index"] = 0

# --- VYKONÁNÍ AKCE (Potvrzení karty) ---
def trigger_action():
    # Najdeme kartu, na které pacient právě stojí
    idx = system_state["selected_index"]
    item = system_state["current_menu"][idx]
    
    # Zaznamenáme přesný čas. HTML si toho všimne a spustí zelené probliknutí karty.
    system_state["last_action"] = time.time()
    
    # --- REŽIM 1: BĚŽNÉ POŽADAVKY (HOME) ---
    if system_state["mode"] == "home":
        if item.get("type") == "cancel":
            system_state["message"] = "Připraveno"  # Zrušení všech požadavků
            
        elif item.get("type") == "zigbee":
            # Ovládání chytré domácnosti přes Zigbee2MQTT
            # Odesíláme zprávu "TOGGLE" (přepnout stav - pokud svítí, zhasne a naopak)
            try: mqtt_client.publish("zigbee2mqtt/zasuvka/set", '{"state": "TOGGLE"}')
            except: pass

        elif item.get("type") == "zigbee_bell":
            # Ovládání chytrého zvonku (sirény) přes Zigbee2MQTT
            # Odesíláme JSON zprávu k aktivaci zvonění. POUZOR: JSON se může drobně lišit podle modelu zvonku.
            try: mqtt_client.publish("zigbee2mqtt/zvonek/set", '{"state": "ON"}')
            except: pass
            
        else:
            # Běžný požadavek (Žízeň, Hlad). Změníme text v horní liště,
            # aby na to mohl pečovatel zareagovat.
            system_state["message"] = f"Vybráno: {item['label']}"

    # --- REŽIM 2: OVLÁDÁNÍ TELEVIZE (TV) ---
    elif system_state["mode"] == "tv":
        if item.get("type") == "ir":
            brand = system_state['tv_brand'] # Podle roletky zjistíme aktuální značku
            code_file = item['code']         # Např. 'power', 'vol_up'
            # Složíme cestu k fyzickému .txt souboru, který jsme nahráli přes skript
            path = f"/home/lukas/rpi/ir_codes/{brand}/{code_file}.txt"
            
            print(f"IR Vysílání: {path}")
            # Spuštění systémového příkazu Linuxu pro odpálení infračervené diody
            try: subprocess.run(["ir-ctl", "-d", "/dev/lirc0", "--send", path])
            except Exception as e: print(f"Chyba IR: {e}")

# --- START SLUŽEB NA POZADÍ ---
# Nastavení MQTT klienta s nejnovější specifikací API
mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
mqtt_client.on_message = on_message # Provázání s naší funkcí výše

# Funkce, která běží v samostatném vlákně a neustále naslouchá MQTT zprávám
def start_mqtt():
    while True:
        try:
            mqtt_client.connect("localhost", 1883, 60) # Připojení k lokálnímu brokerovy
            mqtt_client.subscribe("joystick/#")        # Odběr VŠECH témat začínajících "joystick/"
            mqtt_client.loop_forever()                 # Nekonečná smyčka
        except: time.sleep(5)                          # Pokud broker spadne, zkusíme to znovu za 5s

# --- FLASK WEBOVÉ CESTY (API a zobrazení) ---
# Hlavní stránka (Když do prohlížeče zadáš IP adresu RPi)
@app.route('/')
def index():
    # Vykreslí HTML šablonu a předá jí seznam televizí pro roletku
    return render_template('index.html', brands=AVAILABLE_BRANDS, current_brand=system_state["tv_brand"])

# Tuto adresu volá javascript z HTML každých 300ms (tzv. Polling)
@app.route('/api/status')
def get_status():
    # Odesíláme celý náš "trezor" zabalený jako JSON (srozumitelné pro Javascript)
    return jsonify(system_state)

# Tuto adresu volá HTML, když pečovatel klikne na kartu myší nebo prstem
@app.route('/api/click/<int:index>', methods=['POST'])
def web_click(index):
    system_state["selected_index"] = index # Přesuneme kurzor na kliknutou kartu
    trigger_action()                       # Provedeme akci stejně, jako by ji udělal joystick
    return jsonify({"status": "ok"})

# Zrušení zprávy přes tlačítko "VYŘÍZENO"
@app.route('/api/reset', methods=['POST'])
def reset_message():
    system_state["message"] = "Připraveno"
    return jsonify({"status": "reset"})

# Uložení značky TV po výběru v roletce na webu
@app.route('/api/set_brand/<brand>', methods=['POST'])
def set_brand(brand):
    # Ochrana proti hackerům (přijmeme jen značky, které známe)
    if brand in AVAILABLE_BRANDS:
        system_state["tv_brand"] = brand
        # Pokud je zrovna zapnutý režim TV, rovnou přepíšeme i text nahoře
        if system_state["mode"] == "tv":
            system_state["message"] = f"Režim: TV ({brand.upper()})"
    return jsonify({"status": "ok"})

# --- SPUŠTĚNÍ CELÉ APLIKACE ---
if __name__ == '__main__':
    # Hned po startu Raspberry napíšeme do logu oddělovací čáru pro přehlednost
    log_activity("--- SYSTÉM NASTARTOVÁN ---")
    
    # 1. Spustíme MQTT pošťáka v samostatném vlákně (aby nebrzdil web)
    threading.Thread(target=start_mqtt, daemon=True).start()
    
    # 2. Spustíme samotný webový server na portu 5000 (přístupný pro celou síť)
    app.run(host='0.0.0.0', port=5000, debug=False)
