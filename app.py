import asyncio
import json
import threading
from flask import Flask, jsonify, render_template_string
import websockets

app = Flask(__name__)

# État global du navire C/F TANIT (MMSI: 672748000)
ship_data = {
    "mmsi": "672748000",
    "name": "C/F TANIT",
    "latitude": None,
    "longitude": None,
    "speed": 0.0,
    "course": 0.0,
    "timestamp": "En attente du signal AIS en direct...",
    "packets": 0,
}

AIS_API_KEY = "f6d1a345fe0725cc6e57cdcc079354db7992b257"


async def listen_ais():
  global ship_data
  # Bounding box large couvrant toute la Méditerranée et l'Atlantique Nord proche
  bounding_boxes = [[[30.0, -6.0], [45.0, 36.0]]]

  while True:
    try:
      print("Connexion au flux WebSocket AISStream...")
      async with websockets.connect(
          "wss://stream.aisstream.io/v0/stream"
      ) as websocket:
        subscribe_message = {
            "APIKey": AIS_API_KEY,
            "BoundingBoxes": bounding_boxes,
            "FiltersShipMMSI": ["672748000"],
            "FilterMessageTypes": [
                "PositionReport",
                "StandardClassBPositionReport",
            ],
        }

        await websocket.send(json.dumps(subscribe_message))
        print(
            " Abonnement temps réel envoyé avec succès pour le C/F TANIT"
            " (672748000)."
        )

        async for message_json in websocket:
          message = json.loads(message_json)
          message_type = message.get("MessageType")

          if message_type in [
              "PositionReport",
              "StandardClassBPositionReport",
          ]:
            msg_content = message.get("Message", {}).get(message_type, {})
            metadata = message.get("MetaData", {})

            lat = msg_content.get("Latitude")
            lon = msg_content.get("Longitude")

            if lat is not None and lon is not None:
              ship_data["latitude"] = float(lat)
              ship_data["longitude"] = float(lon)
              ship_data["speed"] = float(msg_content.get("Sog", 0.0))
              ship_data["course"] = float(msg_content.get("Cog", 0.0))
              ship_data["timestamp"] = metadata.get(
                  "time_utc", "Temps réel direct"
              )
              ship_data["packets"] += 1
              ship_data["status"] = "En direct (Temps Réel)"

              print(
                  f"-> [TANIT LIVE] Lat: {lat}, Lon: {lon} | Vitesse:"
                  f" {ship_data['speed']} nds | Cap: {ship_data['course']}°"
              )

    except websockets.exceptions.ConnectionClosedError as e:
      print(f"Connexion fermée ({e}), reconnexion dans 3 secondes...")
      await asyncio.sleep(3)
    except Exception as e:
      print(f"Erreur WebSocket: {repr(e)}, reconnexion dans 3 secondes...")
      await asyncio.sleep(3)


def run_async_loop():
  loop = asyncio.new_event_loop()
  asyncio.set_event_loop(loop)
  loop.run_until_complete(listen_ais())


# Lancement du flux WebSocket en arrière-plan
threading.Thread(target=run_async_loop, daemon=True).start()

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
            box-shadow: 0 4px 20px rgba(0,0,0,0.5); width: 320px; border: 1px solid #1e293b;
        }
        .data-row { display: flex; justify-content: space-between; margin: 10px 0; font-size: 14px; }
        .badge { background: #0284c7; padding: 3px 8px; border-radius: 4px; font-weight: bold; }
    </style>
</head>
<body>
    <div id="panel">
        <h3 style="margin-top:0; color:#38bdf8;">🚢 C/F TANIT</h3>
        <div class="data-row"><strong>Statut :</strong> <span id="status" style="color:#f59e0b;">Connexion...</span></div>
        <div class="data-row"><strong>Latitude :</strong> <span id="lat">En attente...</span></div>
        <div class="data-row"><strong>Longitude :</strong> <span id="lon">En attente...</span></div>
        <div class="data-row"><strong>Vitesse :</strong> <span id="speed">--</span></div>
        <div class="data-row"><strong>Cap :</strong> <span id="course">--</span></div>
        <div class="data-row"><strong>Paquets Reçus :</strong> <span id="packets" class="badge">0</span></div>
        <div style="font-size: 11px; color: #94a3b8; text-align: center; margin-top: 12px;" id="time">-</div>
    </div>
    <div id="map"></div>

    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" crossorigin=""></script>
    <script>
        // Initialisation de la carte centrée par défaut sur la Méditerranée centrale / Tunisie
        var map = L.map('map').setView([36.817, 10.305], 6);
        L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}', {
            maxZoom: 16, attribution: 'Tiles &copy; Esri'
        }).addTo(map);

        var marker = null;
        var centered = false;

        function fetchShipData() {
            fetch('/api/ship')
                .then(response => response.json())
                .then(data => {
                    document.getElementById('status').innerText = data.status || "En direct";
                    document.getElementById('packets').innerText = data.packets;

                    if (data.latitude !== null && data.longitude !== null) {
                        document.getElementById('lat').innerText = data.latitude.toFixed(4);
                        document.getElementById('lon').innerText = data.longitude.toFixed(4);
                        document.getElementById('speed').innerText = data.speed.toFixed(1) + " nds";
                        document.getElementById('course').innerText = data.course.toFixed(0) + "°";
                        document.getElementById('time').innerText = "Dernière synchro : " + data.timestamp;

                        var latLng = [data.latitude, data.longitude];
                        
                        if (!marker) {
                            marker = L.marker(latLng).addTo(map)
                                .bindPopup("<b>C/F TANIT</b><br>MMSI: 672748000")
                                .openPopup();
                        } else {
                            marker.setLatLng(latLng);
                        }

                        // Centrer la carte automatiquement sur le navire à la première réception de position réelle
                        if (!centered) {
                            map.setView(latLng, 10);
                            centered = true;
                        }
                    }
                })
                .catch(err => console.error("Erreur de récupération des données:", err));
        }

        // Interrogation de l'API Flask toutes les 2 secondes pour un rendu ultra fluide en temps réel
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
  app.run(host="0.0.0.0", port=5000, debug=False)