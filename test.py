import tkinter as tk
from tkinter import font
import socket
import threading
import time
from datetime import datetime
import queue 
import os 

# --- Configuration ---
UDP_IP = "0.0.0.0"
UDP_PORT = 12345
TEAM_NAMES_ORDERED_IN_PACKET = ["castile", "capet", "essex", "milan"]

INITIAL_POINTS = { "castile": 10, "capet": 25, "essex": 5, "milan": 15 }
UPDATE_INTERVAL_MS = 100
TEMP_FULLSCREEN_DURATION_MS = 10000 
QUADRANT_SEPARATOR_THICKNESS = 1 
TROPHY_ICON_PATH = "trophy.png" 
IDLE_THRESHOLD_SECONDS = 30 * 60 # 30 minutes for screensaver

class ScoreboardApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Scoreboard") 
        self.root.attributes('-fullscreen', True)
        self.root.config(cursor="none")

        self.team_points = INITIAL_POINTS.copy()
        self.sorted_teams_cache = []
        self.last_update_time = "Never"

        self.team_colors = { 
            "castile": "#228B22", "capet":   "#0000CD",
            "essex":   "#800080", "milan":   "#B22222" 
        }
        self.trophy_icon_image = None 
        
        self.screensaver_active = False
        self.last_activity_time = time.time()
        self.screensaver_window = None
        self.check_inactivity_id = None

        try:
            self.trophy_icon_image = tk.PhotoImage(file=TROPHY_ICON_PATH)
        except Exception as e:
            print(f"WARNING: Could not load trophy icon '{TROPHY_ICON_PATH}': {e}")
            self.trophy_icon_image = None

        self.udp_queue = queue.Queue()
        self.udp_stop_event = threading.Event()
        self.udp_thread = threading.Thread(target=self.udp_listener, daemon=True)

        self.setup_ui()
        self.udp_thread.start()
        self.process_udp_queue()

        # Bindings to reassert fullscreen
        self.root.bind("<FocusIn>", self.reassert_fullscreen_root)
        self.root.bind("<Activate>", self.reassert_fullscreen_root)

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.root.bind('<Escape>', lambda e: self.on_closing())
        
        self.check_inactivity_id = self.root.after(10000, self.check_inactivity)


    def reassert_fullscreen_root(self, event=None):
        # print("DEBUG: Root FocusIn/Activate")
        if self.root.attributes('-fullscreen'):
            # For some WMs, quickly toggling might be more robust
            # self.root.attributes('-fullscreen', False)
            # self.root.update_idletasks() # Process the change
            self.root.attributes('-fullscreen', True)
            self.root.lift()
            # self.root.focus_force() # Be careful with focus_force

    def reassert_fullscreen_fs(self, event=None):
        # print("DEBUG: FS Toplevel FocusIn/Activate")
        if hasattr(self, 'fs_window') and self.fs_window.winfo_exists():
            if self.fs_window.attributes('-fullscreen'):
                # self.fs_window.attributes('-fullscreen', False)
                # self.fs_window.update_idletasks()
                self.fs_window.attributes('-fullscreen', True)
                self.fs_window.lift()
                # self.fs_window.focus_force()

    def record_activity(self):
        self.last_activity_time = time.time()
        if self.screensaver_active:
            self.deactivate_screensaver()

    def check_inactivity(self):
        if not self.screensaver_active and \
           (time.time() - self.last_activity_time > IDLE_THRESHOLD_SECONDS):
            self.activate_screensaver()
        self.check_inactivity_id = self.root.after(30000, self.check_inactivity)

    def activate_screensaver(self):
        if self.screensaver_active: return
        self.screensaver_active = True
        self.screensaver_window = tk.Toplevel(self.root)
        self.screensaver_window.attributes('-fullscreen', True)
        self.screensaver_window.configure(bg="black", cursor="none")
        self.screensaver_window.lift()
        self.screensaver_window.bind("<Button-1>", self.deactivate_screensaver_event)
        self.screensaver_window.bind("<Key>", self.deactivate_screensaver_event)
        self.screensaver_window.focus_set()

    def deactivate_screensaver_event(self, event=None):
        self.deactivate_screensaver() # Call main logic
        self.record_activity()    # And then record activity

    def deactivate_screensaver(self):
        if not self.screensaver_active: return
        if hasattr(self, 'screensaver_window') and self.screensaver_window.winfo_exists():
            self.screensaver_window.destroy()
            self.screensaver_window = None
        self.screensaver_active = False
        # self.record_activity() # Moved to event handler to ensure it's always called on dismiss

    def on_closing(self):
        print("Closing application...") 
        if hasattr(self, 'check_inactivity_id') and self.check_inactivity_id:
            self.root.after_cancel(self.check_inactivity_id)
            self.check_inactivity_id = None
        self.udp_stop_event.set()
        # ... (rest of on_closing) ...
        if self.udp_thread.is_alive():
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.sendto(b"shutdown", ("127.0.0.1", UDP_PORT))
                sock.close()
            except Exception as e: print(f"Error sending shutdown packet: {e}") 
            self.udp_thread.join(timeout=1)
        self.root.quit()
        self.root.destroy()

    def setup_ui(self):
        self.root.configure(bg="black") 
        self.quadrant_container = tk.Frame(self.root, bg="black") 
        self.quadrant_container.pack(fill=tk.BOTH, expand=True)
        # ... (rest of setup_ui) ...
        self.quadrant_container.grid_rowconfigure(0, weight=1, uniform="row_group")
        self.quadrant_container.grid_rowconfigure(1, weight=1, uniform="row_group")
        self.quadrant_container.grid_columnconfigure(0, weight=1, uniform="col_group")
        self.quadrant_container.grid_columnconfigure(1, weight=1, uniform="col_group")
        self.quadrant_frames_positions = { "1st": (0, 0), "2nd": (0, 1), "3rd": (1, 0), "4th": (1, 1) }
        self.quadrant_display_frames = {} 
        for rank_str, (r, c) in self.quadrant_frames_positions.items():
            content_frame = tk.Frame(self.quadrant_container, bg="gray15") 
            content_frame.grid(row=r, column=c, sticky="nsew", 
                               padx=QUADRANT_SEPARATOR_THICKNESS, 
                               pady=QUADRANT_SEPARATOR_THICKNESS)
            self.quadrant_display_frames[rank_str] = content_frame
        self.last_updated_var = tk.StringVar(value=f"Last updated: {self.last_update_time}")
        self.last_updated_label = tk.Label(self.root, textvariable=self.last_updated_var, bg="black", fg="white", font=("Arial", 12))
        self.last_updated_label.place(relx=0.5, rely=0.02, anchor="n")
        self.update_display()

    def udp_listener(self):
        # ... (udp_listener is unchanged from previous final version) ...
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.bind((UDP_IP, UDP_PORT))
            print(f"Listening for UDP packets on {UDP_IP}:{UDP_PORT}") 
            sock.settimeout(1.0)
            while not self.udp_stop_event.is_set():
                try:
                    data, addr = sock.recvfrom(1024)
                    decoded_data = data.decode('utf-8').strip()
                    self.udp_queue.put(decoded_data)
                except socket.timeout: continue
                except Exception as e:
                    if not self.udp_stop_event.is_set(): print(f"UDP Rx Error: {e}") 
        except OSError as e:
            print(f"UDP BIND ERROR: {e}") 
            self.udp_queue.put(f"ERROR: Port {UDP_PORT} in use")
        finally: 
            print("UDP listener stopping.") 
            sock.close()
    
    def process_udp_queue(self):
        # ... (process_udp_queue is unchanged, but ensure record_activity call) ...
        try:
            while not self.udp_queue.empty():
                message = self.udp_queue.get_nowait()
                if message.startswith("ERROR:"): 
                    self.last_updated_var.set(message)
                    print(f"Error from queue: {message}") 
                    continue
                parts = message.split(':')
                if len(parts) == 4:
                    try:
                        self.team_points = { 
                            TEAM_NAMES_ORDERED_IN_PACKET[0]: int(parts[0]), 
                            TEAM_NAMES_ORDERED_IN_PACKET[1]: int(parts[1]), 
                            TEAM_NAMES_ORDERED_IN_PACKET[2]: int(parts[2]), 
                            TEAM_NAMES_ORDERED_IN_PACKET[3]: int(parts[3]) 
                        }
                        self.record_activity() # <--- Activity recorded here
                        now = datetime.now(); hour_12 = int(now.strftime('%I')); self.last_update_time = f"{now.month}/{now.day}/{now.strftime('%y')} {hour_12}:{now.minute:02d} {now.strftime('%p')}"
                        self.last_updated_var.set(f"Last updated: {self.last_update_time}")
                        self.update_display()
                    except ValueError: 
                        print(f"Malformed packet (ValueError): {message}") 
                else: 
                    print(f"Malformed packet (parts != 4): {message}") 
        finally: 
            self.root.after(UPDATE_INTERVAL_MS, self.process_udp_queue)

    def update_display(self):
        # ... (update_display is unchanged) ...
        self.sorted_teams_cache = sorted(self.team_points.items(), key=lambda item: item[1], reverse=True)
        rank_strings = ["1st", "2nd", "3rd", "4th"]
        for i, (team_name, points) in enumerate(self.sorted_teams_cache):
            rank_str = rank_strings[i]
            quadrant_target_frame = self.quadrant_display_frames[rank_str] 
            for widget in quadrant_target_frame.winfo_children(): 
                widget.destroy()
            self.design_single_quadrant(quadrant_target_frame, team_name, points, rank_str)
        if self.last_updated_label: self.last_updated_label.lift() 

    def design_single_quadrant(self, parent_frame, team_name, team_points, rank_position_str):
        # ... (design_single_quadrant is unchanged from previous final version) ...
        current_team_color = self.team_colors.get(team_name.lower(), "gray50")
        parent_frame.configure(bg=current_team_color) 
        font_team_name = ("Gill Sans MT", 60, "bold")
        font_points = ("Arial", 18)
        font_rank_number = ("Arial", 28, "bold")
        font_rank_suffix = ("Arial", 16, "bold")
        top_offset_for_name = 75 
        
        if rank_position_str == "1st" and self.trophy_icon_image: 
            trophy_label = tk.Label(parent_frame, image=self.trophy_icon_image, bg=current_team_color)
            trophy_label.image = self.trophy_icon_image 
            trophy_label.place(x=5, y=5) 
            trophy_label.bind("<Button-1>", lambda e, tn=team_name, tp=team_points, rps=rank_position_str: self.show_fullscreen_quadrant(tn, tp, rps))

        display_team_name = team_name.capitalize()
        lbl_name = tk.Label(parent_frame, text=display_team_name, font=font_team_name, bg=current_team_color, fg="white")
        lbl_name.pack(pady=(top_offset_for_name, 10), padx=10)
        lbl_points = tk.Label(parent_frame, text=str(team_points), font=font_points, bg=current_team_color, fg="yellow")
        lbl_points.pack(pady=(0, 10), padx=10)
        rank_num_text, rank_suffix_text = ScoreboardApp.get_rank_parts_static(rank_position_str)
        rank_holder_frame = tk.Frame(parent_frame, bg=current_team_color)
        rank_holder_frame.pack(pady=(0, 10), padx=10)
        lbl_rank_num = tk.Label(rank_holder_frame, text=rank_num_text, font=font_rank_number, bg=current_team_color, fg="white")
        lbl_rank_num.pack(side=tk.LEFT, fill=tk.NONE, expand=False)
        lbl_rank_suffix = tk.Label(rank_holder_frame, text=rank_suffix_text, font=font_rank_suffix, bg=current_team_color, fg="white")
        lbl_rank_suffix.pack(side=tk.LEFT, anchor='n', padx=(1,0), fill=tk.NONE, expand=False)
        elements_to_bind = [parent_frame, lbl_name, lbl_points, rank_holder_frame, lbl_rank_num, lbl_rank_suffix]
        for widget in elements_to_bind: 
            widget.bind("<Button-1>", lambda e, tn=team_name, tp=team_points, rps=rank_position_str: self.show_fullscreen_quadrant(tn, tp, rps))

    def apply_grab(self):
        # ... (apply_grab is unchanged from previous final version) ...
        if hasattr(self, 'fs_window') and self.fs_window.winfo_exists():
            try:
                self.fs_window.grab_set()
            except tk.TclError as e:
                print(f"WARNING: FS - Error applying grab: {e}") 

    def show_fullscreen_quadrant(self, team_name, team_points, rank_position_str):
        self.record_activity() # Record activity when FS view is shown
        # ... (rest of show_fullscreen_quadrant is largely unchanged from previous final version,
        #      ensure it includes the delayed grab and image handling) ...
        if hasattr(self, 'fs_window') and self.fs_window.winfo_exists():
            self.fs_window.destroy()

        self.fs_window = tk.Toplevel(self.root)
        self.fs_window.attributes('-fullscreen', True) 
        self.fs_window.transient(self.root)      
        self.fs_window.config(cursor="none")
        current_team_color = self.team_colors.get(team_name.lower(), "gray20")
        self.fs_window.configure(bg=current_team_color)

        # Bind FocusIn/Activate for the fs_window
        self.fs_window.bind("<FocusIn>", self.reassert_fullscreen_fs)
        self.fs_window.bind("<Activate>", self.reassert_fullscreen_fs)

        content_frame = tk.Frame(self.fs_window, bg=current_team_color)
        content_frame.pack(fill=tk.BOTH, expand=True)
        info_block_frame = tk.Frame(content_frame, bg=current_team_color)

        # ... [All the label creation and packing for fs_window content] ...
        current_team_name_fs = team_name
        current_team_points_fs = team_points
        current_team_rank_str_fs = rank_position_str
        current_team_rank_index = -1
        for i, (name_iter, pts_iter) in enumerate(self.sorted_teams_cache):
            if name_iter == current_team_name_fs: current_team_rank_index = i; break
        points_ahead_of_next, points_behind_prev = None, None
        if 0 <= current_team_rank_index < len(self.sorted_teams_cache):
            if current_team_rank_index < len(self.sorted_teams_cache) - 1:
                points_ahead_of_next = current_team_points_fs - self.sorted_teams_cache[current_team_rank_index + 1][1]
            if current_team_rank_index > 0:
                points_behind_prev = self.sorted_teams_cache[current_team_rank_index - 1][1] - current_team_points_fs
        points_1st_vs_2nd, points_2nd_vs_1st, points_2nd_vs_3rd, points_3rd_vs_2nd, points_3rd_vs_4th, points_4th_vs_3rd = [None]*6
        if len(self.sorted_teams_cache) >= 2:
            points_1st_vs_2nd = self.sorted_teams_cache[0][1] - self.sorted_teams_cache[1][1]; points_2nd_vs_1st = self.sorted_teams_cache[1][1] - self.sorted_teams_cache[0][1]
        if len(self.sorted_teams_cache) >= 3:
            points_2nd_vs_3rd = self.sorted_teams_cache[1][1] - self.sorted_teams_cache[2][1]; points_3rd_vs_2nd = self.sorted_teams_cache[2][1] - self.sorted_teams_cache[1][1]
        if len(self.sorted_teams_cache) >= 4:
            points_3rd_vs_4th = self.sorted_teams_cache[2][1] - self.sorted_teams_cache[3][1]; points_4th_vs_3rd = self.sorted_teams_cache[3][1] - self.sorted_teams_cache[2][1]

        fs_font_team_name = ("Gill Sans MT", 70, "bold")
        fs_lbl_name = tk.Label(info_block_frame, text=current_team_name_fs.capitalize(), font=fs_font_team_name, bg=current_team_color, fg="white")
        fs_lbl_name.pack(pady=(0, 15))
        fs_font_points = ("Arial", 40)
        fs_lbl_points = tk.Label(info_block_frame, text=str(current_team_points_fs), font=fs_font_points, bg=current_team_color, fg="yellow")
        fs_lbl_points.pack(pady=(0, 15))
        fs_font_rank_number = ("Arial", 50, "bold")
        fs_font_rank_suffix = ("Arial", 25, "bold")
        fs_rank_num_text, fs_rank_suffix_text = ScoreboardApp.get_rank_parts_static(current_team_rank_str_fs)
        fs_rank_holder_frame = tk.Frame(info_block_frame, bg=current_team_color)
        fs_rank_holder_frame.pack(pady=(0, 15))
        fs_lbl_rank_num = tk.Label(fs_rank_holder_frame, text=fs_rank_num_text, font=fs_font_rank_number, bg=current_team_color, fg="white")
        fs_lbl_rank_num.pack(side=tk.LEFT, fill=tk.NONE, expand=False)
        fs_lbl_rank_suffix = tk.Label(fs_rank_holder_frame, text=fs_rank_suffix_text, font=fs_font_rank_suffix, bg=current_team_color, fg="white")
        fs_lbl_rank_suffix.pack(side=tk.LEFT, anchor='n', padx=(1,0), fill=tk.NONE, expand=False)
        diff_label_fg = "white"; diff_font = ("Arial", 16)
        if points_ahead_of_next is not None: tk.Label(info_block_frame, text=f"{points_ahead_of_next} pts ahead of next", font=diff_font, bg=current_team_color, fg=diff_label_fg).pack(pady=3)
        if points_behind_prev is not None: tk.Label(info_block_frame, text=f"{points_behind_prev} pts behind previous", font=diff_font, bg=current_team_color, fg=diff_label_fg).pack(pady=3)
        team_emblem_photo_local = None; emblem_label_widget = None
        try:
            image_filename = f"{team_name.lower()}.png"
            if not os.path.exists(image_filename): print(f"!!! WARNING: FS - TEAM emblem file not found: {image_filename}")
            else:
                team_emblem_photo_local = tk.PhotoImage(file=image_filename)
                emblem_label_widget = tk.Label(info_block_frame, image=team_emblem_photo_local, bg=current_team_color)
                emblem_label_widget.image = team_emblem_photo_local 
                emblem_label_widget.pack(pady=(20, 0)) 
        except Exception as e: print(f"!!! WARNING: FS - ERROR loading TEAM emblem '{image_filename}': {type(e).__name__} - {e} !!!")
        close_button = tk.Button(info_block_frame, text="Close (or Esc)", font=("Arial", 16), command=self.close_fullscreen_quadrant, bg="gray10", fg="white", activebackground="gray30")
        close_button.pack(pady=(20,0)) 
        top_spacer = tk.Frame(content_frame, bg=current_team_color); top_spacer.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        info_block_frame.pack(side=tk.TOP) 
        bottom_spacer = tk.Frame(content_frame, bg=current_team_color); bottom_spacer.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        
        self.fs_window.bind('<Escape>', lambda e: self.close_fullscreen_quadrant())
        self.fs_window_close_timer = self.root.after(TEMP_FULLSCREEN_DURATION_MS, self.close_fullscreen_quadrant)
        self.fs_window.update_idletasks(); self.fs_window.update()           
        self.fs_window.after(100, self.apply_grab) 

    @staticmethod
    def get_rank_parts_static(rank_str):
        # ... (get_rank_parts_static is unchanged) ...
        if not rank_str: return "", ""
        num_part, suffix_part = "", ""
        for char_idx, char_val in enumerate(rank_str):
            if char_val.isdigit(): num_part += char_val
            else: suffix_part = rank_str[char_idx:]; break
        return num_part, suffix_part

    def close_fullscreen_quadrant(self):
        self.record_activity() # Record activity when FS view is closed
        # ... (rest of close_fullscreen_quadrant is unchanged from previous final version) ...
        if hasattr(self, 'fs_window_close_timer') and self.fs_window_close_timer is not None:
            self.root.after_cancel(self.fs_window_close_timer)
            self.fs_window_close_timer = None 
        if hasattr(self, 'fs_window') and self.fs_window.winfo_exists():
            try: self.fs_window.grab_release()
            except tk.TclError as e: print(f"WARNING: FS - Info during grab_release: {e}") 
            self.fs_window.destroy()
        
if __name__ == "__main__":
    root = tk.Tk()
    app = ScoreboardApp(root)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        print("\nCtrl+C detected. Closing application...")
        app.on_closing()
        print("Application closed by user.")
