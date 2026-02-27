import asyncio
from bleak import BleakClient
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

current_status = ""

def publish_status(status):
    global current_status
    if current_status != status:
        print(f"STAV -> {status}") 
        client.publish(TOPIC_STATUS, status, retain=True)
        current_status = status

def notification_handler(sender, data):
    command = data.decode('utf-8').strip()
    print(f"Přijato z BLE: {command}")
    client.publish(MQTT_TOPIC, command)

def disconnected_callback(client_ble):
    pass # Odpojení řešíme v hlavní smyčce, zamezuje spamu z Linuxu

# ASYNCHRONNÍ exekuce systémových příkazů (Nezmrazí Python smyčku!)
async def run_bt_cmd(*args):
    try:
        proc = await asyncio.create_subprocess_exec(
            'bluetoothctl', *args,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        await proc.wait()
    except Exception as e:
        print(f"Chyba při systémovém příkazu: {e}")

async def connect_and_listen():
    print(f"--- SPUŠTĚN PASIVNÍ (INDEXOVÝ) REŽIM NA {TARGET_MAC} ---")
    publish_status("SLEEP")
    
    while True:
        try:
            # NATIVNÍ PŘIPOJENÍ BEZ SKENERU
            # Tohle je naše "Buy and Hold" strategie. Žádné skenování navíc, 
            # prostě BleakClientovi zadáme cíl a necháme ho dělat jeho práci.
            async with BleakClient(TARGET_MAC, disconnected_callback=disconnected_callback, timeout=8.0) as client_ble:
                publish_status("READY") 
                print("+++ PŘIPOJENO! Ovladač je aktivní. +++")
                
                await client_ble.start_notify(UART_TX_CHAR_UUID, notification_handler)
                
                # Udržujeme spojení, dokud pacient neustane v činnosti a ESP32 samo neusne
                while client_ble.is_connected:
                    await asyncio.sleep(0.5)
            
            # Zde jsme, pokud se ESP32 korektně odpojilo (usnulo)
            publish_status("SLEEP")
            await asyncio.sleep(0.5)
            
        except Exception as e:
            error_msg = str(e)
            
            # TICHÁ ABSORPCE ŠUMU: Pokud ovladač prostě spí, Bleak vyhodí "not found".
            # To je naprosto běžný stav, nebudeme s ním spamovat terminál a dělat paniku.
            if "was not found" in error_msg or "Device with address" in error_msg:
                publish_status("SLEEP")
                await asyncio.sleep(0.5)
                continue
            
            # Pokud to není běžný spánek, je to chyba Linuxového adaptéru
            print(f"   [Chyba Linuxu] {error_msg}")
            publish_status("CONNECTING") # Dáme webovému rozhraní vědět, že to řešíme
            
            # Rychlý úklid portů bez tvrdého restartu, aby se to odseklo
            if "In Progress" in error_msg or "br-connection-canceled" in error_msg or "discover services" in error_msg:
                await run_bt_cmd('disconnect', TARGET_MAC)
                await asyncio.sleep(1.5)
            else:
                await asyncio.sleep(1.0)

if __name__ == "__main__":
    try:
        asyncio.run(connect_and_listen())
    except KeyboardInterrupt:
        print("\nUkončuji program...")
        publish_status("SLEEP")
        sys.exit(0)
