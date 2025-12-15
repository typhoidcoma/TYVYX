"""
Simple web front-end for the TEKY WiFi Drone project.

This minimal Flask app provides a basic landing page that can be
used as the starting point for a web-based control interface. The
project primarily uses the command-line controllers in the repo,
so this app is kept intentionally small and optional.

To run the web app (optional):

    python app.py

Then open http://localhost:5000/ in your browser.
"""

from flask import Flask

app = Flask(__name__)


@app.route("/")
def home():
    """Return a short status string for the web UI.

    The function is intentionally minimal — it returns a text
    response suitable for sanity-checking the web server.
    """
    return "WiFi Drone Control Web App"


if __name__ == "__main__":
    # Development server only. Use a production WSGI server for real deployments.
    app.run(host="0.0.0.0", port=5000, debug=True)
