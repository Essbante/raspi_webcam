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
from flask  import Flask, Response, render_template, request, jsonify

# .env file config reads
# Loads the environment variables from the .env file
load_dotenv()
# Port for the service to listen on
port = int(os.environ.get('PORT', 5000))
# The camera device number (dev/video#) to use
dev_video = int(os.environ.get('DEV_VIDEO', 0))
# Resolution width to use
# values 1280, 640
width = int(os.environ.get('WIDTH', 1280))
# Resolution height to use
# values 720, 480
height = int(os.environ.get('HEIGHT', 720))
# FPS to use
# values 25, 10
fps = int(os.environ.get('FPS', 25))
# fingerprint to use (PRUSA Connect)
fingerprint = os.environ.get('FINGERPRINT', '')
# token to use (PRUSA Connect)
token = os.environ.get('TOKEN', '')
# Snapshot post url (PRUSA Connect)
snapshot_post_url = os.environ.get('SNAPSHOT_POST_URL', 'https://webcam.connect.prusa3d.com/c/snapshot}')
# delay between snapshots in seconds
snapshot_delay = int(os.environ.get('SNAPSHOT_DELAY', 10))
# path to save the snapshot
snapshot_path = os.environ.get('SNAPSHOT_PATH', '/tmp/snapshot.jpg')


# creates a camera object
camera = Camera(dev_video, width, height, fps)

# Flag to indicate whether the thread should be running or not (PRUSA Connect Snapshot)
running = False

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/video_feed/')
def video_feed():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/snapshot/')
def snapshot():
    frame = camera.get_frame()
    if frame is None:
        return Response(status=500)
    else:
        return Response(frame, mimetype='image/jpeg')

###############################################
# PRUSA CONNECT SNAPSHOT

# Define routes to start and stop the thread
@app.route('/start_snapshots', methods=['POST'])
def start_snapshots():
    global running
    running = True
    thread = threading.Thread(target=post_snapshots)
    thread.start()
    return 'Thread started'

@app.route('/stop_snapshots', methods=['POST'])
def stop_snapshots_route():
    global running
    running = False
    return 'Thread stopped'

###############################################
# PRUSA CONNECT SNAPSHOT

@app.route('/list-devices', methods=['GET'])
def list_devices():
    try:
        output = subprocess.check_output(['v4l2-ctl', '--list-devices'], text=True)
        return jsonify({"output": output.split('\n')})
    except subprocess.CalledProcessError as e:
        return jsonify({"error": str(e)}), 500

# route to get raspberry pi core voltage and temperature
@app.route('/status', methods=['GET'])
def status():
    try:
        output = subprocess.check_output(['vcgencmd', 'measure_temp'], text=True)
        temperature = output.split('=')[1].split("'")[0]
        output = subprocess.check_output(['vcgencmd', 'measure_volts'], text=True)
        voltage = output.split('=')[1].split("'")[0]
        now = datetime.datetime.now()
        return jsonify({"temperature": temperature, 
                        "voltage": voltage,
                        "current_time": now.strftime("%Y-%m-%d %H:%M:%S"),
                        "prusa_connect":running
                        })
    except subprocess.CalledProcessError as e:
        return jsonify({"error": str(e)}), 500

@app.route('/shutdown', methods=['POST'])
def shutdown():
    os.system('sudo shutdown -h')
    return "Shutting down..."

@app.route('/reboot', methods=['POST'])
def reboot():
    os.system('sudo shutdown -r now')
    return "Rebooting..."

# route to update a .env variable
#
# example curl call to update the CAMERA_ID variable
# curl -X POST -d "env_name=DEV_VIDEO&value=2" http://localhost:5000/update-env
@app.route('/update-env', methods=['POST'])
def update_env():
    try:
        env_name = request.form['env_name']
        value = request.form['value']
        update_env_file(env_name, value)
        return jsonify({"message": f"Updated {env_name} to {value}"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500



# route to get the last 10 logs entries from the service
# raspi_webcam.service
@app.route('/logs', methods=['GET'])
def logs():
    try:
        output = subprocess.check_output(['journalctl', '-u', 'raspi_webcam.service', '-n', '10'], universal_newlines=True, text=True)
        return output
    except subprocess.CalledProcessError as e:
        return jsonify({"error": str(e)}), 500
    
# route to restart the service
@app.route('/restart-service', methods=['POST'])
def restart_service():
    try:
        output = subprocess.check_output(['sudo', 'systemctl', 'restart', 'raspi_webcam.service'], universal_newlines=True, text=True)
        return output
    except subprocess.CalledProcessError as e:
        return jsonify({"error": str(e)}), 500

def gen_frames():  
    while True:
        frame = camera.get_frame()
        if frame is None:
            continue
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
 
def upload_image(http_url, fingerprint, token, frame):
    headers = {
        'accept': '*/*',
        'content-type': 'image/jpg',
        'fingerprint': fingerprint,
        'token': token,
    }
    response = requests.put(http_url, headers=headers, data=frame)
    if response.status_code != 204:
        logging.error(f'Request to {http_url} failed with status code {response.status_code}')
    return response

import logging

def post_snapshots():
    global running
    while running:
        frame = camera.get_frame()
        if frame is not None:
            upload_image(snapshot_post_url, fingerprint, token, frame)
        else:
            logging.error("No frame received")
        time.sleep(snapshot_delay)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=port)