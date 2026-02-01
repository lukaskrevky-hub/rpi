import asyncio
from bleak import BleakScanner, BleakClient
import paho.mqtt.client as mqtt
import sys

# --- KONFIGURACE ---
ESP_NAME = "ESP32-Joystick" # Musí sedět se jménem v ESP32
UART_TX_CHAR_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

# --- MQTT SETUP ---
MQTT_BROKER = "localhost"
MQTT_TOPIC = "joystick/command"
mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

try:
    mqtt_client.connect(MQTT_BROKER, 1883, 60)
    mqtt_client.loop_start()
    print(f"MQTT připojeno.")
except Exception as e:
    print(f"Chyba MQTT: {e}")
    sys.exit(1)

def notification_handler(sender, data):
    try:
        command = data.decode('utf-8').strip()
        print(f"--> Přijato: {command}")
        mqtt_client.publish(MQTT_TOPIC, command)
    except:
        pass

# Event pro signalizaci odpojení
disconnect_event = asyncio.Event()

def disconnected_callback(client):
    print("Joystick se odpojil. Restartuji cyklus připojení...")
    disconnect_event.set()

async def main():
    print("Startuji Robustní Bridge (Direct Connect Loop)...")
    
    target_address = None

    # 1. NAJÍT ADRESU (Jednorázově na začátku)
    print("První skenování: Probuďte joystick...")
    while target_address is None:
        device = await BleakScanner.find_device_by_filter(
            lambda d, ad: d.name and d.name == ESP_NAME,
            timeout=5.0
        )
        if device:
            target_address = device.address
            print(f"ADRESA NALEZENA: {target_address}")
            print("Vypínám skener. Odteď se připojuji přímo na MAC adresu.")
        else:
            print("... stále hledám ...")

    # 2. NEKONEČNÁ SMYČKA PŘÍMÉHO PŘIPOJOVÁNÍ
    # Zde už neskenujeme. Jen se snažíme připojit na známou adresu.
    # BlueZ (Linux Bluetooth stack) si sám pohlídá, kdy se zařízení objeví.
    while True:
        disconnect_event.clear()
        print(f"Čekám na {target_address} (Připojování)...")
        
        try:
            # timeout=None nebo vysoké číslo by znamenalo čekat navždy
            # Dáme 15s timeout, abychom občas vyčistili stav, kdyby se to zaseklo
            async with BleakClient(target_address, disconnected_callback=disconnected_callback, timeout=15.0) as client:
                print("PŘIPOJENO! Čekám na stabilizaci...")
                
                # Krátká pauza pro stabilizaci spojení před zápisem
                await asyncio.sleep(0.5) 
                
                await client.start_notify(UART_TX_CHAR_UUID, notification_handler)
                print("🚀 Ovladač je plně aktivní a data proudí.")

                # Čekáme na signál odpojení (místo smyčky s sleepem)
                # Toto je efektivnější a reaguje okamžitě na pád spojení
                await disconnect_event.wait()
                
        except Exception as e:
            # Toto nastane, když timeout vyprší (joystick spí) nebo se připojení nezdaří
            # Je to normální stav, prostě to zkusíme znovu v dalším cyklu
            # print(f"Info: {e}") 
            await asyncio.sleep(0.1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Ukončuji...")
        mqtt_client.loop_stop()
