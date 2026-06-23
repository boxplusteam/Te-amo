import os
import urllib.parse
import json
import shutil
import re
import random
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# --- CONFIGURACIÓN ---
PORT = 8000
MEDIA_DIR = "storage/downloads/flix"
APK_NAME = "Ryflix.apk"

class RyflixHandler(BaseHTTPRequestHandler):
    def send_cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Range')

    def do_OPTIONS(self):
        self.send_response(200, "ok")
        self.send_cors_headers()
        self.end_headers()

    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed_path.query)

        if parsed_path.path == '/' or parsed_path.path == '/index.html':
            self.serve_file('index.html', 'text/html')
        elif parsed_path.path == '/flix.html':
            self.serve_file('flix.html', 'text/html')
        elif parsed_path.path == '/api/media':
            self.serve_api(query)
        elif parsed_path.path == '/stream':
            self.serve_stream(query)
        elif parsed_path.path == '/img':
            self.serve_image(query)
        elif parsed_path.path == f'/{APK_NAME}':
            self.serve_apk()
        else:
            self.send_error(404, "No encontrado")

    def serve_file(self, filename, content_type):
        if not os.path.exists(filename):
            return self.send_error(404, f"{filename} no encontrado")
        self.send_response(200)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_cors_headers()
        self.end_headers()
        with open(filename, 'rb') as f:
            shutil.copyfileobj(f, self.wfile)

    def find_image_for(self, item_name, folder_path=None):
        extensions = ('.jpg', '.jpeg', '.png', '.webp')
        if folder_path and os.path.isdir(folder_path):
            for file in os.listdir(folder_path):
                if file.lower().endswith(extensions):
                    return f"{item_name}/{file}"
        for ext in extensions:
            img_file = f"{os.path.splitext(item_name)[0]}{ext}"
            if os.path.exists(os.path.join(MEDIA_DIR, img_file)):
                return img_file
        return None

    def scan_media(self):
        media = []
        if not os.path.exists(MEDIA_DIR): return media

        for item in os.listdir(MEDIA_DIR):
            path = os.path.join(MEDIA_DIR, item)
            name = item.replace('_', ' ').replace('-', ' ').title()

            if os.path.isfile(path) and item.lower().endswith(('.mp4', '.mkv', '.avi')):
                name_clean = name.rsplit('.', 1)[0]
                img = self.find_image_for(item)
                media.append({'name': name_clean, 'file': item, 'type': 'movie', 'image': img})

            elif os.path.isdir(path):
                vids = sorted([f for f in os.listdir(path) if f.lower().endswith(('.mp4', '.mkv', '.avi'))])
                img = self.find_image_for(item, path)

                if len(vids) == 1:
                    media.append({'name': name, 'folder': item, 'file': vids[0], 'type': 'movie', 'image': img})
                elif len(vids) > 1:
                    media.append({'name': name, 'folder': item, 'type': 'series', 'is_folder': True, 'image': img})

        return sorted(media, key=lambda x: x['name'])

    def serve_api(self, query):
        folder = query.get('folder', [''])[0]
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_cors_headers()
        self.end_headers()

        if folder:
            path = os.path.join(MEDIA_DIR, folder)
            chapters = []
            if os.path.exists(path) and os.path.isdir(path):
                vids = sorted([f for f in os.listdir(path) if f.lower().endswith(('.mp4', '.mkv', '.avi'))])
                for v in vids:
                    v_name = v.replace('_', ' ').replace('-', ' ').title().rsplit('.', 1)[0]
                    chapters.append({'name': v_name, 'folder': folder, 'file': v, 'type': 'movie'})
            self.wfile.write(json.dumps(chapters).encode('utf-8'))
        else:
            media = self.scan_media()
            self.wfile.write(json.dumps(media).encode('utf-8'))

    def serve_image(self, query):
        path_param = query.get('path', [''])[0]
        if not path_param: return self.send_error(400)
        img_path = os.path.join(MEDIA_DIR, path_param)
        if not os.path.exists(img_path) or not os.path.isfile(img_path): return self.send_error(404)

        mime_type = 'image/jpeg'
        if img_path.lower().endswith('.png'): mime_type = 'image/png'
        elif img_path.lower().endswith('.webp'): mime_type = 'image/webp'

        self.send_response(200)
        self.send_header('Content-Type', mime_type)
        self.send_header('Cache-Control', 'public, max-age=86400')
        self.send_cors_headers()
        self.end_headers()
        with open(img_path, 'rb') as f:
            shutil.copyfileobj(f, self.wfile)

    def serve_apk(self):
        if not os.path.exists(APK_NAME): return self.send_error(404, "APK no encontrado")
        self.send_response(200)
        self.send_header('Content-Type', 'application/vnd.android.package-archive')
        self.send_header('Content-Disposition', f'attachment; filename="{APK_NAME}"')
        self.end_headers()
        with open(APK_NAME, 'rb') as f:
            shutil.copyfileobj(f, self.wfile)

    def serve_stream(self, query):
        folder = query.get('folder', [''])[0]
        file = query.get('file', [''])[0]
        path = os.path.join(MEDIA_DIR, folder, file) if folder else os.path.join(MEDIA_DIR, file)

        if not os.path.exists(path): return self.send_error(404)

        file_size = os.path.getsize(path)
        range_header = self.headers.get('Range')

        if range_header:
            byte1, byte2 = 0, None
            match = re.search(r'bytes=(\d+)-(\d*)', range_header)
            if match:
                byte1 = int(match.group(1))
                if match.group(2): byte2 = int(match.group(2))

            byte2 = byte2 if byte2 is not None else file_size - 1
            length = byte2 - byte1 + 1

            self.send_response(206)
            self.send_header('Content-Type', 'video/mp4')
            self.send_header('Accept-Ranges', 'bytes')
            self.send_header('Content-Range', f'bytes {byte1}-{byte2}/{file_size}')
            self.send_header('Content-Length', str(length))
            self.send_cors_headers()
            self.end_headers()

            with open(path, 'rb') as f:
                f.seek(byte1)
                bytes_to_read = length
                chunk_size = 8192
                while bytes_to_read > 0:
                    chunk = f.read(min(chunk_size, bytes_to_read))
                    if not chunk: break
                    try:
                        self.wfile.write(chunk)
                    except ConnectionError:
                        break
                    bytes_to_read -= len(chunk)
        else:
            self.send_response(200)
            self.send_header('Content-Type', 'video/mp4')
            self.send_header('Content-Length', str(file_size))
            self.send_header('Accept-Ranges', 'bytes')
            self.send_cors_headers()
            self.end_headers()
            with open(path, 'rb') as f:
                shutil.copyfileobj(f, self.wfile)


