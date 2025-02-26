import tkinter as tk
import vlc
import os
import time
import urllib.request
from urllib.parse import quote
from io import BytesIO
from PIL import Image as PILImage
from moviepy.editor import ImageSequenceClip
import yt_dlp
from getmac import get_mac_address
from Crypto.Cipher import AES
import base64
import pyperclip
from Crypto.Util.Padding import pad
import requests
import pystray
from PIL import Image as PILImage
import threading
from datetime import datetime
import sys
import keyboard
from pynput import mouse
from tkinter import messagebox
import pygetwindow as gw
import pyautogui
import signal
import re  # Fuck regex
import logging
import ctypes
import socket
import json

current_app = None


# Define exception logging
def log_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logging.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))


# Assign the custom exception handler
sys.excepthook = log_exception


class MultimediaPlayerApp:
    def __init__(self, root):
        self.media_data = []
        self.root = root
        self.root.title("Multimedia Player")
        print("App initialized")
        self.root.attributes("-fullscreen", True)
        self.listener = mouse.Listener(on_click=self.on_click)
        self.listener.start()
        self.max_attempts = 1000
        self.attempt = 1
        self.vlc_window_keyword = "VLC"

        self.stop_playing = False  # Flag
        self.message_displayed = False  # flag

        # Initialize VLC player
        self.vlc_player = vlc.MediaPlayer()

        self.license_entry = tk.Entry(self.root)
        self.license_entry.pack(pady=10)
        self.license_popup = None
        self.vigencia_popup = None
        self.temp_label = None
        self.list_popup = None
        self.listas_frame = None  # Initialize listas_frame as None
        self.selected_list_id = tk.IntVar()  # Variable to hold the selected list ID

        self.list_var = tk.StringVar()
        self.lista_id = None

        self.listas_frame = tk.Frame(self.root)
        self.listas_frame.pack(pady=10)

        # Base URL for media
        self.base_url = "https://pd.solytecmx.com/storage/"

        # Base path for storing downloaded media
        appdata_dir = os.getenv("APPDATA")
        # Set the base path to be PDdata/multimedia
        self.base_path = os.path.join(appdata_dir, "PDdata")
        os.makedirs(os.path.join(self.base_path, "logs"), exist_ok=True)
        os.makedirs(os.path.join(self.base_path, "multimedia"), exist_ok=True)
        os.makedirs(os.path.join(self.base_path, "offlinedata"), exist_ok=True)
        self.media_file = os.path.join(
            os.makedirs(os.path.join(self.base_path, "offlinedata"), exist_ok=True)
            or os.path.join(self.base_path, "offlinedata"),
            "media_data.json",
        )
        self.license_data_offline = os.path.join(
            os.makedirs(os.path.join(self.base_path, "offlinedata"), exist_ok=True)
            or os.path.join(self.base_path, "offlinedata"),
            "licence_data_offline.json",
        )

        # Rest API Routes
        self.web_service_url = "https://pd.solytecmx.com/EquipoAddLicense/"
        self.web_servicegetinfodevice = "https://pd.solytecmx.com/EquipoInfoGet/"
        self.web_service_licensetrueorfalse = "https://pd.solytecmx.com/HasLicense/"
        self.web_service_get_lists = "https://pd.solytecmx.com/GetListasByMac/"
        self.web_service_get_media_for_list = "https://pd.solytecmx.com/GetListaData/"

        # self.fetch_listas(window=self.list_popup)

        self.current_media_index = 0
        self.media_playing = False

        # Set up system tray icon
        icon_image = PILImage.open("favicon.ico")
        self.tray_icon = pystray.Icon(
            "Multimedia Player",
            icon_image,
            menu=pystray.Menu(
                pystray.MenuItem("Reproducir", self.check_and_play_media),
                pystray.MenuItem(
                    "Copiar Device Key",
                    lambda: self.copy_to_clipboard(self.encrypt_mac(self.get_mac())),
                ),
                pystray.MenuItem("Licencia", self.open_license_popup),
                pystray.MenuItem("Cerrar", self.quit_app),
            ),
        )

        # Hide the root window initially (it will be controlled via the tray icon)
        self.root.withdraw()

        # Start the tray icon in a separate thread
        self.start_tray_icon()

        # If the device has an active license, play media directly, no need for extra processes.
        if self.is_internet_available():
            self.check_and_play_media()
        else:
            self.fetch_listas_offline()

    def stop_app(self):
        print("Stopping the multimedia player...")
        if self.vlc_player is not None:
            if self.vlc_player.is_playing():
                self.vlc_player.stop()  # Stop the VLC player
            self.vlc_player.release()  # Release VLC player resources
            self.vlc_player = None  # Set to None to prevent further access

    def on_click(self, x, y, button, pressed):
        # Check if the VLC window exists and is active
        vlc_window = gw.getWindowsWithTitle("VLC (Direct3D11 output)")
        if vlc_window and vlc_window[0].isActive:
            if button == mouse.Button.left and pressed:
                print(f"Left button clicked at ({x}, {y}) in VLC window.")
                self.stop_playing = True
                self.quit_app()

    def restart_multimedia_player(self):
        """Reinicia la aplicación multimedia correctamente."""
        print("Reiniciando el reproductor multimedia...")

        self.quit_app()  # Cierra la app actual

        global current_app
        current_app = None  # Borra la referencia actual

        # Espera 1 segundo antes de reiniciar para evitar bloqueos
        self.root.after(1000, self.start_new_instance)

    def start_new_instance(self):
        """Crea una nueva instancia del reproductor multimedia."""
        print("Iniciando nueva instancia...")

        self.root.destroy()  # Asegura que la ventana anterior se cierre correctamente

        new_root = tk.Tk()  # Crea una nueva ventana
        global current_app
        current_app = MultimediaPlayerApp(new_root)
        new_root.mainloop()

    def restart_app(self):
        self.restart_multimedia_player()

    def start_tray_icon(self):
        tray_thread = threading.Thread(target=self.tray_icon.run)
        tray_thread.daemon = True
        tray_thread.start()

    def stop_tray_icon(self):
        if self.tray_icon is not None:
            self.tray_icon.stop()
            self.tray_icon = None

    def show_window(self):
        self.root.deiconify()
        self.tray_icon.stop()

    def quit_app(self):
        self.tray_icon.stop()
        self.stop_app()

    def parse_date_range(self, date_range_str):
        try:
            start_str, end_str = date_range_str.split(" al ")
            start_date = datetime.strptime(start_str.strip(), "%d/%m/%Y")
            end_date = datetime.strptime(end_str.strip(), "%d/%m/%Y")
            return start_date, end_date
        except ValueError:
            return None, None

    def check_and_play_media(self):

        self.fetch_listas(window=self.list_popup)
        license_status = self.check_license_status()
        self.attempt += 1
        self.sync_media_files()

        if license_status.get("has_license", False):

            license_dates_str = license_status.get("license_dates", "")
            start_date, end_date = self.parse_date_range(license_dates_str)

            current_date = datetime.now()

            if start_date and end_date and end_date >= current_date:

                date_diff = (end_date - start_date).days
                if date_diff >= 2:

                    self.play_media()
                else:
                    self.show_user_message("Activar Licencia")
            else:
                print("Licencia caducada o no valida")
                self.show_user_message("Licencia Caducada o No Valida")
        else:
            self.show_user_message("Solicitar Licencia")

    def open_license_popup(self, icon, item):
        """Opens a popup window for license management."""
        if self.license_popup and self.license_popup.winfo_exists():
            print("License popup is already open.")
            # Bring the existing popup to the front and focus on it
            self.license_popup.lift()
            self.license_popup.focus()
            return
        else:
            # Create a small popup window for license management
            self.license_popup = tk.Toplevel(self.root)
            self.license_popup.title("Manejador de licencia")

            # Set the dimensions for the popup
            width, height = 300, 200
            screen_width = self.license_popup.winfo_screenwidth()
            screen_height = self.license_popup.winfo_screenheight()

            # Calculate x, y coordinates to center the popup
            x = (screen_width // 2) - (width // 2)
            y = (screen_height // 2) - (height // 2)

            # Set the geometry for the popup
            self.license_popup.geometry(f"{width}x{height}+{x}+{y}")

            # Fetch and display current license status
            license_status = self.check_license_status()
            self.current_license_status = license_status

            # License Entry and Label
            license_label = tk.Label(self.license_popup, text="Licencia:")
            license_label.pack(pady=10)

            self.license_entry = tk.Entry(self.license_popup)

            # Safeguard against non-string or missing values
            license_number = license_status.get("license_number", "Enter license")
            if license_number is None:
                license_number = "Ingresa tu licencia"  # Default fallback text

            try:
                self.license_entry.insert(0, str(license_number))  # Ensure string type
            except tk.TclError as e:
                print(f"TclError: {e}")
                self.license_entry.insert(
                    0, "Ingresa tu licencia"
                )  # Fallback to default text

            self.license_entry.pack(pady=10)
            """Checks for changes on the keyboard to check the license."""
            self.license_entry.bind("<KeyRelease>", self.check_license_length)
            self.license_entry.bind("<Control-v>", self.check_license_length)

            # Create and pack the submit button
            submit_button = tk.Button(
                self.license_popup,
                text="Verificar Licencia",
                command=self.submit_license,
            )
            submit_button.pack(pady=10)

            # License validity information and popup update
            self.update_license_status(license_status)

            # Debugging Logs (Optional)
            print(f"License status: {license_status}")
            print(f"License number: {license_number}, Type: {type(license_number)}")

            self.submit_license()

    def update_license_status(self, license_status):
        """Updates the popup with the license status information reactively."""
        validity_label_text = "Licencia no válida"

        if license_status.get("has_license", False):
            license_dates_str = license_status.get("license_dates", "")
            start_date, end_date = self.parse_date_range(license_dates_str)

            current_date = datetime.now()

            if start_date and end_date:
                if end_date >= current_date:
                    validity_label_text = f"Licencia válida del: {start_date.strftime('%Y-%m-%d')} al {end_date.strftime('%Y-%m-%d')}"
                    self.show_temp_message("Licencia válida, dispositivo autorizado")
                else:
                    validity_label_text = "Licencia expirada"
                    self.show_temp_message_error(
                        "Licencia expirada, dispositivo no autorizado"
                    )
            else:
                validity_label_text = "Licencia expirada"
                self.show_temp_message_error(
                    "Licencia expirada, dispositivo no autorizado"
                )
        else:
            validity_label_text = "Licencia no encontrada"
            self.show_temp_message_error("Licencia no existente")

        # Update the validity label dynamically without recreating it
        if hasattr(self, "vigencia_popup") and self.vigencia_popup:
            self.vigencia_popup.config(text=validity_label_text)
        else:
            # Create the label if it doesn't exist
            self.vigencia_popup = tk.Label(self.license_popup, text=validity_label_text)
            self.vigencia_popup.pack(pady=10)

        # Stop media playback if the license is not valid
        if (
            validity_label_text == "Licencia expirada"
            or validity_label_text == "Licencia no encontrada"
        ):
            self.stop_media_playback()

    def check_license_length(self, event):
        """Checks if the license length is valid and submits if complete."""
        license_text = self.license_entry.get()
        required_length = 19  # Required length for the license

        if len(license_text) == required_length:
            print("License length is valid, submitting...")
            self.submit_license()

    def get_mac(self):
        # Retrieve the MAC address of the device
        return get_mac_address()

    @staticmethod
    def encrypt_mac(mac):
        key = "desencriptar1234".encode("utf-8")
        cipher = AES.new(key, AES.MODE_ECB)
        padded_mac = pad(mac.encode("utf-8"), AES.block_size)
        encrypted = cipher.encrypt(padded_mac)
        return base64.urlsafe_b64encode(encrypted).decode("utf-8")

    def copy_to_clipboard(self, text):
        pyperclip.copy(text)
        print("Encrypted MAC Address copied to clipboard")

    def submit_license(self):
        license_key = self.license_entry.get()
        encrypted_mac = self.encrypt_mac(self.get_mac())
        full_url = f"{self.web_service_url}{encrypted_mac}"

        data = {"licencia": license_key, "mac": encrypted_mac}
        print(f"Submitting to URL: {full_url}")
        print(f"Data: {data}")

        response = requests.post(full_url, json=data)
        response_data = response.json()
        message = response_data.get("message", "No message received")

        # Debugging output for message type and value
        print(f"Message Type: {type(message)} - Value: {message}")
        if message == "Licencia expirada":
            self.show_user_message_once(message)
            self.stop_app()  # Stop media if license is expired
            return
        elif message == "Licencia no encontrada":
            self.show_user_message_once("Licencia no existente")
            self.stop_app()  # Stop media if license is not found
            return

        if response.status_code == 200:
            # Check for expiration message
            if message == "Licencia expirada":
                self.show_user_message_once(message)
                self.stop_media_playback()  # Stop media if license is expired
                return

            # Check for invalid license
            if message == "Licencia no encontrada":
                self.show_user_message_once("Licencia no existente")
                self.stop_app()  # Stop media if license is not found
                return

            self.show_temp_message(message)

            # Validate license status and dates
            license_status = response_data.get("license_status", {})

            if license_status.get("has_license", False):
                license_dates_str = license_status.get("license_dates", "")
                start_date, end_date = self.parse_date_range(license_dates_str)
                current_date = datetime.now()

                if start_date and end_date:
                    if end_date >= current_date:
                        validity_label_text = f"Licencia válida del: {start_date.strftime('%Y-%m-%d')} al {end_date.strftime('%Y-%m-%d')}"
                        self.show_temp_message(
                            "Licencia válida, dispositivo autorizado"
                        )
                    else:
                        validity_label_text = "Licencia expirada"
                        self.show_temp_message_error(
                            "Licencia expirada, dispositivo no autorizado"
                        )
                else:
                    validity_label_text = "Licencia expirada"
                    self.show_temp_message_error(
                        "Licencia expirada, dispositivo no autorizado"
                    )

                self.vigencia_popup = tk.Label(
                    self.license_popup, text=validity_label_text
                )
                self.vigencia_popup.pack(pady=10)

            # Start media playback if necessary
            if not self.is_media_playing():
                self.ask_to_start_playback()
        else:
            self.show_temp_message_error("Licencia no válida")
            print(f"Message Type: {type(message)} - Value: {message}")

    def download_and_play_youtube(self, youtube_url):
        try:
            # Define the base directory for saved videos
            directory = "videos"
            dir_path = os.path.join(self.base_path, "multimedia", directory)

            # Ensure the directory exists
            if not os.path.exists(dir_path):
                os.makedirs(dir_path)

            # ydl_opts with ffmpeg location and output template
            ydl_opts = {
                "format": "bestvideo+bestaudio",  # Download best video and audio
                "merge_output_format": "mp4",  # Merge into mp4 format
                "outtmpl": os.path.join(dir_path, "%(id)s.%(ext)s"),  # Output template
                "ffmpeg_location": r"C:\ffmpeg\bin",  # Path to ffmpeg's directory
                "noplaylist": True,  # Prevent downloading playlists
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Extract video info without downloading
                info_dict = ydl.extract_info(youtube_url, download=False)
                file_name = ydl.prepare_filename(info_dict)
                file_path = os.path.join(dir_path, os.path.basename(file_name))

                # Check if the file already exists
                if os.path.exists(file_path):
                    print(f"File already exists: {file_path}")
                    return file_path

                # Download the video
                ydl.download([youtube_url])
                print(f"Downloaded: {file_path}")
                return file_path

        except Exception as e:
            print(f"Error downloading YouTube video: {e}")
            return None

    def show_temp_message(self, message, duration=3):
        if not self.license_popup:
            print("License popup is not available.")

            return

        # Create a label to show the message
        self.temp_label = tk.Label(self.license_popup, text=message, fg="green")
        self.temp_label.pack(pady=10)

        # Hide the label after a specified duration
        # self.license_popup.after(duration * 1000, self.hide_temp_message)

    def show_temp_message_error(self, message, duration=3):
        if not self.license_popup:
            print("License popup is not available.")
            return
        # Create a label to show the message
        self.temp_label = tk.Label(self.license_popup, text=message, fg="red")
        self.temp_label.pack(pady=10)

        # Hide the label after a specified duration
        self.license_popup.after(duration * 1000, self.hide_temp_message)

    def hide_temp_message(self):
        if hasattr(self, "temp_label"):
            self.temp_label.pack_forget()

    def download_media(self, media_url):
        # Encode the URL to handle spaces and other special characters
        encoded_url = urllib.parse.quote(media_url, safe=":/")
        print("download_media_function")
        print(media_url)

        # Determine the directory and file type based on the URL
        if (
            encoded_url.endswith(".mp4")
            or encoded_url.endswith(".MP4")
            or "youtube.com" in media_url
            or "youtu.be" in media_url
        ):
            directory = "videos"
        elif (
            encoded_url.endswith(".png")
            or encoded_url.endswith(".jpg")
            or encoded_url.endswith(".jpeg")
            or encoded_url.endswith(".PNG")
            or encoded_url.endswith(".JPG")
            or encoded_url.endswith(".JPEG")
        ):
            directory = "images"
        else:
            return None

        # Create the full path to the directory
        dir_path = os.path.join(self.base_path, "multimedia", directory)
        print("FLAG PARA VER DONDE SE DESCARGAN", dir_path)

        # Ensure the directory exists
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)

        # Extract the filename from the URL
        filename = os.path.basename(media_url)
        file_path = os.path.join(dir_path, filename)

        # Check if the file already exists
        if os.path.exists(file_path):
            print(f"File already exists: {file_path}")
            return file_path  # Return the path of the existing file

        # Download the media file
        try:
            if "youtube.com" in media_url or "youtu.be" in media_url:
                file_path = self.download_and_play_youtube(media_url)
            else:
                urllib.request.urlretrieve(encoded_url, file_path)
                print(f"Downloaded new media file: {filename}")

            return file_path

        except Exception as e:
            print(f"Error downloading media: {e}")
            return None

    def play_media(self):
        # Check if the device has a valid license
        self.media_playing = False
        self.stop_playing = False
        self.play_next_media()

    def play_next_media(self):
        if self.stop_playing:  # Check if we should stop playing
            print("Stopping playback of the next media.")
            return

        if self.vlc_player is not None:
            self.vlc_player.set_fullscreen(True)
            self.vlc_player.video_set_mouse_input(False)
        else:
            self.restart_app()

        if not self.media_data:
            print("No media data available.")
            return  # Exit if no media to play

        if self.current_media_index >= len(self.media_data):
            print(
                "End of media list reached. Waiting for media to finish before restarting..."
            )

            # Stop VLC player and reset everything
            if not self.media_playing:
                self.vlc_player.stop()  # Stop the current media player
                # Call your restart function to restart everything
                self.restart_app()

            return

        media_item = self.media_data[self.current_media_index]

        if "data" not in media_item:
            print("data not in media_item")
            print(media_item)
            self.handle_missing_media()
            return

        media_url = media_item["data"]
        print(f"Playing media: {media_url}")

        # Determine the local file path based on media type
        if "youtube.com" in media_url or "youtu.be" in media_url:
            local_file_path = self.get_youtube_local_path(
                media_url
            )  # Get local path of YouTube video
        else:
            category = "videos" if ".mp4" in media_url else "images"
            local_file_path = os.path.join(
                self.base_path,
                "multimedia",
                category,
                os.path.basename(urllib.parse.unquote(media_url)),
            )
        # Ensure the local file exists before playing
        if not os.path.exists(local_file_path):
            print(f"Local file does not exist: {local_file_path}")
            self.handle_missing_media()
            return

        # Play video or image depending on the media type
        if local_file_path.endswith(".mp4"):
            self.media_playing = False
            self.play_video(local_file_path)
        else:
            self.media_playing = False
            duration = int(media_item.get("tiempo", 5))
            self.play_image(local_file_path, duration)

        self.current_media_index += 1
        print(f"Current Index: {self.current_media_index}")
        print(f"Total Media Count: {len(self.media_data)}")

    def handle_missing_media(self):
        print("Media is missing or cannot be downloaded. Skipping to the next media.")
        self.current_media_index = self.current_media_index + 1

        # self.root.after(2000, self.play_media)  # Wait for 1 second before restarting

    def play_video(self, media_path):
        if not os.path.exists(media_path):
            print(f"Video file does not exist: {media_path}")
            return

        media = vlc.Media(media_path)
        self.vlc_player.set_media(media)

        if not self.media_playing:
            self.vlc_player.play()
            self.media_playing = True

        # Attach the media end event to the handler
        self.vlc_player.event_manager().event_attach(
            vlc.EventType.MediaPlayerEndReached, self.on_media_end
        )

    def play_image(self, media_path, duration):
        if os.path.exists(media_path):
            media = vlc.Media(media_path)
            self.vlc_player.set_media(media)

            if not self.media_playing:
                self.vlc_player.play()
                self.media_playing = True

            # Schedule to move to the next media after the image is shown
            self.root.after(duration * 1000, self.on_media_end)

    def on_media_end(self, event=None):
        print("Media has ended.")
        self.media_playing = False
        self.root.after(5000, self.play_next_media)

    def check_license_status(self):
        encrypted_mac = self.encrypt_mac(self.get_mac())
        full_url = f"{self.web_service_licensetrueorfalse}{encrypted_mac}"
        print(f"Checking license status at: {full_url}")
        response = requests.get(full_url)

        if response.status_code == 200:
            license_data = response.json()
            self.save_license_data_offline(license_data)
            return response.json()

        return {}

    def toggle_fullscreen(self, event=None):
        self.root.attributes("-fullscreen", not self.root.attributes("-fullscreen"))

    def sync_media_files(self):
        self.fetch_listas(window=self.list_popup)
        # Retry mechanism using a loop
        while not self.lista_id and self.attempt < self.max_attempts:
            print("No list selected. Trying again.")
            self.fetch_listas(window=self.list_popup)
            self.attempt += 1
            time.sleep(2)

            if not self.lista_id:
                license_status = self.check_license_status()
                print("Max attempts reached. Aborting.")
                print("Checando listas offline guardadas")
                if os.path.exists(self.media_file):
                    if license_status.get("has_license", False):
                        self.fetch_listas_offline()
                else:
                    self.show_user_message(
                        "Error: No se encontró ninguna lista asociada a este equipo. Verifique su configuración en: pd.solytecmx.com"
                    )
                self.attempt = 1  # Reset for future calls
                return

        # Reset attempt counter since a list is selected
        self.attempt = 1

        # Get media data for the selected list
        self.current_media_index = 0  # Reset index to start new cycle
        self.media_data = []
        self.media_data = self.get_media_data_for_list()
        print(self.media_data)

        # Extract URLs of media from the web service response
        media_urls = [item["data"] for item in self.media_data]

        # Determine local file paths
        expected_local_files = []
        for url in media_urls:
            if "youtube.com" in url or "youtu.be" in url:
                local_file_path = self.get_youtube_local_path(url)
                expected_local_files.append(local_file_path)
            else:
                category = "videos" if url.endswith(".mp4") else "images"
                local_file_path = os.path.join(
                    self.base_path,
                    "multimedia",
                    category,
                    os.path.basename(urllib.parse.unquote(url)),
                )
                expected_local_files.append(local_file_path)

        # Get lists of local video and image files
        local_videos = self.list_local_files("videos")
        local_images = self.list_local_files("images")

        # Identify files to remove (not in the web service data anymore)
        files_to_remove = {
            "videos": [
                file
                for file in local_videos
                if not any(
                    (
                        file in os.path.basename(self.get_youtube_local_path(url))
                        if ("youtube.com" in url or "youtu.be" in url)
                        else os.path.basename(urllib.parse.unquote(url))
                    )
                    for url in media_urls
                )
            ],
            "images": [
                file
                for file in local_images
                if not any(file in url for url in media_urls)
            ],
        }

        # Remove obsolete files
        for category, files in files_to_remove.items():
            for file in files:
                file_path = os.path.join(self.base_path, "multimedia", category, file)
                if os.path.exists(file_path):
                    os.remove(file_path)
                    print(f"Removed obsolete file: {file_path}")

        # Download new files if necessary
        for media_item in self.media_data:
            media_url = media_item["data"]

            if "youtube.com" in media_url or "youtu.be" in media_url:
                local_file_path = self.get_youtube_local_path(media_url)
                if not os.path.exists(local_file_path):
                    self.download_and_play_youtube(media_url)
                    print(
                        f"Downloaded new YouTube media file: {os.path.basename(local_file_path)}"
                    )
            else:
                category = "videos" if ".mp4" in media_url else "images"
                local_file_path = os.path.join(
                    self.base_path,
                    "multimedia",
                    category,
                    os.path.basename(urllib.parse.unquote(media_url)),
                )
                if not os.path.exists(local_file_path):
                    self.download_media(media_url)
                    print(
                        f"Downloaded new media file: {os.path.basename(local_file_path)}"
                    )

    def get_video_name_from_url(self, youtube_url):
        # For example, if you use yt-dlp, you might want to use a similar logic:
        info = yt_dlp.YoutubeDL().extract_info(youtube_url, download=False)
        return info["title"]  # Adjust according to your naming convention

    def get_youtube_local_path(self, youtube_url):
        # Use regex to extract the video ID from various YouTube URL formats
        match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", youtube_url)
        video_id = match.group(1) if match else None

        # If a video ID is found, generate the file path; otherwise, return None
        if video_id:
            return os.path.join(
                self.base_path, "multimedia", "videos", f"{video_id}.mp4"
            )
        else:
            print("Invalid YouTube URL format.")
            return None

    def list_local_files(self, category):
        dir_path = os.path.join(self.base_path, "multimedia", category)
        if not os.path.exists(dir_path):
            return []
        return os.listdir(dir_path)

    def get_media_data(self):
        encrypted_mac = self.encrypt_mac(self.get_mac())
        params = {"lista_id": self.lista_id} if self.lista_id else {}
        full_url = f"{self.web_servicegetinfodevice}{encrypted_mac}"
        print(f"Requesting media data from: {full_url} with params: {params}")
        response = requests.get(full_url, params=params)

        if response.status_code == 200:
            media_data = response.json()
            return media_data
        else:
            print(f"Error fetching media data: {response.status_code}")
            return []

    def select_list(self, lista_id):
        self.lista_id = lista_id
        print(f"Selected list ID: {self.lista_id}")
        self.list_popup.destroy()
        self.play_media()  # Start playing media for the selected list

    def fetch_listas(self, window):
        self.media_data = []

        if not self.is_internet_available():
            self.fetch_listas_offline()
        else:

            def fetch_data():
                encrypted_mac = self.encrypt_mac(self.get_mac())
                full_url = f"{self.web_service_get_lists}{encrypted_mac}"
                print(f"Requesting lists from: {full_url}")

                try:
                    response = requests.get(full_url)

                    # Check for non-2xx status codes without raising an exception
                    if response.status_code == 404:
                        print(f"Received 404 error for URL: {full_url}")
                        try:
                            # Attempt to parse the JSON response
                            error_data = response.json()
                            if "error" in error_data:
                                print(f"API error: {error_data['error']}")
                                # self.show_user_message_once(
                                #     "Error: No se encontró ningúna lista asociada a este equipo asociado. Verifique su configuración en: pd.solytecmx.com"
                                # )
                            else:
                                print("Unexpected 404 response format:", error_data)
                        except ValueError:
                            print("Error parsing JSON from 404 response.")
                        if window:
                            window.after(0, self.update_listas_window, [])
                        return

                    # Raise an exception for other HTTP errors
                    response.raise_for_status()

                    # Process valid responses
                    listas = response.json()
                    print("Response received:", listas)

                    if isinstance(listas, list) and listas:
                        lista = listas[0]
                        self.lista_id = lista.get("id_lista")
                        if self.lista_id is not None:
                            print(
                                f"Automatically selected list with ID: {self.lista_id}"
                            )
                            if window:
                                window.after(0, self.update_listas_window, listas)
                        else:
                            self.fetch_listas()
                    else:
                        print("No lists found or unexpected data format:", listas)
                        self.show_user_message_once(
                            "No se encontró ninguna lista o no se ha seleccionado ninguna lista."
                        )
                        if window:
                            window.after(0, self.update_listas_window, [])

                except requests.exceptions.RequestException as e:
                    print(f"Error fetching lists: {e}")
                    self.show_user_message_once(
                        "Error de conexión con el servidor. Verifique su conexión a Internet."
                    )
                    if window:
                        window.after(0, self.update_listas_window, [])

                except ValueError as e:
                    print(f"Error parsing JSON: {e}")
                    self.show_user_message_once(
                        "Error al procesar la respuesta del servidor. Contacte al soporte técnico."
                    )
                    if window:
                        window.after(0, self.update_listas_window, [])

            threading.Thread(target=fetch_data).start()

    def update_listas_window(self, listas):
        # Clear the frame
        self.media_data = []
        for widget in self.listas_frame.winfo_children():
            widget.destroy()

        if not listas:
            print("No listas data available.")
            return
        # Populate the frame with listas data
        for lista in listas:
            lista_radio = tk.Radiobutton(
                self.listas_frame,
                text=lista.get("nombre", "Unnamed List"),
                variable=self.selected_list_id,
                value=lista["id_lista"],
            )
            lista_radio.pack(anchor="w")

    def on_list_selected(self, window, selected_list_id):
        self.media_data = []
        print(f"Selected List ID: {selected_list_id}")
        # Perform any necessary actions with the selected list ID
        window.destroy()

    def get_media_data_for_list(self):
        if not self.lista_id:
            print("No list selected.")
            return []

        # Construct the URL to fetch media data for the selected list
        encrypted_mac = self.encrypt_mac(self.get_mac())
        full_url = f"{self.web_service_get_media_for_list}{self.lista_id}"
        print(f"Requesting media data from: {full_url}")

        try:
            response = requests.get(full_url)
            response.raise_for_status()  # Raise an error if the request failed
            media_data = response.json()  # Assuming the response is JSON
            print(f"Received media data: {media_data}")

            media_data_sorted = sorted(media_data, key=lambda x: x["posicion"])
            self.save_media_data_offline(media_data_sorted)

            return media_data

        except requests.exceptions.RequestException as e:
            print(f"Error fetching media data: {e}")
            return []

        except ValueError as e:
            print(f"Error parsing JSON: {e}")
            return []

    def save_media_data_offline(self, media_data):
        """Save media data to a file."""
        try:
            with open(self.media_file, "w", encoding="utf-8") as f:
                json.dump(media_data, f, ensure_ascii=False, indent=4)
            print(f"Media data saved to {self.media_file}")
        except IOError as e:
            print(f"Error saving media data: {e}")

    def save_license_data_offline(self, media_data):
        """Save media data to a file."""
        try:
            with open(self.license_data_offline, "w", encoding="utf-8") as f:
                json.dump(media_data, f, ensure_ascii=False, indent=4)
            print(f"License data saved to {self.license_data_offline}")
        except IOError as e:
            print(f"Error saving media data: {e}")

    def restart_application(self):
        """Restart the application."""
        os.execv(sys.executable, [sys.executable] + sys.argv)

    def show_user_message(self, message):
        # Show a message box with the specified message
        messagebox.showinfo("Information:", message)

    def show_user_message_once(self, message):

        if not self.message_displayed:
            self.show_user_message(message)
            self.message_displayed = True

    def close_popup(self, popup):
        """Close the given popup window."""
        popup.destroy()

    def start_playback(self, popup):
        """Start playback and close the popup."""
        popup.destroy()  # Close the confirmation popup
        self.close_popup(self.license_popup)  # Close the license popup
        self.check_and_play_media()  # Start media playback

    def ask_to_start_playback(self):
        """Prompt the user to start media playback if no media is currently playing."""
        # Create a new confirmation popup
        confirm_popup = tk.Toplevel(self.root)
        confirm_popup.title("Iniciar reproducción")

        # Center the popup
        width, height = 300, 150
        screen_width = confirm_popup.winfo_screenwidth()
        screen_height = confirm_popup.winfo_screenheight()
        x = (screen_width // 2) - (width // 2)
        y = (screen_height // 2) - (height // 2)
        confirm_popup.geometry(f"{width}x{height}+{x}+{y}")

        # Add message label
        message_label = tk.Label(
            confirm_popup,
            text=f"Licencia valida ¿Deseas iniciar la reproducción?",
        )
        message_label.pack(pady=10)

        # Add "Yes" and "No" buttons
        yes_button = tk.Button(
            confirm_popup,
            text="Sí",
            command=lambda: self.start_playback(confirm_popup),
        )
        yes_button.pack(side=tk.LEFT, padx=50, pady=10)

        no_button = tk.Button(
            confirm_popup,
            text="No",
            command=lambda: self.stop_app(),
        )
        no_button.pack(side=tk.RIGHT, padx=50, pady=10)

    def is_media_playing(self):
        return current_app is not None

    def is_internet_available(self):
        try:
            # Try connecting to a well-known site (e.g., Google DNS)
            socket.create_connection(("8.8.8.8", 53), timeout=5)
            return True
        except OSError:
            pass
        return False

    def fetch_listas_offline(self):
        """Load and check license data and play media in offline mode."""

        try:
            # Load license data
            with open(self.license_data_offline, "r", encoding="utf-8") as f:
                license_status = json.load(f)
            print(f"Loaded license data from {self.license_data_offline}")

            # Validate license
            if license_status.get("has_license", False):
                license_dates_str = license_status.get("license_dates", "")
                start_date, end_date = self.parse_date_range(license_dates_str)
                current_date = datetime.now()

                if start_date and end_date and end_date >= current_date:
                    date_diff = (end_date - current_date).days
                    if date_diff >= 2:
                        # Load and play media data
                        with open(self.media_file, "r", encoding="utf-8") as f:
                            self.media_data = json.load(f)
                        print(f"Loaded media data from {self.media_file}")

                        if not self.media_data:
                            print("No media data found locally.")
                            self.show_user_message(
                                "No hay datos multimedia disponibles."
                            )
                        else:
                            self.play_media()
                    else:
                        self.show_user_message("Activar Licencia")
                else:
                    print("Licencia caducada o no válida")
                    self.show_user_message("Licencia Caducada o No Válida")
            else:
                self.show_user_message("Solicitar Licencia")
        except (IOError, json.JSONDecodeError) as e:
            print(f"Error loading data: {e}")
            self.show_user_message("Error al cargar datos locales.")


if __name__ == "__main__":
    try:
        root = tk.Tk()
        app = MultimediaPlayerApp(root)
        root.mainloop()
    except Exception as e:
        logging.error("Exception in main loop", exc_info=True)
        print("An error occurred. Check the log file for details.")
