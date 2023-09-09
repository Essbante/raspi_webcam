import json
import time
import cv2
import os
import subprocess
import requests
import threading
import logging
import datetime
from dotenv import load_dotenv
from camera import Camera
from flask import Flask, Response, render_template, request, jsonify

# .env file config reads
# Loads the environment variables from the .env file
load_dotenv()
# Port for the service to listen on
port = int(os.environ.get("PORT", 5000))
# The camera device number (dev/video#) to use
dev_video = int(os.environ.get("DEV_VIDEO", 0))
# Resolution width to use
# values 1280, 640
width = int(os.environ.get("WIDTH", 1280))
# Resolution height to use
# values 720, 480
height = int(os.environ.get("HEIGHT", 720))
# FPS to use
# values 25, 10
fps = int(os.environ.get("FPS", 25))
# fingerprint to use (PRUSA Connect)
fingerprint = os.environ.get("FINGERPRINT", "")
# token to use (PRUSA Connect)
token = os.environ.get("TOKEN", "")
# Snapshot post url (PRUSA Connect)
snapshot_post_url = os.environ.get(
    "SNAPSHOT_POST_URL", "https://webcam.connect.prusa3d.com/c/snapshot}"
)
# delay between snapshots in seconds
snapshot_delay = int(os.environ.get("SNAPSHOT_DELAY", 10))
# path to save the snapshot
snapshot_path = os.environ.get("SNAPSHOT_PATH", "/tmp/snapshot.jpg")
# PRUSA Link IP
prusa_link_ip = os.environ.get("PRUSA_LINK_IP", "")
# PRUSA Link API Key
prusa_link_api_key = os.environ.get("PRUSA_LINK_API_KEY", "")


# creates a camera object
camera = Camera(dev_video, width, height, fps)

# Flag to indicate whether the thread should be running or not (PRUSA Connect Snapshot)
running = False

