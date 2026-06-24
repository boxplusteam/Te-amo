import os
import json
import shutil
import re
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# --- CONFIGURACIÓN ---
PORT = 8000
MEDIA_DIR = "storage/downloads/flix"

# --- ORDENAMIENTO NATURAL INTELIGENTE ---
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
            return self.send_error(404, "Archivo APK no encontrado")

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

        for item in sorted(os.listdir(MEDIA_DIR), key=natural_sort_key):
            path = os.path.join(MEDIA_DIR, item)
            name = item.replace('_', ' ').replace('-', ' ').title()

            if os.path.isfile(path) and item.lower().endswith(('.mp4', '.mkv', '.avi', '.webm')):
                name_clean = name.rsplit('.', 1)[0]
                img = self.find_image_for(item)
                media.append({'name': name_clean, 'file': item, 'type': 'movie', 'image': img})

            elif os.path.isdir(path):
                vids = sorted([f for f in os.listdir(path) if f.lower().endswith(('.mp4', '.mkv', '.avi', '.webm'))], key=natural_sort_key)
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
                vids = sorted([f for f in os.listdir(path) if f.lower().endswith(('.mp4', '.mkv', '.avi', '.webm'))], key=natural_sort_key)
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

        mime_type = 'video/mp4'
        if path.lower().endswith('.webm'):
            mime_type = 'video/webm'

        if range_header:
            byte1, byte2 = 0, None
            match = re.search(r'bytes=(\d+)-(\d*)', range_header)
            if match:
                byte1 = int(match.group(1))
                if match.group(2):
                    byte2 = int(match.group(2))

            byte2 = byte2 if byte2 is not None else file_size - 1
            length = byte2 - byte1 + 1

            self.send_response(206)
            self.send_header('Content-Type', mime_type)
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
                    except (ConnectionError, BrokenPipeError):
                        break
                    except Exception:
                        break
                    bytes_to_read -= len(chunk)
        else:
            self.send_response(200)
            self.send_header('Content-Type', mime_type)
            self.send_header('Content-Length', str(file_size))
            self.send_header('Accept-Ranges', 'bytes')
            self.send_cors_headers()
            self.end_headers()
            try:
                with open(path, 'rb') as f:
                    shutil.copyfileobj(f, self.wfile, length=1024*1024)
            except (ConnectionError, BrokenPipeError):
                pass

