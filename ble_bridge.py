import asyncio
from bleak import BleakClient, BleakScanner
import paho.mqtt.client as mqtt
import sys

# ==========================================
# CÍLOVÁ MAC ADRESA (Potvrzená)
TARGET_MAC = "10:06:1C:B5:A7:36"
# ==========================================

UART_TX_CHAR_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"
MQTT_BROKER = "localhost"
MQTT_TOPIC = "joystick/command"
TOPIC_STATUS = "joystick/status" 

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

try:
    client.connect(MQTT_BROKER, 1883, 60)
    client.loop_start()
    print("MQTT připojeno.")
except Exception as e:
    print(f"Chyba MQTT: {e}")
    sys.exit(1)

def publish_status(status):
    print(f"STAV -> {status}") 
    client.publish(TOPIC_STATUS, status, retain=True)

def notification_handler(sender, data):
    command = data.decode('utf-8').strip()
    print(f"Přijato z BLE: {command}")
    client.publish(MQTT_TOPIC, command)

def disconnected_callback(client):
    print(">>> Ztráta spojení (Joystick usnul nebo byl výpadek).")
    publish_status("SLEEP")

async def connect_and_listen():
    print(f"--- SPUŠTĚN STABILNÍ REŽIM PŘIPOJOVÁNÍ NA {TARGET_MAC} ---")
    publish_status("SLEEP")
    
    while True:
        try:
            # 1. Použijeme krátký skener (2 vteřiny). 
            # Je to nutné, aby Linux nenačítal mrtvá spojení ze své zablokované paměti.
            device = await BleakScanner.find_device_by_address(TARGET_MAC, timeout=2.0)
            
            if device:
                print("Nalezeno! Navazuji spojení...")
                publish_status("CONNECTING")
                
                # 2. Připojíme se přímo k zachycenému 'device' (nejodolnější metoda)
                async with BleakClient(device, disconnected_callback=disconnected_callback) as client_ble:
                    print("+++ PŘIPOJENO! Ovladač je aktivní. +++")
                    publish_status("READY") 
                    
                    await client_ble.start_notify(UART_TX_CHAR_UUID, notification_handler)
                    
                    # Dokud spojení běží, jsme v této smyčce
                    while client_ble.is_connected:
                        await asyncio.sleep(0.5)
                
                # 3. ZLATÉ PRAVIDLO LINUXU:
                # Sem se kód dostane, když se ESP32 odpojí. 
                # Abychom se vyhnuli chybě 'br-connection-canceled', 
                # MUSÍME dát Bluetooth modulu chvíli na uzavření starých procesů.
                print("Dávám systému 1.5 vteřiny na vyčištění socketů...")
                await asyncio.sleep(1.5)
                
            else:
                # Joystick zrovna spí, nebudeme spamovat a chvíli počkáme
                await asyncio.sleep(0.5)
                
        except Exception as e:
            print(f"Výpadek: {e}")
            # Záchranná síť: Pokud i tak BlueZ vyhodí "In Progress" nebo jinou chybu,
            # nesmíme na něj tlačit dalším pokusem. Necháme ho 2 vteřiny "vydechnout".
            print("Přetížení modulu! Uklidňuji systém na 2 vteřiny...")
            await asyncio.sleep(2.0)

if __name__ == "__main__":
    try:
        asyncio.run(connect_and_listen())
    except KeyboardInterrupt:
        print("\nUkončuji program...")
        publish_status("SLEEP")
        sys.exit(0)
