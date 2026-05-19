from gui.routes.api import api_bp


def register_socketio_events(socketio):
    @socketio.on("connect")
    def handle_connect():
        pass

    @socketio.on("disconnect")
    def handle_disconnect():
        pass
