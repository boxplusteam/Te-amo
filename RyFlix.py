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

# Función de ordenamiento natural para títulos/capítulos (Evita que Ep 10 vaya antes que Ep 2)
def natural_sort_key(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]

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
        elif parsed_path.path == '/server.html':
            self.serve_file('server.html', 'text/html')
        elif parsed_path.path == '/api/media':
            self.serve_api(query)
        elif parsed_path.path == '/stream':
            self.serve_stream(query)
        elif parsed_path.path == '/img':
            self.serve_image(query)
        elif parsed_path.path == '/download_apk':
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

    def serve_apk(self):
        apk_path = None
        if os.path.exists(MEDIA_DIR):
            for file in os.listdir(MEDIA_DIR):
                if file.lower().endswith('.apk'):
                    apk_path = os.path.join(MEDIA_DIR, file)
                    break
        
        if not apk_path or not os.path.exists(apk_path):
            return self.send_error(404, "Archivo APK no encontrado en la carpeta flix")
            
        file_size = os.path.getsize(apk_path)
        self.send_response(200)
        self.send_header('Content-Type', 'application/vnd.android.package-archive')
        self.send_header('Content-Disposition', f'attachment; filename="{os.path.basename(apk_path)}"')
        self.send_header('Content-Length', str(file_size))
        self.send_cors_headers()
        self.end_headers()
        with open(apk_path, 'rb') as f:
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

        # Escaneo y ordenamiento de elementos raíz
        for item in sorted(os.listdir(MEDIA_DIR), key=natural_sort_key):
            path = os.path.join(MEDIA_DIR, item)
            name = item.replace('_', ' ').replace('-', ' ').title()

            if os.path.isfile(path) and item.lower().endswith(('.mp4', '.mkv', '.avi')):
                name_clean = name.rsplit('.', 1)[0]
                img = self.find_image_for(item)
                media.append({'name': name_clean, 'file': item, 'type': 'movie', 'image': img})

            elif os.path.isdir(path):
                vids = sorted([f for f in os.listdir(path) if f.lower().endswith(('.mp4', '.mkv', '.avi'))], key=natural_sort_key)
                img = self.find_image_for(item, path)

                if len(vids) == 1:
                    media.append({'name': name, 'folder': item, 'file': vids[0], 'type': 'movie', 'image': img})
                elif len(vids) > 1:
                    media.append({'name': name, 'folder': item, 'type': 'series', 'is_folder': True, 'image': img})

        return media

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
                vids = sorted([f for f in os.listdir(path) if f.lower().endswith(('.mp4', '.mkv', '.avi'))], key=natural_sort_key)
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
                chunk_size = 1024 * 1024
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
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="theme-color" content="#110524">
    <title>Descargar Ryflix APK</title>
    <style>
        :root { --bg: #110524; --lime: #76ff03; --lime-hover: #64dd17; --text: #ffffff; }
        body { margin: 0; background: var(--bg); color: var(--text); font-family: system-ui, -apple-system, sans-serif; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh; text-align: center; }
        .logo-title { font-size: 3rem; font-weight: 900; margin-bottom: 10px; text-shadow: 0 2px 10px rgba(0,0,0,0.5); }
        .subtitle { color: #b39ddb; margin-bottom: 40px; }
        .download-btn { display: inline-flex; align-items: center; gap: 10px; background: var(--lime); color: #000; text-decoration: none; padding: 16px 36px; border-radius: 40px; font-weight: 800; font-size: 1.1rem; box-shadow: 0 4px 20px rgba(118,255,3,0.4); transition: all 0.3s ease; }
        .download-btn:active, .download-btn:hover { transform: scale(0.95); background: var(--lime-hover); }
        .download-btn svg { width: 24px; height: 24px; fill: #000; }
        .web-link { margin-top: 30px; color: #b39ddb; text-decoration: none; font-weight: 600; border-bottom: 1px solid transparent; transition: border-color 0.3s ease, color 0.3s ease; }
        .web-link:hover { color: #fff; border-color: #fff; }
    </style>
</head>
<body>
    <div class="logo-title">Ryflix</div>
    <div class="subtitle">Cuevana Premium directamente en tu móvil</div>
    
    <a href="/download_apk" class="download-btn">
        <svg viewBox="0 0 24 24"><path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/></svg>
        Descargar APK
    </a>

    <a href="/server.html" class="web-link">O usar la versión Web</a>
</body>
</html>""")

    # SIEMPRE SOBREESCRIBIR server.html PARA APLICAR CAMBIOS
    with open('server.html', 'w', encoding='utf-8') as f:
        f.write("""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="mobile-web-app-capable" content="yes">
    <meta name="theme-color" content="#110524">
    <title>Ryflix - Cuevana Premium</title>
    <style>
        :root { --bg: #110524; --surface: #200b40; --lime: #76ff03; --lime-hover: #64dd17; --text: #ffffff; --text-muted: #b39ddb; --border: rgba(118, 255, 3, 0.15); }
        * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; font-family: system-ui, -apple-system, sans-serif; user-select: none; }
        body { margin: 0; background: var(--bg); color: var(--text); overflow-x: hidden; padding-bottom: 40px; overscroll-behavior-y: none; }

        @keyframes fadeInScale { from { opacity: 0; transform: scale(0.96) translateY(8px); } to { opacity: 1; transform: scale(1) translateY(0); } }
        
        header { 
            padding: calc(env(safe-area-inset-top, 15px) + 10px) 24px 15px; 
            display: flex; 
            justify-content: space-between; 
            align-items: center; 
            position: fixed; 
            top: 0; 
            width: 100%; 
            background: rgba(17,5,36,0.98);
            backdrop-filter: blur(16px);
            border-bottom: 1px solid var(--border);
            z-index: 100; 
            transition: background 0.3s ease;
        }
        
        .header-brand { font-size: 1.5rem; font-weight: 900; color: var(--text); letter-spacing: -0.5px; }

        .hamburger-btn {
            background: rgba(255,255,255,0.05);
            border: 1px solid var(--border);
            border-radius: 50%;
            width: 42px;
            height: 42px;
            display: flex;
            justify-content: center;
            align-items: center;
            cursor: pointer;
            z-index: 102;
            transition: all 0.3s ease;
        }
        .hamburger-btn:active { transform: scale(0.9); }
        .hamburger-btn svg { width: 22px; height: 22px; fill: white; }

        .header-controls { 
            display: none; 
            flex-direction: column; 
            position: absolute;
            top: 100%;
            left: 0;
            width: 100%;
            background: var(--surface);
            padding: 20px 24px;
            gap: 16px;
            border-bottom: 1px solid var(--border);
            box-shadow: 0 10px 30px rgba(0,0,0,0.6);
            z-index: 101;
        }
        .header-controls.open { display: flex; animation: fadeInScale 0.25s ease-out; }

        .bt-border { background: rgba(255,255,255,0.06); color: white; border: 1px solid var(--border); padding: 12px 20px; border-radius: 30px; font-weight: 600; cursor: pointer; font-size: 0.95rem; transition: all 0.3s ease; text-align: center; width: 100%; display: flex; align-items: center; justify-content: center; gap: 8px;}
        .bt-border.active { border-color: var(--lime); color: #000000; background: var(--lime); box-shadow: 0 0 15px rgba(118,255,3,0.4); }
        .bt-border:active { transform: scale(0.95); }

        .search-box { display: flex; align-items: center; background: rgba(255,255,255,0.04); border: 1px solid var(--border); padding: 10px 18px; border-radius: 30px; width: 100%; transition: border-color 0.3s ease; }
        .search-box:focus-within { border-color: var(--lime); }
        .search-box input { background: transparent; border: none; color: white; outline: none; width: 100%; font-size: 0.95rem; text-align: center; }

        .hero-slider { position: relative; width: 100%; height: 55vh; min-height: 400px; background: #000; overflow: hidden; display: none; border-bottom: 1px solid var(--border); margin-top: 70px; }
        .hero-slide { position: absolute; top: 0; left: 0; width: 100%; height: 100%; opacity: 0; transition: opacity 1s cubic-bezier(0.4, 0, 0.2, 1); background-size: cover; background-position: center 20%; display: flex; flex-direction: column; justify-content: flex-end; }
        .hero-slide.active { opacity: 1; z-index: 2; }
        .hero-slide::after { content: ''; position: absolute; bottom: 0; left: 0; width: 100%; height: 80%; background: linear-gradient(to top, var(--bg) 0%, rgba(17,5,36,0.4) 60%, transparent 100%); z-index: 0; }
        .hero-content { position: relative; z-index: 3; padding: 24px; margin-bottom: 15px; text-align: center; max-width: 600px; margin-left: auto; margin-right: auto; }
        .hero-title { font-size: 2rem; font-weight: 850; text-shadow: 0 2px 10px rgba(0,0,0,0.9); margin: 0 0 16px 0; letter-spacing: -0.5px; line-height: 1.1; }
        .hero-btn { display: inline-flex; align-items: center; gap: 10px; background: var(--lime); color: #000000; border: none; padding: 12px 28px; border-radius: 30px; font-weight: 700; font-size: 0.95rem; cursor: pointer; box-shadow: 0 4px 15px rgba(118,255,3,0.3); transition: all 0.3s ease; }
        .hero-btn:active { transform: scale(0.95); background: var(--lime-hover); }
        .hero-btn svg { width: 20px; height: 20px; fill: #000000; }

        #rowsContainer { margin-top: 85px; }
        .carousel-section { margin-bottom: 28px; width: 100%; }
        .carousel-title { font-size: 1.2rem; margin: 24px 24px 12px; font-weight: 800; letter-spacing: -0.3px; color: white; }
        .carousel-track { display: flex; overflow-x: auto; gap: 14px; padding: 0 24px; scroll-snap-type: x mandatory; -webkit-overflow-scrolling: touch; scroll-behavior: smooth; }
        .carousel-track::-webkit-scrollbar { display: none; }

        .card { flex: 0 0 32vw; max-width: 140px; min-width: 105px; scroll-snap-align: start; background: var(--surface); border-radius: 4px; overflow: hidden; position: relative; cursor: pointer; animation: fadeInScale 0.4s cubic-bezier(0.16, 1, 0.3, 1) backwards; border: 1px solid var(--border); transition: all 0.3s ease; }
        .card:active { transform: scale(0.96); border-color: rgba(118,255,3,0.3); }
        @media (hover: hover) { .card:hover { transform: translateY(-4px); box-shadow: 0 8px 15px rgba(0,0,0,0.5); border-color: rgba(255,255,255,0.2); } }
        
        .poster { width: 100%; aspect-ratio: 2/3; background: #26114a; display: flex; align-items: center; justify-content: center; }
        .poster img { width: 100%; height: 100%; object-fit: cover; }
        .poster-alt { font-size: 2.8rem; font-weight: 900; color: #3d1c73; text-transform: uppercase; }
        .card-title { padding: 12px 10px; font-size: 0.85rem; text-align: left; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-weight: 600; color: #f3f3f5; }

        .fav-icon { position: absolute; top: 10px; right: 10px; width: 30px; height: 30px; background: rgba(17,5,36,0.7); backdrop-filter: blur(8px); border: 1px solid var(--border); border-radius: 50%; display: flex; align-items: center; justify-content: center; z-index: 10; transition: all 0.3s ease; }
        .fav-icon:active { transform: scale(0.8); }
        .fav-icon svg { width: 15px; height: 15px; fill: white; transition: fill 0.3s ease; }
        .fav-icon.active { background: rgba(118,255,3,0.15); border-color: var(--lime); }
        .fav-icon.active svg { fill: var(--lime); }

        .loader { width: 32px; height: 32px; border: 3.5px solid rgba(255,255,255,0.05); border-top-color: var(--lime); border-radius: 50%; animation: spin 0.8s linear infinite; margin: 40px auto; display: none; }
        @keyframes spin { to { transform: rotate(360deg); } }

        #seriesSection, #movieSection { display: none; min-height: 100vh; background: var(--bg); position: relative; padding-bottom: 60px; padding-top: 60px; animation: fadeInScale 0.3s ease-out; }
        .detail-hero-bg { position: absolute; top: 0; left: 0; width: 100%; height: 70vh; background-size: cover; background-position: center top; z-index: 0; opacity: 0.2; filter: blur(15px); transition: background-image 0.5s ease; }
        .detail-hero-bg::after { content: ''; position: absolute; bottom: 0; left: 0; width: 100%; height: 100%; background: linear-gradient(to top, var(--bg) 15%, transparent 100%); }

        .detail-container { position: relative; z-index: 2; padding: calc(env(safe-area-inset-top, 20px) + 24px) 24px 24px; }
        .back-btn { background: rgba(255,255,255,0.06); border: 1px solid var(--border); border-radius: 50%; width: 46px; height: 46px; display: flex; justify-content: center; align-items: center; cursor: pointer; backdrop-filter: blur(10px); margin-bottom: 24px; transition: all 0.3s ease; }
        .back-btn:active { transform: scale(0.9); }
        .back-btn svg { width: 22px; height: 22px; fill: white; }

        .detail-info { display: flex; flex-direction: column; gap: 24px; margin-bottom: 40px; align-items: center; }
        .detail-poster { width: 45vw; max-width: 200px; aspect-ratio: 2/3; border-radius: 4px; box-shadow: 0 10px 30px rgba(0,0,0,0.7); object-fit: cover; border: 1px solid var(--border); }
        .detail-text { text-align: center; width: 100%; }
        .detail-title { font-size: 2.2rem; font-weight: 850; text-shadow: 0 2px 10px rgba(0,0,0,0.8); margin: 0 0 10px 0; letter-spacing: -0.5px; }
        
        .movie-sd-text { color: var(--lime); font-weight: 700; margin-bottom: 15px; font-size: 1.1rem; }
        .movie-actions { display: flex; gap: 10px; justify-content: center; margin-top: 15px; flex-wrap: wrap; }
        .bt-action { background: var(--surface); border: 1px solid var(--border); color: white; padding: 12px 20px; border-radius: 30px; font-weight: bold; cursor: pointer; display: flex; align-items: center; gap: 8px; transition: all 0.3s ease; }
        .bt-action:active { transform: scale(0.95); }
        .bt-action.play { background: var(--lime); color: #000; box-shadow: 0 4px 15px rgba(118,255,3,0.3); }
        .bt-action svg { width: 18px; height: 18px; fill: currentColor; }

        .episodes-title { font-size: 1.3rem; font-weight: 800; margin-bottom: 20px; border-left: 4px solid var(--lime); padding-left: 12px; }
        .episodes-list { display: flex; flex-direction: column; gap: 12px; }
        .episode-row { display: flex; align-items: center; gap: 16px; padding: 14px; background: var(--surface); border-radius: 10px; border: 1px solid var(--border); cursor: pointer; transition: all 0.3s ease; position: relative; overflow: hidden; }
        .episode-row:active { background: rgba(255,255,255,0.05); transform: scale(0.98); }
        @media (hover: hover) { .episode-row:hover { transform: translateX(5px); border-color: rgba(255,255,255,0.2); } }

        .ep-thumb { width: 120px; aspect-ratio: 16/9; background: #26114a; border-radius: 4px; overflow: hidden; display: flex; align-items: center; justify-content: center; position: relative; flex-shrink: 0; }
        .ep-thumb img { width: 100%; height: 100%; object-fit: cover; }
        .ep-thumb-icon { position: absolute; width: 26px; height: 26px; fill: white; filter: drop-shadow(0 2px 5px rgba(0,0,0,0.7)); transition: transform 0.3s ease; }
        .episode-row:hover .ep-thumb-icon { transform: scale(1.1); }
        
        .ep-info { flex: 1; overflow: hidden; display: flex; flex-direction: column; gap: 4px; }
        
        .ep-title-wrapper { width: 100%; overflow: hidden; position: relative; }
        .ep-title { font-size: 0.95rem; font-weight: 700; white-space: nowrap; color: #f3f3f5; display: inline-block; }
        .ep-title.marquee-active { animation: epMarquee 4s linear infinite; }
        @keyframes epMarquee { 0% { transform: translateX(0); } 100% { transform: translateX(-60%); } }
        
        .ep-num { font-size: 0.8rem; color: var(--text-muted); font-weight: 500; }
        
        .ep-progress-bar { width: 100%; height: 4px; background: rgba(255,255,255,0.1); border-radius: 2px; margin-top: 4px; }
        .ep-progress-fill { height: 100%; background: var(--lime); border-radius: 2px; width: 0%; transition: width 0.5s ease; }
        .ep-progress-text { font-size: 0.7rem; color: var(--lime); font-weight: bold; margin-top: 2px; }

        .player-modal { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: #000; z-index: 9999; display: none; flex-direction: column; cursor: pointer; }
        .player-modal.show { display: flex; animation: fadeInScale 0.3s ease; }
        video { width: 100%; height: 100%; background: #000; object-fit: contain; transition: object-fit 0.3s ease; pointer-events: none; }
        video.fit-16-9 { object-fit: fill; }

        .player-loader { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); width: 60px; height: 60px; border: 5px solid rgba(255,255,255,0.1); border-top-color: var(--lime); border-radius: 50%; animation: spin 0.8s linear infinite; z-index: 5; display: none; pointer-events: none; }
        .player-loader.active { display: block; }

        .player-ui { position: absolute; top: 0; left: 0; width: 100%; height: 100%; display: flex; flex-direction: column; justify-content: space-between; z-index: 10; background: radial-gradient(circle, transparent 20%, rgba(0,0,0,0.85) 100%); transition: opacity 0.4s ease; pointer-events: none; }
        .player-ui.hidden { opacity: 0; pointer-events: none; }

        .p-top-bar { padding: env(safe-area-inset-top, 20px) 24px 20px; background: linear-gradient(to bottom, rgba(0,0,0,0.9), transparent); display: flex; align-items: center; gap: 16px; pointer-events: auto; }
        .p-title { flex: 1; font-weight: 700; font-size: 1.15rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

        .p-center-area { flex: 1; display: flex; align-items: center; justify-content: center; gap: 8vw; width: 100%; pointer-events: none; }
        .p-center-icon { width: 80px; height: 80px; background: rgba(118,255,3,0.9); border: none; border-radius: 50%; display: flex; justify-content: center; align-items: center; transform: scale(1); transition: all 0.2s ease; pointer-events: auto; cursor: pointer; box-shadow: 0 0 25px rgba(118,255,3,0.6); }
        .p-center-icon:active { transform: scale(0.85); }
        .p-center-icon svg { width: 38px; height: 38px; fill: black; }

        .p-side-seek-btn { background: transparent; border: none; padding: 0; color: white; font-size: 0.75rem; font-weight: 700; display: flex; flex-direction: column; align-items: center; gap: 4px; transition: transform 0.2s ease; cursor: pointer; pointer-events: auto; }
        .p-side-seek-btn:active { transform: scale(0.85); }
        .p-side-seek-btn svg { width: 36px; height: 36px; fill: white; }

        .p-bottom-bar { padding: 24px; padding-bottom: env(safe-area-inset-bottom, 25px); background: linear-gradient(to top, rgba(0,0,0,0.95), transparent); display: flex; flex-direction: column; gap: 20px; pointer-events: auto; }
        .p-timeline-container { width: 100%; height: 24px; display: flex; align-items: center; position: relative; cursor: pointer; }
        .p-timeline-bg { width: 100%; height: 6px; background: rgba(255,255,255,0.15); border-radius: 4px; position: relative; width: 100%; }
        .p-timeline-progress { height: 100%; background: var(--lime); border-radius: 4px; width: 0%; position: absolute; transition: width 0.1s linear; }
        .p-timeline-thumb { width: 16px; height: 16px; background: var(--lime); border-radius: 50%; position: absolute; top: 50%; transform: translate(-50%, -50%); left: 0%; box-shadow: 0 0 10px rgba(118,255,3,0.5); transition: left 0.1s linear; }

        .p-controls-row { display: flex; justify-content: space-between; align-items: center; }
        .p-controls-left, .p-controls-right { display: flex; align-items: center; gap: 20px; }
        .p-icon-btn { background: transparent; border: none; padding: 0; display: flex; justify-content: center; align-items: center; cursor: pointer; transition: transform 0.2s ease; }
        .p-icon-btn:active { transform: scale(0.85); }
        .p-icon-btn svg { width: 32px; height: 32px; fill: white; }
        .p-time { font-size: 0.9rem; font-weight: 600; color: #e3e3e8; display: none; }
        .p-res-btn { font-size: 0.85rem; font-weight: 700; color: white; background: rgba(255,255,255,0.08); border: 1px solid var(--border); padding: 6px 12px; border-radius: 6px; cursor: pointer; transition: background 0.3s ease; }
        .p-res-btn:active { background: rgba(255,255,255,0.2); }

        @media (min-width: 768px) {
            .hamburger-btn { display: none; }
            .header-controls { display: flex; flex-direction: row; position: static; background: transparent; padding: 0; box-shadow: none; border-bottom: none; width: auto; animation: none; }
            .search-box { width: 300px; }
            .bt-border { width: auto; }
            #rowsContainer { margin-top: 100px; }
            .detail-info { flex-direction: row; align-items: flex-end; text-align: left; gap: 32px; }
            .detail-text { text-align: left; }
            .episodes-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px; }
            .p-time { display: block; }
        }
    </style>
</head>
<body>
    <header id="appHeader">
        <div class="header-brand">Ryflix</div>
        <button class="hamburger-btn" onclick="toggleMenu()">
            <svg viewBox="0 0 24 24"><path d="M3 18h18v-2H3v2zm0-5h18v-2H3v2zm0-7v2h18V6H3z"/></svg>
        </button>
        <div class="header-controls" id="headerControls">
            <div class="search-box">
                <input type="text" id="searchInput" placeholder="Buscar películas o series..." autocomplete="off">
            </div>
            <button class="bt-border" id="favToggleBtn" onclick="toggleFavView()">Favs</button>
            <button class="bt-border" onclick="toggleSettingsModal()">
                <svg style="width:18px;height:18px;fill:white" viewBox="0 0 24 24"><path d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.06-.94l2.03-1.58c.18-.14.23-.41.12-.61l-1.92-3.32c-.12-.22-.37-.29-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54c-.04-.24-.24-.41-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.73 8.89c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.06.94l-2.03 1.58c-.18.14-.23.41-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .43-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.49-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z"/></svg> Ajustes
            </button>
        </div>
    </header>

    <div id="homeSection">
        <div class="hero-slider" id="heroSlider"></div>
        <div id="rowsContainer"></div>
        <div class="loader" id="loader"></div>
    </div>

    <div id="movieSection">
        <div class="detail-hero-bg" id="movieHeroBg"></div>
        <div class="detail-container">
            <button class="back-btn" onclick="goHomeAction()">
                <svg viewBox="0 0 24 24"><path d="M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z"/></svg>
            </button>
            <div class="detail-info">
                <img class="detail-poster" id="moviePoster" src="" alt="Poster">
                <div class="detail-text">
                    <h1 class="detail-title" id="movieTitle">Título</h1>
                    <div class="movie-sd-text" id="movieSubtitle">Disfruta de la película en SD</div>
                    <div class="movie-actions">
                        <button class="bt-action play" id="moviePlayBtn">
                            <svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg> REPRODUCIR
                        </button>
                        <button class="bt-action" id="movieFavBtn">
                            <svg viewBox="0 0 24 24"><path d="M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z"/></svg> FAVORITOS
                        </button>
                    </div>
                </div>
            </div>
            <div id="movieRecommendations"></div>
        </div>
    </div>

    <div id="seriesSection">
        <div class="detail-hero-bg" id="seriesHeroBg"></div>
        <div class="detail-container">
            <button class="back-btn" onclick="goHomeAction()">
                <svg viewBox="0 0 24 24"><path d="M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z"/></svg>
            </button>
            <div class="detail-info">
                <img class="detail-poster" id="seriesPoster" src="" alt="Poster">
                <div class="detail-text">
                    <h1 class="detail-title" id="seriesTitle">Título</h1>
                    <div style="color: var(--text-muted); font-weight: 600; margin-bottom: 15px;" id="seriesMeta">Serie • Temporada Completa</div>
                    <div class="movie-actions">
                        <button class="bt-action play" id="seriesStartBtn">
                            <svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg> <span id="seriesStartText">EMPEZAR</span>
                        </button>
                        <button class="bt-action" id="seriesFavBtn">
                            <svg viewBox="0 0 24 24"><path d="M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z"/></svg> FAVORITOS
                        </button>
                    </div>
                </div>
            </div>
            <h2 class="episodes-title">Selecciona un episodio</h2>
            <div class="episodes-list" id="seriesList"></div>
            <div class="loader" id="seriesLoader"></div>
        </div>
    </div>

    <div class="player-modal" id="settingsModal" style="z-index: 10000; align-items: center; justify-content: center; background: rgba(0,0,0,0.8);">
        <div style="background: var(--surface); padding: 24px; border-radius: 12px; width: 90%; max-width: 400px; border: 1px solid var(--border); position: relative;">
            <h2 style="margin-top:0; margin-bottom: 20px; font-weight: 800;">Ajustes de Reproductor</h2>
            <div style="display: flex; flex-direction: column; gap: 15px;">
                <label style="display: flex; align-items: center; gap: 10px; cursor: pointer; padding: 10px; background: rgba(255,255,255,0.05); border-radius: 8px;">
                    <input type="radio" name="playerPref" value="internal" style="width: 20px; height: 20px; accent-color: var(--lime);">
                    <span style="font-size: 1.05rem; font-weight: 600;">Reproductor Web (Interno)</span>
                </label>
                <label style="display: flex; align-items: center; gap: 10px; cursor: pointer; padding: 10px; background: rgba(255,255,255,0.05); border-radius: 8px;">
                    <input type="radio" name="playerPref" value="external" style="width: 20px; height: 20px; accent-color: var(--lime);">
                    <div style="display: flex; flex-direction: column;">
                        <span style="font-size: 1.05rem; font-weight: 600;">Aplicación Externa</span>
                        <span style="font-size: 0.8rem; color: var(--text-muted);">Elige usar VLC, MX Player u otro de tu móvil</span>
                    </div>
                </label>
            </div>
            <div style="margin-top: 24px; display: flex; justify-content: flex-end; gap: 10px;">
                <button class="bt-action" onclick="closeSettingsModal()" style="background: transparent;">Cancelar</button>
                <button class="bt-action play" onclick="saveSettings()">Guardar</button>
            </div>
        </div>
    </div>

    <div class="player-modal" id="playerModal" onclick="togglePlayerUI(event)">
        <video id="mainVideo" playsinline preload="auto"></video>
        <div class="player-loader" id="playerLoader"></div>
        <div class="player-ui" id="playerUI">
            <div class="p-top-bar">
                <button class="p-icon-btn" onclick="closePlayerAction()">
                    <svg viewBox="0 0 24 24"><path d="M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z"/></svg>
                </button>
                <div class="p-title" id="playerTitle">Reproduciendo...</div>
            </div>
            <div class="p-center-area" id="centerArea">
                <button class="p-side-seek-btn" id="seekBackCenterBtn" onclick="event.stopPropagation(); seekSeconds(-10)">
                    <svg viewBox="0 0 24 24"><path d="M11 18V6l-8.5 6 8.5 6zm.5-6l8.5 6V6l-8.5 6z"/></svg>
                    <span>-10s</span>
                </button>
                <button class="p-center-icon" id="centerIcon" onclick="event.stopPropagation(); togglePlay()">
                    <svg id="c-icon-play" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
                    <svg id="c-icon-pause" style="display:none;" viewBox="0 0 24 24"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>
                </button>
                <button class="p-side-seek-btn" id="seekForwardCenterBtn" onclick="event.stopPropagation(); seekSeconds(10)">
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
                        <button class="p-icon-btn" id="playPauseBtn" onclick="event.stopPropagation(); togglePlay()">
                            <svg id="icon-play" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
                            <svg id="icon-pause" style="display:none;" viewBox="0 0 24 24"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>
                        </button>
                        <div class="p-time"><span id="timeCurrent">00:00</span> / <span id="timeTotal">00:00</span></div>
                    </div>
                    <div class="p-controls-right">
                        <button class="p-icon-btn" id="nextChapBtn" style="display:none;" onclick="event.stopPropagation(); playNext()">
                            <svg viewBox="0 0 24 24"><path d="M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z"/></svg>
                        </button>
                        <button class="p-res-btn" onclick="event.stopPropagation(); toggleResolution()" id="resBtn">16:9</button>
                        <button class="p-icon-btn" id="fullscreenBtn" onclick="event.stopPropagation(); toggleFullScreen()">
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
        let showingFavs = false;
        let currentPlaylist = [];
        let currentVideoIndex = -1;
        let heroInterval, hideUITimeout;
        
        // --- PREFERENCIAS DE REPRODUCTOR ---
        let playerPreference = localStorage.getItem('ry_player_pref') || 'internal';
        
        function toggleSettingsModal() {
            closeMenu();
            const modal = document.getElementById('settingsModal');
            document.querySelector(`input[name="playerPref"][value="${playerPreference}"]`).checked = true;
            modal.style.display = 'flex';
        }
        function closeSettingsModal() { document.getElementById('settingsModal').style.display = 'none'; }
        function saveSettings() {
            playerPreference = document.querySelector('input[name="playerPref"]:checked').value;
            localStorage.setItem('ry_player_pref', playerPreference);
            closeSettingsModal();
        }

        // --- PREVENCIÓN DE SUSPENSIÓN (WAKE LOCK) ---
        let wakeLock = null;
        async function requestWakeLock() {
            try {
                if ('wakeLock' in navigator) {
                    wakeLock = await navigator.wakeLock.request('screen');
                }
            } catch (err) { console.warn('Wake Lock no disponible', err); }
        }
        function releaseWakeLock() {
            if (wakeLock !== null) {
                wakeLock.release().then(() => wakeLock = null);
            }
        }
        document.addEventListener('visibilitychange', () => {
            if (wakeLock !== null && document.visibilityState === 'visible' && !video.paused) {
                requestWakeLock();
            }
        });


        const rowsContainer = document.getElementById('rowsContainer');
        const loader = document.getElementById('loader');
        const homeSection = document.getElementById('homeSection');
        const seriesSection = document.getElementById('seriesSection');
        const movieSection = document.getElementById('movieSection');
        const searchInput = document.getElementById('searchInput');
        const menuControls = document.getElementById('headerControls');

        function toggleMenu() { menuControls.classList.toggle('open'); }
        function closeMenu() { menuControls.classList.remove('open'); }

        function shuffleArray(array) {
            let arr = [...array];
            for (let i = arr.length - 1; i > 0; i--) {
                const j = Math.floor(Math.random() * (i + 1));
                [arr[i], arr[j]] = [arr[j], arr[i]];
            }
            return arr;
        }

        history.replaceState({view: 'home'}, '');
        window.addEventListener('popstate', (e) => {
            const view = e.state ? e.state.view : 'home';
            if (modal.classList.contains('show')) closePlayerUI(); 

            if (view === 'home') {
                seriesSection.style.display = 'none';
                movieSection.style.display = 'none';
                homeSection.style.display = 'block';
                fetchCatalog(false);
            } else if (view === 'series') {
                seriesSection.style.display = 'block';
                movieSection.style.display = 'none';
                homeSection.style.display = 'none';
            } else if (view === 'movie') {
                seriesSection.style.display = 'none';
                movieSection.style.display = 'block';
                homeSection.style.display = 'none';
            }
        });

        document.addEventListener('DOMContentLoaded', () => fetchCatalog(true));

        function fetchCatalog(initRender) {
            if(initRender) { rowsContainer.innerHTML = ''; loader.style.display = 'block'; }
            fetch(API + '/api/media').then(r => r.json()).then(data => {
                allMedia = data; 
                if(initRender) {
                    currentFiltered = shuffleArray(allMedia);
                    loader.style.display = 'none';
                    initHeroSlider();
                    renderCarousels();
                }
            }).catch(() => { if(initRender) loader.style.display = 'none'; });
        }

        function initHeroSlider() {
            const hero = document.getElementById('heroSlider');
            if (allMedia.length === 0) return;
            hero.style.display = 'block';
            let featured = shuffleArray(allMedia).slice(0, 5);
            hero.innerHTML = '';
            featured.forEach((item, idx) => {
                const imgUrl = item.image ? `${API}/img?path=${encodeURIComponent(item.image)}` : '';
                const slide = document.createElement('div');
                slide.className = `hero-slide ${idx === 0 ? 'active' : ''}`;
                slide.style.backgroundImage = imgUrl ? `url('${imgUrl}')` : 'none';
                slide.innerHTML = `<div class="hero-content"><h2 class="hero-title">${item.name}</h2><button class="hero-btn" onclick="playHeroItem('${encodeURIComponent(JSON.stringify(item))}')"><svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg> Ver Ahora</button></div>`;
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
            if (item.is_folder || item.type === 'series') openSeries(item); else openMovie(item);
        };

        function renderCarousels() {
            rowsContainer.innerHTML = '';
            if (currentFiltered.length === 0) return;
            const MAX_ROWS = 4, ITEMS_PER_ROW = 10;
            for (let i = 0; i < MAX_ROWS; i++) {
                const startIdx = i * ITEMS_PER_ROW;
                if (startIdx >= currentFiltered.length) break;
                const chunk = currentFiltered.slice(startIdx, startIdx + ITEMS_PER_ROW);
                const section = document.createElement('div');
                section.className = 'carousel-section';
                const title = document.createElement('h2');
                title.className = 'carousel-title';
                title.textContent = showingFavs ? `Mi Lista - Bloque ${i + 1}` : `Mix Recomendado ${i + 1}`;
                
                const track = document.createElement('div');
                track.className = 'carousel-track';
                chunk.forEach(item => track.appendChild(createCard(item)));
                section.appendChild(title);
                section.appendChild(track);
                rowsContainer.appendChild(section);
            }
        }

        searchInput.addEventListener('input', (e) => {
            const val = e.target.value.toLowerCase().trim();
            if(showingFavs) { showingFavs = false; document.getElementById('favToggleBtn').classList.remove('active'); }
            document.getElementById('heroSlider').style.display = val === '' ? 'block' : 'none';
            currentFiltered = val === '' ? shuffleArray(allMedia) : allMedia.filter(i => i.name.toLowerCase().includes(val));
            renderCarousels();
        });

        function toggleFavView() {
            showingFavs = !showingFavs;
            document.getElementById('favToggleBtn').classList.toggle('active');
            closeMenu();
            if (showingFavs) {
                currentFiltered = allMedia.filter(item => favorites.includes(item.folder || item.file));
            } else {
                searchInput.value = '';
                currentFiltered = shuffleArray(allMedia);
            }
            renderCarousels();
        }

        function toggleFavorite(e, id) {
            if(e) e.stopPropagation();
            const idx = favorites.indexOf(id);
            if (idx > -1) favorites.splice(idx, 1); else favorites.push(id);
            localStorage.setItem('ryflix_favs', JSON.stringify(favorites));
            
            if(e && e.currentTarget) e.currentTarget.classList.toggle('active');
            if (showingFavs) {
                currentFiltered = allMedia.filter(item => favorites.includes(item.folder || item.file));
                renderCarousels();
            }
        }

        function createCard(item) {
            const card = document.createElement('div'); 
            card.className = 'card';
            card.title = item.name;
            const itemId = item.folder || item.file;
            const isFav = favorites.includes(itemId);
            const imgUrl = item.image ? `${API}/img?path=${encodeURIComponent(item.image)}` : '';
            const posterHTML = item.image ? `<img src="${imgUrl}" loading="lazy">` : `<div class="poster-alt">${item.name.charAt(0)}</div>`;
            card.innerHTML = `<div class="poster">${posterHTML}</div><div class="fav-icon ${isFav ? 'active' : ''}" onclick="toggleFavorite(event, '${itemId}')"><svg viewBox="0 0 24 24"><path d="M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z"/></svg></div><div class="card-title">${item.name}</div>`;
            card.onclick = () => { closeMenu(); if (item.is_folder || item.type === 'series') openSeries(item); else openMovie(item); };
            return card;
        }

        // --- SECCIÓN PELÍCULA ---
        function openMovie(movie) {
            history.pushState({view: 'movie'}, '');
            homeSection.style.display = 'none';
            seriesSection.style.display = 'none';
            movieSection.style.display = 'block';
            window.scrollTo(0, 0);

            document.getElementById('movieTitle').textContent = movie.name;
            document.getElementById('movieSubtitle').textContent = `Disfruta de la película ${movie.name} en SD`;
            const imgUrl = movie.image ? `${API}/img?path=${encodeURIComponent(movie.image)}` : '';
            document.getElementById('movieHeroBg').style.backgroundImage = imgUrl ? `url('${imgUrl}')` : 'none';
            document.getElementById('moviePoster').src = imgUrl || '';
            document.getElementById('moviePoster').style.display = imgUrl ? 'block' : 'none';

            const movieId = movie.file;
            const isFav = favorites.includes(movieId);
            const favBtn = document.getElementById('movieFavBtn');
            favBtn.style.background = isFav ? 'rgba(118,255,3,0.2)' : 'rgba(255,255,255,0.08)';
            favBtn.style.color = isFav ? 'var(--lime)' : 'white';
            
            document.getElementById('moviePlayBtn').onclick = () => openPlayer(movie, [movie], 0);
            favBtn.onclick = () => { toggleFavorite(null, movieId); openMovie(movie); };

            const recContainer = document.getElementById('movieRecommendations');
            recContainer.innerHTML = '';
            
            let kw = movie.name.split(' ')[0].toLowerCase();
            let related = allMedia.filter(m => m.file !== movie.file && m.name.toLowerCase().includes(kw));
            let randoms = shuffleArray(allMedia.filter(m => m.file !== movie.file));

            if(related.length > 0) buildRow(recContainer, "Películas y Series Relacionadas", related);
            if(randoms.length > 0) buildRow(recContainer, "Otras Recomendaciones Aleatorias", randoms.slice(0, 10));
        }

        function buildRow(container, titleText, items) {
            const section = document.createElement('div'); section.className = 'carousel-section';
            const title = document.createElement('h2'); title.className = 'carousel-title'; title.textContent = titleText;
            const track = document.createElement('div'); track.className = 'carousel-track';
            items.forEach(item => track.appendChild(createCard(item)));
            section.appendChild(title); section.appendChild(track);
            container.appendChild(section);
        }

        // --- SECCIÓN SERIES ---
        let currentActiveSerie = null;
        function openSeries(serie) {
            currentActiveSerie = serie;
            history.pushState({view: 'series'}, '');
            homeSection.style.display = 'none';
            movieSection.style.display = 'none';
            seriesSection.style.display = 'block';
            window.scrollTo(0, 0);

            document.getElementById('seriesTitle').textContent = serie.name;
            const imgUrl = serie.image ? `${API}/img?path=${encodeURIComponent(serie.image)}` : '';
            document.getElementById('seriesHeroBg').style.backgroundImage = imgUrl ? `url('${imgUrl}')` : 'none';
            document.getElementById('seriesPoster').src = imgUrl || '';
            document.getElementById('seriesPoster').style.display = imgUrl ? 'block' : 'none';

            const serieId = serie.folder || serie.name;
            const isSerieFav = favorites.includes(serieId);
            const sFavBtn = document.getElementById('seriesFavBtn');
            sFavBtn.style.background = isSerieFav ? 'rgba(118,255,3,0.2)' : 'rgba(255,255,255,0.08)';
            sFavBtn.style.color = isSerieFav ? 'var(--lime)' : 'white';
            sFavBtn.onclick = () => { toggleFavorite(null, serieId); openSeries(serie); };

            const sList = document.getElementById('seriesList'); sList.innerHTML = '';
            document.getElementById('seriesLoader').style.display = 'block';

            fetch(`${API}/api/media?folder=${encodeURIComponent(serie.folder || serie.name)}`)
                .then(r => r.json()).then(chapters => {
                    document.getElementById('seriesLoader').style.display = 'none';
                    document.getElementById('seriesMeta').textContent = `Serie • ${chapters.length} Episodios`;
                    
                    let resumeIndex = 0; 
                    let hasStarted = false;

                    chapters.forEach((chap, idx) => {
                        const chapId = chap.folder + '_' + chap.file;
                        const meta = JSON.parse(localStorage.getItem('ry_meta_' + chapId)) || {t: 0, d: 0};
                        
                        let pct = 0; let status = "Inicio";
                        if (meta.d > 0) {
                            pct = (meta.t / meta.d) * 100;
                            if(pct > 90) { status = "Completo"; pct = 100; } 
                            else if(pct > 5) { status = "Mitad"; if(!hasStarted) { resumeIndex = idx; hasStarted = true; } }
                        }

                        const row = document.createElement('div'); 
                        row.className = 'episode-row';
                        
                        const thumbHtml = imgUrl ? `<img src="${imgUrl}" loading="lazy">` : '';
                        row.innerHTML = `
                            <div class="ep-thumb">${thumbHtml}<svg class="ep-thumb-icon" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg></div>
                            <div class="ep-info">
                                <div class="ep-title-wrapper"><div class="ep-title">${chap.name}</div></div>
                                <div class="ep-num">Episodio ${idx + 1}</div>
                                <div class="ep-progress-bar"><div class="ep-progress-fill" style="width:${pct}%"></div></div>
                                <div class="ep-progress-text">${status}</div>
                            </div>
                        `;

                        let pressTimer;
                        const startMarquee = () => { pressTimer = setTimeout(() => { row.querySelector('.ep-title').classList.add('marquee-active'); }, 500); };
                        const stopMarquee = () => { clearTimeout(pressTimer); row.querySelector('.ep-title').classList.remove('marquee-active'); };
                        
                        row.addEventListener('touchstart', startMarquee, {passive: true});
                        row.addEventListener('touchend', stopMarquee);
                        row.addEventListener('mousedown', startMarquee);
                        row.addEventListener('mouseup', stopMarquee);
                        row.addEventListener('mouseleave', stopMarquee);

                        row.addEventListener('click', () => { openPlayer(chap, chapters, idx); });

                        sList.appendChild(row);
                    });

                    const startText = document.getElementById('seriesStartText');
                    startText.textContent = hasStarted ? "CONTINUAR VIENDO" : "EMPEZAR SELECCIÓN";
                    document.getElementById('seriesStartBtn').onclick = () => { if(chapters.length > 0) openPlayer(chapters[resumeIndex], chapters, resumeIndex); };
                });
        }

        function goHomeAction() {
            if (!showingFavs && searchInput.value === '') { currentFiltered = shuffleArray(allMedia); renderCarousels(); }
            history.pushState({view: 'home'}, '');
            seriesSection.style.display = 'none';
            movieSection.style.display = 'none';
            homeSection.style.display = 'block';
            window.scrollTo(0, 0);
        }

        // --- REPRODUCTOR ---
        const video = document.getElementById('mainVideo');
        const modal = document.getElementById('playerModal');
        const playerUI = document.getElementById('playerUI');
        const playerLoader = document.getElementById('playerLoader');
        let currentVideoId = '';
        let autoplayFired = false;

        const iconPlay = document.getElementById('icon-play');
        const iconPause = document.getElementById('icon-pause');
        const cIconPlay = document.getElementById('c-icon-play');
        const cIconPause = document.getElementById('c-icon-pause');
        const timelineCont = document.getElementById('timelineContainer');
        const timeProg = document.getElementById('timelineProgress');
        const timeThumb = document.getElementById('timelineThumb');
        const timeCurrent = document.getElementById('timeCurrent');
        const timeTotal = document.getElementById('timeTotal');
        const nextChapBtn = document.getElementById('nextChapBtn');

        window.togglePlayerUI = function(e) {
            if (e.target.closest('button') || e.target.closest('.p-timeline-container') || e.target.closest('.p-center-icon')) return;
            playerUI.classList.toggle('hidden');
            if (!playerUI.classList.contains('hidden')) resetUIActivity();
        };

        function openPlayer(videoItem, playlist, index) {
            let vUrl = `${API}/stream?file=${encodeURIComponent(videoItem.file)}`;
            if (videoItem.folder) vUrl += `&folder=${encodeURIComponent(videoItem.folder)}`;

            // COMPROBAR PREFERENCIA DE REPRODUCTOR
            if (playerPreference === 'external') {
                // Formatear url para intent nativo de Android
                let cleanUrl = vUrl.replace(/^https?:\\/\\//, '');
                let protocol = window.location.protocol.replace(':', '');
                let intentUrl = `intent://${cleanUrl}#Intent;action=android.intent.action.VIEW;type=video/mp4;scheme=${protocol};end;`;
                
                // Intentar lanzar el selector de aplicaciones del sistema
                window.location.href = intentUrl;
                return; // Detenemos aquí, no abrimos el reproductor web
            }

            // Flujo normal: Reproductor Web Interno
            history.pushState({view: 'player'}, '');
            currentPlaylist = playlist; currentVideoIndex = index;
            currentVideoId = videoItem.folder ? `${videoItem.folder}_${videoItem.file}` : videoItem.file;
            autoplayFired = false;

            document.getElementById('playerTitle').textContent = videoItem.name;
            nextChapBtn.style.display = (index + 1 < playlist.length) ? 'flex' : 'none';

            video.src = vUrl;
            modal.classList.add('show');
            document.body.style.overflow = 'hidden';
            playerLoader.classList.add('active'); 
            resetUIActivity();

            video.onloadedmetadata = () => {
                const meta = JSON.parse(localStorage.getItem('ry_meta_' + currentVideoId));
                if (meta && meta.t) {
                    if ((meta.t / video.duration) < 0.9) video.currentTime = parseFloat(meta.t);
                }
                timeTotal.textContent = formatTime(video.duration);
                
                video.play().then(() => { 
                    updatePlaybackIcons(true); 
                    requestWakeLock(); // Activar mantener pantalla encendida
                }).catch(() => { updatePlaybackIcons(false); });
            };
        }

        video.addEventListener('waiting', () => playerLoader.classList.add('active'));
        video.addEventListener('playing', () => { playerLoader.classList.remove('active'); requestWakeLock(); });
        video.addEventListener('canplay', () => playerLoader.classList.remove('active'));
        video.addEventListener('pause', () => releaseWakeLock());

        function closePlayerAction() { history.back(); }
        
        function closePlayerUI() {
            modal.classList.remove('show');
            video.pause(); video.removeAttribute('src'); video.load();
            document.body.style.overflow = 'auto';
            clearTimeout(hideUITimeout);
            releaseWakeLock(); // Liberar pantalla al cerrar
        }

        function resetUIActivity() {
            playerUI.classList.remove('hidden');
            clearTimeout(hideUITimeout);
            if (!video.paused) { hideUITimeout = setTimeout(() => { playerUI.classList.add('hidden'); }, 3000); }
        }

        playerUI.addEventListener('mousemove', resetUIActivity);
        playerUI.addEventListener('touchmove', resetUIActivity);

        window.togglePlay = function() {
            if (video.paused) {
                video.play();
                updatePlaybackIcons(true);
                resetUIActivity();
            } else {
                video.pause();
                updatePlaybackIcons(false);
                playerUI.classList.remove('hidden'); 
                clearTimeout(hideUITimeout);
            }
        };

        function updatePlaybackIcons(isPlaying) {
            if(isPlaying) {
                iconPlay.style.display = 'none'; iconPause.style.display = 'block';
                cIconPlay.style.display = 'none'; cIconPause.style.display = 'block';
            } else {
                iconPlay.style.display = 'block'; iconPause.style.display = 'none';
                cIconPlay.style.display = 'block'; cIconPause.style.display = 'none';
            }
        }

        function formatTime(sec) {
            if(isNaN(sec)) return "00:00";
            const h = Math.floor(sec / 3600);
            const m = Math.floor((sec % 3600) / 60);
            const s = Math.floor(sec % 60);
            return h > 0 ? `${h}:${m < 10 ? '0' : ''}${m}:${s < 10 ? '0' : ''}${s}` : `${m}:${s < 10 ? '0' : ''}${s}`;
        }

        video.addEventListener('timeupdate', () => {
            if (!video.duration) return;
            timeCurrent.textContent = formatTime(video.currentTime);
            const percent = (video.currentTime / video.duration) * 100;
            timeProg.style.width = `${percent}%`; timeThumb.style.left = `${percent}%`;
            
            if (video.currentTime > 1) playerLoader.classList.remove('active');

            if (video.currentTime > 5 && !video.paused) {
                localStorage.setItem('ry_meta_' + currentVideoId, JSON.stringify({t: video.currentTime, d: video.duration}));
            }

            if (!autoplayFired && !video.paused && nextChapBtn.style.display !== 'none' && (video.duration - video.currentTime) <= 5) {
                autoplayFired = true;
                playNext();
            }
        });

        timelineCont.addEventListener('click', (e) => {
            e.stopPropagation();
            const rect = timelineCont.getBoundingClientRect();
            const pos = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
            video.currentTime = pos * video.duration; resetUIActivity();
        });

        function seekSeconds(seconds) { video.currentTime = Math.max(0, Math.min(video.duration, video.currentTime + seconds)); resetUIActivity(); }

        window.playNext = function() {
            if(video.duration) localStorage.setItem('ry_meta_' + currentVideoId, JSON.stringify({t: video.duration, d: video.duration}));
            
            if (currentVideoIndex + 1 < currentPlaylist.length) {
                history.replaceState({view: 'player'}, ''); closePlayerUI();
                openPlayer(currentPlaylist[currentVideoIndex + 1], currentPlaylist, currentVideoIndex + 1);
            } else { closePlayerAction(); }
        }
        video.addEventListener('ended', () => { if(!autoplayFired) playNext(); });

        let isFit16_9 = false;
        window.toggleResolution = function() {
            isFit16_9 = !isFit16_9; video.className = isFit16_9 ? 'fit-16-9' : '';
            document.getElementById('resBtn').textContent = isFit16_9 ? 'Orig' : '16:9'; resetUIActivity();
        }

        window.toggleFullScreen = function() {
            if (!document.fullscreenElement) {
                if (modal.requestFullscreen) modal.requestFullscreen();
            } else { if (document.exitFullscreen) document.exitFullscreen(); }
            resetUIActivity();
        }
    </script>
</body>
</html>""")

if __name__ == '__main__':
    if not os.path.exists(MEDIA_DIR): os.makedirs(MEDIA_DIR)
    generate_html_files()

    httpd = ThreadingHTTPServer(('0.0.0.0', PORT), RyflixHandler)
    print(f"Servidor MULTIHILO activo en el puerto {PORT}")
    print(f"Página de Descarga APK: http://localhost:{PORT}/index.html")
    print(f"Página Web de Ryflix:   http://localhost:{PORT}/server.html")
    httpd.serve_forever()
