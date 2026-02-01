import asyncio
from bleak import BleakScanner, BleakClient
import paho.mqtt.client as mqtt
import sys

# --- KONFIGURACE ---
ESP_NAME = "ESP32-Joystick"
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

def disconnected_callback(client):
    print("Joystick se odpojil (spojení ztraceno).")

async def main():
    print("Startuji Rychlý Bridge v2 (Direct Connect)...")
    
    target_address = None

    # FÁZE 1: ZÍSKÁNÍ ADRESY (Skenujeme jen jednou na začátku)
    print("Hledám joystick, abych zjistil jeho adresu...")
    
    while target_address is None:
        device = await BleakScanner.find_device_by_filter(
            lambda d, ad: d.name and d.name == ESP_NAME,
            timeout=5.0
        )
        if device:
            target_address = device.address
            print(f"ADRESA NALEZENA: {target_address}")
            print("Vypínám skener. Odteď se připojuji napřímo.")
        else:
            print("... stále hledám (zkuste pohnout páčkou) ...")

    # FÁZE 2: NEKONEČNÁ SMYČKA PŘÍMÉHO PŘIPOJOVÁNÍ
    # Už nikdy neskenujeme. Jen se dokola snažíme připojit na známou adresu.
    while True:
        print(f"Zkouším přímé připojení k {target_address}...")
        
        try:
            # timeout=5.0: Zkouší se připojit 5 sekund, pokud se nepovede, zkusí to hned znovu
            async with BleakClient(target_address, disconnected_callback=disconnected_callback, timeout=5.0) as client:
                print("PŘIPOJENO! Ovladač je aktivní.")
                
                # Aktivace notifikací
                await client.start_notify(UART_TX_CHAR_UUID, notification_handler)
                
                # Smyčka udržující program naživu, dokud je spojení aktivní
                while client.is_connected:
                    await asyncio.sleep(1.0)
            
            # Zde se kód dostane, jen když 'async with' skončí (odpojení)
            print("INFO: Cyklus připojení ukončen, jdu to zkusit znovu...")

        except Exception as e:
            # Pokud se připojení nepovede (joystick spí), vypíšeme chybu a zkusíme to hned znovu
            # print(f"Čekám na joystick... ({e})") # Odkomentujte pro detailní výpis
            await asyncio.sleep(0.5) # Malá pauza, aby procesor nejel na 100%

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Ukončuji...")
        mqtt_client.loop_stop()
