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
TEMP_FULLSCREEN_DURATION_MS = 10000 # Back to original application duration
QUADRANT_SEPARATOR_THICKNESS = 1 
TROPHY_ICON_PATH = "trophy.png" 
# TEST_EMBLEM_FILENAME no longer needed

class ScoreboardApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Scoreboard") # Back to original title
        self.root.attributes('-fullscreen', True)

        self.team_points = INITIAL_POINTS.copy()
        self.sorted_teams_cache = []
        self.last_update_time = "Never"
        self.team_colors = { "castile": "darkgreen", "capet": "medium blue", "essex": "purple3", "milan": "firebrick" }
        self.trophy_icon_image = None 
        
        self.main_debug_messages = [] 
        self.main_debug_label = None
        # self.fs_debug_label_ref removed, fs debug will be console only now

        try:
            self.add_main_debug(f"Loading trophy: {os.path.abspath(TROPHY_ICON_PATH)}")
            self.trophy_icon_image = tk.PhotoImage(file=TROPHY_ICON_PATH)
            self.add_main_debug("Trophy icon loaded successfully.")
        except Exception as e:
            self.add_main_debug(f"ERROR loading trophy: {type(e).__name__} - {e}", is_error=True)
            self.trophy_icon_image = None

        self.udp_queue = queue.Queue()
        self.udp_stop_event = threading.Event()
        self.udp_thread = threading.Thread(target=self.udp_listener, daemon=True)

        self.setup_ui()
        self.udp_thread.start()
        self.process_udp_queue()

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.root.bind('<Escape>', lambda e: self.on_closing())

    def add_main_debug(self, message, is_error=False):
        print(message) 
        timestamp = datetime.now().strftime("%H:%M:%S")
        prefix = "ERROR: " if is_error else "DEBUG: "
        self.main_debug_messages.append(f"{timestamp} - {prefix}{message}")
        if len(self.main_debug_messages) > 5: 
            self.main_debug_messages.pop(0)
        if self.main_debug_label and self.main_debug_label.winfo_exists():
            self.main_debug_label.config(text="\n".join(self.main_debug_messages))
            if self.main_debug_label.master.winfo_exists(): # Check master too
                 self.main_debug_label.master.update_idletasks()


    def on_closing(self):
        self.add_main_debug("Closing application...")
        self.udp_stop_event.set()
        if self.udp_thread.is_alive():
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.sendto(b"shutdown", ("127.0.0.1", UDP_PORT))
                sock.close()
            except Exception as e: self.add_main_debug(f"Error sending shutdown packet: {e}", True)
            self.udp_thread.join(timeout=1)
        self.root.quit()
        self.root.destroy()

    def setup_ui(self):
        self.root.configure(bg="black") 
        self.quadrant_container = tk.Frame(self.root, bg="black") 
        self.quadrant_container.pack(fill=tk.BOTH, expand=True)

        self.quadrant_container.grid_rowconfigure(0, weight=1, uniform="row_group")
        self.quadrant_container.grid_rowconfigure(1, weight=1, uniform="row_group")
        self.quadrant_container.grid_columnconfigure(0, weight=1, uniform="col_group")
        self.quadrant_container.grid_columnconfigure(1, weight=1, uniform="col_group")

        self.quadrant_frames_positions = { "1st": (0, 0), "2nd": (0, 1), "3rd": (1, 0), "4th": (1, 1) }
        self.quadrant_display_frames = {} 
        for rank_str, (r, c) in self.quadrant_frames_positions.items():
            content_frame = tk.Frame(self.quadrant_container, bg="gray15") 
            content_frame.grid(row=r, column=c, sticky="nsew", padx=QUADRANT_SEPARATOR_THICKNESS, pady=QUADRANT_SEPARATOR_THICKNESS)
            self.quadrant_display_frames[rank_str] = content_frame

        self.last_updated_var = tk.StringVar(value=f"Last updated: {self.last_update_time}")
        self.last_updated_label = tk.Label(self.root, textvariable=self.last_updated_var, bg="black", fg="white", font=("Arial", 12))
        self.last_updated_label.place(relx=0.5, rely=0.02, anchor="n")

        self.main_debug_label = tk.Label(self.root, text="Starting up...", justify=tk.LEFT, font=("Arial", 8), fg="lightgreen", bg="black", wraplength=self.root.winfo_screenwidth() - 20)
        self.main_debug_label.place(relx=0.5, rely=0.98, anchor="s")
        self.add_main_debug("UI Setup Complete.")
        self.update_display()

    def udp_listener(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.bind((UDP_IP, UDP_PORT))
            self.add_main_debug(f"Listening on {UDP_IP}:{UDP_PORT}")
            sock.settimeout(1.0)
            while not self.udp_stop_event.is_set():
                try:
                    data, addr = sock.recvfrom(1024)
                    decoded_data = data.decode('utf-8').strip()
                    self.udp_queue.put(decoded_data)
                except socket.timeout: continue
                except Exception as e:
                    if not self.udp_stop_event.is_set(): self.add_main_debug(f"UDP Rx Error: {e}", True)
        except OSError as e:
            self.add_main_debug(f"UDP BIND ERROR: {e}", True)
            self.udp_queue.put(f"ERROR: Port {UDP_PORT} in use")
        finally: 
            self.add_main_debug("UDP listener stopping.")
            sock.close()
    
    def process_udp_queue(self):
        try:
            while not self.udp_queue.empty():
                message = self.udp_queue.get_nowait()
                if message.startswith("ERROR:"): 
                    self.last_updated_var.set(message)
                    self.add_main_debug(message, True)
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
                        now = datetime.now(); hour_12 = int(now.strftime('%I')); self.last_update_time = f"{now.month}/{now.day}/{now.strftime('%y')} {hour_12}:{now.minute:02d} {now.strftime('%p')}"
                        self.last_updated_var.set(f"Last updated: {self.last_update_time}")
                        self.update_display()
                    except ValueError: 
                        self.add_main_debug(f"UDP Value Error: {message}", True)
                else: 
                    self.add_main_debug(f"UDP Format Error: {message}", True)
        finally: 
            self.root.after(UPDATE_INTERVAL_MS, self.process_udp_queue)

    def update_display(self):
        self.sorted_teams_cache = sorted(self.team_points.items(), key=lambda item: item[1], reverse=True)
        rank_strings = ["1st", "2nd", "3rd", "4th"]
        for i, (team_name, points) in enumerate(self.sorted_teams_cache):
            rank_str = rank_strings[i]
            quadrant_target_frame = self.quadrant_display_frames[rank_str] 
            for widget in quadrant_target_frame.winfo_children(): 
                widget.destroy()
            self.design_single_quadrant(quadrant_target_frame, team_name, points, rank_str)
        if self.last_updated_label: self.last_updated_label.lift() 
        if self.main_debug_label: self.main_debug_label.lift()

    def design_single_quadrant(self, parent_frame, team_name, team_points, rank_position_str):
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
        lbl_rank_num.pack(side=tk.LEFT, anchor='s')
        lbl_rank_suffix = tk.Label(rank_holder_frame, text=rank_suffix_text, font=font_rank_suffix, bg=current_team_color, fg="white")
        lbl_rank_suffix.pack(side=tk.LEFT, anchor='n', padx=(0, 5))
        elements_to_bind = [parent_frame, lbl_name, lbl_points, rank_holder_frame, lbl_rank_num, lbl_rank_suffix]
        for widget in elements_to_bind: 
            widget.bind("<Button-1>", lambda e, tn=team_name, tp=team_points, rps=rank_position_str: self.show_fullscreen_quadrant(tn, tp, rps))

    def apply_grab(self):
        """Helper function to apply grab after a delay."""
        if hasattr(self, 'fs_window') and self.fs_window.winfo_exists():
            try:
                print(f"DEBUG: FS - Attempting grab_set now for {self.fs_window.title()}")
                self.fs_window.grab_set()
                print(f"DEBUG: FS - Grab applied successfully for {self.fs_window.title()}.")
                self.add_main_debug(f"FS Grab OK for {self.fs_window.title()}") # Log to main screen
            except tk.TclError as e:
                print(f"DEBUG: FS - Error applying grab: {e}")
                self.add_main_debug(f"FS Grab ERR: {e}", True)
        else:
            print("DEBUG: FS - Window closed before delayed grab.")
            self.add_main_debug("FS - Window closed before delayed grab.", True)

    def show_fullscreen_quadrant(self, team_name, team_points, rank_position_str):
        # This is Step 4: Full application logic with DELAYED Grab
        print(f"DEBUG: FS - Opening FULL content for {team_name}") # Console debug
        if hasattr(self, 'fs_window') and self.fs_window.winfo_exists():
            print(f"DEBUG: FS - Destroying existing fs_window for {getattr(self.fs_window, 'title', 'N/A')}")
            self.fs_window.destroy()

        self.fs_window = tk.Toplevel(self.root)
        self.fs_window.title(f"Fullscreen - {team_name.capitalize()}") # Set a title for debug
        
        self.fs_window.attributes('-fullscreen', True) 
        self.fs_window.transient(self.root)      
        # grab_set() will be called by self.apply_grab() after a delay
        
        current_team_color = self.team_colors.get(team_name.lower(), "gray20")
        self.fs_window.configure(bg=current_team_color)

        # --- Main content_frame for centering ---
        content_frame = tk.Frame(self.fs_window, bg=current_team_color)
        content_frame.pack(fill=tk.BOTH, expand=True)
        info_block_frame = tk.Frame(content_frame, bg=current_team_color)

        # --- Score difference calculations ---
        current_team_name_fs = team_name
        current_team_points_fs = team_points
        current_team_rank_str_fs = rank_position_str
        current_team_rank_index = -1
        for i, (name_iter, pts_iter) in enumerate(self.sorted_teams_cache): # Renamed iter vars
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

        # --- Populate info_block_frame (text content first) ---
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
        fs_lbl_rank_num.pack(side=tk.LEFT, anchor='s')
        fs_lbl_rank_suffix = tk.Label(fs_rank_holder_frame, text=fs_rank_suffix_text, font=fs_font_rank_suffix, bg=current_team_color, fg="white")
        fs_lbl_rank_suffix.pack(side=tk.LEFT, anchor='n', padx=(0, 10))

        diff_label_fg = "white"
        diff_font = ("Arial", 16)
        if points_ahead_of_next is not None:
            tk.Label(info_block_frame, text=f"{points_ahead_of_next} pts ahead of next", font=diff_font, bg=current_team_color, fg=diff_label_fg).pack(pady=3)
        if points_behind_prev is not None:
            tk.Label(info_block_frame, text=f"{points_behind_prev} pts behind previous", font=diff_font, bg=current_team_color, fg=diff_label_fg).pack(pady=3)
        
        # --- Load and Display Team Emblem (at the bottom of info_block_frame) ---
        team_emblem_photo_local = None 
        emblem_label_widget = None # Define to ensure it exists for the print statement
        try:
            image_filename = f"{team_name.lower()}.png"
            abs_image_path = os.path.abspath(image_filename)
            print(f"DEBUG: FS - Attempting to load TEAM emblem: {abs_image_path}")
            if not os.path.exists(abs_image_path):
                 print(f"!!! WARNING: FS - TEAM emblem file not found: {abs_image_path}")
            else:
                team_emblem_photo_local = tk.PhotoImage(file=image_filename)
                emblem_label_widget = tk.Label(info_block_frame, image=team_emblem_photo_local, bg=current_team_color)
                emblem_label_widget.image = team_emblem_photo_local 
                emblem_label_widget.pack(pady=(20, 0)) 
                print(f"DEBUG: FS - TEAM emblem {image_filename} loaded and packed.")
        except Exception as e: # Catch broad exceptions for image loading
            print(f"!!! WARNING: FS - ERROR loading TEAM emblem '{image_filename}': {type(e).__name__} - {e} !!!")
        
        close_button = tk.Button(info_block_frame, text="Close (or Esc)", font=("Arial", 16), command=self.close_fullscreen_quadrant, bg="gray10", fg="white", activebackground="gray30")
        close_button.pack(pady=(20,0)) 

        # --- Centering the info_block_frame vertically ---
        top_spacer = tk.Frame(content_frame, bg=current_team_color)
        top_spacer.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        info_block_frame.pack(side=tk.TOP) 
        bottom_spacer = tk.Frame(content_frame, bg=current_team_color)
        bottom_spacer.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        
        # --- Bindings and Timers ---
        self.fs_window.bind('<Escape>', lambda e: self.close_fullscreen_quadrant())
        # Click to close might be too easy to trigger accidentally now with full content.
        # You can re-enable if desired:
        # self.fs_window.bind('<Button-1>', lambda e: self.close_fullscreen_quadrant()) 
        self.fs_window_close_timer = self.root.after(TEMP_FULLSCREEN_DURATION_MS, self.close_fullscreen_quadrant)
        
        # --- Force window to draw and then attempt grab ---
        print(f"DEBUG: FS - Forcing update for {self.fs_window.title()} before delayed grab.")
        self.fs_window.update_idletasks() 
        self.fs_window.update()           
        self.fs_window.after(100, self.apply_grab) # Call apply_grab after 100ms

        print(f"DEBUG: FS - Full content for {team_name} setup complete. Grab scheduled.")

    @staticmethod
    def get_rank_parts_static(rank_str):
        if not rank_str: return "", ""
        num_part, suffix_part = "", ""
        for char_idx, char_val in enumerate(rank_str):
            if char_val.isdigit(): num_part += char_val
            else: suffix_part = rank_str[char_idx:]; break
        return num_part, suffix_part

    def close_fullscreen_quadrant(self):
        self.add_main_debug("FS - close_fullscreen_quadrant called")
        if hasattr(self, 'fs_window_close_timer') and self.fs_window_close_timer is not None:
            self.root.after_cancel(self.fs_window_close_timer)
            self.fs_window_close_timer = None # Clear it
        
        if hasattr(self, 'fs_window') and self.fs_window.winfo_exists():
            try:
                self.fs_window.grab_release()
                self.add_main_debug("FS - Grab released.")
            except tk.TclError as e:
                self.add_main_debug(f"FS - Info during grab_release: {e}")
            
            self.fs_window.destroy()
            self.add_main_debug("FS - Window destroyed.")
            # Consider 'del self.fs_window' if you want to be very explicit,
            # but reassigning in show_fullscreen_quadrant also replaces it.
            # For now, let's rely on the hasattr check.
        else:
            self.add_main_debug("FS - fs_window did not exist or was already destroyed.", True)

if __name__ == "__main__":
    root = tk.Tk()
    app = ScoreboardApp(root)
    root.mainloop()
