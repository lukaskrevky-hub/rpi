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

async def hard_reset_bluetooth():
    """Nekompromisní restart celého adaptéru - vypne a zapne napájení."""
    print(">>> PROVÁDÍM TVRDÝ RESTART BLUETOOTH ADAPTÉRU <<<")
    try:
        # Vypnutí Bluetooth
        proc_off = await asyncio.create_subprocess_exec(
            'bluetoothctl', 'power', 'off',
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        await proc_off.wait()
        await asyncio.sleep(1.0) # Dáme modulu 1 vteřinu na úplné vybití
        
        # Zapnutí Bluetooth
        proc_on = await asyncio.create_subprocess_exec(
            'bluetoothctl', 'power', 'on',
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        await proc_on.wait()
        await asyncio.sleep(2.0) # Dáme modulu 2 vteřiny na kompletní nastartování
        print(">>> ADAPTÉR JE ČISTÝ A PŘIPRAVENÝ <<<")
    except Exception as e:
        print(f"Chyba při restartu: {e}")

async def connect_and_listen():
    print(f"--- SPUŠTĚN REŽIM S TVRDÝM RESTARTEM NA {TARGET_MAC} ---")
    publish_status("SLEEP")
    
    # 1. Čistý stůl hned po startu
    await hard_reset_bluetooth()
    
    while True:
        try:
            # Čekáme, až se ovladač objeví ve vzduchu
            device = None
            while not device:
                device = await BleakScanner.find_device_by_address(TARGET_MAC, timeout=3.0)
            
            publish_status("CONNECTING")
            print(">>> Ovladač nalezen. Navazuji spojení...")
            
            # Drobná pauza už stačí, adaptér je dokonale čistý
            await asyncio.sleep(0.5)
            
            # Připojení k nalezenému objektu
            async with BleakClient(device, timeout=10.0) as client_ble:
                publish_status("READY") 
                print("\n+++ PŘIPOJENO! Ovladač je aktivní. +++")
                
                await client_ble.start_notify(UART_TX_CHAR_UUID, notification_handler)
                
                # Držíme spojení, dokud pacient neustane v činnosti
                while client_ble.is_connected:
                    await asyncio.sleep(0.5)
            
            # Jakmile se ESP32 uspí...
            print("--- Ovladač usnul ---")
            publish_status("SLEEP")
            
            # 2. OKAMŽITÝ TVRDÝ RESTART!
            # Uživatel teď ovladač nepotřebuje, takže máme čas (3 vteřiny) 
            # na pozadí Linux vyčistit, aby byl připraven na další použití.
            await hard_reset_bluetooth()
            
        except Exception as e:
            error_msg = str(e)
            
            if "was not found" not in error_msg:
                print(f"   [Chyba spojení] {error_msg}")
                
            publish_status("SLEEP")
            
            # 3. Tvrdý restart při jakékoliv chybě
            await hard_reset_bluetooth()

if __name__ == "__main__":
    try:
        asyncio.run(connect_and_listen())
    except KeyboardInterrupt:
        print("\nUkončuji program...")
        publish_status("SLEEP")
        sys.exit(0)
