# raspi_webcam
Simple camera app to run on o a raspberry pi

# requirements

```bash
sudo apt-get update
sudo apt-get install python3-opencv
pip3 install flask
pip3 install python-dotenv
```

Create a service config file:
```bash
sudo nano /etc/systemd/system/raspi_webcam.service
```

Add this 
```
[Unit]
Description=raspi_webcam     
After=multi-user.target

[Service]
ExecStart=/usr/bin/python3 </path/to>/app.py
Restart=on-failure
RestartSec=10
User=<user>

[Install]
WantedBy=multi-user.target
```
Replace </path/to> with the full path to your app.py.

--

load file  
```sudo systemctl daemon-reload```

enable service  
```sudo systemctl enable raspi_webcam.service```

start service  
```sudo systemctl start raspi_webcam.service```

stop service
```sudo systemctl stop raspi_webcam.service```

restart service
```sudo systemctl restart raspi_webcam.service```

service status  
```sudo systemctl status raspi_webcam.service```

service logs  
```journalctl -u raspi_webcam.service -n 50```

----

usefull commands

```v4l2-ctl --list-devices```

```v4l2-ctl --device=/dev/video0 --list-formats-ext```

```v4l2-ctl --device=/dev/video0 --list-framesizes=MJPG```
