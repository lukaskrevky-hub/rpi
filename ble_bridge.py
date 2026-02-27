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
    pass # Odpojení řešíme v hlavní smyčce, zamezuje spamu

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
    print(f"--- SPUŠTĚN ASYNCHRONNÍ REŽIM PŘIPOJOVÁNÍ NA {TARGET_MAC} ---")
    publish_status("SLEEP")
    
    consecutive_errors = 0
    
    while True:
        try:
            # 1. Hledáme zařízení (Skener)
            device = await BleakScanner.find_device_by_address(TARGET_MAC, timeout=2.0)
            
            if device:
                publish_status("CONNECTING")
                
                # ZLATÁ PAUZA: Nutná pro Linux! Protože ESP32 teď čeká 30s,
                # máme spoustu času nechat BlueZ modul uzavřít skenování.
                await asyncio.sleep(1.0)
                
                # 2. Připojení k nalezenému objektu
                async with BleakClient(device, disconnected_callback=disconnected_callback, timeout=10.0) as client_ble:
                    publish_status("READY") 
                    print("+++ PŘIPOJENO! Ovladač je aktivní. +++")
                    consecutive_errors = 0
                    
                    await client_ble.start_notify(UART_TX_CHAR_UUID, notification_handler)
                    
                    # Udržujeme spojení
                    while client_ble.is_connected:
                        await asyncio.sleep(0.5)
                
                # Odpojení proběhlo korektně (ESP32 usnulo)
                publish_status("SLEEP")
                await asyncio.sleep(0.5)
                
            else:
                await asyncio.sleep(0.5)
                
        except Exception as e:
            error_msg = str(e)
            print(f"   [Chyba Linuxu] {error_msg}")
            publish_status("SLEEP")
            
            # OPRAVENÝ ÚKLID: Nezmrazuje aplikaci
            if "discover services" in error_msg:
                print("!!! Poškozená mezipaměť. Mažu profil...")
                await run_bt_cmd('remove', TARGET_MAC)
                await asyncio.sleep(1.5)
            
            elif "br-connection-canceled" in error_msg or "In Progress" in error_msg:
                await run_bt_cmd('disconnect', TARGET_MAC)
                consecutive_errors += 1
                await asyncio.sleep(1.0)
            
            else:
                await asyncio.sleep(1.0)
            
            # Tvrdý restart adaptéru
            if consecutive_errors >= 3:
                print("!!! Tvrdý restart Bluetooth napájení...")
                await run_bt_cmd('power', 'off')
                await asyncio.sleep(1.0)
                await run_bt_cmd('power', 'on')
                consecutive_errors = 0
                await asyncio.sleep(2.0)

if __name__ == "__main__":
    try:
        asyncio.run(connect_and_listen())
    except KeyboardInterrupt:
        print("\nUkončuji program...")
        publish_status("SLEEP")
        sys.exit(0)
