from mqtt import MQTTClient
import micropython
import urequests
import ubinascii
import machine
from machine import Pin, ADC
import onewire
import ds18x20
import network
import ntptime
import random
import ujson
import time
import esp
import dht
import os
import gc

machine.freq(80000000)
esp.osdebug(None)
gc.collect()
rtc = machine.RTC()
dht22 = dht.DHT22(Pin(4))
panel_temp = ds18x20.DS18X20(onewire.OneWire(Pin(23)))
panel_naprazdno = ADC(Pin(2))
panel_naprazdno.atten(ADC.ATTN_11DB)
panel_zatez = ADC(Pin(15))
panel_zatez.atten(ADC.ATTN_0DB)
#sensors = panel_temp.scan()
FW_VERSION = 0.01
UID = int(machine.unique_id().hex(), 16)
MQTT_POST_TOPIC = "/mfve/" + str(UID) + "/data"
print(MQTT_POST_TOPIC)
WIFI_SSID = ''
WIFI_PASS = ''
mqtt_server = ''
mqtt_user = ''
mqtt_port = 0
mqtt_pass = ''
perioda_mereni = 0
perioda_posilani = 0
namereno = 0
last_unix_time = 0
unix_epoch_difference = 946684796
send = False
sampling_config = {}
data = {}
fw_config = {}
data_zero = {}
vykon , proud, teplota, timestamp, vlhkost, napeti_zatez, napeti_naprazdno, teplota_panel = 0,0,0,0,0,0,0,0
napeti_hod = 0
timezone = 0
last_update_check = 0
send_success = True
files = ["main.py"]

with open('fw_config.json', 'r') as f:
    fw_config = ujson.load(f)
    timezone = fw_config['timezone']
    last_update_check = fw_config['last_update_check']
with open('sampling_config.json', 'r') as f:
    sampling_config = ujson.load(f)
    perioda_mereni = sampling_config['perioda_mereni']
    perioda_posilani = sampling_config['perioda_posilani']
    namereno = sampling_config['namereno']

with open('data.json', 'r') as f:
    data = ujson.load(f)
    
last_message = 0
message_interval = 5
counter = 0

def Measure():
    global send, perioda_mereni, perioda_posilani, sampling_config, namereno, data, vykon , proud, teplota, timestamp, vlhkost, napeti_zatez, napeti_naprazdno, teplota_panel, timezone
    namereno += 1
    sample_count = int(perioda_posilani / perioda_mereni)
    if sample_count == namereno:
        send = True
        sampling_config['namereno'] = 0
        with open('sampling_config.json', 'w') as f:
            ujson.dump(sampling_config, f)
    else:
        sampling_config['namereno'] = namereno
        with open('sampling_config.json', 'w') as f:
            ujson.dump(sampling_config, f)
            
    #dht22.measure()
    
    teplota = data['teplota']
    teplota.append(random.randint(20,25))#dht22.temperature())
    data['teplota'] = teplota
    
    vlhkost = data['vlhkost']
    vlhkost.append(random.randint(40,50))
    vlhkost = data['vlhkost']
    
    #panel_temp.convert_temp()
    teplota_panel = data['teplota_panel']
    teplota_panel.append(random.randint(40,50))#panel_temp.read_temp(sensors[0]))
    data['teplota_panel'] = teplota_panel
     
    napeti_hod = round((panel_zatez.read() * (1.2 / 4095)), 3)
    napeti_zatez = data['napeti_zatez']
    napeti_zatez.append(random.randint(100,200) / 100)
    data['napeti_zatez'] = napeti_zatez
    
    napeti_naprazdno = data['napeti_naprazdno']
    napeti_naprazdno.append(random.randint(6000,6450) / 100)
    data['napeti_naprazdno'] = napeti_naprazdno
    
    vykon = data['vykon']
    vykon.append((((napeti_hod * napeti_hod) / 9) * 727.272727))
    data['vykon'] = vykon
    
    proud = data['proud']
    proud.append(round(napeti_hod / 9, 4))
    data['proud'] = proud
    
    timestamp = data['timestamp']
    timenow = time.time()
    timestamp.append((unix_epoch_difference + (timezone * 3600) + timenow))
    data['timestamp'] = timestamp
    
    with open('data.json', 'w') as f:
        ujson.dump(data, f)
        
