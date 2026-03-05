# Import asynchronních funkcí (umožňuje programu čekat na Bluetooth, aniž by "zamrzl")
import asyncio
import time
# Knihovna Bleak slouží pro komunikaci přes Bluetooth Low Energy (BLE) v Pythonu
from bleak import BleakClient, BleakScanner
# Knihovna Paho MQTT pro komunikaci s naším lokálním brokerem
import paho.mqtt.client as mqtt
import sys

# --- KONFIGURACE HARDWARU A SÍTĚ ---
# Fyzická adresa ESP32. RPi bude ignorovat všechna ostatní zařízení v dosahu.
TARGET_MAC = "10:06:1C:B5:A7:36"

# Unikátní identifikátor (UUID) charakteristiky, přes kterou ESP32 posílá data. 
# Musí se přesně shodovat s tím, co je v main.py na ESP32.
UART_TX_CHAR_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

# Nastavení MQTT (běží lokálně na samotném Raspberry Pi)
MQTT_BROKER = "localhost"
MQTT_TOPIC = "joystick/command"
TOPIC_STATUS = "joystick/status" 

# --- INICIALIZACE MQTT KLIENTA ---
# Vytvoření instance MQTT klienta (s nejnovější specifikací API)
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

try:
    # Připojení na port 1883 s keep-alive intervalem 60 vteřin
    client.connect(MQTT_BROKER, 1883, 60)
    # Spuštění MQTT smyčky na pozadí. Tím pádem odesílání zpráv nebrzdí Bluetooth logiku.
    client.loop_start()
    print("MQTT připojeno.")
except Exception as e:
    print(f"Chyba MQTT: {e}")
    sys.exit(1) # Pokud se nelze připojit k MQTT, celý program se bezpečně ukončí

# Globální proměnná pro uchování aktuálního stavu (aby se na web neposílalo pořád to samé)
current_status = ""

# --- POMOCNÉ FUNKCE ---
def publish_status(status):
    """
    Odešle aktuální stav připojení do MQTT, ale pouze pokud se stav změnil.
    Parametr retain=True znamená, že si broker tuto zprávu pamatuje, 
    takže když se webová stránka načte (nebo obnoví), okamžitě ví, jaký je stav.
    """
    global current_status
    if current_status != status:
        print(f"STAV -> {status}") 
        client.publish(TOPIC_STATUS, status, retain=True)
        current_status = status
        
def notification_handler(sender, data):
    """
    Tato funkce se spustí automaticky POKAŽDÉ, když ESP32 přes Bluetooth odešle povel.
    """
    # Z přijatých bytů udělá čitelný text a ořízne prázdné znaky
    command = data.decode('utf-8').strip()
    # Okamžitě tento text (např. "UP") přepošle do MQTT sítě, aby na to reagoval web
    client.publish(MQTT_TOPIC, command)

def disconnected_callback(client_ble):
    """
    Funkce volaná knihovnou Bleak při nečekaném odpojení.
    Necháváme prázdnou (pass), protože stav 'SLEEP' a opětovné připojení 
    si inteligentně řešíme sami v naší hlavní smyčce.
    """
    pass # Ignorujeme spam z Linuxu, stav vyřeší smyčka níže

# --- HLAVNÍ BLUETOOTH SMYČKA (SNIPER MODE) ---
async def connect_and_listen():
    print(f"--- SPUŠTĚN SNIPER REŽIM 5.0 (ANTI-PHANTOM FILTER) NA {TARGET_MAC} ---")
    publish_status("SLEEP")

    # Nekonečná smyčka - zaručuje, že RPi bude na ESP32 čekat navždy
    while True:
        try:
            # Asynchronní "vlajka", na kterou program čeká, než bude pokračovat
            device_event = asyncio.Event()
            target_device = None
            
            # Zapamatujeme si čas spuštění skeneru
            scanner_start_time = time.time()

            # Funkce, která hodnotí každé zařízení, které anténa RPi "uslyší"
            def detection_callback(device, advertisement_data):
                nonlocal target_device
                # Je to naše ESP32?
                if device.address.lower() == TARGET_MAC.lower():
                    # --- ANTI-PHANTOM FILTER ---
                    # Linuxový Bluetooth (BlueZ) má zlozvyk pamatovat si stará vysílání (cache).
                    # Když se ESP32 uspí, RPi občas z mezipaměti vyhrabe starý paket a tváří se, 
                    # že ESP32 vysílá. Ignorujeme proto vše, co přijde v první vteřině skenování.
                    if time.time() - scanner_start_time > 1.0:
                        target_device = device    # Našli jsme čerstvé ESP32
                        device_event.set()        # Zvedneme vlajku a jdeme se připojit

            # 1. KROK: Nasloucháme okolí a ignorujeme šum z mezipamětí
            async with BleakScanner(detection_callback):
                await device_event.wait() # Zde program tiše čeká, dokud ESP32 nezačne vysílat
                
            # Pokud kód došel sem, znamená to, že se pacient pohnul joystickem, probudil ESP32 a právě ESP32 vysílá.
            publish_status("CONNECTING")
            
            # Mikro-pauza pro bezpečné uvolnění Bluetooth adaptéru po vypnutí skeneru
            await asyncio.sleep(0.1)
            
            # 2. KROK: Bleskové připojení (3 pokusy)
            for attempt in range(3):
                try:
                    # Timeout 3.0 je velmi agresivní – pokud se to nepovede do 3 vteřin, 
                    # spojení spadne a okamžitě zkusíme další pokus.
                    async with BleakClient(target_device, disconnected_callback=disconnected_callback, timeout=3.0) as client_ble:
                        publish_status("READY") 
                        print("\n+++ PŘIPOJENO! Ovladač je aktivní. +++")

                        # Zaregistrujeme "odposlech" charakteristiky z ESP32.
                        # Od teď každá změna páčky spustí funkci notification_handler.
                        await client_ble.start_notify(UART_TX_CHAR_UUID, notification_handler)

                        # Tato minismyčka drží připojení aktivní a neustále ho kontroluje.
                        # Jakmile ESP32 (po 30s nečinnosti pacienta) samo usne a odstřihne Bluetooth,
                        # client_ble.is_connected bude False a tato smyčka skončí.
                        while client_ble.is_connected:
                            await asyncio.sleep(0.5)
                            
                    # Pokud jsme tady, ESP32 se korektně uspalo a ukončilo Bluetooth spojení.
                    break # Vyskočíme z opakovací smyčky
                    
                except Exception as e:
                    # Pokud spojení selhalo z technických důvodů...
                    if "was not found" in str(e):
                        break # Zařízení už opravdu není v dosahu, jdeme zpět skenovat
                    await asyncio.sleep(0.2) # Krátká pauza před dalším pokusem
            
            # Konec cyklu - ovladač spí (nebo selhaly všechny 3 pokusy)
            publish_status("SLEEP")
            await asyncio.sleep(0.2)
            
        except Exception as e:
            # Globální ochrana proti zamrznutí skriptu. Pokud dojde k nečekané chybě
            # (např. se restartuje Bluetooth adaptér na RPi), skript počká 0.2s a jede dál.
            await asyncio.sleep(0.2)

# --- SPUŠTĚNÍ PROGRAMU ---
# Tento blok zajistí, že se asynchronní smyčka správně nastartuje při spuštění souboru.
if __name__ == "__main__":
    try:
        asyncio.run(connect_and_listen())
    except KeyboardInterrupt:
        # Pěkné a čisté ukončení při stisknutí Ctrl+C v terminálu
        print("\nUkončuji program...")
        publish_status("SLEEP")
        sys.exit(0)

