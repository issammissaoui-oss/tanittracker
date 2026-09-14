from flask import Flask, jsonify, render_template_string, request
import json
import threading
import websocket
import time
import os

app = Flask(__name__)

AIS_API_KEY = "ea9d58747246902dbd8d544a2fe5a3137caf2a59"
TANIT_MMSI = "672748000"

# Données du navire (pouvant être mises à jour par l'AIS ou manuellement depuis le panneau de bord)
ship_data = {
    "mmsi": TANIT_MMSI,
    "name": "C/F TANIT",
    "latitude": 36.8170,  
    "longitude": 10.3050,
    "speed": 0.0,
    "course": 0.0,
    "timestamp": "Position initiale / Manuelle",
    "packets": 0,
    "status": "En attente de signal AIS..."
}

def on_message(ws, message):
    global ship_data
    try:
        packet = json.loads(message)
        msg_type = packet.get("MessageType")
        
        if msg_type == "SubscriptionConfirmation":
            ship_data["status"] = "Connecté au flux AIS"
            print("[AIS] Abonnement validé par le serveur.", flush=True)
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
            sog = pos.get("Sog")
            cog = pos.get("Cog")
            
            if lat is not None and lon is not None and lat != 0 and lon != 0:
                ship_data["latitude"] = float(lat)
                ship_data["longitude"] = float(lon)
                ship_data["speed"] = float(sog) if sog is not None else 0.0
                ship_data["course"] = float(cog) if cog is not None else 0.0
                ship_data["timestamp"] = meta.get("time_utc", "Temps réel AIS")
                ship_data["packets"] += 1
                ship_data["status"] = "En direct (Signal AIS reçu)"
                print(f"--> [TANIT AIS] Lat: {lat}, Lon: {lon}", flush=True)
    except Exception as e:
        print(f"Erreur de traitement JSON: {e}", flush=True)

def on_error(ws, error):
    global ship_data
    ship_data["status"] = "Erreur de liaison"
    print(f"Erreur WebSocket: {error}", flush=True)

def on_close(ws, close_status_code, close_msg):
    global ship_data
    ship_data["status"] = "Reconnexion..."
    print("Connexion fermée, tentative...", flush=True)

def run_ais_stream():
    def on_open(ws):
        sub = {
            "APIKey": AIS_API_KEY,
            "BoundingBoxes": [[[30.0, -6.0], [45.0, 36.0]]],
            "FiltersShipMMSI": [TANIT_MMSI],
            "FilterMessageTypes": ["PositionReport", "StandardClassBPositionReport"]
        }
        ws.send(json.dumps(sub))
        print("Abonnement envoyé.", flush=True)

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
            print(f"Exception flux: {e}", flush=True)
        time.sleep(5)

threading.Thread(target=run_ais_stream, daemon=True).start()

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Suivi C/F TANIT</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" crossorigin=""/>
    <style>
        body { font-family: Arial, sans-serif; margin: 0; padding: 0; background: #0b1724; color: white; }
        #map { height: 100vh; width: 100vw; }
        #panel {
            position: absolute; top: 15px; right: 15px; z-index: 1000;
            background: rgba(11, 23, 36, 0.95); padding: 20px; border-radius: 12px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.5); width: 330px; border: 1px solid #1e293b;
        }
        .data-row { display: flex; justify-content: space-between; margin: 8px 0; font-size: 14px; }
        .badge { background: #0284c7; padding: 3px 8px; border-radius: 4px; font-weight: bold; }
        .form-group { margin-top: 10px; border-top: 1px solid #334155; padding-top: 10px; }
        .form-group input { width: 45%; padding: 5px; background: #1e293b; border: 1px solid #475569; color: white; border-radius: 4px; }
        .form-group button { width: 100%; margin-top: 8px; padding: 6px; background: #0284c7; border: none; color: white; font-weight: bold; border-radius: 4px; cursor: pointer; }
        .form-group button:hover { background: #0369a1; }
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
        <div style="font-size: 11px; color: #94a3b8; text-align: center; margin: 8px 0;" id="time">-</div>

        <div class="form-group">
            <div style="font-size: 12px; margin-bottom: 5px; color: #cbd5e1;">Mise à jour manuelle (Pont / Quai) :</div>
            <div style="display: flex; justify-content: space-between;">
                <input type="text" id="manualLat" placeholder="Latitude">
                <input type="text" id="manualLon" placeholder="Longitude">
            </div>
            <button onclick="updateManualPosition()">Forcer la position</button>
        </div>
    </div>
    <div id="map"></div>

    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" crossorigin=""></script>
    <script>
        var map = L.map('map').setView([36.8170, 10.3050], 13);
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
                            map.setView(latLng, 14);
                            centered = true;
                        }
                    }
                })
                .catch(err => console.error("Erreur:", err));
        }

        function updateManualPosition() {
            let lat = parseFloat(document.getElementById('manualLat').value);
            let lon = parseFloat(document.getElementById('manualLon').value);

            if (isNaN(lat) || isNaN(lon)) {
                alert("Veuillez entrer des coordonnées valides.");
                return;
            }

            fetch('/api/update', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ latitude: lat, longitude: lon })
            })
            .then(res => res.json())
            .then(data => {
                alert("Position mise à jour avec succès !");
                fetchShipData();
            });
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

@app.route("/api/update", methods=["POST"])
def update_ship_data():
    global ship_data
    content = request.json
    if "latitude" in content and "longitude" in content:
        ship_data["latitude"] = float(content["latitude"])
        ship_data["longitude"] = float(content["longitude"])
        ship_data["timestamp"] = "Saisie manuelle (Pont)"
        ship_data["status"] = "Mode Manuel Actif"
    return jsonify({"success": True})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)