last_prusa_link_status = None
last_raspi_status = None

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/video_feed/")
def video_feed():
    return Response(gen_frames(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/snapshot/")
def snapshot():
    frame = camera.get_frame()
    if frame is None:
        return Response(status=500)
    else:
        return Response(frame, mimetype="image/jpeg")


###############################################
# PRUSA CONNECT SNAPSHOT


# Define routes to start and stop the thread
@app.route("/start_snapshots", methods=["POST"])
def start_snapshots():
    global running
    running = True
    thread = threading.Thread(target=post_snapshots)
    thread.start()
    return "Thread started"


@app.route("/stop_snapshots", methods=["POST"])
def stop_snapshots_route():
    global running
    running = False
    return "Thread stopped"


###############################################
# PRUSA CONNECT SNAPSHOT


@app.route("/list-devices", methods=["GET"])
def list_devices():
    try:
        output = subprocess.check_output(["v4l2-ctl", "--list-devices"], text=True)
        return jsonify({"output": output.split("\n")})
    except subprocess.CalledProcessError as e:
        return jsonify({"error": str(e)}), 500


# route to get raspberry pi core voltage and temperature
@app.route("/status", methods=["GET"])
def status():
    global running
    global last_raspi_status
    try:
        output = subprocess.check_output(["vcgencmd", "measure_temp"], text=True)
        temperature = output.split("=")[1].split("'")[0]
        output = subprocess.check_output(["vcgencmd", "measure_volts"], text=True)
        voltage = output.split("=")[1].split("'")[0]
        now = datetime.datetime.now()
        last_raspi_status = jsonify(
            {
                "temperature": temperature,
                "voltage": voltage,
                "current_time": now.strftime("%Y-%m-%d %H:%M:%S"),
                "prusa_connect": running,
            }
        )
        return last_raspi_status
    except subprocess.CalledProcessError as e:
        return jsonify({"error": str(e)}), 500


@app.route("/shutdown", methods=["POST"])
def shutdown():
    os.system("sudo shutdown -h")
    return "Shutting down..."


@app.route("/reboot", methods=["POST"])
def reboot():
    os.system("sudo shutdown -r now")
    return "Rebooting..."


# route to get the last 10 logs entries from the service
# raspi_webcam.service
@app.route("/logs", methods=["GET"])
def logs():
    try:
        output = subprocess.check_output(
            ["journalctl", "-u", "raspi_webcam.service", "-n", "10"],
            universal_newlines=True,
            text=True,
        )
        return output
    except subprocess.CalledProcessError as e:
        return jsonify({"error": str(e)}), 500


# route to restart the service
@app.route("/restart-service", methods=["POST"])
def restart_service():
    try:
        output = subprocess.check_output(
            ["sudo", "systemctl", "restart", "raspi_webcam.service"],
            universal_newlines=True,
            text=True,
        )
        return output
    except subprocess.CalledProcessError as e:
        return jsonify({"error": str(e)}), 500


# route to get PRUSA Link status. Make a request to the PRUSA Link API and return the response.
# X-Api-Key is the token.
# curl --location '192.168.0.60/api/v1/status' \
# --header 'Accept: application/json' \
# --header 'X-Api-Key: P3wQ8Ssrbiqnawi'
@app.route("/prusa-link-status", methods=["GET"])
def prusa_link_status():
    global last_prusa_link_status
    try:
        headers = {
            "accept": "application/json",
            "X-Api-Key": prusa_link_api_key,
        }
        response = requests.get(
            f"http://{prusa_link_ip}/api/v1/status", headers=headers
        )
        last_prusa_link_status = response.json()
        return jsonify(response.json())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# curl --location --request PUT '192.168.0.150/api/v1/job/<integer>/pause' \
# --header 'Accept: text/plain' \
# --header 'X-Api-Key: DjcZkgxor5bo9gB'
@app.route("/prusa-link-pause", methods=["POST"])
def prusa_link_pause():
    global last_prusa_link_status
    if(last_prusa_link_status is not None and 
       last_prusa_link_status["printer"]["state"] == "PRINTING"):
        try:            
            headers = {
                "accept": "text/plain",
                "X-Api-Key": prusa_link_api_key,
            }
            response = requests.put(
                f"http://{prusa_link_ip}/api/v1/job/{last_prusa_link_status['job']['id']}/pause", headers=headers
            )
            return response.text, response.status_code
        except Exception as e:
            logging.error(str(e))
            return jsonify({"error": str(e)}), 500
    else:
        return jsonify({"error": "Printer not printing"}), 409


# curl --location --request PUT '192.168.0.150/api/v1/job/<integer>/resume' \
# --header 'Accept: text/plain' \
# --header 'X-Api-Key: DjcZkgxor5bo9gB'
@app.route("/prusa-link-resume", methods=["POST"])
def prusa_link_resume():
    if(last_prusa_link_status is not None and 
       last_prusa_link_status["printer"]["state"] == "PAUSED"):
        try:
            headers = {
                "accept": "text/plain",
                "X-Api-Key": prusa_link_api_key,
            }
            response = requests.put(
                f"http://{prusa_link_ip}/api/v1/job/{last_prusa_link_status['job']['id']}/resume", headers=headers
            )
            return response.text, response.status_code
        except Exception as e:
            logging.error(str(e))
            return jsonify({"error": str(e)}), 500
    else:
        return jsonify({"error": "Printer not paused"}), 409

# curl --location --request DELETE '192.168.0.150/api/v1/job/<integer>' \
# --header 'Accept: text/plain' \
# --header 'X-Api-Key: DjcZkgxor5bo9gB'
@app.route("/prusa-link-cancel", methods=["DELETE"])
def prusa_link_cancel():
    if(last_prusa_link_status is not None and 
       last_prusa_link_status["printer"]["state"] == "PRINTING"):
        try:
            headers = {
                "accept": "text/plain",
                "X-Api-Key": prusa_link_api_key,
            }
            response = requests.delete(
                f"http://{prusa_link_ip}/api/v1/job/{last_prusa_link_status['job']['id']}", headers=headers
            )
            return response.text, response.status_code
        except Exception as e:
            logging.error(str(e))
            return jsonify({"error": str(e)}), 500
    else:
        return jsonify({"error": "Printer not printing"}), 409

def gen_frames():
    while True:
        frame = camera.get_frame()
        if frame is None:
            continue
        yield (b"--frame\r\n" b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n")


def upload_image(http_url, fingerprint, token, frame):
    headers = {
        "accept": "*/*",
        "content-type": "image/jpg",
        "fingerprint": fingerprint,
        "token": token,
    }
    response = requests.put(http_url, headers=headers, data=frame)
    if response.status_code != 204:
        logging.error(
            f"Request to {http_url} failed with status code {response.status_code}"
        )
        return False
    else:
        return True


import logging


def post_snapshots():
    global running
    while running:
        frame = camera.get_frame()
        if frame is not None:
            running = upload_image(snapshot_post_url, fingerprint, token, frame)
        else:
            running = False
            logging.error("No frame received")
        time.sleep(snapshot_delay)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=port)
