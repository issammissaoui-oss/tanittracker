from flask import Flask, render_template_string, jsonify
import json
import threading
import websocket
import os
import time

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
    "status": "Écoute du flux..."
}

def on_message(ws, message):
    global ship_data
    try:
        packet = json.loads(message)
        meta = packet.get("MetaData", {})
        mmsi_str = str(meta.get("MMSI", ""))
        ship_name = meta.get("ShipName", "").strip().upper()
        
        # On capture soit par MMSI, soit si le nom contient TANIT
        if TANIT_MMSI in mmsi_str or "TANIT" in ship_name or "C/F TANIT" in ship_name:
            msg_type = packet.get("MessageType")
            pos = {}
            if msg_type == "PositionReport":
                pos = packet.get("Message", {}).get("PositionReport", {})
            elif msg_type == "StandardClassBPositionReport":
                pos = packet.get("Message", {}).get("StandardClassBPositionReport", {})
            
            lat = pos.get("Latitude")
            lon = pos.get("Longitude")
            
            if lat is not None and lon is not None:
                ship_data["lat"] = float(lat)
                ship_data["lon"] = float(lon)
                ship_data["speed"] = float(pos.get("Sog", 0))
                ship_data["course"] = float(pos.get("Cog", 0))
                ship_data["packets"] += 1
                ship_data["status"] = "En direct (AIS)"
                if ship_name:
                    ship_data["name"] = ship_name
                print(f"-> Trouvé ! Pos: {lat}, {lon} | SOG: {ship_data['speed']}")
        
        # Affichage de débogage pour voir passer les paquets dans les logs Render
        msg_count = ship_data["packets"]
        if msg_count == 0 and "Message" in packet:
            # Affiche un extrait pour diagnostic si aucun paquet n'est encore validé
            pass

    except Exception as e:
        print("Erreur de parsing:", e)

def on_error(ws, error):
    global ship_data
    ship_data["status"] = "Erreur WebSocket"
    print("Erreur WS:", error)

def on_close(ws, close_status_code, close_msg):
    global ship_data
    ship_data["status"] = "Reconnexion..."

def run_ais_stream():
    def on_open(ws):
        global ship_data
        ship_data["status"] = "Connecté (Balayage Méditerranée)"
        # On demande un flux large sur toute la Méditerranée sans filtre strict pour être sûr de capter
        sub = {
            "APIKey": AIS_API_KEY,
            "BoundingBoxes": [[[30.0, -6.0], [46.0, 36.0]]],
            "FilterMessageTypes": ["PositionReport", "StandardClassBPositionReport"]
        }
        ws.send(json.dumps(sub))

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
        time.sleep(3)

# Lancement du flux en arrière-plan
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
    <title>Suivi C/F TANIT - Temps Réel</title>
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
        <div class="data-row"><strong>Statut :</strong> <span id="status" style="color:#d97706;">Connexion...</span></div>
        <div class="data-row"><strong>Position :</strong> <span id="pos">--</span></div>
        <div class="data-row"><strong>Vitesse :</strong> <span id="speed">--</span></div>
        <div class="data-row"><strong>Cap :</strong> <span id="course">--</span></div>
        <div class="data-row"><strong>Paquets reçus :</strong> <span id="packets">0</span></div>
    </div>
    <div id="map"></div>

    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" crossorigin=""></script>
    <script>
        const map = L.map('map').setView([36.817, 10.305], 7);
        L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}', {
            maxZoom: 14, attribution: 'Tiles &copy; Esri'
        }).addTo(map);

        let marker = null;
        let centered = false;

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
                    }
                    if (!centered && data.packets > 0) {
                        map.setView(pos, 10);
                        centered = true;
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