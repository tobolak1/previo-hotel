#!/usr/bin/env python3
"""
Previo Hotel System - Railway Deployment
Main Flask application
"""

from flask import Flask, jsonify
import os

app = Flask(__name__)

# Import previo blueprint
from previo_routes import previo_bp
app.register_blueprint(previo_bp)

@app.route('/')
def index():
    return jsonify({
        'service': 'Previo Hotel System',
        'status': 'running',
        'endpoints': [
            '/previo/',
            '/previo/api/recommendations',
            '/previo/api/occupancy',
            '/previo/api/prices'
        ]
    })

@app.route('/health')
def health():
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
