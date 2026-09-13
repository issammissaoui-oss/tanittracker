import asyncio
import json
import threading
from flask import Flask, jsonify, render_template_string
import websockets

app = Flask(__name__)

# Données globales du navire C/F TANIT (MMSI: 672748000)
ship_data = {
    "mmsi": "672748000",
    "name": "TANIT",
    "latitude": None,
    "longitude": None,
    "speed": None,
    "course": None,
    "timestamp": "En attente du signal AIS...",
}

AIS_API_KEY = "f6d1a345fe0725cc6e57cdcc079354db7992b257"


async def listen_ais():
  # Bounding box large couvrant toute la Méditerranée pour ne pas rater le navire
  bounding_boxes = [
      [[30.0, -6.0], [45.0, 36.0]]
  ]  # [Sud-Ouest, Nord-Est] Méditerranée

  while True:
    try:
      print("Connexion au flux AISStream...")
      async with websockets.connect(
          "wss://stream.aisstream.io/v0/stream"
      ) as websocket:
        subscribe_message = {
            "APIKey": AIS_API_KEY,
            "BoundingBoxes": bounding_boxes,
            "FiltersShipMMSI": ["672748000"],
            "FilterMessageTypes": ["PositionReport"],
        }

        await websocket.send(json.dumps(subscribe_message))
        print(" Abonnement AISStream envoyé avec succès pour le TANIT.")

        async for message_json in websocket:
          message = json.loads(message_json)
          message_type = message.get("MessageType")

          if message_type == "PositionReport":
            position_report = message.get("Message", {}).get(
                "PositionReport", {}
            )
            metadata = message.get("MetaData", {})

            ship_data["latitude"] = position_report.get("Latitude")
            ship_data["longitude"] = position_report.get("Longitude")
            ship_data["speed"] = position_report.get("Sog")
            ship_data["course"] = position_report.get("Cog")
            ship_data["timestamp"] = metadata.get("time_utc")

            print(
                f"Position reçue -> Lat: {ship_data['latitude']}, Lon:"
                f" {ship_data['longitude']}, Vitesse:"
                f" {ship_data['speed']} kts"
            )

    except websockets.exceptions.ConnectionClosedError as e:
      print(f"Connexion fermée ({e}), reconnexion dans 5 secondes...")
      await asyncio.sleep(5)
    except Exception as e:
      print(f"Erreur WebSocket: {repr(e)}, reconnexion dans 5 secondes...")
      await asyncio.sleep(5)


def run_async_loop():
  loop = asyncio.new_event_loop()
  asyncio.set_event_loop(loop)
  loop.run_until_complete(listen_ais())


# Lancement du thread d'écoute en arrière-plan dès le démarrage de Flask
threading.Thread(target=run_async_loop, daemon=True).start()

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <title>Suivi en Direct - C/F TANIT</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <style>
        body { font-family: Arial, sans-serif; margin: 0; padding: 0; background: #0f172a; color: white; }
        header { background: #1e293b; padding: 15px; text-align: center; border-bottom: 1px solid #334155; }
        #map { height: 80vh; width: 100vw; }
        #info { position: absolute; bottom: 20px; left: 20px; z-index: 1000; background: rgba(15, 23, 42, 0.9); padding: 15px; border-radius: 8px; border: 1px solid #475569; width: 300px; }
    </style>
</head>
<body>
    <header>
        <h2>Suivi Temps Réel - C/F TANIT (MMSI: 672748000)</h2>
    </header>
    <div id="info">
        <p><strong>Statut :</strong> <span id="status">Connexion en cours...</span></p>
        <p><strong>Latitude :</strong> <span id="lat">-</span></p>
        <p><strong>Longitude :</strong> <span id="lon">-</span></p>
        <p><strong>Vitesse :</strong> <span id="speed">-</span> nds</p>
        <p><strong>Cap :</strong> <span id="course">-</span>°</p>
        <p><small id="time">-</small></p>
    </div>
    <div id="map"></div>

    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script>
        var map = L.map('map').setView([36.817, 10.305], 6);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 19,
            attribution: '© OpenStreetMap'
        }).addTo(map);

        var marker = null;

        function updateData() {
            fetch('/data')
                .then(response => response.json())
                .then(data => {
                    if (data.latitude && data.longitude) {
                        document.getElementById('status').innerText = "Signal Reçu (En direct)";
                        document.getElementById('lat').innerText = data.latitude.toFixed(4);
                        document.getElementById('lon').innerText = data.longitude.toFixed(4);
                        document.getElementById('speed').innerText = data.speed !== null ? data.speed : '-';
                        document.getElementById('course').innerText = data.course !== null ? data.course : '-';
                        document.getElementById('time').innerText = "Maj : " + data.timestamp;

                        var latLng = [data.latitude, data.longitude];
                        if (!marker) {
                            marker = L.marker(latLng).addTo(map).bindPopup("<b>C/F TANIT</b>").openPopup();
                            map.setView(latLng, 10);
                        } else {
                            marker.setLatLng(latLng);
                        }
                    } else {
                        document.getElementById('status').innerText = "En attente de trames AIS...";
                    }
                }).catch(err => console.error("Erreur fetch:", err));
        }

        setInterval(updateData, 3000);
    </script>
</body>
</html>
"""


@app.route("/")
def index():
  return render_template_string(HTML_TEMPLATE)


@app.route("/data")
def get_data():
  return jsonify(ship_data)


if __name__ == "__main__":
  app.run(host="0.0.0.0", port=5000, debug=True)