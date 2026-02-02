import asyncio
from bleak import BleakScanner, BleakClient, BleakError
import paho.mqtt.client as mqtt
import sys

# --- KONFIGURACE ---
# Musí odpovídat jménu v ESP32!
ESP_NAME = "ESP32-Joystick"
UART_TX_CHAR_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

# --- MQTT SETUP ---
MQTT_BROKER = "localhost"
MQTT_TOPIC = "joystick/command"

# Oprava pro novější verze knihovny
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
    print("Joystick se odpojil.")

# --- HLAVNÍ SMYČKA ---
async def main():
    print("Startuji Synchronizovaný Bridge...")
    
    target_address = None

    # FÁZE 1: ZÍSKÁNÍ ADRESY (Skenujeme jen jednou na začátku)
    print("První hledání: Prosím, probuďte joystick (hýbejte páčkou)...")
    
    while target_address is None:
        device = await BleakScanner.find_device_by_filter(
            lambda d, ad: d.name and d.name == ESP_NAME,
            timeout=5.0
        )
        if device:
            target_address = device.address
            print(f"ADRESA NALEZENA: {target_address}")
            print("Vypínám skener. Přecházím na agresivní připojování.")
        else:
            print("... stále hledám ...")

    # FÁZE 2: NEKONEČNÁ SMYČKA PŘIPOJOVÁNÍ
    while True:
        print(f"Čekám na signál od {target_address}...")
        
        client = None
        try:
            # timeout=10.0: Zkoušíme se připojit 10 sekund.
            # Pokud joystick spí, vyhodí to chybu (to je v pořádku).
            # Pokud se probudí, chytne se to téměř hned.
            client = BleakClient(target_address, disconnected_callback=disconnected_callback, timeout=10.0)
            await client.connect()
            
            print("PŘIPOJENO! Ovladač je aktivní.")
            
            # Aktivace notifikací
            await client.start_notify(UART_TX_CHAR_UUID, notification_handler)
            
            # Smyčka udržující spojení naživu
            while client.is_connected:
                await asyncio.sleep(0.5)
        
        except BleakError:
            # Specifická chyba Bluetooth (zařízení nedostupné/spí)
            # Nevypisujeme celý traceback, jen info, že čekáme
            # print(".", end="", flush=True)
            await asyncio.sleep(0.2)
            
        except Exception as e:
            print(f"Chyba: {e}")
            await asyncio.sleep(1.0)
            
        finally:
            # Důležité: Ujistíme se, že je klient čistě odpojen před dalším pokusem
            if client:
                try:
                    await client.disconnect()
                except:
                    pass

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Ukončuji...")
        mqtt_client.loop_stop()


