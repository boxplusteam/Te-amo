import tkinter as tk
from tkinter import ttk, messagebox
import re
import os
import subprocess
import json
import time

# --- CONFIGURACIÓN DE RUTAS ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config_hls.json")
BASE_PATH = r"C:\hls"

class AceStreamHLS:
    def __init__(self, root):
        self.root = root
        self.root.title("AceStream HLS Manager Pro - Ultra Stable")
        self.root.geometry("850x650")
        
        # 1. Limpieza radical al iniciar
        self.kill_all_ffmpeg_system()

        # Asegurar carpetas
        if not os.path.exists(BASE_PATH):
            os.makedirs(BASE_PATH, exist_ok=True)

        self.channels = self.load_config()
        self.active_processes = {}

        self.setup_ui()
        
        # 2. AUTOSTART: Iniciar todos los canales guardados automáticamente
        # Esperamos 2 segundos para dar tiempo a que el sistema limpie procesos previos
        self.root.after(2000, self.start_all)

    def kill_all_ffmpeg_system(self):
        try:
            if os.name == 'nt':
                subprocess.run("taskkill /F /IM ffmpeg.exe /T", shell=True, capture_output=True)
        except: pass

    def setup_ui(self):
        style = ttk.Style()
        style.configure("TButton", font=("Segoe UI", 9))

        top_frame = ttk.LabelFrame(self.root, text=" Configuración de Canal ", padding=10)
        top_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Label(top_frame, text="ID AceStream:").grid(row=0, column=0, sticky=tk.W)
        self.url_entry = ttk.Entry(top_frame, width=55)
        self.url_entry.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(top_frame, text="Carpeta (c1, c2...):").grid(row=1, column=0, sticky=tk.W)
        self.name_entry = ttk.Entry(top_frame, width=15)
        self.name_entry.grid(row=1, column=1, sticky=tk.W, padx=5, pady=5)

        ttk.Label(top_frame, text="Calidad:").grid(row=1, column=1, sticky=tk.E)
        self.quality_var = tk.StringVar(value="720p")
        self.quality_combo = ttk.Combobox(top_frame, textvariable=self.quality_var, values=["720p", "480p"], state="readonly", width=8)
        self.quality_combo.grid(row=1, column=2, padx=5, pady=5)

        ttk.Button(top_frame, text="Guardar y Lanzar", command=self.add_channel).grid(row=0, column=2, padx=5, pady=5)

        ctrl_frame = ttk.Frame(self.root, padding=5)
        ctrl_frame.pack(fill=tk.X, padx=10)

        ttk.Button(ctrl_frame, text="▶ START TODOS", command=self.start_all).pack(side=tk.LEFT, padx=2)
        ttk.Button(ctrl_frame, text="■ STOP TODOS", command=self.stop_all).pack(side=tk.LEFT, padx=2)
        
        self.status_global = ttk.Label(ctrl_frame, text="Estado: Listo", foreground="blue")
        self.status_global.pack(side=tk.RIGHT, padx=10)

        list_frame = ttk.LabelFrame(self.root, text=" Canales Registrados ", padding=10)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.tree = ttk.Treeview(list_frame, columns=("ID", "Calidad", "Estado"), show='headings')
        self.tree.heading("ID", text="Nombre/Carpeta")
        self.tree.heading("Calidad", text="Calidad")
        self.tree.heading("Estado", text="Status CMD")
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.tree.bind('<<TreeviewSelect>>', self.load_data_to_edit)
        ttk.Button(list_frame, text="Eliminar", command=self.delete_channel).pack(side=tk.TOP, padx=5)

    def extract_clean_id(self, text):
        match = re.search(r'([a-fA-F0-9]{40})', text)
        return match.group(1) if match else None

    def load_data_to_edit(self, event):
        selected = self.tree.selection()
        if not selected: return
        name = selected[0]
        if name in self.channels:
            data = self.channels[name]
            self.name_entry.delete(0, tk.END)
            self.name_entry.insert(0, name)
            self.url_entry.delete(0, tk.END)
            self.url_entry.insert(0, data['id'])
            self.quality_var.set(data['quality'])

    def add_channel(self):
        name = self.name_entry.get().strip().lower()
        raw_input = self.url_entry.get().strip()
        quality = self.quality_var.get()
        clean_id = self.extract_clean_id(raw_input)

        if not name or not clean_id:
            messagebox.showerror("Error", "ID o Nombre inválido")
            return

        os.makedirs(os.path.join(BASE_PATH, name), exist_ok=True)
        self.stop_single_process(name)

        self.channels[name] = {"id": clean_id, "quality": quality}
        self.save_config()
        self.run_ffmpeg(name, self.channels[name])
        self.refresh_table()

    def run_ffmpeg(self, name, data):
        path = os.path.join(BASE_PATH, name)
        v_bit = "1800k" if data['quality'] == "720p" else "1000k"
        v_res = "720" if data['quality'] == "720p" else "480"
        
        url = f"http://127.0.0.1:6878/ace/getstream?id={data['id']}"
        output = f'"{os.path.join(path, "index.m3u8")}"'

        # Cambiamos el comando para que si FFmpeg falla, la ventana NO se cierre (usando cmd /K)
        # Esto permite leer el error exacto.
        ffmpeg_cmd = (
            f'ffmpeg -y -i "{url}" '
            f'-c:v libx264 -preset superfast -b:v {v_bit} -maxrate {v_bit} -bufsize 3500k '
            f'-vf "scale=-2:{v_res}" -c:a aac -b:a 128k '
            f'-f hls -hls_time 6 -hls_list_size 5 -hls_flags delete_segments {output}'
        )
        
        full_cmd = f'cmd /K "title FFmpeg_{name} && {ffmpeg_cmd}"'

        try:
            proc = subprocess.Popen(full_cmd, creationflags=subprocess.CREATE_NEW_CONSOLE)
            self.active_processes[name] = proc
        except Exception as e:
            print(f"Error lanzando canal {name}: {e}")

    def start_all(self):
        if not self.channels:
            self.status_global.config(text="Estado: Sin canales guardados", foreground="orange")
            return
            
        for name, data in self.channels.items():
            if name not in self.active_processes or self.active_processes[name].poll() is not None:
                self.run_ffmpeg(name, data)
        
        self.status_global.config(text="Estado: AUTOSTART ACTIVADO", foreground="green")
        self.refresh_table()

    def stop_single_process(self, name):
        if name in self.active_processes:
            proc = self.active_processes[name]
            try:
                # En Windows, al usar 'cmd /K', hay que matar el árbol de procesos
                subprocess.run(f"taskkill /F /T /PID {proc.pid}", shell=True, capture_output=True)
            except: pass
            del self.active_processes[name]

    def stop_all(self):
        for name in list(self.active_processes.keys()):
            self.stop_single_process(name)
        self.kill_all_ffmpeg_system()
        self.status_global.config(text="Estado: TODO DETENIDO", foreground="red")
        self.refresh_table()

    def delete_channel(self):
        selected = self.tree.selection()
        if not selected: return
        name = selected[0]
        self.stop_single_process(name)
        if name in self.channels:
            del self.channels[name]
            self.save_config()
        self.refresh_table()

    def refresh_table(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        for name, data in self.channels.items():
            is_alive = name in self.active_processes and self.active_processes[name].poll() is None
            status = "▶ ACTIVO" if is_alive else "■ STOP / ERROR"
            self.tree.insert("", tk.END, iid=name, values=(name, data['quality'], status))

    def save_config(self):
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(self.channels, f, indent=4)
        except Exception as e: print(f"Error guardando JSON: {e}")

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    data = json.load(f)
                    return data if isinstance(data, dict) else {}
            except: return {}
        return {}

    def on_close(self):
        self.stop_all()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = AceStreamHLS(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()