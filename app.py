from flask import Flask, jsonify, render_template_string, request
import json
import os

app = Flask(__name__)

# Position initiale exacte : La Goulette / Tunis
ship_state = {
    "name": "C/F TANIT",
    "route": "Tunis (La Goulette) ⇄ Marseille / Gênes",
    "latitude": 36.8170,
    "longitude": 10.3050,
    "speed": 18.5,
    "course": 340.0,
    "status": "En navigation",
    "next_port": "Marseille",
    "eta": "Demain à 08:00",
    "timestamp": "Temps réel"
}

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>C/F TANIT - Moving Map</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" crossorigin=""/>
    <style>
        * { box-sizing: border-box; }
        body, html { margin: 0; padding: 0; height: 100%; width: 100%; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #071019; color: #fff; overflow: hidden; }
        
        #map { height: 100%; width: 100%; position: absolute; z-index: 1; }

        /* Panneau supérieur */
        #top-banner {
            position: absolute; top: 15px; left: 15px; right: 15px; z-index: 1000;
            background: rgba(11, 23, 36, 0.9); backdrop-filter: blur(10px);
            border: 1px solid rgba(56, 189, 248, 0.2); border-radius: 16px;
            padding: 15px 20px; display: flex; justify-content: space-between; align-items: center;
            box-shadow: 0 10px 30px rgba(0,0,0,0.5);
        }
        .ship-title h1 { margin: 0; font-size: 18px; color: #38bdf8; letter-spacing: 0.5px; }
        .ship-title p { margin: 3px 0 0 0; font-size: 12px; color: #94a3b8; }

        /* Panneau de télémétrie en bas */
        #telemetry-bar {
            position: absolute; bottom: 20px; left: 15px; right: 15px; z-index: 1000;
            background: rgba(11, 23, 36, 0.9); backdrop-filter: blur(10px);
            border: 1px solid rgba(56, 189, 248, 0.2); border-radius: 16px;
            padding: 15px; display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.5); text-align: center;
        }
        .tele-item .label { font-size: 11px; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.5px; }
        .tele-item .value { font-size: 16px; font-weight: bold; color: #f8fafc; margin-top: 4px; }

        /* Bouton discret de mise à jour pour l'équipage */
        #admin-toggle {
            position: absolute; bottom: 115px; right: 20px; z-index: 1000;
            background: #0284c7; border: none; color: white; padding: 8px 12px;
            border-radius: 8px; font-size: 12px; cursor: pointer; box-shadow: 0 4px 10px rgba(0,0,0,0.3);
        }
        #admin-panel {
            position: absolute; bottom: 160px; right: 20px; z-index: 1001;
            background: rgba(15, 23, 42, 0.95); padding: 15px; border-radius: 12px;
            border: 1px solid #334155; width: 280px; display: none; box-shadow: 0 10px 25px rgba(0,0,0,0.5);
        }
        #admin-panel input { width: 100%; padding: 6px; margin: 5px 0; background: #1e293b; border: 1px solid #475569; color: white; border-radius: 4px; }
        #admin-panel button { width: 100%; margin-top: 8px; padding: 8px; background: #10b981; border: none; color: white; font-weight: bold; border-radius: 4px; cursor: pointer; }

        @media (max-width: 768px) {
            #telemetry-bar { grid-template-columns: repeat(2, 1fr); gap: 12px; }
        }
    </style>
</head>
<body>

    <div id="top-banner">
        <div class="ship-title">
            <h1>🚢 C/F TANIT</h1>
            <p id="route-text">Tunis (La Goulette) ⇄ Marseille / Gênes</p>
        </div>
        <div style="font-size: 12px; background: rgba(16, 185, 129, 0.2); color: #34d399; padding: 5px 10px; border-radius: 20px; border: 1px solid rgba(16, 185, 129, 0.4);">
            En direct
        </div>
    </div>

    <div id="map"></div>

    <div id="telemetry-bar">
        <div class="tele-item">
            <div class="label">Vitesse</div>
            <div class="value" id="val-speed">-- nds</div>
        </div>
        <div class="tele-item">
            <div class="label">Cap</div>
            <div class="value" id="val-course">--°</div>
        </div>
        <div class="tele-item">
            <div class="label">Prochaine Escale</div>
            <div class="value" id="val-port">--</div>
        </div>
        <div class="tele-item">
            <div class="label">Arrivée Prévue</div>
            <div class="value" id="val-eta">--</div>
        </div>
    </div>

    <button id="admin-toggle" onclick="toggleAdmin()">⚙️ Pont</button>
    <div id="admin-panel">
        <div style="font-size: 13px; font-weight: bold; margin-bottom: 8px; color: #38bdf8;">Mise à jour Position</div>
        <input type="text" id="latInput" placeholder="Latitude (ex: 36.817)">
        <input type="text" id="lonInput" placeholder="Longitude (ex: 10.305)">
        <input type="text" id="speedInput" placeholder="Vitesse (nds)">
        <input type="text" id="courseInput" placeholder="Cap (°)">
        <button onclick="submitPosition()">Mettre à jour</button>
    </div>

    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" crossorigin=""></script>
    <script>
        // Initialisation centrée précisément sur La Goulette / Tunis
        var map = L.map('map', { zoomControl: false }).setView([36.8170, 10.3050], 13);
        
        // Utilisation d'OpenStreetMap (100% gratuit, sans clé API, sans filigrane)
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 19,
            attribution: '&copy; OpenStreetMap contributors'
        }).addTo(map);

        var marker = L.marker([36.8170, 10.3050]).addTo(map)
            .bindPopup("<b>C/F TANIT</b><br>Compagnie Tunisienne de Navigation");

        function fetchData() {
            fetch('/api/data')
                .then(res => res.json())
                .then(data => {
                    document.getElementById('route-text').innerText = data.route;
                    document.getElementById('val-speed').innerText = data.speed.toFixed(1) + " nds";
                    document.getElementById('val-course').innerText = data.course.toFixed(0) + "°";
                    document.getElementById('val-port').innerText = data.next_port;
                    document.getElementById('val-eta').innerText = data.eta;

                    var newLatLng = [data.latitude, data.longitude];
                    marker.setLatLng(newLatLng);
                });
        }

        function toggleAdmin() {
            var panel = document.getElementById('admin-panel');
            panel.style.display = panel.style.display === 'block' ? 'none' : 'block';
        }

        function submitPosition() {
            let lat = parseFloat(document.getElementById('latInput').value);
            let lon = parseFloat(document.getElementById('lonInput').value);
            let speed = parseFloat(document.getElementById('speedInput').value);
            let course = parseFloat(document.getElementById('courseInput').value);

            fetch('/api/update', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ latitude: lat, longitude: lon, speed: speed, course: course })
            }).then(() => {
                toggleAdmin();
                fetchData();
                map.setView([lat, lon], 14);
            });
        }

        setInterval(fetchData, 3000);
        fetchData();
    </script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route("/api/data")
def get_data():
    return jsonify(ship_state)

@app.route("/api/update", methods=["POST"])
def update_data():
    global ship_state
    req = request.json
    if "latitude" in req and not str(req["latitude"]) == "nan":
        ship_state["latitude"] = float(req["latitude"])
    if "longitude" in req and not str(req["longitude"]) == "nan":
        ship_state["longitude"] = float(req["longitude"])
    if "speed" in req and not str(req["speed"]) == "nan":
        ship_state["speed"] = float(req["speed"])
    if "course" in req and not str(req["course"]) == "nan":
        ship_state["course"] = float(req["course"])
    return jsonify({"success": True})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)