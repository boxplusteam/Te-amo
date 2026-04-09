import os
import shutil
import subprocess
import json
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

# --- CONFIGURACIÓN DE RUTAS ---
BASE_PATH = r"C:\hls"
CONFIG_FILE = os.path.join(BASE_PATH, "config.json")

class HlsManagerPro:
    def __init__(self, root):
        self.root = root
        self.root.title("Gestor IPTV PRO - V2.0 (Optimizado i5-3470)")
        self.root.geometry("1150x850")
        
        # Estilo Moderno
        self.style = ttk.Style(self.root)
        self.style.theme_use("clam")
        self.configurar_estilos()
        
        self.autostart_tiempo = 120
        self.autostart_activo = True
        
        # Estructura base con valores optimizados para ahorro
        self.config_data = {
            "cloudflare_url": "", 
            "default_res": "480",        # 480p es ideal para 4 canales en un i5 3470
            "default_bitrate": "800k",   # Bajado a 800k para asegurar la red con 30 clientes
            "canales": {}
        }

        self.preparar_entorno()
        self.cargar_datos() 
        self.construir_interfaz()
        self.actualizar_tabla()
        self.iniciar_cuenta_atras()

    def configurar_estilos(self):
        bg_color = "#f4f6f9"
        self.root.configure(bg=bg_color)
        self.style.configure("TFrame", background=bg_color)
        self.style.configure("TLabelframe", background=bg_color, font=("Segoe UI", 10, "bold"))
        self.style.configure("TLabelframe.Label", background=bg_color, foreground="#333333")
        self.style.configure("TLabel", background=bg_color, font=("Segoe UI", 10))
        self.style.configure("TButton", font=("Segoe UI", 9, "bold"), padding=5)
        self.style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"), background="#e1e6eb")
        self.style.configure("Treeview", font=("Segoe UI", 9), rowheight=25)

    def preparar_entorno(self):
        if not os.path.exists(BASE_PATH): os.makedirs(BASE_PATH)
        if not os.path.exists(CONFIG_FILE):
            self.guardar_json()

    def construir_interfaz(self):
        # --- PANEL SUPERIOR ---
        frame_top = ttk.Frame(self.root, padding="10 10 10 0")
        frame_top.pack(fill=tk.X)

        # Opciones Globales (Resolución y Bitrate base)
        global_frame = ttk.LabelFrame(frame_top, text=" Configuración Global (Optimizada) ", padding="10")
        global_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

        ttk.Label(global_frame, text="Res. Base:").grid(row=0, column=0, padx=5, pady=2)
        self.var_global_res = tk.StringVar(value=self.config_data.get("default_res", "480"))
        cb_global_res = ttk.Combobox(global_frame, textvariable=self.var_global_res, values=["360", "480", "720", "1080"], width=8, state="readonly")
        cb_global_res.grid(row=0, column=1, padx=5, pady=2)

        ttk.Label(global_frame, text="Bitrate Base:").grid(row=0, column=2, padx=5, pady=2)
        self.var_global_bitrate = tk.StringVar(value=self.config_data.get("default_bitrate", "800k"))
        cb_global_bit = ttk.Combobox(global_frame, textvariable=self.var_global_bitrate, values=["500k", "800k", "1200k", "1500k", "2500k"], width=10)
        cb_global_bit.grid(row=0, column=3, padx=5, pady=2)
        
        ttk.Button(global_frame, text="Guardar Globales", command=self.guardar_globales).grid(row=0, column=4, padx=10)

        # Cloudflare y Timer
        cf_frame = ttk.LabelFrame(frame_top, text=" Sistema ", padding="10")
        cf_frame.pack(side=tk.RIGHT, fill=tk.BOTH)

        self.lbl_timer = tk.Label(cf_frame, text="Autostart: 120s", font=('Segoe UI', 10, 'bold'), fg="red", bg="#f4f6f9")
        self.lbl_timer.pack(side=tk.LEFT, padx=10)
        tk.Button(cf_frame, text="Parar", command=self.cancelar_autostart, bg="#ff5252", fg="white", relief="flat", padx=10).pack(side=tk.LEFT)

        # --- PANEL CENTRAL: Tabla ---
        table_frame = ttk.Frame(self.root, padding="10")
        table_frame.pack(fill=tk.BOTH, expand=True)

        self.tree = ttk.Treeview(table_frame, columns=("ID", "Nombre", "Grupo", "Res", "Bitrate", "Estado"), show="headings")
        self.tree.heading("ID", text="ID")
        self.tree.heading("Nombre", text="Canal")
        self.tree.heading("Grupo", text="Grupo")
        self.tree.heading("Res", text="Resolución")
        self.tree.heading("Bitrate", text="Bitrate")
        self.tree.heading("Estado", text="Estado")
        
        for col in ("ID", "Res", "Bitrate"): self.tree.column(col, width=80, anchor="center")
        self.tree.pack(fill=tk.BOTH, expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.cargar_datos_formulario)

        # --- PANEL CONTROLES ---
        frame_ctrl = ttk.Frame(self.root, padding="10")
        frame_ctrl.pack(fill=tk.X)

        tk.Button(frame_ctrl, text="▶ INICIAR CANAL", command=self.iniciar_seleccionado, bg="#4caf50", fg="white", relief="flat", width=18).pack(side=tk.LEFT, padx=5)
        tk.Button(frame_ctrl, text="⏹ DETENER CANAL", command=self.detener_seleccionado, bg="#f44336", fg="white", relief="flat", width=18).pack(side=tk.LEFT, padx=5)
        tk.Button(frame_ctrl, text="🚀 INICIAR TODOS", command=self.iniciar_todos_hilo, bg="#2196f3", fg="white", relief="flat", font=('Segoe UI', 9, 'bold')).pack(side=tk.RIGHT, padx=5)

        # --- FORMULARIO ---
        self.crear_formulario()

    def crear_formulario(self):
        f = ttk.LabelFrame(self.root, text=" Añadir / Editar Canal ", padding="15")
        f.pack(fill=tk.X, padx=10, pady=10)

        self.var_id = tk.StringVar()
        self.var_nom = tk.StringVar()
        self.var_grp = tk.StringVar(value="TV")
        self.var_img = tk.StringVar()
        self.var_url = tk.StringVar()
        self.var_ind_res = tk.StringVar(value="Por defecto")
        self.var_ind_bitrate = tk.StringVar(value="Por defecto")

        # Layout del formulario
        ttk.Label(f, text="ID/Carpeta:").grid(row=0, column=0, sticky="w")
        ttk.Entry(f, textvariable=self.var_id, width=15).grid(row=0, column=1, sticky="w", padx=5)
        
        ttk.Label(f, text="Nombre:").grid(row=0, column=2, sticky="e")
        ttk.Entry(f, textvariable=self.var_nom, width=30).grid(row=0, column=3, sticky="w", padx=5)

        ttk.Label(f, text="URL Stream:").grid(row=1, column=0, sticky="w", pady=10)
        ttk.Entry(f, textvariable=self.var_url, width=80).grid(row=1, column=1, columnspan=4, sticky="w", padx=5)

        # Selección de calidad individual
        lbl_q = ttk.Label(f, text="Ajuste de Calidad:")
        lbl_q.grid(row=2, column=0, sticky="w")
        
        q_frame = ttk.Frame(f)
        q_frame.grid(row=2, column=1, columnspan=4, sticky="w")
        
        ttk.Label(q_frame, text="Res:").pack(side=tk.LEFT)
        ttk.Combobox(q_frame, textvariable=self.var_ind_res, values=["Por defecto", "360", "480", "720", "1080"], width=12, state="readonly").pack(side=tk.LEFT, padx=5)
        
        ttk.Label(q_frame, text="Bitrate:").pack(side=tk.LEFT, padx=(10,0))
        ttk.Combobox(q_frame, textvariable=self.var_ind_bitrate, values=["Por defecto", "500k", "800k", "1200k", "1500k", "2500k"], width=12).pack(side=tk.LEFT, padx=5)

        tk.Button(f, text="💾 GUARDAR CANAL", command=self.guardar_canal, bg="#ff9800", fg="white", relief="flat", font=('Segoe UI', 9, 'bold')).grid(row=3, column=1, pady=10, sticky="w")

    # --- LÓGICA DE PROCESAMIENTO ---

    def calcular_bufsize(self, bitrate_str):
        try:
            val = int(bitrate_str.lower().replace('k', ''))
            return f"{val * 2}k"
        except: return "1500k"

    def iniciar_ffmpeg(self, cid):
        canal = self.config_data["canales"].get(cid)
        if not canal: return
        
        ruta_hls = os.path.join(BASE_PATH, cid)
        if not os.path.exists(ruta_hls): os.makedirs(ruta_hls)
        
        # Lógica de prioridad: Calidad Individual > Calidad Global
        res_final = self.config_data.get("default_res", "480") if canal.get("res") == "Por defecto" else canal.get("res")
        bit_final = self.config_data.get("default_bitrate", "800k") if canal.get("bitrate") == "Por defecto" else canal.get("bitrate")
        buf_final = self.calcular_bufsize(bit_final)

        output = os.path.join(ruta_hls, "index.m3u8")
        
        # --- COMANDO EXTREMADAMENTE OPTIMIZADO PARA i5 3470 ---
        # -reconnect* : Evita que se cierre si la fuente original falla momentáneamente.
        # -threads 1 : CRUCIAL para que los 4 canales no peleen por la CPU.
        # -tune zerolatency -profile:v baseline : Máxima velocidad y compatibilidad en dispositivos bajos.
        # -r 25 : Baja a 25 fps para ahorrar un 20% de consumo de CPU.
        # -c:a aac -b:a 64k : Audio comprimido al máximo para ahorrar internet a esos 30 usuarios.
        
        cmd = (
            f'ffmpeg -y '
            f'-reconnect 1 -reconnect_at_eof 1 -reconnect_streamed 1 -reconnect_delay_max 5 '
            f'-i "{canal["url"]}" '
            f'-c:v libx264 -preset ultrafast -tune zerolatency -profile:v baseline '
            f'-threads 1 -r 25 '
            f'-b:v {bit_final} -maxrate {bit_final} -bufsize {buf_final} '
            f'-vf "scale=-2:{res_final}" '
            f'-c:a aac -b:a 64k -ac 2 '
            f'-f hls -hls_time 4 -hls_list_size 6 -hls_flags delete_segments+independent_segments '
            f'"{output}"'
        )
        
        # Abrir ventana minimizada para no saturar visualmente Windows
        subprocess.Popen(f'start /min "{cid}" cmd /c {cmd}', shell=True)
        self.tree.set(cid, "Estado", "▶ EN CURSO")

    # --- AUXILIARES ---

    def guardar_globales(self):
        self.config_data["default_res"] = self.var_global_res.get()
        self.config_data["default_bitrate"] = self.var_global_bitrate.get()
        self.guardar_json()
        messagebox.showinfo("OK", "Configuración global actualizada.")

    def cargar_datos(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    self.config_data.update(json.load(f))
            except: pass

    def guardar_json(self):
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.config_data, f, indent=4)

    def guardar_canal(self):
        cid = self.var_id.get().strip()
        if not cid: return
        self.config_data["canales"][cid] = {
            "nombre": self.var_nom.get(),
            "grupo": self.var_grp.get(),
            "url": self.var_url.get(),
            "res": self.var_ind_res.get(),
            "bitrate": self.var_ind_bitrate.get(),
            "logo": self.var_img.get()
        }
        self.guardar_json()
        self.actualizar_tabla()
        messagebox.showinfo("OK", f"Canal {cid} guardado.")

    def actualizar_tabla(self):
        self.tree.delete(*self.tree.get_children())
        for cid, d in self.config_data["canales"].items():
            self.tree.insert("", tk.END, iid=cid, values=(cid, d['nombre'], d['grupo'], d.get('res'), d.get('bitrate'), "⏹ Detenido"))

    def iniciar_seleccionado(self):
        sel = self.tree.selection()
        if sel: self.iniciar_ffmpeg(sel[0])

    def detener_seleccionado(self):
        sel = self.tree.selection()
        if sel:
            cid = sel[0]
            os.system(f'taskkill /fi "windowtitle eq {cid}*" /f')
            self.tree.set(cid, "Estado", "⏹ Detenido")

    def iniciar_todos_hilo(self):
        self.cancelar_autostart()
        def tarea():
            for cid in self.config_data["canales"]:
                self.iniciar_ffmpeg(cid)
                time.sleep(8) # He subido a 8 seg de espera para no ahogar la CPU al arrancar todos de golpe
        threading.Thread(target=tarea, daemon=True).start()

    def cancelar_autostart(self):
        self.autostart_activo = False
        self.lbl_timer.config(text="AUTOSTART OFF", fg="grey")

    def iniciar_cuenta_atras(self):
        if self.autostart_activo and self.autostart_tiempo > 0:
            self.lbl_timer.config(text=f"Autostart: {self.autostart_tiempo}s")
            self.autostart_tiempo -= 1
            self.root.after(1000, self.iniciar_cuenta_atras)
        elif self.autostart_activo:
            self.iniciar_todos_hilo()

    def cargar_datos_formulario(self, event):
        sel = self.tree.selection()
        if not sel: return
        cid = sel[0]
        c = self.config_data["canales"][cid]
        self.var_id.set(cid); self.var_nom.set(c['nombre'])
        self.var_url.set(c['url']); self.var_ind_res.set(c.get('res', 'Por defecto'))
        self.var_ind_bitrate.set(c.get('bitrate', 'Por defecto'))

if __name__ == "__main__":
    root = tk.Tk()
    app = HlsManagerPro(root)
    root.mainloop()
