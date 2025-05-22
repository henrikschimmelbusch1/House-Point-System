import tkinter as tk
from tkinter import messagebox
import socket

# Default values - can be changed in the GUI
DEFAULT_PI_IP = "192.168.1.100" # <--- CHANGE THIS TO YOUR RASPBERRY PI'S ACTUAL IP ADDRESS
DEFAULT_UDP_PORT = 12345
TEAM_NAMES_ORDER = ["castile", "capet", "essex", "milan"] # Order for packet construction

class UDPSenderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Score Sender")
        self.root.geometry("350x300") # Adjusted size for better fit

        # --- Variables ---
        self.ip_var = tk.StringVar(value=DEFAULT_PI_IP)
        self.port_var = tk.StringVar(value=str(DEFAULT_UDP_PORT))
        self.status_var = tk.StringVar(value="Enter scores and IP/Port.")

        self.score_entries = {} # To store Entry widgets for scores
        self.score_vars = {}    # To store StringVars for scores

        # --- UI Elements ---
        # IP Address
        tk.Label(root, text="Target IP:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        ip_entry = tk.Entry(root, textvariable=self.ip_var, width=20)
        ip_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        # Port
        tk.Label(root, text="Target Port:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        port_entry = tk.Entry(root, textvariable=self.port_var, width=10)
        port_entry.grid(row=1, column=1, padx=5, pady=5, sticky="w") # sticky w for port

        # Score Entries
        current_row = 2
        for team_name in TEAM_NAMES_ORDER:
            tk.Label(root, text=f"{team_name.capitalize()}:").grid(row=current_row, column=0, padx=5, pady=5, sticky="w")
            score_var = tk.StringVar(value="0") # Default score to 0
            score_entry = tk.Entry(root, textvariable=score_var, width=10)
            score_entry.grid(row=current_row, column=1, padx=5, pady=5, sticky="w") # sticky w for score
            
            self.score_vars[team_name] = score_var
            self.score_entries[team_name] = score_entry # Not strictly needed but good to have
            current_row += 1

        # Send Button
        send_button = tk.Button(root, text="Send Scores", command=self.send_scores)
        send_button.grid(row=current_row, column=0, columnspan=2, padx=5, pady=10)

        # Status Label
        status_label = tk.Label(root, textvariable=self.status_var, relief=tk.SUNKEN, anchor="w")
        status_label.grid(row=current_row + 1, column=0, columnspan=2, padx=5, pady=5, sticky="ew")

        # Configure column weights for resizing if window were resizable
        root.grid_columnconfigure(1, weight=1)


    def send_scores(self):
        target_ip = self.ip_var.get()
        try:
            target_port = int(self.port_var.get())
            if not (0 < target_port < 65536):
                raise ValueError("Port must be between 1 and 65535")
        except ValueError as e:
            messagebox.showerror("Invalid Port", f"Error: {e}")
            self.status_var.set(f"Error: Invalid port - {e}")
            return

        scores_list = []
        try:
            for team_name in TEAM_NAMES_ORDER:
                score_str = self.score_vars[team_name].get()
                score_val = int(score_str) # Ensure it's an integer
                scores_list.append(str(score_val)) # Keep as string for join
            
            # Construct message in the format: {castile}:{capet}:{essex}:{milan}
            # The order is determined by TEAM_NAMES_ORDER
            message_str = ":".join(scores_list)
            message_bytes = message_str.encode('utf-8')

            # Send UDP packet
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.sendto(message_bytes, (target_ip, target_port))
            sock.close()

            self.status_var.set(f"Sent: {message_str} to {target_ip}:{target_port}")
            print(f"Sent: {message_str} to {target_ip}:{target_port}")

        except ValueError:
            messagebox.showerror("Invalid Score", "Error: Scores must be integers.")
            self.status_var.set("Error: Scores must be integers.")
        except socket.gaierror: # For IP address resolution errors
            messagebox.showerror("Invalid IP", f"Error: Could not resolve IP address '{target_ip}'.")
            self.status_var.set(f"Error: Invalid IP '{target_ip}'.")
        except Exception as e:
            messagebox.showerror("Send Error", f"An error occurred: {e}")
            self.status_var.set(f"Error: {e}")


if __name__ == "__main__":
    sender_root = tk.Tk()
    app = UDPSenderApp(sender_root)
    sender_root.mainloop()
