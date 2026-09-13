from flask import Flask, render_template_string, jsonify
import json
import threading
import websocket
import os

app = Flask(__name__)

AIS_API_KEY = "f6d1a345fe0725cc6e57cdcc079354db7992b257"
TANIT_MMSI = "672748000"

ship_data = {
    "lat": 36.817, 
    "lon": 10.305, 
    "speed": 0.0, 
    "course": 0.0, 
    "mmsi": TANIT_MMSI, 
    "name": "C/F TANIT", 
    "packets": 0,
    "status": "En attente..."
}

def on_message(ws, message):
    global ship_data
    try:
        packet = json.loads(message)
        if packet.get("MessageType") != "PositionReport":
            return
        
        pos = packet.get("Message", {}).get("PositionReport", {})
        lat = pos.get("Latitude")
        lon = pos.get("Longitude")
        
        if lat is not None and lon is not None:
            ship_data["lat"] = float(lat)
            ship_data["lon"] = float(lon)
            ship_data["speed"] = float(pos.get("Sog", 0))
            ship_data["course"] = float(pos.get("Cog", 0))
            ship_data["packets"] += 1
            ship_data["status"] = "AIS en direct"
            
            meta = packet.get("MetaData", {})
            if "ShipName" in meta:
                ship_data["name"] = meta["ShipName"].strip()
    except Exception as e:
        print("Erreur:", e)

def run_ais_stream():
    def on_open(ws):
        sub = {
            "APIKey": AIS_API_KEY,
            "BoundingBoxes": [[[30.0, 3.0], [47.0, 16.0]]],
            "FiltersShipMMSI": [TANIT_MMSI],
            "FilterMessageTypes": ["PositionReport"]
        }
        ws.send(json.dumps(sub))

    while True:
        try:
            ws = websocket.WebSocketApp(
                "wss://stream.aisstream.io/v0/stream",
                on_open=on_open,
                on_message=on_message
            )
            ws.run_forever(ping_interval=30, ping_timeout=10)
        except Exception:
            pass

# Lancement du flux AIS en arrière-plan
threading.Thread(target=run_ais_stream, daemon=True).start()

@app.route("/api/ship")
def get_ship_data():
    return jsonify(ship_data)

@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Suivi C/F TANIT - Cloud</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" crossorigin=""/>
    <style>
        body { margin: 0; padding: 0; font-family: Arial, sans-serif; background: #0b1724; }
        #map { width: 100%; height: 100vh; }
        #panel {
            position: absolute; top: 15px; right: 15px; z-index: 1000;
            background: white; padding: 15px; border-radius: 12px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.3); width: 320px;
        }
        .data-row { display: flex; justify-content: space-between; margin: 8px 0; font-size: 14px; }
    </style>
</head>
<body>
    <div id="panel">
        <h3 style="margin-top:0; color:#063970;">🚢 C/F TANIT</h3>
        <div class="data-row"><strong>Statut :</strong> <span id="status" style="color:#16a34a;">Connexion...</span></div>
        <div class="data-row"><strong>Position :</strong> <span id="pos">--</span></div>
        <div class="data-row"><strong>Vitesse :</strong> <span id="speed">--</span></div>
        <div class="data-row"><strong>Cap :</strong> <span id="course">--</span></div>
        <div class="data-row"><strong>Paquets :</strong> <span id="packets">0</span></div>
    </div>
    <div id="map"></div>

    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" crossorigin=""></script>
    <script>
        const map = L.map('map').setView([36.817, 10.305], 7);
        L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}', {
            maxZoom: 13, attribution: 'Tiles &copy; Esri'
        }).addTo(map);

        let marker = null;

        function updateData() {
            fetch('/api/ship')
                .then(res => res.json())
                .then(data => {
                    document.getElementById('status').innerText = data.status;
                    document.getElementById('pos').innerText = data.lat.toFixed(4) + ", " + data.lon.toFixed(4);
                    document.getElementById('speed').innerText = data.speed.toFixed(1) + " nds";
                    document.getElementById('course').innerText = data.course.toFixed(0) + "°";
                    document.getElementById('packets').innerText = data.packets;

                    const pos = [data.lat, data.lon];
                    if (marker) {
                        marker.setLatLng(pos);
                    } else {
                        marker = L.marker(pos).addTo(map);
                        map.setView(pos, 9);
                    }
                })
                .catch(err => console.error(err));
        }

        setInterval(updateData, 3000);
        updateData();
    </script>
</body>
</html>
"""

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)