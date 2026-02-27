import asyncio
from bleak import BleakClient, BleakScanner
import paho.mqtt.client as mqtt
import sys

# ==========================================
# CÍLOVÁ MAC ADRESA
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
    client.publish(MQTT_TOPIC, command)

async def kill_ghost_connection():
    """Tento buldozer okamžitě smaže zaseknuté spojení z paměti Linuxu, 
       aby bylo RPi připraveno na další bleskové připojení."""
    try:
        proc = await asyncio.create_subprocess_exec(
            'bluetoothctl', 'disconnect', TARGET_MAC,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        await proc.wait()
    except Exception:
        pass

async def connect_and_listen():
    print(f"--- SPUŠTĚN BLESKOVÝ REŽIM NA {TARGET_MAC} ---")
    publish_status("SLEEP")
    
    # Pro jistotu vyčistíme porty hned po startu skriptu
    await kill_ghost_connection()
    
    while True:
        try:
            # 1. Tichá a neviditelná smyčka - čekáme, až se ovladač objeví ve vzduchu
            device = None
            while not device:
                device = await BleakScanner.find_device_by_address(TARGET_MAC, timeout=3.0)
            
            publish_status("CONNECTING")
            
            # 2. Okamžité připojení
            async with BleakClient(device, timeout=7.0) as client_ble:
                publish_status("READY") 
                print("\n+++ PŘIPOJENO! Ovladač je aktivní. +++")
                
                await client_ble.start_notify(UART_TX_CHAR_UUID, notification_handler)
                
                # Držíme spojení
                while client_ble.is_connected:
                    await asyncio.sleep(0.2)
            
            # 3. Jakmile se ESP32 uspí, jdeme okamžitě uklízet
            print("--- Ovladač usnul ---")
            publish_status("SLEEP")
            await kill_ghost_connection() # ZABITÍ DUCHA
            
        except Exception:
            # Pokud dojde k jakékoliv chybě (např. In Progress), 
            # nevyplivneme chybu do terminálu, ale rovnou vyčistíme port.
            publish_status("SLEEP")
            await kill_ghost_connection()
            await asyncio.sleep(0.5)

if __name__ == "__main__":
    try:
        asyncio.run(connect_and_listen())
    except KeyboardInterrupt:
        print("\nUkončuji program...")
        publish_status("SLEEP")
        sys.exit(0)
