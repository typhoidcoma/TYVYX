"""Flask web front-end packaged under `teky`."""

from flask import Flask

app = Flask(__name__)


@app.route("/")
def home():
    """Return a short status string for the web UI."""
    return "WiFi Drone Control Web App"


if __name__ == "__main__":
    # Development server only. Use a production WSGI server for real deployments.
    app.run(host="0.0.0.0", port=5000, debug=True)
