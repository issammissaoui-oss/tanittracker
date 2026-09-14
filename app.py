from flask import Flask, jsonify, render_template_string
import json
import threading
import websocket
import time
import os

app = Flask(__name__)

AIS_API_KEY = "ea9d58747246902dbd8d544a2fe5a3137caf2a59"
TANIT_MMSI = "672748000"

# Position initiale dans le port de La Goulette (bassin)
ship_data = {
    "mmsi": TANIT_MMSI,
    "name": "C/F TANIT",
    "latitude": 36.8122,  
    "longitude": 10.3094,
    "speed": 0.0,
    "course": 0.0,
    "timestamp": "En attente du flux...",
    "packets": 0,
    "status": "Connexion au flux AIS en cours..."
}

def on_message(ws, message):
    global ship_data
    try:
        packet = json.loads(message)
        msg_type = packet.get("MessageType")
        
        if msg_type == "SubscriptionConfirmation":
            ship_data["status"] = "Connecté au flux (Écoute active)"
            print("[AIS] Abonnement validé par aisstream.io.")
            return

        meta = packet.get("MetaData", {})
        mmsi_str = str(meta.get("MMSI", ""))
        ship_name = meta.get("ShipName", "").strip().upper()
        
        if TANIT_MMSI in mmsi_str or "TANIT" in ship_name:
            pos = {}
            if msg_type == "PositionReport":
                pos = packet.get("Message", {}).get("PositionReport", {})
            elif msg_type == "StandardClassBPositionReport":
                pos = packet.get("Message", {}).get("StandardClassBPositionReport", {})
            
            lat = pos.get("Latitude")
            lon = pos.get("Longitude")
            
            if lat is not None and lon is not None and lat != 0 and lon != 0:
                ship_data["latitude"] = float(lat)
                ship_data["longitude"] = float(lon)
                ship_data["speed"] = float(pos.get("Sog", 0.0))
                ship_data["course"] = float(pos.get("Cog", 0.0))
                ship_data["timestamp"] = meta.get("time_utc", "Temps réel")
                ship_data["packets"] += 1
                ship_data["status"] = "En direct (Signal AIS reçu)"
                print(f"--> [TANIT TROUVÉ] Lat: {lat}, Lon: {lon}")
    except Exception as e:
        pass

def on_error(ws, error):
    global ship_data
    ship_data["status"] = "Erreur de liaison WebSocket"
    print("Erreur WebSocket:", error)

def on_close(ws, close_status_code, close_msg):
    global ship_data
    ship_data["status"] = "Reconnexion au flux..."
    print("Connexion fermée, tentative de reconnexion...")

def run_ais_stream():
    def on_open(ws):
        sub = {
            "APIKey": AIS_API_KEY,
            "BoundingBoxes": [[[30.0, -6.0], [45.0, 36.0]]],
            "FiltersShipMMSI": [TANIT_MMSI],
            "FilterMessageTypes": ["PositionReport", "StandardClassBPositionReport"]
        }
        ws.send(json.dumps(sub))
        print("Abonnement envoyé pour le C/F TANIT.")

    while True:
        try:
            ws = websocket.WebSocketApp(
                "wss://stream.aisstream.io/v0/stream",
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close
            )
            ws.run_forever(ping_interval=30, ping_timeout=10)
        except Exception as e:
            print("Exception flux:", e)
        time.sleep(5)

# Lancement du flux en arrière-plan
threading.Thread(target=run_ais_stream, daemon=True).start()

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Suivi Temps Réel - C/F TANIT</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" crossorigin=""/>
    <style>
        body { font-family: Arial, sans-serif; margin: 0; padding: 0; background: #0b1724; color: white; }
        #map { height: 100vh; width: 100vw; }
        #panel {
            position: absolute; top: 15px; right: 15px; z-index: 1000;
            background: rgba(11, 23, 36, 0.95); padding: 20px; border-radius: 12px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.5); width: 330px; border: 1px solid #1e293b;
        }
        .data-row { display: flex; justify-content: space-between; margin: 10px 0; font-size: 14px; }
        .badge { background: #0284c7; padding: 3px 8px; border-radius: 4px; font-weight: bold; }
    </style>
</head>
<body>
    <div id="panel">
        <h3 style="margin-top:0; color:#38bdf8;">🚢 C/F TANIT</h3>
        <div class="data-row"><strong>Statut :</strong> <span id="status" style="color:#f59e0b;">Chargement...</span></div>
        <div class="data-row"><strong>Latitude :</strong> <span id="lat">--</span></div>
        <div class="data-row"><strong>Longitude :</strong> <span id="lon">--</span></div>
        <div class="data-row"><strong>Vitesse :</strong> <span id="speed">--</span></div>
        <div class="data-row"><strong>Cap :</strong> <span id="course">--</span></div>
        <div class="data-row"><strong>Paquets Reçus :</strong> <span id="packets" class="badge">0</span></div>
        <div style="font-size: 11px; color: #94a3b8; text-align: center; margin-top: 12px;" id="time">-</div>
    </div>
    <div id="map"></div>

    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" crossorigin=""></script>
    <script>
        var map = L.map('map').setView([36.8122, 10.3094], 15);
        L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}', {
            maxZoom: 18, attribution: 'Tiles &copy; Esri'
        }).addTo(map);

        var marker = null;
        var centered = false;

        function fetchShipData() {
            fetch('/api/ship')
                .then(response => response.json())
                .then(data => {
                    document.getElementById('status').innerText = data.status;
                    document.getElementById('packets').innerText = data.packets;

                    if (data.latitude !== null && data.longitude !== null) {
                        document.getElementById('lat').innerText = data.latitude.toFixed(4);
                        document.getElementById('lon').innerText = data.longitude.toFixed(4);
                        document.getElementById('speed').innerText = data.speed.toFixed(1) + " nds";
                        document.getElementById('course').innerText = data.course.toFixed(0) + "°";
                        document.getElementById('time').innerText = data.timestamp;

                        var latLng = [data.latitude, data.longitude];
                        
                        if (!marker) {
                            marker = L.marker(latLng).addTo(map)
                                .bindPopup("<b>C/F TANIT</b><br>MMSI: 672748000")
                                .openPopup();
                        } else {
                            marker.setLatLng(latLng);
                        }

                        if (!centered) {
                            map.setView(latLng, 15);
                            centered = true;
                        }
                    }
                })
                .catch(err => console.error("Erreur de récupération:", err));
        }

        setInterval(fetchShipData, 2000);
        fetchShipData();
    </script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route("/api/ship")
def get_ship_data():
    return jsonify(ship_data)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)