"""
Flask entry point for the detective game API.
"""

import os
from flask import Flask, request, jsonify
from flask_cors import CORS

from handlers import dispatch
from game_state import STATE
import scenarios as _sc

app = Flask(__name__)
CORS(app)

# Auto-initialize default scenario on startup so commands work immediately
_default = _sc.resolve_scenario("hargrove_affair")
if _default:
    STATE.load_from_scenario(_default)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/command", methods=["POST"])
def command():
    """
    Accept a player command and return a game response.

    Request body (JSON):
        {"input": "look around"}

    Response (JSON):
        {
            "message": "...",
            "time": "Day 1, Morning",
            "case_status": "open",
            "hint": "...",       // optional
            "event": "..."       // optional: clue_found | time_advanced | solve_attempt | ...
        }
    """
    body = request.get_json(silent=True)
    if not body or "input" not in body:
        return jsonify({"error": "Request body must be JSON with an 'input' field."}), 400

    player_input = str(body["input"]).strip()
    if not player_input:
        return jsonify({"error": "'input' must not be empty."}), 400

    result = dispatch(player_input)
    return jsonify(result), 200


@app.route("/state", methods=["GET"])
def state():
    """Return the full game state (useful for debugging / building a UI)."""
    return jsonify(STATE.to_dict()), 200


@app.route("/reset", methods=["POST"])
def reset():
    """Hard-reset the game via REST (no command parsing needed)."""
    STATE.reset()
    return jsonify({"message": "Game reset.", "state": STATE.to_dict()}), 200


@app.route("/healthz", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


# ---------------------------------------------------------------------------
# Startup banner
# ---------------------------------------------------------------------------

def _print_banner():
    print()
    print("╔══════════════════════════════════════╗")
    print("║   The Hargrove Affair — API Server   ║")
    print("╠══════════════════════════════════════╣")
    print("║  POST /command  { \"input\": \"...\" }   ║")
    print("║  GET  /state                         ║")
    print("║  POST /reset                         ║")
    print("║  GET  /healthz                       ║")
    print("╚══════════════════════════════════════╝")
    print()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    _print_banner()
    app.run(host="0.0.0.0", port=port, debug=False)
