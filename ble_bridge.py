import asyncio
from bleak import BleakScanner, BleakClient
import paho.mqtt.client as mqtt
import sys

# --- KONFIGURACE ---
# Musí odpovídat jménu v ESP32!
ESP_NAME = "ESP32-Joystick"
UART_TX_CHAR_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

# --- MQTT SETUP ---
MQTT_BROKER = "localhost"
MQTT_TOPIC = "joystick/command"

# Oprava pro novější verze knihovny (odstranění warningu)
mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

try:
    mqtt_client.connect(MQTT_BROKER, 1883, 60)
    mqtt_client.loop_start()
    print(f"MQTT připojeno k {MQTT_BROKER}")
except Exception as e:
    print(f"Chyba MQTT: {e}")
    sys.exit(1)

# --- CALLBACK FUNKCE ---
def notification_handler(sender, data):
    try:
        command = data.decode('utf-8').strip()
        print(f"--> Přijato z BLE: {command}")
        mqtt_client.publish(MQTT_TOPIC, command)
    except Exception as e:
        print(f"Chyba při zpracování: {e}")

def disconnected_callback(client):
    print("Joystick se odpojil. Okamžitě restartuji čekání na připojení...")

# --- HLAVNÍ SMYČKA ---
async def main():
    print("Startuji Rychlý Bridge v2 (Direct Connect Mode)...")
    
    target_address = None

    # FÁZE 1: ZÍSKÁNÍ ADRESY (Skenujeme jen jednou na začátku)
    print("🔍 První hledání: Prosím, probuďte joystick (hýbejte páčkou)...")
    
    while target_address is None:
        device = await BleakScanner.find_device_by_filter(
            lambda d, ad: d.name and d.name == ESP_NAME,
            timeout=5.0
        )
        if device:
            target_address = device.address
            print(f"ADRESA NALEZENA: {target_address}")
            print("Vypínám skener. Odteď se připojuji PŘÍMO (bude to rychlejší).")
        else:
            print("... stále hledám ...")

    # FÁZE 2: NEKONEČNÁ SMYČKA PŘÍMÉHO PŘIPOJOVÁNÍ
    # Už nikdy neskenujeme. Jen se dokola snažíme připojit na známou adresu.
    while True:
        print(f"📡 Čekám na probuzení joysticku ({target_address})...")
        
        try:
            # timeout=20.0 znamená: RPi bude 20 sekund aktivně 'číhat' na tuto adresu.
            # Jakmile se ESP32 probudí, RPi to zachytí okamžitě (bez skenování).
            async with BleakClient(
                target_address, 
                disconnected_callback=disconnected_callback, 
                timeout=20.0
            ) as client:
                
                print("PŘIPOJENO! Ovladač je aktivní.")
                
                # Aktivace notifikací
                await client.start_notify(UART_TX_CHAR_UUID, notification_handler)
                
                # Smyčka udržující spojení naživu
                while client.is_connected:
                    await asyncio.sleep(0.5)
            
            # Zde se kód dostane, jen když se zařízení odpojí
            # Smyčka while True zajistí okamžitý návrat k pokusu o připojení

        except Exception as e:
            # Pokud vyprší 20s timeout (nikdo se neprobudil), nebo se připojení nezdaří:
            # print(f"Info: {e}") # Pro debug odkomentujte
            # Krátká pauza a zkusíme to hned znovu
            await asyncio.sleep(0.1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Ukončuji...")
        mqtt_client.loop_stop()