def generate_html_files():
    # --- INDEX / APK DOWNLOAD PAGE ---
    if not os.path.exists('index.html'):
        with open('index.html', 'w', encoding='utf-8') as f:
            f.write("""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Instalar App</title>
    <style>
        :root {
            --bg: #0b0c10; --accent: #8a2be2; --text: #ffffff;
            --font-stack: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        }
        body { margin: 0; background: var(--bg); color: var(--text); font-family: var(--font-stack); display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 100vh; text-align: center; padding: 20px; box-sizing: border-box; }
        .subtitle { color: #8f98b2; margin-bottom: 40px; font-size: clamp(0.9rem, 4vw, 1.2rem); max-width: 90%; }
        .download-btn { display: inline-flex; align-items: center; gap: 12px; background: var(--accent); color: #fff; text-decoration: none; padding: 16px 32px; border-radius: 12px; font-weight: 700; font-size: clamp(1rem, 3vw, 1.1rem); box-shadow: 0 6px 20px rgba(138, 43, 226, 0.4); transition: transform 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275), box-shadow 0.3s; width: 100%; max-width: 300px; justify-content: center; }
        .download-btn:hover { transform: scale(1.05) translateY(-2px); box-shadow: 0 10px 25px rgba(138, 43, 226, 0.6); }
        .download-btn:active { transform: scale(0.96); }
        .download-btn svg { width: 22px; height: 22px; fill: #fff; }
        .web-link { margin-top: 35px; color: #d182ff; text-decoration: none; font-weight: 600; font-size: 1rem; transition: color 0.3s; }
        .web-link:hover { color: #fff; }
    </style>
</head>
<body>
    <div style="width: 80px; height: 80px; background: linear-gradient(135deg, var(--accent), #d122e3); border-radius: 20px; margin-bottom: 20px; display: flex; align-items: center; justify-content: center; box-shadow: 0 10px 30px rgba(138,43,226,0.5);">
        <svg viewBox="0 0 24 24" width="40" height="40" fill="#fff"><path d="M8 5v14l11-7z"/></svg>
    </div>
    <div class="subtitle">Tu servidor de streaming local definitivo</div>
    <a href="/download_apk" class="download-btn">
        <svg viewBox="0 0 24 24"><path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/></svg> DESCARGAR APK
    </a>
    <a href="/server.html" class="web-link">Entrar desde el navegador →</a>
</body>
</html>""")

    # --- SERVER / PLATAFORMA PREMIUM ---
    with open('server.html', 'w', encoding='utf-8') as f:
        f.write("""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <title>Plataforma Streaming</title>
    <style>
        :root {
            --bg: #0b0c10;
            --surface: #141622;
            --surface-card: #1c1e2e;
            --accent: #8a2be2;
            --accent-glow: rgba(138, 43, 226, 0.4);
            --text: #f5f6f8;
            --text-muted: #7e8b9b;
            --radius: 12px;
            --px: clamp(16px, 5vw, 40px);
            --font-stack: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        }

        * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; font-family: var(--font-stack); user-select: none; margin: 0; padding: 0; }
        body { background: var(--bg); color: var(--text); overflow-x: hidden; padding-bottom: calc(env(safe-area-inset-bottom, 20px) + 90px); }

        header {
            padding: calc(env(safe-area-inset-top, 15px) + 15px) var(--px) 15px;
            position: fixed; top: 0; left: 0; right: 0;
            background: linear-gradient(to bottom, rgba(11,12,16,0.98), rgba(11,12,16,0));
            z-index: 90; pointer-events: none; height: 60px;
        }

        .bottom-nav {
            position: fixed; bottom: 0; left: 0; right: 0;
            background: rgba(20, 22, 34, 0.85); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
            display: flex; justify-content: space-around; align-items: center;
            padding: 12px 10px calc(env(safe-area-inset-bottom, 15px) + 12px);
            z-index: 100; border-top: 1px solid rgba(255,255,255,0.06);
            box-shadow: 0 -10px 30px rgba(0,0,0,0.5);
        }
        .nav-item {
            background: transparent; border: none; color: var(--text-muted);
            display: flex; flex-direction: column; align-items: center; gap: 6px;
            cursor: pointer; transition: all 0.3s ease; width: 50%;
        }
        .nav-item svg { width: 24px; height: 24px; fill: currentColor; transition: transform 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275); }
        .nav-item span { font-size: 0.7rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; }
        .nav-item.active { color: var(--accent); }
        .nav-item.active svg { transform: scale(1.2); filter: drop-shadow(0 4px 8px var(--accent-glow)); }

        .main-view { display: none; margin-top: clamp(60px, 8vh, 80px); animation: fadeIn 0.4s cubic-bezier(0.1, 0.9, 0.2, 1); width: 100%; min-height: calc(100vh - 100px); }
        .main-view.active { display: block; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(15px); } to { opacity: 1; transform: translateY(0); } }

        .search-container { padding: 0 var(--px); margin-bottom: 25px; width: 100%; position: relative; z-index: 50; }
        .search-box { display: flex; align-items: center; background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); border-radius: 16px; padding: 14px 20px; width: 100%; transition: all 0.3s ease; backdrop-filter: blur(10px); }
        .search-box:focus-within { border-color: var(--accent); background: rgba(255,255,255,0.08); box-shadow: 0 4px 20px var(--accent-glow); transform: translateY(-2px); }
        .search-box input { background: transparent; border: none; color: white; outline: none; width: 100%; font-size: 1.05rem; margin-left: 12px; }
        .search-box input::placeholder { color: var(--text-muted); }
        .search-box svg { width: 22px; height: 22px; fill: var(--text-muted); transition: fill 0.3s; }
        .search-box:focus-within svg { fill: var(--accent); }

        .hero-slider { position: relative; margin: 0 var(--px) 35px; height: clamp(200px, 45vw, 400px); border-radius: 16px; overflow: hidden; box-shadow: 0 15px 30px rgba(0,0,0,0.6); background: var(--surface); }
        .hero-slide { position: absolute; inset: 0; opacity: 0; transition: opacity 0.8s ease; background-size: cover; background-position: center 20%; display: flex; flex-direction: column; justify-content: flex-end; }
        .hero-slide.active { opacity: 1; z-index: 2; }
        .hero-slide::after { content: ''; position: absolute; inset: 0; background: linear-gradient(0deg, var(--bg) 5%, rgba(11,12,16,0.2) 60%, transparent 100%); z-index: 1; }
        .hero-content { position: relative; z-index: 3; padding: clamp(20px, 5vw, 35px); text-align: left; animation: slideUpFade 0.6s ease forwards; }
        @keyframes slideUpFade { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }

        .hero-title { font-size: clamp(1.4rem, 4vw, 2.5rem); font-weight: 900; margin-bottom: 12px; text-shadow: 0 2px 10px rgba(0,0,0,0.9); }
        .hero-btn { display: inline-flex; align-items: center; gap: 8px; background: #fff; color: #000; border: none; padding: 10px 24px; border-radius: 30px; font-weight: 800; font-size: 0.9rem; cursor: pointer; transition: all 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275); }
        .hero-btn svg { width: 18px; height: 18px; fill: #000; transition: transform 0.3s; }
        .hero-btn:hover { transform: scale(1.05); box-shadow: 0 8px 20px rgba(255,255,255,0.3); }
        .hero-btn:active { transform: scale(0.95); }

        .carousel-title { font-size: clamp(1.15rem, 3.5vw, 1.4rem); margin: 0 var(--px) 14px; font-weight: 800; color: #fff; }
        .carousel-track { display: flex; overflow-x: auto; gap: clamp(12px, 3vw, 18px); padding: 5px var(--px) 25px; scroll-snap-type: x mandatory; }
        .carousel-track::-webkit-scrollbar { display: none; }

        .card {
            flex: 0 0 clamp(130px, 35vw, 160px) !important;
            width: clamp(130px, 35vw, 160px) !important;
            max-width: clamp(130px, 35vw, 160px) !important;
            scroll-snap-align: start;
            position: relative;
            cursor: pointer;
            transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
            display: flex;
            flex-direction: column;
        }
        .card:hover { transform: translateY(-6px) scale(1.03); z-index: 5; }
        .card:active { transform: scale(0.96); }

        .poster { width: 100%; aspect-ratio: 2 / 3 !important; background: var(--surface-card); border-radius: 12px; overflow: hidden; position: relative; box-shadow: 0 8px 20px rgba(0,0,0,0.4); border: 1px solid rgba(255,255,255,0.05); transition: box-shadow 0.3s ease; }
        .card:hover .poster { box-shadow: 0 12px 28px var(--accent-glow); border-color: rgba(138, 43, 226, 0.3); }
        .poster img { width: 100% !important; height: 100% !important; object-fit: cover !important; display: block; transition: transform 0.5s ease; }
        .card:hover .poster img { transform: scale(1.08); }

        .poster-alt { font-size: 2.2rem; font-weight: 900; color: var(--accent); height: 100%; width: 100%; display: flex; align-items: center; justify-content: center; background: linear-gradient(135deg, #141622, #1c1e2e); text-transform: uppercase; }
        .card-title { padding: 10px 2px 0; font-size: clamp(0.85rem, 2.5vw, 0.95rem); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-weight: 600; color: #f5f6f8; transition: color 0.3s; }
        .card:hover .card-title { color: var(--accent); }

        .app-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(clamp(130px, 35vw, 160px), 1fr));
            gap: clamp(12px, 3vw, 20px);
            padding: var(--px);
            align-items: start;
            justify-items: center;
        }
        .empty-state { text-align: center; padding: 60px 20px; color: var(--text-muted); font-size: 1rem; width: 100%; grid-column: 1/-1; display: flex; flex-direction: column; align-items: center; gap: 15px; animation: fadeIn 0.5s ease; }
        .loader-more { width: 100%; text-align: center; padding: 20px; color: var(--text-muted); font-size: 0.9rem; position: relative; overflow: hidden; }

        #movieSection, #seriesSection { display: none; min-height: 100vh; background: var(--bg); position: relative; width: 100%; padding-bottom: 30px; animation: fadeIn 0.4s ease; }
        .detail-backdrop { position: absolute; top: 0; left: 0; width: 100%; height: clamp(350px, 60vh, 550px); background-size: cover; background-position: center top; z-index: 0; opacity: 0.5; mask-image: linear-gradient(180deg, black 40%, transparent 100%); -webkit-mask-image: linear-gradient(180deg, black 40%, transparent 100%); filter: saturate(1.2) blur(2px); transition: opacity 0.5s ease; }
        .detail-content { position: relative; z-index: 2; padding: clamp(220px, 45vh, 400px) var(--px) 0; display: flex; flex-direction: column; gap: 20px; max-width: 1000px; margin: 0 auto; animation: slideUpFade 0.6s cubic-bezier(0.1, 0.9, 0.2, 1); }
        .detail-header-row { display: flex; gap: clamp(15px, 4vw, 30px); align-items: flex-end; margin-bottom: 20px; }
        .detail-poster { width: clamp(110px, 30vw, 190px); aspect-ratio: 2/3 !important; border-radius: 12px; object-fit: cover !important; box-shadow: 0 15px 35px rgba(0,0,0,0.8); border: 2px solid rgba(255,255,255,0.1); flex-shrink: 0; background: var(--surface); transition: transform 0.4s ease; }
        .detail-poster:hover { transform: scale(1.02); }
        .detail-info { display: flex; flex-direction: column; justify-content: flex-end; gap: 10px; }
        .detail-title { font-size: clamp(1.8rem, 6vw, 3.5rem); font-weight: 900; line-height: 1.1; text-shadow: 0 4px 20px rgba(0,0,0,0.9); }

        .detail-actions { display: flex; align-items: center; gap: 15px; margin-top: 10px; flex-wrap: wrap; }
        .btn-play-primary { flex: 1; min-width: 200px; display: inline-flex; align-items: center; justify-content: center; gap: 12px; background: linear-gradient(135deg, var(--accent), #d122e3); color: #fff; border: none; padding: 16px 32px; border-radius: 14px; font-weight: 800; font-size: 1.05rem; cursor: pointer; box-shadow: 0 8px 25px var(--accent-glow); transition: all 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275); }
        .btn-play-primary:hover { transform: scale(1.03) translateY(-2px); box-shadow: 0 12px 30px rgba(138,43,226,0.6); }
        .btn-play-primary:active { transform: scale(0.96); }
        .btn-play-primary svg { width: 24px; height: 24px; fill: currentColor; transition: transform 0.3s; }
        .btn-play-primary:hover svg { transform: translateX(3px); }

        .chapters-wrapper { margin-top: 35px; width: 100%; max-width: 1000px; margin-left: auto; margin-right: auto; padding: 0 var(--px); animation: fadeIn 0.8s ease; }
        .chapters-header { font-size: 1.3rem; font-weight: 800; margin-bottom: 20px; color: #fff; display: flex; justify-content: space-between; align-items: center; }
        .ep-count { font-size: 0.9rem; color: var(--text-muted); font-weight: 600; }
        .chapters-grid { display: flex; flex-direction: column; gap: 16px; }

        .chapter-card { display: flex; flex-direction: row; gap: clamp(12px, 4vw, 20px); padding: 12px; background: rgba(255,255,255,0.03); border-radius: 14px; align-items: center; cursor: pointer; border: 1px solid rgba(255,255,255,0.02); transition: all 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275); }
        .chapter-card:hover { transform: translateX(8px); background: rgba(255,255,255,0.08); border-color: rgba(138,43,226,0.2); box-shadow: 0 8px 20px rgba(0,0,0,0.3); }
        .chapter-card:active { transform: scale(0.98); }

        .ch-thumb-box { width: clamp(130px, 35vw, 220px); aspect-ratio: 16 / 9; background: #000; border-radius: 10px; overflow: hidden; position: relative; flex-shrink: 0; box-shadow: 0 4px 12px rgba(0,0,0,0.4); }
        .ch-thumb-box img { width: 100%; height: 100%; object-fit: cover !important; opacity: 0.6; display: block; transition: all 0.5s ease; }
        .chapter-card:hover .ch-thumb-box img { opacity: 0.9; transform: scale(1.05); }
        .ch-play-overlay { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; background: rgba(0,0,0,0.3); border: 2px solid transparent; transition: all 0.3s ease; border-radius: 10px; }
        .chapter-card:hover .ch-play-overlay { border-color: rgba(138,43,226,0.5); background: rgba(138,43,226,0.1); }
        .ch-play-overlay svg { width: 32px; height: 32px; fill: #fff; filter: drop-shadow(0 2px 5px rgba(0,0,0,0.8)); transition: transform 0.3s; }
        .chapter-card:hover .ch-play-overlay svg { transform: scale(1.15); }

        .ch-details { flex: 1; min-width: 0; display: flex; flex-direction: column; justify-content: center; }
        .ch-ep-num { font-size: 0.8rem; color: var(--accent); font-weight: 800; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 4px; transition: color 0.3s; }
        .chapter-card:hover .ch-ep-num { color: #d182ff; }
        .ch-title { font-size: clamp(0.95rem, 2.8vw, 1.15rem); font-weight: 700; line-height: 1.3; margin-bottom: 8px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; color: #fff; }

        .ch-progress-container { width: 100%; height: 4px; background: rgba(255,255,255,0.1); border-radius: 4px; overflow: hidden; margin-top: auto; }
        .ch-progress-bar { height: 100%; background: var(--accent); width: 0%; box-shadow: 0 0 10px var(--accent); transition: width 0.3s ease; }

        .player-fullscreen { position: fixed; inset: 0; background: #000; z-index: 999999; display: none; flex-direction: column; width: 100vw; height: 100vh; animation: fadeIn 0.3s ease; }
        .player-fullscreen.show { display: flex; }
        video { width: 100%; height: 100%; background: #000; object-fit: contain; }

        .loader-spinner { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); width: 50px; height: 50px; border: 4px solid rgba(255,255,255,0.1); border-top-color: var(--accent); border-radius: 50%; animation: spin 0.8s linear infinite; display: none; z-index: 11; }
        .loader-spinner.active { display: block; }
        @keyframes spin { to { transform: translate(-50%, -50%) rotate(360deg); } }

        .p-ui { position: absolute; inset: 0; display: flex; flex-direction: column; justify-content: space-between; z-index: 12; background: rgba(0,0,0,0.55); transition: opacity 0.4s ease; }
        .p-ui.hidden { opacity: 0; pointer-events: none; }

        .p-top-bar { padding: calc(env(safe-area-inset-top, 15px) + 12px) var(--px) 20px; display: flex; align-items: center; gap: 16px; background: linear-gradient(to bottom, rgba(0,0,0,0.85), transparent); }
        .p-title-display { font-weight: 700; font-size: clamp(1rem, 3vw, 1.3rem); text-shadow: 0 2px 6px #000; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; width: 100%; color: #fff; }

        .p-center-controls { flex: 1; display: flex; align-items: center; justify-content: center; gap: clamp(25px, 10vw, 60px); }
        .p-circ-btn { background: rgba(255,255,255,0.1); border: none; width: clamp(54px, 12vw, 68px); height: clamp(54px, 12vw, 68px); border-radius: 50%; display: flex; align-items: center; justify-content: center; cursor: pointer; color: white; backdrop-filter: blur(10px); transition: all 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275); }
        .p-circ-btn:hover { background: rgba(255,255,255,0.2); transform: scale(1.1); }
        .p-circ-btn:active { transform: scale(0.9); }
        .p-circ-btn.big { background: var(--accent); color: white; width: clamp(75px, 16vw, 95px); height: clamp(75px, 16vw, 95px); box-shadow: 0 5px 20px var(--accent-glow); }
        .p-circ-btn.big:hover { box-shadow: 0 8px 30px rgba(138,43,226,0.6); transform: scale(1.1); }
        .p-circ-btn svg { width: clamp(28px, 6vw, 36px); height: clamp(28px, 6vw, 36px); fill: currentColor; }

        .p-bottom-bar { padding: 20px var(--px) calc(env(safe-area-inset-bottom, 20px) + 20px); background: linear-gradient(to top, rgba(0,0,0,0.85), transparent); display: flex; flex-direction: column; gap: 16px; width: 100%; }
        .p-timeline-box { width: 100%; height: 32px; display: flex; align-items: center; position: relative; cursor: pointer; }
        .p-rail { width: 100%; height: 6px; background: rgba(255,255,255,0.25); position: relative; border-radius: 3px; transition: height 0.2s; }
        .p-timeline-box:hover .p-rail { height: 8px; }
        .p-fill { height: 100%; background: var(--accent); width: 0%; position: absolute; border-radius: 3px; box-shadow: 0 0 10px var(--accent); transition: width 0.1s linear; }
        .p-bullet { width: 18px; height: 18px; background: #fff; position: absolute; top: 50%; transform: translate(-50%, -50%); left: 0%; border-radius: 50%; box-shadow: 0 2px 6px rgba(0,0,0,0.6); transition: transform 0.2s; }
        .p-timeline-box:hover .p-bullet { transform: translate(-50%, -50%) scale(1.3); }

        .p-flex-row { display: flex; justify-content: space-between; align-items: center; width: 100%; }
        .p-timestamp { font-size: clamp(0.85rem, 3vw, 1rem); font-weight: 600; text-shadow: 0 1px 3px #000; color: #e1e3e6; letter-spacing: 0.5px; }
        .p-actions-group { display: flex; gap: clamp(16px, 4vw, 26px); align-items: center; }
        .p-flat-btn { background: transparent; border: none; color: #fff; display: flex; align-items: center; justify-content: center; cursor: pointer; transition: all 0.3s; }
        .p-flat-btn:hover { color: var(--accent); transform: scale(1.1); }
        .p-flat-btn svg { width: clamp(26px, 5vw, 32px); height: clamp(26px, 5vw, 32px); fill: currentColor; filter: drop-shadow(0 2px 4px rgba(0,0,0,0.5)); }

        @media (max-width: 767px) {
            .detail-header-row { flex-direction: column; align-items: center; text-align: center; gap: 15px; }
            .detail-actions { justify-content: center; }
            .btn-play-primary { width: 100%; }
        }
        @media (min-width: 1024px) {
            .bottom-nav { top: 0; left: 0; bottom: auto; width: auto; padding: 15px var(--px); background: transparent; border: none; box-shadow: none; justify-content: flex-end; gap: 30px; }
            .nav-item { flex-direction: row; width: auto; }
            .nav-item span { font-size: 0.9rem; }
            body { padding-bottom: 0; }
        }
    </style>
</head>
<body>

    <header></header>
    <nav class="bottom-nav">
        <button class="nav-item active" id="tab-home" onclick="navigate('home')">
            <svg viewBox="0 0 24 24"><path d="M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z"/></svg><span>Inicio</span>
        </button>
        <button class="nav-item" id="tab-catalog" onclick="navigate('catalog')">
            <svg viewBox="0 0 24 24"><path d="M4 6H2v14c0 1.1.9 2 2 2h14v-2H4V6zm16-4H8c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm-1 9h-4v4h-2v-4H9V9h4V5h2v4h4v2z"/></svg><span>Catálogo</span>
        </button>
    </nav>

    <div id="view-home" class="main-view active">
        <div class="search-container">
            <div class="search-box">
                <svg viewBox="0 0 24 24"><path d="M15.5 14h-.79l-.28-.27C15.41 12.59 16 11.11 16 9.5 16 5.91 13.09 3 9.5 3S3 5.91 3 9.5 5.91 16 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 14z"/></svg>
                <input type="text" id="searchInput" placeholder="Buscar contenido...">
            </div>
        </div>
        <div class="hero-slider" id="heroSlider"></div>
        <div id="rowsContainer"></div>
    </div>

    <div id="view-catalog" class="main-view">
        <h2 class="carousel-title" style="font-size: clamp(1.6rem, 5vw, 2rem); margin-bottom: 5px;">Todo el Catálogo</h2>
        <p style="color: var(--text-muted); margin: 0 var(--px) 25px; font-size: 0.95rem;">Explora todo nuestro contenido.</p>
        <div class="app-grid" id="catalogGrid"></div>
        <div class="loader-more" id="catalogSentinel">Cargando más...</div>
    </div>

    <div id="movieSection">
        <div class="detail-backdrop" id="movieHeroBg"></div>
        <div class="detail-content">
            <div class="detail-header-row">
                <img class="detail-poster" id="moviePoster" src="" alt="Poster">
                <div class="detail-info">
                    <h1 class="detail-title" id="movieTitle">Título Película</h1>
                    <div class="detail-actions">
                        <button class="btn-play-primary" id="moviePlayBtn">
                            <svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg> REPRODUCIR
                        </button>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <div id="seriesSection">
        <div class="detail-backdrop" id="seriesHeroBg"></div>
        <div class="detail-content">
            <div class="detail-header-row">
                <img class="detail-poster" id="seriesPoster" src="" alt="Poster">
                <div class="detail-info">
                    <h1 class="detail-title" id="seriesTitle">Título de la Serie</h1>
                    <div class="detail-actions">
                        <button class="btn-play-primary" id="seriesPlayFirstBtn">
                            <svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg> VER EPISODIO 1
                        </button>
                    </div>
                </div>
            </div>
        </div>

        <div class="chapters-wrapper">
            <div class="chapters-header">
                Episodios <span class="ep-count" id="seriesMeta">0 Episodios</span>
            </div>
            <div class="chapters-grid" id="chaptersContainer"></div>
        </div>
    </div>

    <div class="player-fullscreen" id="playerModal" onclick="triggerPlayerUI(event)">
        <video id="mainVideo" playsinline preload="auto"></video>
        <div class="loader-spinner" id="playerLoader"></div>

        <div class="p-ui" id="playerUI">
            <div class="p-top-bar">
                <div class="p-title-display" id="playerTitle">Cargando...</div>
                <button class="p-flat-btn" style="position:absolute; right: var(--px); top: calc(env(safe-area-inset-top, 15px) + 12px);" onclick="shutdownPlayer()">
                    <svg viewBox="0 0 24 24" width="30" height="30"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
                </button>
            </div>

            <div class="p-center-controls" id="centerPanel">
                <button class="p-circ-btn" onclick="event.stopPropagation(); jumpSeconds(-10)">
                    <svg viewBox="0 0 24 24"><path d="M11 18V6l-8.5 6 8.5 6zm.5-6l8.5 6V6l-8.5 6z"/></svg>
                </button>
                <button class="p-circ-btn big" onclick="event.stopPropagation(); handlePlaybackToggle()">
                    <svg id="p-play-ico" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
                    <svg id="p-pause-ico" style="display:none;" viewBox="0 0 24 24"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>
                </button>
                <button class="p-circ-btn" onclick="event.stopPropagation(); jumpSeconds(10)">
                    <svg viewBox="0 0 24 24"><path d="M4 18l8.5-6L4 6v12zm9-12v12l8.5-6L13 6z"/></svg>
                </button>
            </div>

            <div class="p-bottom-bar">
                <div class="p-timeline-box" id="timelineBar">
                    <div class="p-rail">
                        <div class="p-fill" id="timelineFill"></div>
                        <div class="p-bullet" id="timelineBullet"></div>
                    </div>
                </div>
                <div class="p-flex-row">
                    <div class="p-timestamp"><span id="timeNow">00:00</span> <span style="opacity:0.5; margin:0 4px;">/</span> <span id="timeDuration">00:00</span></div>
                    <div class="p-actions-group">
                        <button class="p-flat-btn" id="nextEpisodeBtn" style="display:none;" onclick="event.stopPropagation(); loadNextInPlaylist()">
                            <svg viewBox="0 0 24 24"><path d="M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z"/></svg>
                        </button>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        const HOST = window.location.origin;
        let masterCatalog = [];
        let currentView = 'home';
        let playlistContext = [];
        let playlistIndex = -1;
        let uiTimeout, screenWakeLock = null;

        let catalogIndex = 0;
        const CATALOG_CHUNK = 30;

        if (!history.state) {
            history.replaceState({view: 'home', payload: null}, '', '#home');
        }

        window.addEventListener('popstate', (e) => {
            if (document.getElementById('playerModal').classList.contains('show')) {
                shutdownPlayer();
                return;
            }

            if (e.state && e.state.view) {
                navigate(e.state.view, e.state.payload, false);
            } else {
                navigate('home', null, false);
            }
        });

        function navigate(viewName, payload = null, pushToHistory = true) {
            document.querySelectorAll('.main-view, #movieSection, #seriesSection').forEach(el => {
                if(el) el.classList.remove('active');
                if(el.id === 'movieSection' || el.id === 'seriesSection') el.style.display = 'none';
            });

            document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
            currentView = viewName;

            if (pushToHistory) {
                history.pushState({view: viewName, payload: payload}, '', '#' + viewName);
            }

            if(viewName === 'home') {
                document.getElementById('view-home').classList.add('active');
                document.getElementById('tab-home').classList.add('active');
            } else if(viewName === 'catalog') {
                document.getElementById('view-catalog').classList.add('active');
                document.getElementById('tab-catalog').classList.add('active');
            } else if(viewName === 'movie') {
                document.getElementById('movieSection').style.display = 'block';
                document.getElementById('movieSection').classList.add('active');
                if(payload) renderMovieDetails(payload);
            } else if(viewName === 'series') {
                document.getElementById('seriesSection').style.display = 'block';
                document.getElementById('seriesSection').classList.add('active');
                if(payload) renderSeriesDetails(payload);
            }
            window.scrollTo({ top: 0, behavior: 'smooth' });
        }

        document.addEventListener('DOMContentLoaded', () => {
            loadCatalogData();
            setupSearch();
            setupCatalogObserver();
        });

        function addToRecent(item) {
            let recents = JSON.parse(localStorage.getItem('ry_recent')) || [];
            const id = item.folder || item.file;
            // Eliminar si ya existe para moverlo al principio
            recents = recents.filter(i => (i.folder || i.file) !== id);
            recents.unshift(item);
            if (recents.length > 10) recents.pop();
            localStorage.setItem('ry_recent', JSON.stringify(recents));
        }

        function loadCatalogData() {
            fetch(HOST + '/api/media')
                .then(res => res.json())
                .then(data => {
                    masterCatalog = data;
                    buildHeroBanner();
                    buildCarousels(masterCatalog);
                    initCatalog();
                });
        }

        function initCatalog() {
            catalogIndex = 0;
            document.getElementById('catalogGrid').innerHTML = '';
            loadMoreCatalog();
        }

        function loadMoreCatalog() {
            let chunk = masterCatalog.slice(catalogIndex, catalogIndex + CATALOG_CHUNK);
            if (chunk.length === 0) {
                document.getElementById('catalogSentinel').style.display = 'none';
                return;
            }

            const grid = document.getElementById('catalogGrid');
            chunk.forEach(item => {
                grid.appendChild(generateCardElement(item));
            });
            catalogIndex += CATALOG_CHUNK;

            if (catalogIndex >= masterCatalog.length) {
                document.getElementById('catalogSentinel').style.display = 'none';
            } else {
                document.getElementById('catalogSentinel').style.display = 'block';
            }
        }

        function setupCatalogObserver() {
            let observer = new IntersectionObserver((entries) => {
                if(entries[0].isIntersecting && currentView === 'catalog') {
                    loadMoreCatalog();
                }
            }, { rootMargin: '200px' });
            observer.observe(document.getElementById('catalogSentinel'));
        }

        function buildHeroBanner() {
            const hero = document.getElementById('heroSlider');
            if(masterCatalog.length === 0) return;
            let shuffled = [...masterCatalog].sort(() => 0.5 - Math.random()).slice(0, 3);
            hero.innerHTML = '';

            shuffled.forEach((item, index) => {
                const slide = document.createElement('div');
                slide.className = `hero-slide ${index === 0 ? 'active' : ''}`;
                if(item.image) slide.style.backgroundImage = `url('${HOST}/img?path=${encodeURIComponent(item.image)}')`;

                slide.innerHTML = `
                    <div class="hero-content">
                        <h2 class="hero-title">${item.name}</h2>
                        <button class="hero-btn" id="btn-h-${index}">
                            <svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg> VER AHORA
                        </button>
                    </div>
                `;
                hero.appendChild(slide);
                document.getElementById(`btn-h-${index}`).onclick = () => {
                    addToRecent(item);
                    if (item.type === 'series') navigate('series', item);
                    else navigate('movie', item);
                };
            });
        }

        function buildCarousels(items) {
            const container = document.getElementById('rowsContainer');
            container.innerHTML = '';

            if(items.length === 0) {
                container.innerHTML = '<div class="empty-state" style="margin-top:20px;">No se encontraron resultados.</div>';
                return;
            }

            const input = document.getElementById('searchInput');
            const isSearching = input && input.value.trim() !== '';
            let recents = JSON.parse(localStorage.getItem('ry_recent')) || [];

            // --- SECCIÓN VISTO RECIENTEMENTE ---
            if (!isSearching && recents.length > 0) {
                const section = document.createElement('div');
                section.className = 'carousel-section';
                section.style.marginBottom = '25px';

                const sectionTitle = document.createElement('h2');
                sectionTitle.className = 'carousel-title';
                sectionTitle.textContent = 'Visto Recientemente';

                const track = document.createElement('div');
                track.className = 'carousel-track';

                recents.forEach(item => {
                    track.appendChild(generateCardElement(item));
                });

                section.appendChild(sectionTitle);
                section.appendChild(track);
                container.appendChild(section);
            }

            const chunks = [];
            for (let i = 0; i < items.length; i += 10) { chunks.push(items.slice(i, i + 10)); }
            const titles = ["Novedades", "Recomendados para ti", "Explora más", "Tendencias"];

            chunks.forEach((chunk, i) => {
                const section = document.createElement('div');
                section.className = 'carousel-section';
                section.style.marginBottom = '25px';

                const sectionTitle = document.createElement('h2');
                sectionTitle.className = 'carousel-title';
                sectionTitle.textContent = titles[i] || `Colección ${i + 1}`;

                const track = document.createElement('div');
                track.className = 'carousel-track';

                chunk.forEach(item => {
                    track.appendChild(generateCardElement(item));
                });

                section.appendChild(sectionTitle);
                section.appendChild(track);
                container.appendChild(section);
            });
        }

        function generateCardElement(item) {
            const card = document.createElement('div');
            card.className = 'card';
            const itemId = item.folder || item.file;

            let imgHTML = item.image ? `<img src="${HOST}/img?path=${encodeURIComponent(item.image)}" loading="lazy">` : `<div class="poster-alt">${item.name.charAt(0)}</div>`;

            card.innerHTML = `
                <div class="poster">
                    ${imgHTML}
                </div>
                <div class="card-title">${item.name}</div>
            `;

            card.onclick = () => {
                addToRecent(item);
                if(item.type === 'series') navigate('series', item);
                else navigate('movie', item);
            };

            return card;
        }

        function setupSearch() {
            const input = document.getElementById('searchInput');
            input.addEventListener('input', (e) => {
                let query = e.target.value.toLowerCase().trim();
                document.getElementById('heroSlider').style.display = query === '' ? 'block' : 'none';
                if(query === '') {
                    buildCarousels(masterCatalog);
                } else {
                    let filtered = masterCatalog.filter(i => i.name.toLowerCase().includes(query));
                    buildCarousels(filtered);
                }
            });
        }

        function renderMovieDetails(movie) {
            document.getElementById('movieTitle').textContent = movie.name;
            let imgUrl = movie.image ? `${HOST}/img?path=${encodeURIComponent(movie.image)}` : '';
            document.getElementById('moviePoster').style.display = imgUrl ? 'block' : 'none';
            document.getElementById('moviePoster').src = imgUrl;
            document.getElementById('movieHeroBg').style.backgroundImage = imgUrl ? `url('${imgUrl}')` : 'none';

            let movieId = movie.file;
            document.getElementById('moviePlayBtn').onclick = () => bootPlayer(movie, [movie], 0);
        }

        function renderSeriesDetails(serie) {
            document.getElementById('seriesTitle').textContent = serie.name;
            let imgUrl = serie.image ? `${HOST}/img?path=${encodeURIComponent(serie.image)}` : '';
            document.getElementById('seriesPoster').style.display = imgUrl ? 'block' : 'none';
            document.getElementById('seriesPoster').src = imgUrl;
            document.getElementById('seriesHeroBg').style.backgroundImage = imgUrl ? `url('${imgUrl}')` : 'none';

            let serieId = serie.folder || serie.name;

            const chaptersContainer = document.getElementById('chaptersContainer');
            chaptersContainer.innerHTML = '<div class="empty-state">Buscando capítulos locales...</div>';

            fetch(`${HOST}/api/media?folder=${encodeURIComponent(serie.folder)}`)
                .then(r => r.json())
                .then(chapters => {
                    chaptersContainer.innerHTML = '';
                    document.getElementById('seriesMeta').textContent = `${chapters.length} Episodios`;

                    if(chapters.length === 0) {
                        chaptersContainer.innerHTML = '<div class="empty-state">No hay archivos en esta carpeta.</div>';
                        document.getElementById('seriesPlayFirstBtn').style.display = 'none';
                        return;
                    }

                    document.getElementById('seriesPlayFirstBtn').style.display = 'inline-flex';
                    document.getElementById('seriesPlayFirstBtn').onclick = () => bootPlayer(chapters[0], chapters, 0);

                    chapters.forEach((chap, idx) => {
                        const chapId = `${chap.folder}_${chap.file}`;
                        const meta = JSON.parse(localStorage.getItem('ry_meta_' + chapId)) || {t:0, d:0};
                        let progressPct = 0;
                        if(meta.d > 0) progressPct = Math.min(100, (meta.t / meta.d) * 100);

                        const itemRow = document.createElement('div');
                        itemRow.className = 'chapter-card';

                        let thumbHTML = serie.image ? `<img src="${HOST}/img?path=${encodeURIComponent(serie.image)}" loading="lazy">` : '';

                        itemRow.innerHTML = `
                            <div class="ch-thumb-box">
                                ${thumbHTML}
                                <div class="ch-play-overlay"><svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg></div>
                            </div>
                            <div class="ch-details">
                                <div class="ch-ep-num">Episodio ${idx + 1}</div>
                                <div class="ch-title">${chap.name}</div>
                                <div class="ch-progress-container"><div class="ch-progress-bar" style="width: ${progressPct}%"></div></div>
                            </div>
                        `;

                        itemRow.onclick = () => bootPlayer(chap, chapters, idx);
                        chaptersContainer.appendChild(itemRow);
                    });
                });
        }

        const video = document.getElementById('mainVideo');
        const pModal = document.getElementById('playerModal');
        const pUI = document.getElementById('playerUI');
        const pLoader = document.getElementById('playerLoader');
        const playIco = document.getElementById('p-play-ico');
        const pauseIco = document.getElementById('p-pause-ico');
        const timelineFill = document.getElementById('timelineFill');
        const timelineBullet = document.getElementById('timelineBullet');
        let currentMediaId = '';

        // --- SISTEMA ANTISUSPENSIÓN REFORZADO ---
        async function requestWakeLock() {
            if ('wakeLock' in navigator && !screenWakeLock) {
                try {
                    screenWakeLock = await navigator.wakeLock.request('screen');
                    screenWakeLock.addEventListener('release', () => { screenWakeLock = null; });
                } catch (err) {}
            }
        }
        function dropWakeLock() {
            if(screenWakeLock) {
                screenWakeLock.release().then(() => screenWakeLock = null).catch(() => { screenWakeLock = null; });
            }
        }

        video.addEventListener('play', requestWakeLock);
        video.addEventListener('pause', dropWakeLock);
        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'visible' && pModal.classList.contains('show') && !video.paused) {
                requestWakeLock();
            }
        });

        function bootPlayer(item, playlist, index) {
            let streamUrl = `${HOST}/stream?file=${encodeURIComponent(item.file)}`;
            if(item.folder) streamUrl += `&folder=${encodeURIComponent(item.folder)}`;

            playlistContext = playlist;
            playlistIndex = index;
            currentMediaId = item.folder ? `${item.folder}_${item.file}` : item.file;

            let displayName = item.folder ? `Ep. ${index+1} - ${item.name}` : item.name;
            document.getElementById('playerTitle').textContent = displayName;
            document.getElementById('nextEpisodeBtn').style.display = (index + 1 < playlist.length) ? 'block' : 'none';

            video.src = streamUrl;
            pModal.classList.add('show');
            pLoader.classList.add('active');
            keepUIAlive();

            // FORZAR PANTALLA COMPLETA INMEDIATA usando el gesto de click actual
            try {
                if (pModal.requestFullscreen) {
                    pModal.requestFullscreen().catch(err => console.log(err));
                } else if (pModal.webkitRequestFullscreen) {
                    pModal.webkitRequestFullscreen();
                } else if (video.webkitEnterFullscreen) {
                    video.webkitEnterFullscreen();
                }
            } catch (err) {}

            video.onloadedmetadata = () => {
                const meta = JSON.parse(localStorage.getItem('ry_meta_' + currentMediaId));
                if(meta && meta.t && (meta.t / video.duration) < 0.95) {
                    video.currentTime = parseFloat(meta.t);
                }
                document.getElementById('timeDuration').textContent = convertTime(video.duration);
                video.play().then(() => {
                    toggleIcons(true);
                    requestWakeLock();
                }).catch(() => { toggleIcons(false); });
            };
        }

        function triggerPlayerUI(e) {
            if(e.target.closest('button') || e.target.closest('#timelineBar')) return;
            pUI.classList.toggle('hidden');
            if(!pUI.classList.contains('hidden')) keepUIAlive();
        }

        function keepUIAlive() {
            pUI.classList.remove('hidden');
            clearTimeout(uiTimeout);
            if(!video.paused) {
                uiTimeout = setTimeout(() => { pUI.classList.add('hidden'); }, 3500);
            }
        }

        function handlePlaybackToggle() {
            if(video.paused) {
                video.play();
                toggleIcons(true);
                keepUIAlive();
            } else {
                video.pause();
                toggleIcons(false);
                pUI.classList.remove('hidden');
                clearTimeout(uiTimeout);
            }
        }

        function toggleIcons(playing) {
            playIco.style.display = playing ? 'none' : 'block';
            pauseIco.style.display = playing ? 'block' : 'none';
        }

        function jumpSeconds(secs) {
            video.currentTime = Math.max(0, Math.min(video.duration, video.currentTime + secs));
            keepUIAlive();
        }

        video.addEventListener('timeupdate', () => {
            if(!video.duration) return;
            const current = video.currentTime;
            document.getElementById('timeNow').textContent = convertTime(current);
            const pct = (current / video.duration) * 100;
            timelineFill.style.width = `${pct}%`;
            timelineBullet.style.left = `${pct}%`;

            if(current > 5) {
                localStorage.setItem('ry_meta_' + currentMediaId, JSON.stringify({t: current, d: video.duration}));
            }
        });

        video.addEventListener('waiting', () => pLoader.classList.add('active'));
        video.addEventListener('playing', () => pLoader.classList.remove('active'));

        document.getElementById('timelineBar').addEventListener('click', (e) => {
            const rect = e.currentTarget.getBoundingClientRect();
            const pos = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
            video.currentTime = pos * video.duration;
            keepUIAlive();
        });

        function loadNextInPlaylist() {
            if(playlistIndex + 1 < playlistContext.length) {
                shutdownPlayer();
                bootPlayer(playlistContext[playlistIndex + 1], playlistContext, playlistIndex + 1);
            }
        }

        video.addEventListener('ended', () => {
            localStorage.setItem('ry_meta_' + currentMediaId, JSON.stringify({t: video.duration, d: video.duration}));
            if(playlistIndex + 1 < playlistContext.length) {
                loadNextInPlaylist();
            } else {
                shutdownPlayer();
            }
        });

        // --- APAGADO LIMPIO DEL REPRODUCTOR SIN REPETIR CONSULTAS ---
        function shutdownPlayer() {
            if(document.fullscreenElement) document.exitFullscreen().catch(()=>{});
            pModal.classList.remove('show');
            video.pause();
            video.removeAttribute('src');
            video.load();
            dropWakeLock();
            clearTimeout(uiTimeout);

            if(currentView === 'series') {
                updateLocalProgress();
            }
        }

        function updateLocalProgress() {
            document.querySelectorAll('.chapter-card').forEach((card, idx) => {
                if(playlistContext[idx]) {
                    const chap = playlistContext[idx];
                    const chapId = `${chap.folder}_${chap.file}`;
                    const meta = JSON.parse(localStorage.getItem('ry_meta_' + chapId)) || {t:0, d:0};
                    let progressPct = 0;
                    if(meta.d > 0) progressPct = Math.min(100, (meta.t / meta.d) * 100);
                    const bar = card.querySelector('.ch-progress-bar');
                    if(bar) bar.style.width = `${progressPct}%`;
                }
            });
        }

        function convertTime(sec) {
            if(isNaN(sec)) return "00:00";
            const h = Math.floor(sec / 3600);
            const m = Math.floor((sec % 3600) / 60);
            const s = Math.floor(sec % 60);
            return h > 0 ? `${h}:${m < 10 ? '0':''}${m}:${s < 10 ? '0':''}${s}` : `${m < 10 ? '0':''}${m}:${s < 10 ? '0':''}${s}`;
        }
    </script>
</body>
</html>""")

if __name__ == '__main__':
    if not os.path.exists(MEDIA_DIR):
        os.makedirs(MEDIA_DIR)
    generate_html_files()

    httpd = ThreadingHTTPServer(('0.0.0.0', PORT), RyflixHandler)
    print("="*60)
    print(f" Servidor Multihilo Local Activo en el Puerto: {PORT}")
    print(f" -> Panel de Acceso e Interfaz Premium: http://localhost:{PORT}/server.html")
    print("="*60)
    httpd.serve_forever()