def WiFiBegin():
    global mqtt_pass, mqtt_port, mqtt_server, mqtt_user, send_success
    counter = 0
    with open('wifi_config.json', 'r') as f:
        wifi_config = ujson.load(f)
        WIFI_SSID = wifi_config['SSID']
        WIFI_PASS = wifi_config['PASS']
    with open('mqtt_config.json', 'r') as f:
        mqtt_config = ujson.load(f)
        mqtt_server = mqtt_config['server']
        mqtt_user = mqtt_config['user']
        mqtt_port = mqtt_config['port']
        mqtt_pass = mqtt_config['pass']
    station = network.WLAN(network.STA_IF)
    station.active(True)
    station.connect(WIFI_SSID, WIFI_PASS)
    while station.isconnected() == False or counter > 10:
        print("Attempting to connect to '" + WIFI_SSID + "'")
        time.sleep(2)
        counter += 1
    if station.isconnected():
        print("Connected to '" + WIFI_SSID + "'" + " with IP address: " + station.ifconfig()[0])
        #ntptime.settime()
    else:
        send_success = False

def CheckUpdate():
    global FW_VERSION
    url = "https://raw.githubusercontent.com/OMEGA-TSC/ESP32_Firmware_update_dev/main/update.json"
    response = urequests.get(url)
    json_string = response.text
    try:
        data = ujson.loads(json_string)
        version = data['version']
        if version > FW_VERSION:
            return True
        else:
            return False
    except ValueError:
        print("Error parsing JSON data")
    response.close()
                     
def Update():
    global files
    success = False
    print('Downloading files')
    for file in files:
        success = False
        while not success:
            response = urequests.get("https://raw.githubusercontent.com/OMEGA-TSC/ESP32_Firmware_update_dev/main/" + file)
            x = response.text
            response = urequests.get("https://raw.githubusercontent.com/OMEGA-TSC/ESP32_Firmware_update_dev/main/" + file)
            if response.text == x:
                f = open(file,"w")
                f.write(response.text)
                response.close()
                f.flush()
                f.close
                success = True
            else:
                success = False
                
def sub_cb(topic, msg):
    print((topic, msg))
    if topic == b'hello' and msg == b'received':
        print('ESP received hello message')
  
def SendData():
    global data_zero, MQTT_POST_TOPIC, data, UID, mqtt_server, mqtt_pass, mqtt_port, mqtt_user, send_success
    try:
        client = MQTTClient(str(UID), mqtt_server, user=mqtt_user, password=mqtt_pass, port=mqtt_port, keepalive=60)
        client.connect()
        print('Connected to %s MQTT broker' % mqtt_server)
        client.check_msg()
        client.publish(MQTT_POST_TOPIC, str(data))
    except OSError as e:
        send_success = False
        print(e)
    if send_success:
        with open('data_zero.json', 'r') as f:
            data_zero = ujson.load(f)
        with open('data.json', 'w') as f:
            ujson.dump(data_zero, f)

    
def main():
    global fw_config, send, last_update_check, send_success
    Measure()
    if send:   
        WiFiBegin()
        if send_success:
            SendData() 
            timenow = time.time()
            if timenow > (last_update_check + 86400):
                fw_config['last_update_check'] = timenow
                with open('fw_config.json', 'w') as f:
                    ujson.dump(fw_config, f)
                update = CheckUpdate()
                if update:
                    Update()
    machine.deepsleep((perioda_mereni * 1000) - 200)   
main()
