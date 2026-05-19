import os

from flask import Flask
from flask_socketio import SocketIO

from gui.ssh_manager import SSHManager
from gui.data_receiver import DataReceiver
from gui.routes.api import api_bp
from gui.routes.socketio_events import register_socketio_events


def create_app():
    app = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(__file__), "templates"),
        static_folder=os.path.join(os.path.dirname(__file__), "static"),
    )
    app.config["SECRET_KEY"] = "duck-robot-dashboard"

    socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

    ssh_manager = SSHManager()
    data_receiver = DataReceiver()

    app.config["ssh_manager"] = ssh_manager
    app.config["socketio"] = socketio
    app.config["data_receiver"] = data_receiver

    app.register_blueprint(api_bp)
    register_socketio_events(socketio)

    @app.route("/")
    def index():
        from flask import render_template

        return render_template("index.html")

    return app, socketio
