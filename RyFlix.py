import os
import urllib.parse
import json
import shutil
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# --- CONFIGURACIÓN ---
PORT = 8000
MEDIA_DIR = "storage/downloads/flix"

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
        elif parsed_path.path == '/api/media':
            self.serve_api(query)
        elif parsed_path.path == '/stream':
            self.serve_stream(query)
        elif parsed_path.path == '/img':
            self.serve_image(query)
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
                chunk_size = 1024 * 1024 # Buffer optimizado a 1MB
                while bytes_to_read > 0:
                    chunk = f.read(min(chunk_size, bytes_to_read))
                    if not chunk: break
                    try:
                        self.wfile.write(chunk)
                    except Exception:
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
                shutil.copyfileobj(f, self.wfile, length=1024*1024)


# --- GENERACIÓN AUTOMÁTICA DE HTML ---
def generate_html_files():
    if not os.path.exists('index.html'):
        with open('index.html', 'w', encoding='utf-8') as f:
            f.write("""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="mobile-web-app-capable" content="yes">
    <meta name="theme-color" content="#09090e">
    <title>Ryflix - Cuevana Premium</title>
    <style>
        :root { --bg: #09090e; --surface: #13131a; --red: #ff003c; --red-hover: #ff2a5f; --text: #ffffff; --text-muted: #a0a0ab; --border: rgba(255, 255, 255, 0.08); }
        * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; font-family: system-ui, -apple-system, sans-serif; user-select: none; }
        body { margin: 0; background: var(--bg); color: var(--text); overflow-x: hidden; padding-bottom: 40px; overscroll-behavior-y: none; }

        @keyframes fadeInScale { from { opacity: 0; transform: scale(0.96) translateY(8px); } to { opacity: 1; transform: scale(1) translateY(0); } }

        /* HEADER al estilo Cuevana */
        header { padding: env(safe-area-inset-top, 15px) 24px 15px; display: flex; justify-content: space-between; align-items: center; position: fixed; top: 0; width: 100%; background: linear-gradient(to bottom, rgba(9,9,14,0.95) 0%, rgba(9,9,14,0.8) 50%, transparent 100%); z-index: 100; transition: all 0.3s ease; }
        header.scrolled { background: rgba(19,19,26,0.96); backdrop-filter: blur(16px); border-bottom: 1px solid var(--border); box-shadow: 0 4px 30px rgba(0,0,0,0.4); }
        .logo { color: var(--text); font-size: 1.7rem; font-weight: 900; font-style: italic; cursor: pointer; letter-spacing: 0.5px; text-shadow: 0 0 15px rgba(255,0,60,0.6); }
        .logo span { color: var(--red); }
        .header-controls { display: flex; align-items: center; gap: 16px; }

        .bt-border { background: rgba(255,255,255,0.06); color: white; border: 1px solid var(--border); padding: 8px 18px; border-radius: 30px; font-weight: 600; cursor: pointer; font-size: 0.85rem; transition: all 0.2s ease; backdrop-filter: blur(5px); }
        .bt-border:hover, .bt-border:active { background: rgba(255,255,255,0.12); transform: scale(0.96); }
        .bt-border.active { border-color: var(--red); color: white; background: var(--red); box-shadow: 0 0 15px rgba(255,0,60,0.4); }

        .search-box { display: flex; align-items: center; background: rgba(255,255,255,0.04); border: 1px solid var(--border); padding: 6px 14px; border-radius: 30px; transition: all 0.3s ease; }
        .search-box:focus-within { border-color: rgba(255,0,60,0.5); background: rgba(255,255,255,0.07); }
        .search-box input { background: transparent; border: none; color: white; outline: none; width: 110px; font-size: 0.9rem; transition: width 0.3s; }
        .search-box input:focus { width: 160px; }

        /* HERO SLIDER */
        .hero-slider { position: relative; width: 100%; height: 55vh; background: #000; overflow: hidden; display: none; border-bottom: 1px solid var(--border); }
        .hero-slide { position: absolute; top: 0; left: 0; width: 100%; height: 100%; opacity: 0; transition: opacity 1s cubic-bezier(0.4, 0, 0.2, 1); background-size: cover; background-position: center 20%; display: flex; flex-direction: column; justify-content: flex-end; }
        .hero-slide.active { opacity: 1; z-index: 2; }
        .hero-slide::after { content: ''; position: absolute; bottom: 0; left: 0; width: 100%; height: 80%; background: linear-gradient(to top, var(--bg) 0%, rgba(9,9,14,0.4) 60%, transparent 100%); z-index: 0; }
        .hero-content { position: relative; z-index: 3; padding: 24px; margin-bottom: 15px; text-align: center; max-width: 600px; margin-left: auto; margin-right: auto; }
        .hero-title { font-size: 2.2rem; font-weight: 850; text-shadow: 0 2px 10px rgba(0,0,0,0.9); margin: 0 0 16px 0; letter-spacing: -0.5px; }
        .hero-btn { display: inline-flex; align-items: center; gap: 10px; background: var(--red); color: white; border: none; padding: 12px 28px; border-radius: 30px; font-weight: 700; font-size: 0.95rem; cursor: pointer; box-shadow: 0 4px 15px rgba(255,0,60,0.3); transition: all 0.2s; }
        .hero-btn:active { transform: scale(0.95); background: var(--red-hover); }
        .hero-btn svg { width: 20px; height: 20px; fill: white; }

        /* CATALOG GRID MÁS ESTILIZADO */
        .section-title { font-size: 1.35rem; margin: 24px 24px 16px; font-weight: 800; letter-spacing: -0.3px; color: white; position: relative; display: inline-block; }
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(115px, 1fr)); gap: 14px; padding: 0 24px; }
        .card { background: var(--surface); border-radius: 10px; overflow: hidden; position: relative; cursor: pointer; animation: fadeInScale 0.4s cubic-bezier(0.16, 1, 0.3, 1) backwards; border: 1px solid var(--border); transition: all 0.25s ease; }
        .card:active { transform: scale(0.96); border-color: rgba(255,0,60,0.3); }
        .poster { width: 100%; aspect-ratio: 2/3; background: #181824; display: flex; align-items: center; justify-content: center; }
        .poster img { width: 100%; height: 100%; object-fit: cover; transition: transform 0.3s ease; }
        .poster-alt { font-size: 2.8rem; font-weight: 900; color: #2a2a3a; text-transform: uppercase; }
        .card-title { padding: 12px 10px; font-size: 0.85rem; text-align: left; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-weight: 600; color: #f3f3f5; }

        .fav-icon { position: absolute; top: 10px; right: 10px; width: 30px; height: 30px; background: rgba(19,19,26,0.7); backdrop-filter: blur(8px); border: 1px solid var(--border); border-radius: 50%; display: flex; align-items: center; justify-content: center; z-index: 10; transition: all 0.2s; }
        .fav-icon svg { width: 15px; height: 15px; fill: white; transition: transform 0.2s; }
        .fav-icon.active { background: rgba(255,0,60,0.15); border-color: var(--red); }
        .fav-icon.active svg { fill: var(--red); transform: scale(1.1); }

        .loader { width: 32px; height: 32px; border: 3.5px solid rgba(255,255,255,0.05); border-top-color: var(--red); border-radius: 50%; animation: spin 0.8s linear infinite; margin: 40px auto; display: none; }
        @keyframes spin { to { transform: rotate(360deg); } }

        /* SECCIÓN DE DETALLES DE SERIES */
        #seriesSection { display: none; min-height: 100vh; background: var(--bg); position: relative; padding-bottom: 60px; }
        .series-hero-bg { position: absolute; top: 0; left: 0; width: 100%; height: 70vh; background-size: cover; background-position: center top; z-index: 0; opacity: 0.2; filter: blur(15px); }
        .series-hero-bg::after { content: ''; position: absolute; bottom: 0; left: 0; width: 100%; height: 100%; background: linear-gradient(to top, var(--bg) 15%, transparent 100%); }

        .series-container { position: relative; z-index: 2; padding: calc(env(safe-area-inset-top, 20px) + 24px) 24px 24px; }
        .series-header-nav { display: flex; align-items: center; margin-bottom: 24px; }
        .back-btn { background: rgba(255,255,255,0.06); border: 1px solid var(--border); border-radius: 50%; width: 46px; height: 46px; display: flex; justify-content: center; align-items: center; cursor: pointer; backdrop-filter: blur(10px); transition: all 0.2s; }
        .back-btn:active { transform: scale(0.92); background: rgba(255,255,255,0.12); }
        .back-btn svg { width: 22px; height: 22px; fill: white; }

        .series-details { display: flex; flex-direction: column; gap: 24px; margin-bottom: 40px; }
        .series-poster-main { width: 150px; aspect-ratio: 2/3; border-radius: 12px; box-shadow: 0 10px 30px rgba(0,0,0,0.7); object-fit: cover; align-self: center; border: 1px solid var(--border); }
        .series-info-text { text-align: center; }
        .series-title-main { font-size: 2.2rem; font-weight: 850; text-shadow: 0 2px 10px rgba(0,0,0,0.8); margin: 0 0 10px 0; letter-spacing: -0.5px; }
        .series-meta { font-size: 0.95rem; color: var(--text-muted); font-weight: 600; }

        .episodes-title { font-size: 1.3rem; font-weight: 800; margin-bottom: 20px; border-left: 4px solid var(--red); padding-left: 12px; }
        .episodes-list { display: flex; flex-direction: column; gap: 12px; }
        .episode-row { display: flex; align-items: center; gap: 16px; padding: 14px; background: var(--surface); border-radius: 10px; border: 1px solid var(--border); cursor: pointer; transition: all 0.2s ease; }
        .episode-row:active { background: rgba(255,255,255,0.05); border-color: rgba(255,0,60,0.2); }

        .ep-thumb { width: 120px; aspect-ratio: 16/9; background: #181824; border-radius: 6px; overflow: hidden; display: flex; align-items: center; justify-content: center; position: relative; flex-shrink: 0; }
        .ep-thumb img { width: 100%; height: 100%; object-fit: cover; }
        .ep-thumb-icon { position: absolute; width: 26px; height: 26px; fill: white; filter: drop-shadow(0 2px 5px rgba(0,0,0,0.7)); }
        .ep-info { flex: 1; overflow: hidden; }
        .ep-title { font-size: 0.95rem; font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-bottom: 4px; color: #f3f3f5; }
        .ep-num { font-size: 0.8rem; color: var(--text-muted); font-weight: 500; }

        /* REPRODUCTOR MÓVIL AVANZADO */
        .player-modal { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: #000; z-index: 9999; display: none; flex-direction: column; }
        .player-modal.show { display: flex; }
        video { width: 100%; height: 100%; background: #000; object-fit: contain; }
        video.fit-16-9 { object-fit: fill; }

        .player-ui { position: absolute; top: 0; left: 0; width: 100%; height: 100%; display: flex; flex-direction: column; justify-content: space-between; z-index: 10; opacity: 1; transition: opacity 0.4s cubic-bezier(0.25, 1, 0.5, 1); background: radial-gradient(circle, transparent 20%, rgba(0,0,0,0.85) 100%); }
        .player-ui.hidden { opacity: 0; pointer-events: none; }

        .p-top-bar { padding: env(safe-area-inset-top, 20px) 24px 20px; background: linear-gradient(to bottom, rgba(0,0,0,0.9), transparent); display: flex; align-items: center; gap: 16px; }
        .p-title { flex: 1; font-weight: 700; font-size: 1.15rem; text-shadow: 0 2px 5px rgba(0,0,0,0.9); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

        .p-center-area { flex: 1; display: flex; align-items: center; justify-content: center; gap: 40px; cursor: pointer; width: 100%; }
        .p-center-icon { width: 66px; height: 66px; background: rgba(19,19,26,0.75); border: 1px solid var(--border); border-radius: 50%; display: flex; justify-content: center; align-items: center; opacity: 0; transform: scale(0.8); transition: all 0.2s ease-out; pointer-events: none; backdrop-filter: blur(8px); }
        .p-center-icon svg { width: 30px; height: 30px; fill: white; }
        .p-center-icon.animate { opacity: 1; transform: scale(1.1); }

        .p-side-seek-btn { background: transparent; border: none; padding: 0; cursor: pointer; display: flex; flex-direction: column; align-items: center; justify-content: center; color: white; font-size: 0.75rem; font-weight: 700; gap: 4px; text-shadow: 0 2px 4px rgba(0,0,0,0.8); z-index: 12; }
        .p-side-seek-btn svg { width: 36px; height: 36px; fill: white; transition: transform 0.15s; }
        .p-side-seek-btn:active svg { transform: scale(0.85); }

        .p-bottom-bar { padding: 24px; padding-bottom: env(safe-area-inset-bottom, 25px); background: linear-gradient(to top, rgba(0,0,0,0.95), transparent); display: flex; flex-direction: column; gap: 20px; }

        .p-timeline-container { width: 100%; height: 24px; display: flex; align-items: center; cursor: pointer; position: relative; }
        .p-timeline-bg { width: 100%; height: 6px; background: rgba(255,255,255,0.15); border-radius: 4px; position: relative; }
        .p-timeline-progress { height: 100%; background: var(--red); border-radius: 4px; width: 0%; position: absolute; box-shadow: 0 0 10px rgba(255,0,60,0.5); }
        .p-timeline-thumb { width: 16px; height: 16px; background: var(--red); border-radius: 50%; position: absolute; top: 50%; transform: translate(-50%, -50%); left: 0%; box-shadow: 0 0 8px rgba(0,0,0,0.8); }

        .p-controls-row { display: flex; justify-content: space-between; align-items: center; }
        .p-controls-left, .p-controls-right { display: flex; align-items: center; gap: 28px; }

        .p-icon-btn { background: transparent; border: none; padding: 0; cursor: pointer; display: flex; justify-content: center; align-items: center; transition: transform 0.15s; }
        .p-icon-btn:active { transform: scale(0.9); }
        .p-icon-btn svg { width: 32px; height: 32px; fill: white; }

        .p-time { font-size: 0.9rem; opacity: 0.9; font-weight: 600; font-variant-numeric: tabular-nums; color: #e3e3e8; }
        .p-res-btn { font-size: 0.85rem; font-weight: 700; color: white; background: rgba(255,255,255,0.08); border: 1px solid var(--border); padding: 6px 12px; border-radius: 6px; cursor: pointer; }

        @media (min-width: 768px) {
            .grid { grid-template-columns: repeat(auto-fill, minmax(145px, 1fr)); gap: 18px; padding: 0 32px; }
            .section-title { margin: 30px 32px 20px; font-size: 1.5rem; }
            .series-details { flex-direction: row; align-items: flex-end; text-align: left; gap: 32px; margin-top: 20px; }
            .series-poster-main { width: 190px; }
            .series-info-text { text-align: left; }
            .series-title-main { font-size: 3rem; }
            .episodes-list { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
            .p-icon-btn svg { width: 36px; height: 36px; }
            .p-side-seek-btn svg { width: 42px; height: 42px; font-size: 0.85rem; }
        }
    </style>
</head>
<body>
    <header id="appHeader">
        <div class="header-left">
            <div class="logo" onclick="goHomeAction()">RY<span>FLIX</span></div>
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
                <button class="p-side-seek-btn" id="seekBackCenterBtn">
                    <svg viewBox="0 0 24 24"><path d="M11 18V6l-8.5 6 8.5 6zm.5-6l8.5 6V6l-8.5 6z"/></svg>
                    <span>-10s</span>
                </button>

                <div class="p-center-icon" id="centerIcon">
                    <svg id="c-icon-play" style="display:none;" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
                    <svg id="c-icon-pause" style="display:none;" viewBox="0 0 24 24"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>
                </div>

                <button class="p-side-seek-btn" id="seekForwardCenterBtn">
                    <svg viewBox="0 0 24 24"><path d="M4 18l8.5-6L4 6v12zm9-12v12l8.5-6L13 6z"/></svg>
                    <span>+10s</span>
                </button>
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
                        <button class="p-icon-btn" id="rewindBtn" title="Retroceder 10s">
                            <svg viewBox="0 0 24 24"><path d="M11 18V6l-8.5 6 8.5 6zm.5-6l8.5 6V6l-8.5 6z"/></svg>
                        </button>
                        <button class="p-icon-btn" id="forwardBtn" title="Avanzar 10s">
                            <svg viewBox="0 0 24 24"><path d="M4 18l8.5-6L4 6v12zm9-12v12l8.5-6L13 6z"/></svg>
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

        window.addEventListener('scroll', () => {
            if (window.scrollY > 30) header.classList.add('scrolled');
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
            }).catch(() => { loader.style.display = 'none'; grid.innerHTML = '<p style="padding:24px;">Error de conexión.</p>'; });
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
                            <svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg> Ver Ahora
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
            if (item.is_folder || item.type === 'series') { openSeries(item); } else { openPlayer(item, [item], 0); }
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
                if (favItems.length === 0) grid.innerHTML = '<p style="margin:24px; color:var(--text-muted);">Tu lista está vacía.</p>';
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

            const sList = document.getElementById('seriesList'); sList.innerHTML = '';
            document.getElementById('seriesLoader').style.display = 'block';

            fetch(`${API}/api/media?folder=${encodeURIComponent(serie.folder || serie.name)}`)
                .then(r => r.json()).then(chapters => {
                    document.getElementById('seriesLoader').style.display = 'none';
                    document.getElementById('seriesMeta').textContent = `Serie • ${chapters.length} Episodios`;
                    chapters.forEach((chap, idx) => {
                        const row = document.createElement('div'); row.className = 'episode-row';
                        const thumbHtml = imgUrl ? `<img src="${imgUrl}" loading="lazy">` : '';
                        row.innerHTML = `
                            <div class="ep-thumb">${thumbHtml}<svg class="ep-thumb-icon" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg></div>
                            <div class="ep-info"><div class="ep-title">${chap.name}</div><div class="ep-num">Episodio ${idx + 1}</div></div>
                        `;
                        row.onclick = () => openPlayer(chap, chapters, idx);
                        sList.appendChild(row);
                    });
                });
        }

        function goHomeAction() { if (seriesSection.style.display === 'block' || modal.classList.contains('show')) { history.back(); } }

        // --- LÓGICA DEL REPRODUCTOR MÓVIL ---
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
        const forwardBtn = document.getElementById('forwardBtn');
        const seekBackCenterBtn = document.getElementById('seekBackCenterBtn');
        const seekForwardCenterBtn = document.getElementById('seekForwardCenterBtn');
        const fullscreenBtn = document.getElementById('fullscreenBtn');

        function openPlayer(videoItem, playlist, index) {
            history.pushState({view: 'player'}, '');
            currentPlaylist = playlist; currentVideoIndex = index;
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

        function closePlayerAction() { history.back(); }

        function closePlayerUI() {
            modal.classList.remove('show');
            video.pause(); video.removeAttribute('src'); video.load();
            document.body.style.overflow = 'auto';
            clearTimeout(hideUITimeout);
            if (document.fullscreenElement) document.exitFullscreen().catch(()=>{});
        }

        function resetUIActivity() {
            playerUI.classList.remove('hidden');
            clearTimeout(hideUITimeout);
            if (!video.paused) { hideUITimeout = setTimeout(() => { playerUI.classList.add('hidden'); }, 3000); }
        }

        playerUI.addEventListener('mousemove', resetUIActivity);
        playerUI.addEventListener('touchmove', resetUIActivity);

        video.addEventListener('click', () => { if (playerUI.classList.contains('hidden')) { resetUIActivity(); } });

        centerArea.addEventListener('click', (e) => {
            if(e.target === centerArea || e.target === centerIcon) {
                e.stopPropagation();
                playerUI.classList.add('hidden');
                clearTimeout(hideUITimeout);
            }
        });

        function togglePlay() {
            if (video.paused) {
                video.play(); iconPlay.style.display = 'none'; iconPause.style.display = 'block';
                showCenterIcon('play'); resetUIActivity();
            } else {
                video.pause(); iconPlay.style.display = 'block'; iconPause.style.display = 'none';
                showCenterIcon('pause'); playerUI.classList.remove('hidden'); clearTimeout(hideUITimeout);
            }
        }
        playPauseBtn.addEventListener('click', (e) => { e.stopPropagation(); togglePlay(); });

        function showCenterIcon(state) {
            cIconPlay.style.display = state === 'play' ? 'block' : 'none';
            cIconPause.style.display = state === 'pause' ? 'block' : 'none';
            centerIcon.classList.remove('animate'); void centerIcon.offsetWidth;
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
            timeProg.style.width = `${percent}%`; timeThumb.style.left = `${percent}%`;

            if (video.currentTime > 5 && !video.paused && video.currentTime < video.duration - 2) {
                localStorage.setItem('ry_prog_' + currentVideoId, video.currentTime);
            }
        });

        timelineCont.addEventListener('click', (e) => {
            e.stopPropagation();
            const rect = timelineCont.getBoundingClientRect();
            const pos = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
            video.currentTime = pos * video.duration; resetUIActivity();
        });

        // --- SISTEMA DE NAVEGACIÓN DE TIEMPO ±10 SEGUNDOS ---
        function seekSeconds(seconds) {
            video.currentTime = Math.max(0, Math.min(video.duration, video.currentTime + seconds));
            resetUIActivity();
        }

        rewindBtn.addEventListener('click', (e) => { e.stopPropagation(); seekSeconds(-10); });
        forwardBtn.addEventListener('click', (e) => { e.stopPropagation(); seekSeconds(10); });
        seekBackCenterBtn.addEventListener('click', (e) => { e.stopPropagation(); seekSeconds(-10); });
        seekForwardCenterBtn.addEventListener('click', (e) => { e.stopPropagation(); seekSeconds(10); });

        function playNext() {
            localStorage.removeItem('ry_prog_' + currentVideoId);
            if (currentVideoIndex + 1 < currentPlaylist.length) {
                history.replaceState({view: 'player'}, ''); closePlayerUI();
                openPlayer(currentPlaylist[currentVideoIndex + 1], currentPlaylist, currentVideoIndex + 1);
            } else { closePlayerAction(); }
        }
        video.addEventListener('ended', playNext);
        nextChapBtn.addEventListener('click', (e) => { e.stopPropagation(); playNext(); });

        let isFit16_9 = false;
        function toggleResolution() {
            isFit16_9 = !isFit16_9; video.className = isFit16_9 ? 'fit-16-9' : '';
            document.getElementById('resBtn').textContent = isFit16_9 ? 'Orig' : '16:9'; resetUIActivity();
        }

        fullscreenBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            if (!document.fullscreenElement) {
                if (modal.requestFullscreen) modal.requestFullscreen();
                else if (modal.webkitRequestFullscreen) modal.webkitRequestFullscreen();
            } else { if (document.exitFullscreen) document.exitFullscreen(); }
            resetUIActivity();
        });
    </script>
</body>
</html>""")

if __name__ == '__main__':
    if not os.path.exists(MEDIA_DIR): os.makedirs(MEDIA_DIR)
    generate_html_files()

    httpd = ThreadingHTTPServer(('0.0.0.0', PORT), RyflixHandler)
    print(f"Servidor MULTIHILO activo en el puerto {PORT}")
    print(f"Abre http://localhost:8000/index.html para ver el inicio")
    httpd.serve_forever()
