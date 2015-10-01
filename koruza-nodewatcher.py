#!/usr/bin/env python
import json
import os
import requests
import sqlite3
import sys
import time
import uuid
import OpenSSL

# Namespace for KORUZA device UUIDs.
KORUZA_UUID_NAMESPACE = uuid.UUID('d52e15af-f8ca-4b1b-b982-c70bb3d1ec4e')
# Database location.
KORUZA_DATABASE = '/var/tmp/koruza/database.db'
# Nodewatcher push interval (in seconds).
NODEWATCHER_PUSH_INTERVAL = 300
# Nodewatcher push URL.
NODEWATCHER_PUSH_URL = 'https://push.nodes.wlan-si.net/push/http/%(uuid)s'
# Private key and certificate location.
NODEWATCHER_CERTIFICATE = '/koruza/config/nodewatcher-authentication.crt'
NODEWATCHER_PRIVATE_KEY = '/koruza/config/nodewatcher-authentication.key'
# Sensor data that should be reported.
REPORT_SENSOR_DATA = {
    'motor_accel': {'name': "Motor Acceleration", 'unit': ""},
    'motor_command': {'name': "Motor Command", 'unit': ""},
    'motor_current_f': {'name': "Motor Current F", 'unit': ""},
    'motor_current_x': {'name': "Motor Current X", 'unit': ""},
    'motor_current_y': {'name': "Motor Current Y", 'unit': ""},
    'motor_empty': {'name': "Motor Empty", 'unit': ""},
    'motor_flash_status': {'name': "Motor Flash Status", 'unit': ""},
    'motor_flash_write_count': {'name': "Motor Flash Write Count", 'unit': ""},
    'motor_laser': {'name': "Motor Laser", 'unit': ""},
    'motor_max_f': {'name': "Motor Maximum F", 'unit': ""},
    'motor_max_x': {'name': "Motor Maximum X", 'unit': ""},
    'motor_max_y': {'name': "Motor Maximum Y", 'unit': ""},
    'motor_next_f': {'name': "Motor Next F", 'unit': ""},
    'motor_next_x': {'name': "Motor Next X", 'unit': ""},
    'motor_next_y': {'name': "Motor Next Y", 'unit': ""},
    'motor_speed': {'name': "Motor Speed", 'unit': ""},
    'motor_status_f': {'name': "Motor Status F", 'unit': ""},
    'motor_status_x': {'name': "Motor Status X", 'unit': ""},
    'motor_status_y': {'name': "Motor Status Y", 'unit': ""},
    'remote_connected': {'name': "Remote Connected", 'unit': ""},
    'sfp_rx_power_mw': {'name': "SFP RX Power", 'unit': "mW"},
    'case_temperature_c': {'name': "Case Temperature", 'unit': "C"},
    'sfp_temperature_c': {'name': "SFP Temperature", 'unit': "C"},
    'sfp_tx_bias_ma': {'name': "SFP TX Bias", 'unit': "mA"},
    'sfp_tx_power_mw': {'name': "SFP TX Power", 'unit': "mW"},
    'sfp_vcc_v': {'name': "SFP VCC", 'unit': "V"},
}

# Generate node UUID from this node's MAC address.
node_uuid = uuid.uuid5(KORUZA_UUID_NAMESPACE, hex(uuid.getnode()).upper()[2:-1])
print "INIT: Initialized on node with UUID '%s'." % str(node_uuid)

# Generate private key and certifikate if needed.
if not os.path.exists(NODEWATCHER_CERTIFICATE) or not os.path.exists(NODEWATCHER_PRIVATE_KEY):
    print "INIT: Generating nodewatcher authentication certificate..."

    # Generate private key.
    private_key = OpenSSL.crypto.PKey()
    private_key.generate_key(OpenSSL.crypto.TYPE_RSA, 2048)

    # Generate self-signed certificate.
    certificate = OpenSSL.crypto.X509()
    certificate.get_subject().C = "SI"
    certificate.get_subject().ST = "Slovenia"
    certificate.get_subject().L = "Slovenia"
    certificate.get_subject().O = "IRNAS"
    certificate.get_subject().OU = "KORUZA"
    certificate.get_subject().CN = str(node_uuid)
    certificate.set_serial_number(1)
    certificate.gmtime_adj_notBefore(0)
    certificate.gmtime_adj_notAfter(10*365*24*60*60)
    certificate.set_issuer(certificate.get_subject())
    certificate.set_pubkey(private_key)
    certificate.sign(private_key, 'sha256')

    # Store certificate file.
    try:
        with open(NODEWATCHER_CERTIFICATE, 'wt') as certificate_file:
            certificate_file.write(OpenSSL.crypto.dump_certificate(OpenSSL.crypto.FILETYPE_PEM, certificate))

        with open(NODEWATCHER_PRIVATE_KEY, 'wt') as key_file:
            key_file.write(OpenSSL.crypto.dump_privatekey(OpenSSL.crypto.FILETYPE_PEM, private_key))
    except IOError:
        print "ERROR: Failed to write certificate to '%s'!" % NODEWATCHER_CERTIFICATE
        sys.exit(1)

    print "INIT: Nodewatcher authentication certificate ready."
else:
    print "INIT: Nodewatcher authentication certificate ready."

while True:
    # Query the sqlite database for any updates.
    try:
        database = sqlite3.connect(KORUZA_DATABASE)
        database.row_factory = sqlite3.Row

        try:
            cursor = database.execute('SELECT * FROM local')
            try:
                data = cursor.fetchone()

                # Generate nodewatcher JSON.
                feed = {
                    'sensors.generic': {
                        '_meta': {
                            'version': 1,
                        }
                    }
                }

                for key in data.keys():
                    if key not in REPORT_SENSOR_DATA:
                        continue

                    descriptor = REPORT_SENSOR_DATA[key]
                    feed['sensors.generic'][key] = {
                        'name': descriptor['name'],
                        'unit': descriptor['unit'],
                        'value': float(data[key]),
                    }

                # Post update to nodewatcher.
                try:
                    request = requests.post(
                        NODEWATCHER_PUSH_URL % {'uuid': str(node_uuid)},
                        data=json.dumps(feed),
                        cert=(NODEWATCHER_CERTIFICATE, NODEWATCHER_PRIVATE_KEY),
                    )

                    # Check for successful post.
                    if request.json()['status'] != 'ok':
                        print "WARNING: Received failure while pushing to nodewatcher."
                    else:
                        print "OK: Data pushed to nodewatcher."
                except (requests.HTTPError, requests.ConnectionError, ValueError):
                    print "WARNING: Failed to push data to nodewatcher."
            finally:
                cursor.close()
        finally:
            database.close()
    except (sqlite3.OperationalError, AttributeError):
        print "WARNING: Failed to access the status database."

    time.sleep(NODEWATCHER_PUSH_INTERVAL)
