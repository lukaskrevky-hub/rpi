import asyncio
from bleak import BleakScanner, BleakClient
import paho.mqtt.client as mqtt
import sys

# --- KONFIGURACE ---
# Musí přesně odpovídat jménu v ESP32!
ESP_NAME = "ESP32-Joystick"
# Standardní UUID pro Nordic UART Service (TX charakteristika)
UART_TX_CHAR_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

# --- MQTT SETUP ---
MQTT_BROKER = "localhost"
MQTT_TOPIC = "joystick/command"

# Oprava pro novější verze knihovny Paho MQTT
mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

try:
    mqtt_client.connect(MQTT_BROKER, 1883, 60)
    mqtt_client.loop_start()
    print(f"MQTT připojeno.")
except Exception as e:
    print(f"Chyba MQTT: {e}")
    sys.exit(1)

# --- CALLBACKY ---

def notification_handler(sender, data):
    """Tato funkce se spustí pokaždé, když joystick pošle data."""
    try:
        command = data.decode('utf-8').strip()
        print(f"--> Přijato z BLE: {command}")
        mqtt_client.publish(MQTT_TOPIC, command)
    except:
        pass

def disconnected_callback(client):
    """Tato funkce se spustí, když se spojení přeruší."""
    print("Spojení ztraceno! Okamžitě se pokouším o obnovu...")

# --- HLAVNÍ SMYČKA ---

async def main():
    print("Startuji Trvalý Bridge (Režim Always On)...")
    
    target_address = None

    # FÁZE 1: ZÍSKÁNÍ ADRESY (Skenujeme jen jednou)
    print("Hledám joystick, abych zjistil jeho adresu...")
    while target_address is None:
        device = await BleakScanner.find_device_by_filter(
            lambda d, ad: d.name and d.name == ESP_NAME,
            timeout=5.0
        )
        if device:
            target_address = device.address
            print(f"ADRESA NALEZENA: {target_address}")
            print("Vypínám skener. Odteď držím trvalé spojení.")
        else:
            print("... stále hledám (zapněte joystick) ...")

    # FÁZE 2: NEKONEČNÁ SMYČKA DRŽENÍ SPOJENÍ
    while True:
        print(f"Připojuji se k {target_address}...")
        
        try:
            # timeout=15.0: Zkoušíme se připojit 15 sekund.
            async with BleakClient(target_address, disconnected_callback=disconnected_callback, timeout=15.0) as client:
                print("PŘIPOJENO! Ovladač je aktivní a připraven.")
                
                # Zapneme příjem dat
                await client.start_notify(UART_TX_CHAR_UUID, notification_handler)
                
                # Tady program "visí" a drží spojení, dokud se nepřeruší
                while client.is_connected:
                    await asyncio.sleep(1.0)
            
            # Sem se dostaneme jen při odpojení
            print("INFO: Spojení ukončeno, restartuji cyklus...")

        except Exception as e:
            # Pokud se připojení nepovede (např. joystick je vypnutý/vybitý)
            # print(f"Chyba připojení: {e}") 
            await asyncio.sleep(1.0) # Počkáme vteřinu a zkusíme to hned znovu

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Ukončuji...")
        mqtt_client.loop_stop()