# --- GENERACIÓN AUTOMÁTICA DE HTMLs ---
def generate_html_files():
    if not os.path.exists('index.html'):
        with open('index.html', 'w', encoding='utf-8') as f:
            f.write(f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <meta http-equiv="refresh" content="5;url=/flix.html">
    <title>Ryflix - Inicio</title>
    <style>
        body {{ background: #000; color: #fff; font-family: system-ui, sans-serif; display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 100vh; margin: 0; padding: 20px; text-align: center; box-sizing: border-box; }}
        .logo {{ color: #e50914; font-size: 2.5rem; font-weight: 900; text-transform: uppercase; margin-bottom: 20px; letter-spacing: 2px; }}
        .card {{ background: #111; padding: 30px; border-radius: 8px; border: 1px solid #333; max-width: 500px; width: 100%; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }}
        h1 {{ font-size: 1.5rem; margin-top: 0; color: #ddd; }}
        p {{ color: #888; font-size: 0.95rem; line-height: 1.5; text-align: justify; margin-bottom: 20px; }}
        .apk-btn {{ display: inline-block; background: #e50914; color: white; text-decoration: none; padding: 12px 24px; border-radius: 6px; font-weight: bold; margin-bottom: 20px; transition: background 0.2s; font-size: 1.1rem; }}
        .apk-btn:active {{ background: #b20710; transform: scale(0.98); }}
        .loader {{ width: 30px; height: 30px; border: 3px solid rgba(229,9,20,0.2); border-top-color: #e50914; border-radius: 50%; animation: spin 1s linear infinite; margin: 0 auto 15px; }}
        .countdown {{ font-size: 0.9rem; color: #666; font-weight: bold; margin-bottom: 15px; }}
        .webapp-link {{ color: #555; text-decoration: underline; font-size: 0.85rem; }}
        @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
    </style>
</head>
<body>
    <div class="logo">RYFLIX</div>
    <div class="card">
        <h1>Bienvenido a Ryflix</h1>
        <p>Al acceder a esta plataforma, aceptas que el contenido mostrado es de carácter personal, local y para uso privado sin conexión a internet. Esta es una WebApp nativa diseñada para consumo offline.</p>

        <a href="/{APK_NAME}" class="apk-btn" download>Descargar App (APK)</a>

        <div class="loader"></div>
        <div class="countdown" id="cd-text">Redirigiendo a la WebApp en 5s...</div>
        <a href="/flix.html" class="webapp-link">Ir a la WebApp directamente</a>
    </div>
    <script>
        let secs = 4;
        setInterval(() => {{
            if(secs > 0) document.getElementById('cd-text').innerText = `Redirigiendo a la WebApp en ${{secs}}s...`;
            secs--;
        }}, 1000);
    </script>
</body>
</html>""")

    with open('flix.html', 'w', encoding='utf-8') as f:
        f.write("""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="mobile-web-app-capable" content="yes">
    <meta name="theme-color" content="#000000">
    <title>Ryflix</title>
    <style>
        :root { --bg: #141414; --red: #E50914; --text: #fff; --card-bg: #222; }
        * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; font-family: system-ui, -apple-system, sans-serif; user-select: none; }
        body { margin: 0; background: var(--bg); color: var(--text); overflow-x: hidden; padding-bottom: 40px; overscroll-behavior-y: none; }

        @keyframes fadeInScale { from { opacity: 0; transform: scale(0.95) translateY(10px); } to { opacity: 1; transform: scale(1) translateY(0); } }

        /* HEADER */
        header { padding: env(safe-area-inset-top, 15px) 20px 15px; display: flex; justify-content: space-between; align-items: center; position: fixed; top: 0; width: 100%; background: linear-gradient(to bottom, rgba(0,0,0,0.9) 0%, transparent 100%); z-index: 100; transition: background 0.3s; }
        header.scrolled { background: rgba(20,20,20,0.95); backdrop-filter: blur(10px); }
        .header-left { display: flex; align-items: center; gap: 15px; }
        .logo { color: var(--red); font-size: 1.6rem; font-weight: 900; text-transform: uppercase; cursor: pointer; letter-spacing: 1.5px; text-shadow: 0 2px 4px rgba(0,0,0,0.8); }
        .header-controls { display: flex; align-items: center; gap: 12px; }

        .bt-border { background: rgba(255,255,255,0.1); color: white; border: 1px solid rgba(255,255,255,0.2); padding: 6px 14px; border-radius: 20px; font-weight: 600; cursor: pointer; font-size: 0.85rem; transition: all 0.2s; backdrop-filter: blur(5px); }
        .bt-border:active { transform: scale(0.95); }
        .bt-border.active { border-color: var(--red); color: var(--text); background: var(--red); }

        .search-box { display: flex; align-items: center; background: rgba(0,0,0,0.6); border: 1px solid rgba(255,255,255,0.2); padding: 6px 12px; border-radius: 20px; transition: all 0.3s; }
        .search-box input { background: transparent; border: none; color: white; outline: none; width: 100px; font-size: 0.9rem; transition: width 0.3s; }
        .search-box input:focus { width: 140px; }

        /* HERO SLIDER */
        .hero-slider { position: relative; width: 100%; height: 50vh; background: #000; overflow: hidden; display: none; }
        .hero-slide { position: absolute; top: 0; left: 0; width: 100%; height: 100%; opacity: 0; transition: opacity 1s ease; background-size: cover; background-position: top center; display: flex; flex-direction: column; justify-content: flex-end; }
        .hero-slide.active { opacity: 1; z-index: 2; }
        .hero-slide::after { content: ''; position: absolute; bottom: 0; left: 0; width: 100%; height: 60%; background: linear-gradient(to top, var(--bg) 0%, transparent 100%); z-index: 0; }
        .hero-content { position: relative; z-index: 3; padding: 20px; margin-bottom: 20px; text-align: center; }
        .hero-title { font-size: 2rem; font-weight: 900; text-shadow: 0 2px 8px rgba(0,0,0,0.9); margin: 0 0 15px 0; }
        .hero-btn { display: inline-flex; align-items: center; gap: 8px; background: white; color: black; border: none; padding: 10px 24px; border-radius: 4px; font-weight: bold; font-size: 1rem; cursor: pointer; }
        .hero-btn svg { width: 24px; height: 24px; fill: black; }

        /* CATALOG GRID */
        .section-title { font-size: 1.25rem; margin: 20px 20px 15px; font-weight: 700; text-shadow: 0 1px 2px rgba(0,0,0,0.8); }
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(110px, 1fr)); gap: 12px; padding: 0 20px; }
        .card { background: var(--card-bg); border-radius: 6px; overflow: hidden; position: relative; cursor: pointer; animation: fadeInScale 0.3s ease-out backwards; box-shadow: 0 4px 10px rgba(0,0,0,0.6); transition: transform 0.2s; }
        .card:active { transform: scale(0.95); }
        .poster { width: 100%; aspect-ratio: 2/3; background: #111; display: flex; align-items: center; justify-content: center; }
        .poster img { width: 100%; height: 100%; object-fit: cover; }
        .poster-alt { font-size: 2.5rem; font-weight: 900; color: #333; text-transform: uppercase; }
        .card-title { padding: 10px 8px; font-size: 0.8rem; text-align: center; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-weight: 500; background: linear-gradient(to top, #111, #1a1a1a); }

        .fav-icon { position: absolute; top: 8px; right: 8px; width: 28px; height: 28px; background: rgba(0,0,0,0.6); backdrop-filter: blur(4px); border-radius: 50%; display: flex; align-items: center; justify-content: center; z-index: 10; }
        .fav-icon svg { width: 16px; height: 16px; fill: white; }
        .fav-icon.active svg { fill: var(--red); }

        .loader { width: 26px; height: 26px; border: 3px solid rgba(255,255,255,0.1); border-top-color: var(--red); border-radius: 50%; animation: spin 0.8s linear infinite; margin: 30px auto; display: none; }
        @keyframes spin { to { transform: rotate(360deg); } }

        /* --- SECCIÓN DE SERIES --- */
        #seriesSection { display: none; min-height: 100vh; background: #000; position: relative; padding-bottom: 50px; }
        .series-hero-bg { position: absolute; top: 0; left: 0; width: 100%; height: 65vh; background-size: cover; background-position: center top; z-index: 0; opacity: 0.35; filter: blur(10px); }
        .series-hero-bg::after { content: ''; position: absolute; bottom: 0; left: 0; width: 100%; height: 100%; background: linear-gradient(to top, #000 20%, transparent 100%); }

        .series-container { position: relative; z-index: 2; padding: calc(env(safe-area-inset-top, 20px) + 20px) 20px 20px; }
        .series-header-nav { display: flex; align-items: center; margin-bottom: 30px; }
        .back-btn { background: rgba(255,255,255,0.1); border-radius: 50%; border: none; width: 44px; height: 44px; display: flex; justify-content: center; align-items: center; cursor: pointer; backdrop-filter: blur(10px); }
        .back-btn svg { width: 24px; height: 24px; fill: white; }

        .series-details { display: flex; flex-direction: column; gap: 20px; margin-bottom: 40px; }
        .series-poster-main { width: 140px; aspect-ratio: 2/3; border-radius: 8px; box-shadow: 0 8px 25px rgba(0,0,0,0.8); object-fit: cover; align-self: center; }
        .series-info-text { text-align: center; }
        .series-title-main { font-size: 2rem; font-weight: 800; text-shadow: 0 2px 10px rgba(0,0,0,0.9); margin: 0 0 10px 0; }
        .series-meta { font-size: 0.9rem; color: #aaa; font-weight: 500; }

        .episodes-title { font-size: 1.3rem; font-weight: 700; margin-bottom: 20px; border-left: 4px solid var(--red); padding-left: 10px; }
        .episodes-list { display: flex; flex-direction: column; gap: 12px; }
        .episode-row { display: flex; align-items: center; gap: 15px; padding: 12px; background: rgba(255,255,255,0.04); border-radius: 8px; border: 1px solid rgba(255,255,255,0.05); cursor: pointer; transition: background 0.2s; }
        .episode-row:active { background: rgba(255,255,255,0.12); }

        .ep-thumb { width: 110px; aspect-ratio: 16/9; background: #222; border-radius: 6px; overflow: hidden; display: flex; align-items: center; justify-content: center; position: relative; flex-shrink: 0; box-shadow: 0 2px 8px rgba(0,0,0,0.4); }
        .ep-thumb img { width: 100%; height: 100%; object-fit: cover; }
        .ep-thumb-icon { position: absolute; width: 24px; height: 24px; fill: white; filter: drop-shadow(0 2px 4px rgba(0,0,0,0.6)); }
        .ep-info { flex: 1; overflow: hidden; }
        .ep-title { font-size: 0.95rem; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-bottom: 4px; }
        .ep-num { font-size: 0.8rem; color: #888; }

        /* REPRODUCTOR */
        .player-modal { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: #000; z-index: 9999; display: none; flex-direction: column; }
        .player-modal.show { display: flex; }
        video { width: 100%; height: 100%; background: #000; object-fit: contain; }
        video.fit-16-9 { object-fit: fill; }

        .player-ui { position: absolute; top: 0; left: 0; width: 100%; height: 100%; display: flex; flex-direction: column; justify-content: space-between; z-index: 10; opacity: 1; transition: opacity 0.4s cubic-bezier(0.25, 1, 0.5, 1); background: radial-gradient(circle, transparent 30%, rgba(0,0,0,0.7) 100%); }
        .player-ui.hidden { opacity: 0; pointer-events: none; }

        .p-top-bar { padding: env(safe-area-inset-top, 20px) 20px 20px; background: linear-gradient(to bottom, rgba(0,0,0,0.8), transparent); display: flex; align-items: center; gap: 15px; }
        .p-title { flex: 1; font-weight: 600; font-size: 1.1rem; text-shadow: 0 2px 4px rgba(0,0,0,0.8); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

        .p-center-area { flex: 1; display: flex; align-items: center; justify-content: center; cursor: pointer; }
        .p-center-icon { width: 70px; height: 70px; background: rgba(0,0,0,0.6); border-radius: 50%; display: flex; justify-content: center; align-items: center; opacity: 0; transform: scale(0.8); transition: all 0.2s; pointer-events: none; }
        .p-center-icon svg { width: 35px; height: 35px; fill: white; }
        .p-center-icon.animate { opacity: 1; transform: scale(1.1); }

        .p-bottom-bar { padding: 20px; padding-bottom: env(safe-area-inset-bottom, 25px); background: linear-gradient(to top, rgba(0,0,0,0.9), transparent); display: flex; flex-direction: column; gap: 18px; }

        .p-timeline-container { width: 100%; height: 24px; display: flex; align-items: center; cursor: pointer; position: relative; }
        .p-timeline-bg { width: 100%; height: 6px; background: rgba(255,255,255,0.2); border-radius: 3px; position: relative; }
        .p-timeline-progress { height: 100%; background: var(--red); border-radius: 3px; width: 0%; position: absolute; }
        .p-timeline-thumb { width: 16px; height: 16px; background: var(--red); border-radius: 50%; position: absolute; top: 50%; transform: translate(-50%, -50%); left: 0%; box-shadow: 0 0 6px rgba(0,0,0,0.6); }

        .p-controls-row { display: flex; justify-content: space-between; align-items: center; }
        .p-controls-left, .p-controls-right { display: flex; align-items: center; gap: 25px; }

        .p-icon-btn { background: transparent; border: none; padding: 0; cursor: pointer; display: flex; justify-content: center; align-items: center; }
        .p-icon-btn svg { width: 30px; height: 30px; fill: white; }

        .p-time { font-size: 0.9rem; opacity: 0.9; font-weight: 500; font-variant-numeric: tabular-nums; }
        .p-res-btn { font-size: 0.85rem; font-weight: bold; color: white; background: rgba(0,0,0,0.5); border: 1px solid rgba(255,255,255,0.4); padding: 5px 10px; border-radius: 6px; cursor: pointer; }

        @media (min-width: 768px) {
            .grid { grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 18px; }
            .series-details { flex-direction: row; align-items: flex-end; text-align: left; gap: 30px; margin-top: 20px; }
            .series-poster-main { width: 180px; }
            .series-info-text { text-align: left; }
            .series-title-main { font-size: 2.8rem; }
            .episodes-list { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; }
            .p-icon-btn svg { width: 34px; height: 34px; }
        }
    </style>
</head>
<body>
    <header id="appHeader">
        <div class="header-left">
            <div class="logo" onclick="goHomeAction()">RYFLIX</div>
        </div>
        <div class="header-controls">
            <div class="search-box">
                <input type="text" id="searchInput" placeholder="Buscar..." autocomplete="off">
            </div>
            <button class="bt-border" id="favToggleBtn" onclick="toggleFavView()">Favs</button>
        </div>
    </header>

    <div id="homeSection">
        <div class="hero-slider" id="heroSlider"></div>
        <h2 class="section-title" id="mainTitle">Películas y Series</h2>
        <div class="grid" id="grid"></div>
        <div class="loader" id="loader"></div>
    </div>

    <div id="seriesSection">
        <div class="series-hero-bg" id="seriesHeroBg"></div>
        <div class="series-container">
            <div class="series-header-nav">
                <button class="back-btn" onclick="goHomeAction()">
                    <svg viewBox="0 0 24 24"><path d="M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z"/></svg>
                </button>
            </div>

            <div class="series-details">
                <img class="series-poster-main" id="seriesPoster" src="" alt="Poster">
                <div class="series-info-text">
                    <h1 class="series-title-main" id="seriesTitle">Título</h1>
                    <div class="series-meta" id="seriesMeta">Serie • Temporada Completa</div>
                </div>
            </div>

            <h2 class="episodes-title">Episodios disponibles</h2>
            <div class="episodes-list" id="seriesList"></div>
            <div class="loader" id="seriesLoader"></div>
        </div>
    </div>

    <div class="player-modal" id="playerModal">
        <video id="mainVideo" playsinline preload="auto"></video>
        <div class="player-ui" id="playerUI">
            <div class="p-top-bar">
                <button class="p-icon-btn" onclick="closePlayerAction()">
                    <svg viewBox="0 0 24 24"><path d="M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z"/></svg>
                </button>
                <div class="p-title" id="playerTitle">Reproduciendo...</div>
            </div>

            <div class="p-center-area" id="centerArea">
                <div class="p-center-icon" id="centerIcon">
                    <svg id="c-icon-play" style="display:none;" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
                    <svg id="c-icon-pause" style="display:none;" viewBox="0 0 24 24"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>
                </div>
            </div>

            <div class="p-bottom-bar">
                <div class="p-timeline-container" id="timelineContainer">
                    <div class="p-timeline-bg">
                        <div class="p-timeline-progress" id="timelineProgress"></div>
                        <div class="p-timeline-thumb" id="timelineThumb"></div>
                    </div>
                </div>

                <div class="p-controls-row">
                    <div class="p-controls-left">
                        <button class="p-icon-btn" id="playPauseBtn">
                            <svg id="icon-play" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
                            <svg id="icon-pause" style="display:none;" viewBox="0 0 24 24"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>
                        </button>
                        <button class="p-icon-btn" id="rewindBtn">
                            <svg viewBox="0 0 24 24"><path d="M11 18V6l-8.5 6 8.5 6zm.5-6l8.5 6V6l-8.5 6z"/></svg>
                        </button>
                        <div class="p-time"><span id="timeCurrent">00:00</span> / <span id="timeTotal">00:00</span></div>
                    </div>

                    <div class="p-controls-right">
                        <button class="p-icon-btn" id="nextChapBtn" style="display:none;">
                            <svg viewBox="0 0 24 24"><path d="M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z"/></svg>
                        </button>
                        <button class="p-res-btn" onclick="toggleResolution()" id="resBtn">16:9</button>
                        <button class="p-icon-btn" id="fullscreenBtn">
                            <svg viewBox="0 0 24 24"><path d="M7 14H5v5h5v-2H7v-3zm-2-4h2V7h3V5H5v5zm12 7h-3v2h5v-5h-2v3zM14 5v2h3v3h2V5h-5z"/></svg>
                        </button>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        const API = window.location.origin;
        let allMedia = [], currentFiltered = [];
        let favorites = JSON.parse(localStorage.getItem('ryflix_favs')) || [];

        // SCROLL 30 EN 30 CONFIGURACIÓN
        let displayedCount = 0; const CHUNK_SIZE = 30; let showingFavs = false;

        let currentPlaylist = [];
        let currentVideoIndex = -1;
        let heroInterval;
        let hideUITimeout;

        const grid = document.getElementById('grid');
        const loader = document.getElementById('loader');
        const homeSection = document.getElementById('homeSection');
        const seriesSection = document.getElementById('seriesSection');
        const searchInput = document.getElementById('searchInput');
        const header = document.getElementById('appHeader');

        // BOTÓN ATRÁS NATIVO - SISTEMA HISTORY API
        history.replaceState({view: 'home'}, '');

        window.addEventListener('popstate', (e) => {
            const view = e.state ? e.state.view : 'home';

            if (view === 'home') {
                if (modal.classList.contains('show')) closePlayerUI();
                seriesSection.style.display = 'none';
                homeSection.style.display = 'block';
            } else if (view === 'series') {
                if (modal.classList.contains('show')) closePlayerUI();
                seriesSection.style.display = 'block';
                homeSection.style.display = 'none';
            } else if (view === 'player') {
                modal.classList.add('show');
            }
        });

        // SCROLL 30 EN 30 LÓGICA
        window.addEventListener('scroll', () => {
            if (window.scrollY > 50) header.classList.add('scrolled');
            else header.classList.remove('scrolled');

            if (homeSection.style.display !== 'none' && !showingFavs) {
                if (window.innerHeight + window.scrollY >= document.body.offsetHeight - 200) loadNextChunk();
            }
        });

        document.addEventListener('DOMContentLoaded', fetchCatalog);

        function fetchCatalog() {
            grid.innerHTML = ''; loader.style.display = 'block';
            fetch(API + '/api/media').then(r => r.json()).then(data => {
                allMedia = data; currentFiltered = [...allMedia]; displayedCount = 0;
                loader.style.display = 'none';
                initHeroSlider();
                loadNextChunk();
            }).catch(() => { loader.style.display = 'none'; grid.innerHTML = '<p>Error de conexión.</p>'; });
        }

        function initHeroSlider() {
            const hero = document.getElementById('heroSlider');
            if (allMedia.length === 0) return;
            hero.style.display = 'block';

            let featured = [...allMedia].sort(() => 0.5 - Math.random()).slice(0, 5);
            hero.innerHTML = '';

            featured.forEach((item, idx) => {
                const imgUrl = item.image ? `${API}/img?path=${encodeURIComponent(item.image)}` : '';
                const slide = document.createElement('div');
                slide.className = `hero-slide ${idx === 0 ? 'active' : ''}`;
                slide.style.backgroundImage = imgUrl ? `url('${imgUrl}')` : 'none';

                const itemJson = encodeURIComponent(JSON.stringify(item));

                slide.innerHTML = `
                    <div class="hero-content">
                        <h2 class="hero-title">${item.name}</h2>
                        <button class="hero-btn" onclick="playHeroItem('${itemJson}')">
                            <svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg> Reproducir
                        </button>
                    </div>
                `;
                hero.appendChild(slide);
            });

            let currentSlide = 0;
            const slides = document.querySelectorAll('.hero-slide');
            if (slides.length > 1) {
                clearInterval(heroInterval);
                heroInterval = setInterval(() => {
                    slides[currentSlide].classList.remove('active');
                    currentSlide = (currentSlide + 1) % slides.length;
                    slides[currentSlide].classList.add('active');
                }, 5000);
            }
        }

        window.playHeroItem = function(jsonStr) {
            const item = JSON.parse(decodeURIComponent(jsonStr));
            if (item.is_folder || item.type === 'series') {
                openSeries(item);
            } else {
                openPlayer(item, [item], 0);
            }
        };

        function loadNextChunk() {
            if (displayedCount >= currentFiltered.length) return;
            const chunk = currentFiltered.slice(displayedCount, displayedCount + CHUNK_SIZE);
            chunk.forEach(item => grid.appendChild(createCard(item)));
            displayedCount += CHUNK_SIZE;
        }

        searchInput.addEventListener('input', (e) => {
            const val = e.target.value.toLowerCase().trim();
            if(showingFavs) toggleFavView();
            document.getElementById('heroSlider').style.display = val === '' ? 'block' : 'none';
            currentFiltered = val === '' ? [...allMedia] : allMedia.filter(i => i.name.toLowerCase().includes(val));
            grid.innerHTML = ''; displayedCount = 0; loadNextChunk();
        });

        function toggleFavView() {
            showingFavs = !showingFavs; grid.innerHTML = '';
            document.getElementById('favToggleBtn').classList.toggle('active');
            document.getElementById('mainTitle').textContent = showingFavs ? 'Mi Lista' : 'Películas y Series';
            document.getElementById('heroSlider').style.display = showingFavs ? 'none' : 'block';

            if (showingFavs) {
                const favItems = allMedia.filter(item => favorites.includes(item.folder || item.file));
                if (favItems.length === 0) grid.innerHTML = '<p style="margin:20px;">Lista vacía.</p>';
                else favItems.forEach(item => grid.appendChild(createCard(item)));
            } else { searchInput.value = ''; currentFiltered = [...allMedia]; displayedCount = 0; loadNextChunk(); }
        }

        function toggleFavorite(e, id) {
            e.stopPropagation();
            const idx = favorites.indexOf(id);
            if (idx > -1) favorites.splice(idx, 1); else favorites.push(id);
            localStorage.setItem('ryflix_favs', JSON.stringify(favorites));
            e.currentTarget.classList.toggle('active');
            if (showingFavs) { grid.innerHTML = ''; toggleFavView(); toggleFavView(); }
        }

        function createCard(item) {
            const card = document.createElement('div'); card.className = 'card';
            const isFolder = item.is_folder || item.type === 'series';
            const itemId = item.folder || item.file;
            const isFav = favorites.includes(itemId);

            const imgUrl = item.image ? `${API}/img?path=${encodeURIComponent(item.image)}` : '';
            const posterHTML = item.image ? `<img src="${imgUrl}" loading="lazy">` : `<div class="poster-alt">${item.name.charAt(0)}</div>`;

            let favHtml = `<div class="fav-icon ${isFav ? 'active' : ''}" onclick="toggleFavorite(event, '${itemId}')">
                <svg viewBox="0 0 24 24"><path d="M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z"/></svg></div>`;

            card.innerHTML = `<div class="poster">${posterHTML}</div>${favHtml}<div class="card-title">${item.name}</div>`;
            card.onclick = () => isFolder ? openSeries(item) : openPlayer(item, [item], 0);
            return card;
        }

        /* ABRE LA SERIE Y REGISTRA HISTORY */
        function openSeries(serie) {
            history.pushState({view: 'series'}, '');
            homeSection.style.display = 'none';
            seriesSection.style.display = 'block';
            window.scrollTo(0, 0);

            document.getElementById('seriesTitle').textContent = serie.name;

            const imgUrl = serie.image ? `${API}/img?path=${encodeURIComponent(serie.image)}` : '';
            document.getElementById('seriesHeroBg').style.backgroundImage = imgUrl ? `url('${imgUrl}')` : 'none';
            document.getElementById('seriesPoster').src = imgUrl || '';
            document.getElementById('seriesPoster').style.display = imgUrl ? 'block' : 'none';

            const sList = document.getElementById('seriesList');
            sList.innerHTML = '';
            document.getElementById('seriesLoader').style.display = 'block';

            fetch(`${API}/api/media?folder=${encodeURIComponent(serie.folder || serie.name)}`)
                .then(r => r.json()).then(chapters => {
                    document.getElementById('seriesLoader').style.display = 'none';
                    document.getElementById('seriesMeta').textContent = `Serie • ${chapters.length} Episodios`;
                    chapters.forEach((chap, idx) => {
                        const row = document.createElement('div');
                        row.className = 'episode-row';
                        const thumbHtml = imgUrl ? `<img src="${imgUrl}" loading="lazy">` : '';

                        row.innerHTML = `
                            <div class="ep-thumb">
                                ${thumbHtml}
                                <svg class="ep-thumb-icon" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
                            </div>
                            <div class="ep-info">
                                <div class="ep-title">${chap.name}</div>
                                <div class="ep-num">Episodio ${idx + 1}</div>
                            </div>
                        `;
                        row.onclick = () => openPlayer(chap, chapters, idx);
                        sList.appendChild(row);
                    });
                });
        }

        function goHomeAction() {
            if (seriesSection.style.display === 'block' || modal.classList.contains('show')) {
                history.back();
            }
        }

        // --- LÓGICA DEL REPRODUCTOR MÓVIL/TABLET ---
        const video = document.getElementById('mainVideo');
        const modal = document.getElementById('playerModal');
        const playerUI = document.getElementById('playerUI');
        let currentVideoId = '';

        const playPauseBtn = document.getElementById('playPauseBtn');
        const iconPlay = document.getElementById('icon-play');
        const iconPause = document.getElementById('icon-pause');
        const centerArea = document.getElementById('centerArea');
        const centerIcon = document.getElementById('centerIcon');
        const cIconPlay = document.getElementById('c-icon-play');
        const cIconPause = document.getElementById('c-icon-pause');

        const timelineCont = document.getElementById('timelineContainer');
        const timeProg = document.getElementById('timelineProgress');
        const timeThumb = document.getElementById('timelineThumb');
        const timeCurrent = document.getElementById('timeCurrent');
        const timeTotal = document.getElementById('timeTotal');
        const nextChapBtn = document.getElementById('nextChapBtn');
        const rewindBtn = document.getElementById('rewindBtn');
        const fullscreenBtn = document.getElementById('fullscreenBtn');

        function openPlayer(videoItem, playlist, index) {
            history.pushState({view: 'player'}, '');
            currentPlaylist = playlist;
            currentVideoIndex = index;
            currentVideoId = videoItem.folder ? `${videoItem.folder}_${videoItem.file}` : videoItem.file;

            document.getElementById('playerTitle').textContent = videoItem.name;
            nextChapBtn.style.display = (index + 1 < playlist.length) ? 'flex' : 'none';

            let vUrl = `${API}/stream?file=${encodeURIComponent(videoItem.file)}`;
            if (videoItem.folder) vUrl += `&folder=${encodeURIComponent(videoItem.folder)}`;
            video.src = vUrl;

            modal.classList.add('show');
            document.body.style.overflow = 'hidden';
            resetUIActivity();

            video.onloadedmetadata = () => {
                const saved = localStorage.getItem('ry_prog_' + currentVideoId);
                if (saved) video.currentTime = parseFloat(saved);
                timeTotal.textContent = formatTime(video.duration);

                video.play().then(() => {
                    iconPlay.style.display = 'none'; iconPause.style.display = 'block';
                }).catch(() => {
                    iconPlay.style.display = 'block'; iconPause.style.display = 'none';
                });
            };
        }

        function closePlayerAction() {
            history.back(); // Delega a PopState
        }

        function closePlayerUI() {
            modal.classList.remove('show');
            video.pause(); video.removeAttribute('src'); video.load();
            document.body.style.overflow = 'auto';
            clearTimeout(hideUITimeout);
            if (document.fullscreenElement) document.exitFullscreen().catch(()=>{});
        }

        // OCULTACIÓN INTELIGENTE DE BOTONES
        function resetUIActivity() {
            playerUI.classList.remove('hidden');
            clearTimeout(hideUITimeout);
            if (!video.paused) {
                hideUITimeout = setTimeout(() => { playerUI.classList.add('hidden'); }, 3000);
            }
        }

        // Detectar movimiento sobre el UI
        playerUI.addEventListener('mousemove', resetUIActivity);
        playerUI.addEventListener('touchmove', resetUIActivity);

        // CUANDO LA UI ESTÁ OCULTA (pointer-events: none), EL CLIC LLEGA AL VIDEO
        video.addEventListener('click', () => {
            if (playerUI.classList.contains('hidden')) {
                resetUIActivity(); // Un toque para mostrar
            }
        });

        // CUANDO LA UI ESTÁ VISIBLE, UN TOQUE EN EL CENTRO LA OCULTA
        centerArea.addEventListener('click', (e) => {
            e.stopPropagation();
            playerUI.classList.add('hidden'); // Otro toque para ocultar
            clearTimeout(hideUITimeout);
        });

        function togglePlay() {
            if (video.paused) {
                video.play();
                iconPlay.style.display = 'none'; iconPause.style.display = 'block';
                showCenterIcon('play');
                resetUIActivity();
            } else {
                video.pause();
                iconPlay.style.display = 'block'; iconPause.style.display = 'none';
                showCenterIcon('pause');
                playerUI.classList.remove('hidden');
                clearTimeout(hideUITimeout);
            }
        }
        playPauseBtn.addEventListener('click', (e) => { e.stopPropagation(); togglePlay(); });

        function showCenterIcon(state) {
            cIconPlay.style.display = state === 'play' ? 'block' : 'none';
            cIconPause.style.display = state === 'pause' ? 'block' : 'none';
            centerIcon.classList.remove('animate');
            void centerIcon.offsetWidth;
            centerIcon.classList.add('animate');
        }

        function formatTime(sec) {
            if(isNaN(sec)) return "00:00";
            const m = Math.floor(sec / 60); const s = Math.floor(sec % 60);
            return `${m}:${s < 10 ? '0' : ''}${s}`;
        }

        video.addEventListener('timeupdate', () => {
            if (!video.duration) return;
            timeCurrent.textContent = formatTime(video.currentTime);
            const percent = (video.currentTime / video.duration) * 100;
            timeProg.style.width = `${percent}%`;
            timeThumb.style.left = `${percent}%`;

            if (video.currentTime > 5 && !video.paused && video.currentTime < video.duration - 2) {
                localStorage.setItem('ry_prog_' + currentVideoId, video.currentTime);
            }
        });

        timelineCont.addEventListener('click', (e) => {
            e.stopPropagation();
            const rect = timelineCont.getBoundingClientRect();
            const pos = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
            video.currentTime = pos * video.duration;
            resetUIActivity();
        });

        rewindBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            video.currentTime = Math.max(0, video.currentTime - 10);
            resetUIActivity();
        });

        function playNext() {
            localStorage.removeItem('ry_prog_' + currentVideoId);
            if (currentVideoIndex + 1 < currentPlaylist.length) {
                // Modificamos el historial actual en lugar de añadir uno nuevo para evitar apilar
                history.replaceState({view: 'player'}, '');
                closePlayerUI();
                openPlayer(currentPlaylist[currentVideoIndex + 1], currentPlaylist, currentVideoIndex + 1);
            } else { closePlayerAction(); }
        }
        video.addEventListener('ended', playNext);
        nextChapBtn.addEventListener('click', (e) => { e.stopPropagation(); playNext(); });

        let isFit16_9 = false;
        function toggleResolution() {
            isFit16_9 = !isFit16_9;
            video.className = isFit16_9 ? 'fit-16-9' : '';
            document.getElementById('resBtn').textContent = isFit16_9 ? 'Orig' : '16:9';
            resetUIActivity();
        }

        fullscreenBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            if (!document.fullscreenElement) {
                if (modal.requestFullscreen) modal.requestFullscreen();
                else if (modal.webkitRequestFullscreen) modal.webkitRequestFullscreen();
            } else {
                if (document.exitFullscreen) document.exitFullscreen();
            }
            resetUIActivity();
        });
    </script>
</body>
</html>""")

if __name__ == '__main__':
    if not os.path.exists(MEDIA_DIR): os.makedirs(MEDIA_DIR)
    generate_html_files()
    if not os.path.exists(APK_NAME): open(APK_NAME, 'w').close()

    httpd = ThreadingHTTPServer(('0.0.0.0', PORT), RyflixHandler)
    print(f"Servidor MULTIHILO activo en el puerto {PORT}")
    print(f"Abre http://localhost:8000/index.html para ver el inicio")
    httpd.serve_forever()
