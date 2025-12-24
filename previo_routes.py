#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SAASPrevio - Flask Blueprint pro integraci do hlavni aplikace
v2 - s ukladanim rozhodnuti a propojenim na Previo API
"""
import sys
import os
import requests

# Pridat cestu k previo modulum
previo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "previo")
if previo_path not in sys.path:
    sys.path.insert(0, previo_path)

from flask import Blueprint, jsonify, request, Response
from datetime import datetime, date, timedelta
import csv
import io
import xml.etree.ElementTree as ET

previo_bp = Blueprint("previo", __name__, url_prefix="/previo")

# ==============================================================================
# INLINE HTML TEMPLATES
# ==============================================================================

BASE_STYLE = """
<style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; color: #333; }
    .container { max-width: 1400px; margin: 0 auto; padding: 20px; }
    .header { background: #2c3e50; color: white; padding: 20px; margin-bottom: 20px; }
    .header h1 { font-size: 24px; }
    .nav { display: flex; gap: 20px; margin-top: 10px; }
    .nav a { color: #ecf0f1; text-decoration: none; padding: 8px 16px; border-radius: 4px; }
    .nav a:hover, .nav a.active { background: #34495e; }
    .card { background: white; border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
    .card h2 { margin-bottom: 15px; color: #2c3e50; }
    table { width: 100%; border-collapse: collapse; }
    th, td { padding: 12px; text-align: left; border-bottom: 1px solid #eee; }
    th { background: #f8f9fa; font-weight: 600; }
    .btn { padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer; font-size: 14px; }
    .btn-success { background: #27ae60; color: white; }
    .btn-danger { background: #e74c3c; color: white; }
    .btn-primary { background: #3498db; color: white; }
    .btn:hover { opacity: 0.9; }
    .badge { padding: 4px 8px; border-radius: 4px; font-size: 12px; }
    .badge-up { background: #27ae60; color: white; }
    .badge-down { background: #e74c3c; color: white; }
    .badge-neutral { background: #95a5a6; color: white; }
    .status { display: inline-block; padding: 4px 8px; border-radius: 4px; font-size: 12px; }
    .status-pending { background: #f39c12; color: white; }
    .status-approved { background: #27ae60; color: white; }
    .status-rejected { background: #e74c3c; color: white; }
    .filters { display: flex; gap: 10px; margin-bottom: 20px; flex-wrap: wrap; }
    .filters select, .filters input { padding: 8px; border: 1px solid #ddd; border-radius: 4px; }
    .kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; }
    .kpi-card { background: white; padding: 20px; border-radius: 8px; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
    .kpi-value { font-size: 32px; font-weight: bold; color: #2c3e50; }
    .kpi-label { color: #7f8c8d; margin-top: 5px; }
    .alert { padding: 15px; border-radius: 4px; margin-bottom: 20px; }
    .alert-success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
    .alert-error { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
    .loading { text-align: center; padding: 40px; color: #7f8c8d; }
</style>
"""

def render_page(title, content, active_page=""):
    nav_items = [
        ("/previo/", "Dashboard", "dashboard"),
        ("/previo/recommendations", "Doporuceni", "recommendations"),
        ("/previo/settings", "Nastaveni", "settings"),
    ]
    nav_html = ""
    for url, label, page in nav_items:
        active = "active" if page == active_page else ""
        nav_html += f'<a href="{url}" class="{active}">{label}</a>'

    return f"""<!DOCTYPE html>
<html lang="cs">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - Previo Hotel</title>
    {BASE_STYLE}
</head>
<body>
    <div class="header">
        <div class="container">
            <h1>Previo Hotel - Cenovy Optimalizator</h1>
            <nav class="nav">{nav_html}</nav>
        </div>
    </div>
    <div class="container">
        {content}
    </div>
    <script>
        async function approveRecommendation(recId, change) {{
            if (!confirm('Opravdu chcete schvalit tuto zmenu ceny?')) return;
            try {{
                const response = await fetch('/previo/api/recommendations/' + recId + '/decide', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{decision: 'approved', user_change: change}})
                }});
                const result = await response.json();
                if (result.success) {{
                    alert('Cena byla uspesne zmenena!');
                    location.reload();
                }} else {{
                    alert('Chyba: ' + (result.error || 'Neznama chyba'));
                }}
            }} catch (e) {{
                alert('Chyba: ' + e.message);
            }}
        }}

        async function rejectRecommendation(recId) {{
            if (!confirm('Opravdu chcete zamitnout toto doporuceni?')) return;
            try {{
                const response = await fetch('/previo/api/recommendations/' + recId + '/decide', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{decision: 'rejected'}})
                }});
                const result = await response.json();
                if (result.success) {{
                    location.reload();
                }}
            }} catch (e) {{
                alert('Chyba: ' + e.message);
            }}
        }}

        async function applyAllForDays(days) {{
            if (!confirm('Opravdu chcete aplikovat vsechna doporuceni na ' + days + ' dni dopredu?')) return;
            try {{
                const response = await fetch('/previo/api/eqc/apply-recommendations', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{days_ahead: days}})
                }});
                const result = await response.json();
                if (result.success) {{
                    alert('Aplikovano ' + result.applied_count + ' zmen!');
                    location.reload();
                }} else {{
                    alert('Chyba: ' + (result.error || 'Neznama chyba'));
                }}
            }} catch (e) {{
                alert('Chyba: ' + e.message);
            }}
        }}
    </script>
</body>
</html>"""

# Konfigurace
SUPABASE_URL = "https://kchbzmncwdidjzxnegck.supabase.co"
SUPABASE_KEY = "sb_secret_52w8jQGJ2qYNu6RLURvpDw_0R1tRBrQ"

# REST API konfigurace pro Previo
REST_CONFIG = {
    "username": "api@vincentluhacovice.cz",
    "password": "2P0QHc9XPph7",
    "hotel_id": "731186",
    "api_url": "https://api.previo.app/rest/"
}

HOTEL = {
    "name": "Vincentluhacovice.cz",
    "id": "731186",
    "currency": "CZK"
}

# ==============================================================================
# PREDPOCITANA DATA - nacitaji se ze Supabase (cron je pocita 1x denne)
# ==============================================================================
import json

def get_precomputed_recommendations():
    """Nacte predpocitana doporuceni ze Supabase."""
    try:
        headers = {
            'apikey': SUPABASE_KEY,
            'Authorization': f'Bearer {SUPABASE_KEY}',
            'Content-Type': 'application/json'
        }

        response = requests.get(
            f'{SUPABASE_URL}/rest/v1/previo_precomputed',
            headers=headers,
            params={
                'id': f'eq.{REST_CONFIG["hotel_id"]}_recommendations',
                'select': 'data,computed_at'
            },
            timeout=30
        )

        if response.status_code == 200:
            results = response.json()
            if results and len(results) > 0:
                data = json.loads(results[0]['data'])
                data['computed_at'] = results[0]['computed_at']
                return data

        # Fallback - pokud neni v DB, pocitat (pomale)
        print("Predpocitana data nenalezena, pocitam...")
        return get_recommendations_with_prices()

    except Exception as e:
        print(f"Error loading precomputed: {e}")
        return {"recommendations_with_prices": [], "daily": [], "count": 0, "error": str(e)}

# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================

def get_rest_client():
    """Ziska REST API klienta."""
    try:
        from previo_api_client import PrevioRestClient
        return PrevioRestClient(
            username=REST_CONFIG["username"],
            password=REST_CONFIG["password"],
            hotel_id=REST_CONFIG["hotel_id"],
            api_url=REST_CONFIG["api_url"]
        )
    except Exception as e:
        print(f"Error creating REST client: {e}")
        return None

def get_price_optimizer():
    """Ziska instanci SmartRoomPriceOptimizer (pouziva Supabase s daty po pokojich)."""
    try:
        from smart_price_optimizer import SmartRoomPriceOptimizer
        return SmartRoomPriceOptimizer(hotel_id=REST_CONFIG["hotel_id"])
    except Exception as e:
        print(f"Error creating optimizer: {e}")
        return None

# ==============================================================================
# ROUTES
# ==============================================================================

@previo_bp.route("/test")
def test_page():
    """Debug test page."""
    return "Test page works! Version 2"

@previo_bp.route("/test2")
def test_page2():
    """Debug test page 2."""
    return render_page("Test", "<p>Test page works!</p>", "dashboard")

@previo_bp.route("/")
def dashboard():
    """Hlavni dashboard."""
    try:
        kpi = get_kpi_data()
    except Exception as e:
        kpi = {"occupancy": "N/A", "error": str(e)}

    content = f"""
    <div class="kpi-grid">
        <div class="kpi-card">
            <div class="kpi-value">{kpi.get('occupancy', 'N/A')}</div>
            <div class="kpi-label">Obsazenost dnes</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-value">{kpi.get('arrivals', 0)}</div>
            <div class="kpi-label">Prijezdy dnes</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-value">{kpi.get('departures', 0)}</div>
            <div class="kpi-label">Odjezdy dnes</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-value">{kpi.get('revenue', 'N/A')}</div>
            <div class="kpi-label">Trzba dnes</div>
        </div>
    </div>

    <div class="card" style="margin-top: 20px;">
        <h2>Rychle akce</h2>
        <p>Aplikovat cenova doporuceni:</p>
        <div style="display: flex; gap: 10px; margin-top: 15px;">
            <button class="btn btn-primary" onclick="applyAllForDays(1)">Na zitra</button>
            <button class="btn btn-primary" onclick="applyAllForDays(7)">Na tyden</button>
            <button class="btn btn-primary" onclick="applyAllForDays(14)">Na 14 dni</button>
        </div>
    </div>

    <div class="card">
        <h2>API Endpointy</h2>
        <ul style="list-style: none; padding: 0;">
            <li style="padding: 8px 0;"><a href="/previo/api/recommendations">/api/recommendations</a> - JSON doporuceni</li>
            <li style="padding: 8px 0;"><a href="/previo/api/export/csv">/api/export/csv</a> - Export CSV</li>
            <li style="padding: 8px 0;"><a href="/previo/api/eqc/test">/api/eqc/test</a> - Test EQC API</li>
            <li style="padding: 8px 0;"><a href="/previo/api/status">/api/status</a> - API Status</li>
        </ul>
    </div>
    """
    return render_page("Dashboard", content, "dashboard")

@previo_bp.route("/recommendations")
def recommendations():
    """Stranka s cenovymi doporucennimi - bere z cache."""
    try:
        data = get_precomputed_recommendations()
        # Cache obsahuje recommendations_with_prices (novy format s cenami)
        recs = data.get("recommendations_with_prices", [])
    except Exception as e:
        data = {"recommendations_with_prices": [], "error": str(e)}
        recs = []

    # Filtrovat jen ty co maji zmenu
    active_recs = [r for r in recs if r.get("recommendation_type") != "no_change"]

    rows_html = ""
    for rec in active_recs[:50]:  # Limit na 50
        rec_id = f"{rec.get('date')}_{rec.get('room_kind_id', 'daily')}"
        change = rec.get("recommended_change", 0)
        badge_class = "badge-up" if change > 0 else "badge-down" if change < 0 else "badge-neutral"

        rows_html += f"""
        <tr>
            <td>{rec.get('date', '')}</td>
            <td>{rec.get('weekday_name', '')}</td>
            <td>{rec.get('room_name', 'Vsechny pokoje')}</td>
            <td>{rec.get('current_price', 'N/A')} CZK</td>
            <td><span class="badge {badge_class}">{change:+.0f}%</span></td>
            <td>{rec.get('new_price', 'N/A')} CZK</td>
            <td>{rec.get('reason', '')[:50]}</td>
            <td style="text-align: right;">
                <button class="btn btn-success" onclick="approveRecommendation('{rec_id}', {change})">Schvalit</button>
                <button class="btn btn-danger" onclick="rejectRecommendation('{rec_id}')">Zamitnout</button>
            </td>
        </tr>
        """

    content = f"""
    <div class="card">
        <h2>Hromadna aplikace</h2>
        <p>Aplikovat vsechna doporuceni:</p>
        <div style="display: flex; gap: 10px; margin-top: 15px;">
            <button class="btn btn-primary" onclick="applyAllForDays(1)">Na zitra</button>
            <button class="btn btn-primary" onclick="applyAllForDays(7)">Na tyden</button>
            <button class="btn btn-primary" onclick="applyAllForDays(14)">Na 14 dni</button>
        </div>
    </div>

    <div class="card">
        <h2>Cenova doporuceni ({len(active_recs)})</h2>
        <table>
            <thead>
                <tr>
                    <th>Datum</th>
                    <th>Den</th>
                    <th>Pokoj</th>
                    <th>Aktualni cena</th>
                    <th>Zmena</th>
                    <th>Nova cena</th>
                    <th>Duvod</th>
                    <th style="text-align: right;">Akce</th>
                </tr>
            </thead>
            <tbody>
                {rows_html if rows_html else '<tr><td colspan="8" style="text-align: center;">Zadna doporuceni</td></tr>'}
            </tbody>
        </table>
    </div>

    <div class="card">
        <h2>Export</h2>
        <a href="/previo/api/export/csv" class="btn btn-primary">Stahnout CSV</a>
        <a href="/previo/api/export/json" class="btn btn-primary">Stahnout JSON</a>
    </div>
    """
    return render_page("Cenova doporuceni", content, "recommendations")

@previo_bp.route("/occupancy")
def occupancy():
    """Analyza obsazenosti - redirect na API."""
    return jsonify({"message": "Pouzijte /previo/api/recommendations pro data", "redirect": "/previo/"})

@previo_bp.route("/prices")
def prices():
    """Cenova analyza - redirect na API."""
    return jsonify({"message": "Pouzijte /previo/api/prices pro data", "redirect": "/previo/"})

@previo_bp.route("/settings")
def settings():
    """Nastaveni systemu."""
    api_status = test_api_connection()

    eqc_status = "OK" if api_status.get('eqc_api') else (api_status.get('eqc_message') or 'Error')

    content = f"""
    <div class="card">
        <h2>API Status</h2>
        <table>
            <tr><td>REST API</td><td>{'OK' if api_status.get('rest_api') else 'Error'}</td></tr>
            <tr><td>XML API (ceny)</td><td>{'OK' if api_status.get('xml_api') else 'Error'}</td></tr>
            <tr><td>EQC API (zmena cen)</td><td>{eqc_status}</td></tr>
        </table>
    </div>

    <div class="card">
        <h2>Konfigurace</h2>
        <table>
            <tr><td>Hotel</td><td>{HOTEL['name']}</td></tr>
            <tr><td>Hotel ID</td><td>{HOTEL['id']}</td></tr>
            <tr><td>Mena</td><td>{HOTEL['currency']}</td></tr>
            <tr><td>Pocet pokoju</td><td>{api_status.get('rooms_count', 0)}</td></tr>
            <tr><td>Pocet cen</td><td>{api_status.get('prices_count', 0)}</td></tr>
        </table>
    </div>

    <div class="card">
        <h2>Akce</h2>
        <p><a href="/previo/api/eqc/test" class="btn btn-primary">Test EQC API</a></p>
        <p style="margin-top: 10px;"><a href="/previo/api/precompute" class="btn btn-primary">Prepocitat doporuceni</a></p>
    </div>
    """
    return render_page("Nastaveni", content, "settings")

# ==============================================================================
# API ENDPOINTY
# ==============================================================================

@previo_bp.route("/api/status")
def api_status():
    return jsonify({"status": "ok", "timestamp": datetime.now().isoformat(), "hotel": HOTEL["name"]})

@previo_bp.route("/api/kpi")
def api_kpi():
    try:
        data = get_kpi_data()
        return jsonify({"success": True, "data": data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@previo_bp.route("/api/recommendations")
def api_recommendations():
    try:
        data = get_recommendations_data()
        return jsonify({"success": True, "data": data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@previo_bp.route("/api/recommendations/<rec_id>/decide", methods=["POST"])
def api_recommendation_decide(rec_id):
    try:
        data = request.get_json()
        decision = data.get("decision")
        user_change = data.get("user_change")

        if decision not in ["approved", "rejected", "modified"]:
            return jsonify({"success": False, "error": "Neplatne rozhodnuti"}), 400

        result = record_recommendation_decision(rec_id, decision, user_change)
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@previo_bp.route("/api/export/csv")
def api_export_csv():
    """Export doporuceni do CSV pro import do Previo."""
    try:
        data = get_recommendations_with_prices()

        output = io.StringIO()
        writer = csv.writer(output, delimiter=';')

        # Hlavicka
        writer.writerow([
            'Datum', 'Den', 'Pokoj', 'Kategorie', 'Obsazenost',
            'Aktualni cena (2os)', 'Doporucena zmena %', 'Nova cena',
            'Duvod', 'Svatek', 'Sezona', 'Confidence'
        ])

        # Data
        for rec in data.get('recommendations_with_prices', []):
            if rec.get('recommendation_type') != 'no_change':
                writer.writerow([
                    rec.get('date', ''),
                    rec.get('weekday_name', ''),
                    rec.get('room_name', ''),
                    rec.get('room_category', ''),
                    f"{rec.get('same_weekday_occupancy', 0):.0f}%",
                    rec.get('current_price', ''),
                    f"{rec.get('recommended_change', 0):+.0f}%",
                    rec.get('new_price', ''),
                    rec.get('reason', ''),
                    rec.get('holiday', '') or '',
                    rec.get('season', '') or '',
                    f"{rec.get('confidence', 0)*100:.0f}%"
                ])

        output.seek(0)

        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={
                'Content-Disposition': f'attachment; filename=previo_doporuceni_{date.today().isoformat()}.csv',
                'Content-Type': 'text/csv; charset=utf-8'
            }
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@previo_bp.route("/api/export/json")
def api_export_json():
    """Export doporuceni do JSON."""
    try:
        data = get_recommendations_with_prices()
        return jsonify({"success": True, "data": data, "exported_at": datetime.now().isoformat()})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@previo_bp.route("/api/prices")
def api_current_prices():
    """Ziska aktualni ceny z Previo."""
    try:
        prices = get_current_prices()
        return jsonify({"success": True, "data": prices})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@previo_bp.route("/api/eqc/test")
def api_eqc_test():
    """Test pripojeni k EQC API."""
    try:
        eqc_client = get_eqc_client()
        if not eqc_client:
            return jsonify({
                "success": False,
                "error": "EQC klient neni k dispozici",
                "note": "EQC API vyzaduje specialni opravneni. Kontaktujte Previo na info@previo.cz."
            }), 500

        result = eqc_client.test_connection()
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@previo_bp.route("/api/eqc/apply", methods=["POST"])
def api_eqc_apply():
    """
    Aplikuje cenovou zmenu primo do Previo.

    Request body:
    {
        "room_kind_id": 640240,
        "target_date": "2025-01-20",
        "change_percent": -10,    // procenta zmeny
        // NEBO
        "new_price": 1500         // absolutni cena
    }
    """
    try:
        data = request.get_json()

        room_kind_id = data.get("room_kind_id")
        target_date = data.get("target_date")
        change_percent = data.get("change_percent")
        new_price = data.get("new_price")

        if not room_kind_id or not target_date:
            return jsonify({
                "success": False,
                "error": "Chybi room_kind_id nebo target_date"
            }), 400

        if change_percent is not None:
            # Aplikovat procentualni zmenu
            result = apply_price_to_previo(target_date, room_kind_id, change_percent)
            return jsonify(result)

        elif new_price is not None:
            # Aplikovat absolutni cenu
            eqc_client = get_eqc_client()
            rate_manager = get_rate_manager()

            if not eqc_client or not rate_manager:
                return jsonify({
                    "success": False,
                    "error": "EQC klient nebo rate manager neni k dispozici"
                }), 500

            rate_plan_id = rate_manager.get_base_rate_plan_id()
            if not rate_plan_id:
                return jsonify({
                    "success": False,
                    "error": "Nepodarilo se ziskat rate plan ID"
                }), 500

            # Prevest datum
            if isinstance(target_date, str):
                from datetime import datetime
                target_date = datetime.strptime(target_date, "%Y-%m-%d").date()

            result = eqc_client.update_rate(
                room_type_id=room_kind_id,
                rate_plan_id=rate_plan_id,
                target_date=target_date,
                new_rate=new_price,
                currency='CZK'
            )
            return jsonify(result)

        else:
            return jsonify({
                "success": False,
                "error": "Chybi change_percent nebo new_price"
            }), 400

    except Exception as e:
        import traceback
        return jsonify({
            "success": False,
            "error": str(e),
            "trace": traceback.format_exc()
        }), 500


@previo_bp.route("/api/eqc/apply-recommendations", methods=["POST"])
def api_eqc_apply_recommendations():
    """
    Aplikuje doporuceni do Previo.

    Request body (varianta 1 - konkretni doporuceni):
    {
        "recommendations": [
            {"id": "2025-01-20_640240", "change_percent": -10},
            {"id": "2025-01-21_640238", "change_percent": +5}
        ]
    }

    Request body (varianta 2 - vsechna na X dni):
    {
        "days_ahead": 7
    }
    """
    try:
        data = request.get_json()
        days_ahead = data.get("days_ahead")
        recommendations = data.get("recommendations", [])

        # Pokud je zadano days_ahead, nacist doporuceni automaticky
        if days_ahead and not recommendations:
            rec_data = get_precomputed_recommendations()
            today = date.today()
            max_date = today + timedelta(days=days_ahead)

            for rec in rec_data.get("recommendations", []):
                if rec.get("recommendation_type") == "no_change":
                    continue

                rec_date_str = rec.get("date")
                if rec_date_str:
                    rec_date = datetime.strptime(rec_date_str, "%Y-%m-%d").date()
                    if today <= rec_date <= max_date:
                        room_kind_id = rec.get("room_kind_id")
                        if room_kind_id:
                            recommendations.append({
                                "id": f"{rec_date_str}_{room_kind_id}",
                                "change_percent": rec.get("recommended_change", 0)
                            })

        if not recommendations:
            return jsonify({
                "success": False,
                "error": "Zadna doporuceni k aplikovani"
            }), 400

        results = []
        success_count = 0
        error_count = 0

        for rec in recommendations:
            rec_id = rec.get("id", "")
            change_percent = rec.get("change_percent", 0)

            # Rozebrat rec_id na datum a room_kind_id
            parts = rec_id.rsplit('_', 1)
            if len(parts) != 2 or parts[1] == "daily":
                results.append({
                    "rec_id": rec_id,
                    "success": False,
                    "error": "Neplatne ID doporuceni"
                })
                error_count += 1
                continue

            target_date = parts[0]
            room_kind_id = int(parts[1])

            result = apply_price_to_previo(target_date, room_kind_id, change_percent)
            result["rec_id"] = rec_id

            if result.get("success"):
                success_count += 1
            else:
                error_count += 1

            results.append(result)

        return jsonify({
            "success": error_count == 0,
            "total": len(recommendations),
            "success_count": success_count,
            "error_count": error_count,
            "results": results
        })

    except Exception as e:
        import traceback
        return jsonify({
            "success": False,
            "error": str(e),
            "trace": traceback.format_exc()
        }), 500


@previo_bp.route("/api/precompute")
def api_precompute():
    """Spusti prepocet doporuceni a ulozi do Supabase. Trva ~60-90 sekund."""
    try:
        # Vypocitat data VCETNE CEN
        data = get_recommendations_with_prices()

        # Ulozit do Supabase
        headers = {
            'apikey': SUPABASE_KEY,
            'Authorization': f'Bearer {SUPABASE_KEY}',
            'Content-Type': 'application/json',
            'Prefer': 'resolution=merge-duplicates'
        }

        record = {
            'id': f"{HOTEL['id']}_recommendations",
            'hotel_id': HOTEL['id'],
            'data': json.dumps(data, ensure_ascii=False, default=str),
            'computed_at': datetime.now().isoformat()
        }

        response = requests.post(
            f'{SUPABASE_URL}/rest/v1/previo_precomputed',
            headers=headers,
            json=record,
            timeout=60
        )

        if response.status_code in [200, 201, 409]:
            return jsonify({
                "success": True,
                "message": "Doporuceni prepocitana a ulozena",
                "daily_count": data.get("daily_count", 0),
                "count": data.get("count", 0)
            })
        else:
            return jsonify({
                "success": False,
                "error": f"Supabase error: {response.status_code}",
                "details": response.text[:200]
            }), 500

    except Exception as e:
        import traceback
        return jsonify({"success": False, "error": str(e), "trace": traceback.format_exc()}), 500

# ==============================================================================
# DATA FUNCTIONS
# ==============================================================================

def get_kpi_data():
    try:
        client = get_rest_client()
        if not client:
            return {"occupancy": "N/A", "error": "No client"}

        today = date.today()
        date_from = today.strftime("%Y-%m-%d")
        date_to = (today + timedelta(days=30)).strftime("%Y-%m-%d")

        kpi = {"occupancy": "N/A", "occupancy_today": "N/A", "total_rooms": 0, "guests": 0, "rate_plans": 0}

        try:
            occupancy_data = client.get_occupancy_data(date_from, date_to)
            if occupancy_data and "summary" in occupancy_data:
                summary = occupancy_data["summary"]
                kpi["occupancy"] = round(summary.get("average_occupancy", 0))
                kpi["total_rooms"] = summary.get("total_rooms", 0)
        except:
            pass

        try:
            guests_data = client.get_guests(limit=1)
            if guests_data and "foundRows" in guests_data:
                kpi["guests"] = guests_data["foundRows"]
        except:
            pass

        return kpi
    except Exception as e:
        return {"occupancy": "N/A", "error": str(e)}

def get_occupancy_data():
    try:
        client = get_rest_client()
        if not client:
            return {"days": [], "summary": {}}
        today = date.today()
        date_from = (today - timedelta(days=7)).strftime("%Y-%m-%d")
        date_to = (today + timedelta(days=30)).strftime("%Y-%m-%d")
        data = client.get_occupancy_data(date_from, date_to)
        return data if data else {"days": [], "summary": {}}
    except:
        return {"days": [], "summary": {}}

def get_price_data():
    try:
        client = get_rest_client()
        if not client:
            return {"rooms": [], "rate_plans": [], "rates": {}, "suggestions": []}
        rate_plans = client.get_rate_plans()
        rooms = client.call_api("rooms")
        return {
            "rooms": rooms if isinstance(rooms, list) else [],
            "rate_plans": rate_plans if isinstance(rate_plans, list) else [],
            "rates": {},
            "suggestions": []
        }
    except:
        return {"rooms": [], "rate_plans": [], "rates": {}, "suggestions": []}

def get_recommendations_data():
    """Ziska doporuceni z optimalizatoru v4 (s ucenim)."""
    try:
        optimizer = get_price_optimizer()
        client = get_rest_client()
        if not optimizer or not client:
            return {"recommendations": [], "daily": [], "count": 0}

        today = date.today()
        date_from = today.strftime("%Y-%m-%d")
        date_to = (today + timedelta(days=60)).strftime("%Y-%m-%d")  # 2 mesice dopredu
        occupancy_data = client.get_occupancy_data(date_from, date_to)
        daily_recommendations = optimizer.generate_recommendations(occupancy_data, days_ahead=60)

        # Naucene vlivy svatku
        learned_holidays = optimizer.get_learned_holiday_impacts()

        # Denni doporuceni (souhrn)
        daily_list = []
        # Jednotliva doporuceni pro pokoje
        room_list = []

        for daily_rec in daily_recommendations:
            # v4 format - holiday_name a holiday_learned_impact
            holiday_name = daily_rec.holiday_name
            holiday_impact = daily_rec.holiday_learned_impact

            daily_list.append({
                "id": daily_rec.id,
                "date": daily_rec.date,
                "weekday": daily_rec.weekday,
                "weekday_name": daily_rec.weekday_name,
                "is_weekend": daily_rec.is_weekend,
                "total_rooms": daily_rec.total_rooms,
                "occupied_rooms": daily_rec.occupied_rooms,
                "free_rooms": daily_rec.free_rooms,
                "occupancy_percent": daily_rec.occupancy_percent,
                "historical_avg": daily_rec.historical_avg,
                "same_weekday_historical": daily_rec.same_weekday_historical,
                "last_year_same_weekday": daily_rec.last_year_same_weekday,
                # Svatky s naucenym vlivem
                "holiday": holiday_name,
                "holiday_impact": holiday_impact,
                "holiday_effect": learned_holidays.get(holiday_name, {}).get("effect") if holiday_name else None,
                # Sezona
                "season": daily_rec.season.get("name") if daily_rec.season else None,
                "season_type": daily_rec.season.get("type") if daily_rec.season else None,
                "days_until": daily_rec.days_until,
                # Doporuceni
                "recommendation_type": daily_rec.recommendation_type,
                "recommended_change": daily_rec.recommended_change,
                "reason": daily_rec.reason,
                "confidence": daily_rec.confidence,
                "decision": daily_rec.decision,
                "room_count_with_recommendations": len([r for r in daily_rec.room_recommendations if r.recommendation_type != "no_change"])
            })

            # Pridat doporuceni pro jednotlive pokoje (pouze volne pokoje s doporucenim)
            for room_rec in daily_rec.room_recommendations:
                if room_rec.recommendation_type != "no_change" or not room_rec.is_occupied:
                    room_list.append({
                        "id": room_rec.id,
                        "date": room_rec.date,
                        "room_kind_id": room_rec.room_kind_id,
                        "room_name": room_rec.room_name,
                        "room_category": room_rec.room_category,
                        "capacity": room_rec.capacity,
                        "is_occupied": room_rec.is_occupied,
                        "historical_occupancy_rate": room_rec.historical_occupancy_rate,
                        "same_weekday_occupancy": room_rec.same_weekday_occupancy,
                        "last_year_same_weekday": room_rec.last_year_same_weekday,
                        "weekday": room_rec.weekday,
                        "weekday_name": room_rec.weekday_name,
                        "is_weekend": room_rec.is_weekend,
                        # Svatky s naucenym vlivem
                        "holiday": room_rec.holiday_name,
                        "holiday_impact": room_rec.holiday_learned_impact,
                        "season": room_rec.season.get("name") if room_rec.season else None,
                        "days_until": room_rec.days_until,
                        # Doporuceni
                        "recommendation_type": room_rec.recommendation_type,
                        "recommended_change": room_rec.recommended_change,
                        "reason": room_rec.reason,
                        "confidence": room_rec.confidence,
                        "decision": room_rec.decision
                    })

        return {
            "daily": daily_list,
            "recommendations": room_list,
            "count": len(room_list),
            "daily_count": len(daily_list),
            "learned_holidays": learned_holidays
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"recommendations": [], "daily": [], "count": 0, "error": str(e)}

def get_year_comparison():
    try:
        optimizer = get_price_optimizer()
        client = get_rest_client()
        if not optimizer or not client:
            return {}
        today = date.today()
        date_from = (today - timedelta(days=7)).strftime("%Y-%m-%d")
        date_to = (today + timedelta(days=7)).strftime("%Y-%m-%d")
        occupancy_data = client.get_occupancy_data(date_from, date_to)
        return optimizer.get_year_comparison(occupancy_data)
    except:
        return {}

def get_predictions():
    try:
        from smart_price_optimizer import SmartOccupancyPredictor
        optimizer = get_price_optimizer()
        client = get_rest_client()
        if not optimizer or not client:
            return []
        predictor = SmartOccupancyPredictor(optimizer)
        today = date.today()
        date_from = today.strftime("%Y-%m-%d")
        date_to = (today + timedelta(days=30)).strftime("%Y-%m-%d")
        occupancy_data = client.get_occupancy_data(date_from, date_to)
        return predictor.get_predictions_for_period(occupancy_data, days_ahead=30)
    except:
        return []

def get_optimizer_stats():
    try:
        optimizer = get_price_optimizer()
        if not optimizer:
            return {}
        stats = optimizer.get_statistics()
        stats["historical_days"] = len(optimizer.historical_data)
        return stats
    except:
        return {}

def test_api_connection():
    status = {
        "rest_api": False,
        "xml_api": False,
        "eqc_api": False,
        "hotel_info": None,
        "rooms_count": 0,
        "guests_count": 0,
        "prices_count": 0,
        "eqc_message": ""
    }

    # Test REST API
    try:
        client = get_rest_client()
        if client:
            rooms = client.call_api("rooms")
            if rooms and isinstance(rooms, list):
                status["rest_api"] = True
                status["rooms_count"] = len(rooms)
    except:
        pass

    # Test XML API (ceny)
    try:
        prices = get_current_prices()
        if prices:
            status["xml_api"] = True
            status["prices_count"] = len(prices)
    except:
        pass

    # Test EQC API
    try:
        eqc_client = get_eqc_client()
        if eqc_client:
            eqc_result = eqc_client.test_connection()
            status["eqc_api"] = eqc_result.get("success", False)
            status["eqc_message"] = eqc_result.get("message", "")
    except Exception as e:
        status["eqc_message"] = str(e)

    return status

def record_recommendation_decision(rec_id, decision, user_change=None):
    """
    Ulozi rozhodnuti uzivatele do Supabase a propise cenu do Previo.

    1. Ulozi rozhodnuti do Supabase (pro uceni)
    2. Pokud approved/modified -> propise cenu do Previo (TODO: EQC API)
    """
    result = {
        "success": True,
        "rec_id": rec_id,
        "decision": decision,
        "saved_to_supabase": False,
        "applied_to_previo": False
    }

    # 1. Ulozit do Supabase
    try:
        headers = {
            'apikey': SUPABASE_KEY,
            'Authorization': f'Bearer {SUPABASE_KEY}',
            'Content-Type': 'application/json',
            'Prefer': 'resolution=merge-duplicates'
        }

        data = {
            'id': rec_id,
            'hotel_id': HOTEL["id"],
            'decision': decision,
            'user_change': user_change,
            'decided_at': datetime.now().isoformat()
        }

        response = requests.post(
            f'{SUPABASE_URL}/rest/v1/previo_recommendations',
            headers=headers,
            json=data,
            timeout=30
        )

        if response.status_code in [200, 201, 409]:
            result["saved_to_supabase"] = True
        else:
            print(f"Supabase error: {response.status_code} {response.text[:200]}")

    except Exception as e:
        print(f"Error saving to Supabase: {e}")

    # 2. Pokud schvaleno, propsat do Previo
    if decision in ["approved", "modified"]:
        try:
            # Rozebrat rec_id na datum a room_kind_id
            # Format: "2025-01-15_640240" nebo "2025-01-15_daily"
            parts = rec_id.rsplit('_', 1)
            if len(parts) == 2:
                target_date = parts[0]
                room_or_daily = parts[1]

                if room_or_daily != "daily":
                    room_kind_id = int(room_or_daily)
                    final_change = user_change if user_change is not None else 0

                    # Aplikovat cenu do Previo pres EQC API
                    print(f"Aplikuji cenu do Previo: {target_date}, room {room_kind_id}, change {final_change}%")

                    previo_result = apply_price_to_previo(target_date, room_kind_id, final_change)
                    result["applied_to_previo"] = previo_result.get("success", False)
                    result["previo_result"] = previo_result

                    if result["applied_to_previo"]:
                        result["previo_note"] = f"Cena uspesne zmenena na {previo_result.get('new_price')} CZK"
                    else:
                        result["previo_note"] = f"Chyba: {previo_result.get('error', 'Neznama chyba')}"

        except Exception as e:
            print(f"Error applying to Previo: {e}")
            result["previo_error"] = str(e)

    return result


def get_eqc_client():
    """Ziska EQC API klienta."""
    try:
        from previo_eqc_client import PrevioEqcClient
        return PrevioEqcClient(
            username=REST_CONFIG["username"],
            password=REST_CONFIG["password"],
            hotel_id=REST_CONFIG["hotel_id"]
        )
    except Exception as e:
        print(f"Error creating EQC client: {e}")
        return None


def get_rate_manager():
    """Ziska Rate Manager pro spravu cen."""
    try:
        from previo_eqc_client import PrevioRateManager
        eqc_client = get_eqc_client()
        rest_client = get_rest_client()
        return PrevioRateManager(eqc_client=eqc_client, rest_client=rest_client)
    except Exception as e:
        print(f"Error creating rate manager: {e}")
        return None


def apply_price_to_previo(target_date, room_kind_id, change_percent):
    """
    Propise cenovou zmenu do Previo pres EQC API.

    EQC API (https://eqc.apidocs.previo.app/) umoznuje:
    - Poslat rates a availability do Previo
    - Stahnout rezervace z Previo

    Args:
        target_date: Datum pro zmenu ceny (string YYYY-MM-DD nebo date objekt)
        room_kind_id: ID typu pokoje
        change_percent: Procentualni zmena ceny (napr. -10 pro slevu 10%)

    Returns:
        Dict: Vysledek operace
    """
    result = {
        "success": False,
        "target_date": str(target_date),
        "room_kind_id": room_kind_id,
        "change_percent": change_percent
    }

    try:
        # Prevest datum na date objekt
        if isinstance(target_date, str):
            from datetime import datetime
            target_date = datetime.strptime(target_date, "%Y-%m-%d").date()

        # Ziskat aktualni cenu
        current_prices = get_current_prices()
        if room_kind_id not in current_prices:
            result["error"] = f"Pokoj {room_kind_id} nema definovane ceny"
            return result

        room_prices = current_prices[room_kind_id]
        # Pouzit cenu pro 2 osoby nebo prvni dostupnou
        current_price = room_prices.get(2) or (list(room_prices.values())[0] if room_prices else None)

        if current_price is None:
            result["error"] = "Nepodařilo se získat aktuální cenu"
            return result

        result["current_price"] = current_price

        # Vypocitat novou cenu
        new_price = round(current_price * (1 + change_percent / 100))
        result["new_price"] = new_price

        # Ziskat rate plan ID
        rate_manager = get_rate_manager()
        if not rate_manager:
            result["error"] = "Rate manager není k dispozici"
            return result

        rate_plan_id = rate_manager.get_base_rate_plan_id()
        if not rate_plan_id:
            result["error"] = "Nepodařilo se získat rate plan ID"
            return result

        result["rate_plan_id"] = rate_plan_id

        # Aplikovat zmenu pres EQC API
        eqc_client = get_eqc_client()
        if not eqc_client:
            result["error"] = "EQC klient není k dispozici"
            return result

        eqc_result = eqc_client.update_rate(
            room_type_id=room_kind_id,
            rate_plan_id=rate_plan_id,
            target_date=target_date,
            new_rate=new_price,
            currency='CZK'
        )

        result["eqc_result"] = eqc_result
        result["success"] = eqc_result.get("success", False)

        if not result["success"]:
            result["error"] = eqc_result.get("error", "Neznámá chyba EQC API")

        return result

    except Exception as e:
        import traceback
        result["error"] = str(e)
        result["trace"] = traceback.format_exc()
        print(f"Error applying price to Previo: {e}")
        return result


def get_supabase_decisions(hotel_id=None, limit=100):
    """Nacte historii rozhodnuti ze Supabase."""
    try:
        headers = {
            'apikey': SUPABASE_KEY,
            'Authorization': f'Bearer {SUPABASE_KEY}',
            'Content-Type': 'application/json'
        }

        params = {
            'order': 'decided_at.desc',
            'limit': limit
        }

        if hotel_id:
            params['hotel_id'] = f'eq.{hotel_id}'

        response = requests.get(
            f'{SUPABASE_URL}/rest/v1/previo_recommendations',
            headers=headers,
            params=params,
            timeout=30
        )

        if response.status_code == 200:
            return response.json()
        return []

    except Exception as e:
        print(f"Error loading decisions: {e}")
        return []


def get_current_prices(date_from=None, date_to=None):
    """
    Ziska aktualni ceny z Previo XML API.
    Vraci slovnik: {room_kind_id: {occupancy: price}}
    """
    if date_from is None:
        date_from = date.today().strftime("%Y-%m-%d")
    if date_to is None:
        date_to = (date.today() + timedelta(days=60)).strftime("%Y-%m-%d")

    xml_request = f'''<?xml version="1.0" encoding="UTF-8"?>
<request>
  <login>{REST_CONFIG["username"]}</login>
  <password>{REST_CONFIG["password"]}</password>
  <hotId>{REST_CONFIG["hotel_id"]}</hotId>
  <term>
    <from>{date_from}</from>
    <to>{date_to}</to>
  </term>
  <currencies>
    <currency><code>CZK</code></currency>
  </currencies>
</request>'''

    try:
        response = requests.post(
            "https://api.previo.app/x1/hotel/getRates",
            headers={"Content-Type": "application/xml"},
            data=xml_request.encode('utf-8'),
            timeout=60
        )

        if response.status_code != 200:
            return {}

        # Parsovat XML odpoved
        root = ET.fromstring(response.content)

        prices = {}
        # Projit vsechny rate plany a sezony
        for rate_plan in root.findall('.//ratePlan'):
            for season in rate_plan.findall('.//season'):
                for obj_kind in season.findall('.//objectKind'):
                    obk_id = obj_kind.find('obkId')
                    if obk_id is not None:
                        room_kind_id = int(obk_id.text)
                        if room_kind_id not in prices:
                            prices[room_kind_id] = {}

                        for rate in obj_kind.findall('.//rate'):
                            occupancy = rate.find('occupancy')
                            price = rate.find('price')
                            if occupancy is not None and price is not None:
                                prices[room_kind_id][int(occupancy.text)] = float(price.text)

        return prices

    except Exception as e:
        print(f"Error getting prices: {e}")
        return {}


def get_recommendations_with_prices():
    """
    Ziska doporuceni a prida k nim aktualni ceny a nove doporucene ceny.
    """
    recommendations_data = get_recommendations_data()
    current_prices = get_current_prices()

    # Standardni obsazenost pro vypocet ceny (2 osoby)
    standard_occupancy = 2

    recommendations_with_prices = []

    for rec in recommendations_data.get('recommendations', []):
        room_kind_id = rec.get('room_kind_id')
        # Pretypovat na int pro porovnani s cenami
        if room_kind_id:
            try:
                room_kind_id = int(room_kind_id)
            except (ValueError, TypeError):
                pass
        recommended_change = rec.get('recommended_change', 0)

        # Ziskat aktualni cenu pro dany pokoj
        current_price = None
        new_price = None

        if room_kind_id and room_kind_id in current_prices:
            room_prices = current_prices[room_kind_id]
            # Pouzit cenu pro 2 osoby, nebo nejblizsi dostupnou
            if standard_occupancy in room_prices:
                current_price = room_prices[standard_occupancy]
            elif room_prices:
                current_price = list(room_prices.values())[0]

            if current_price and recommended_change:
                new_price = round(current_price * (1 + recommended_change / 100))

        rec_with_price = {**rec}
        rec_with_price['current_price'] = current_price
        rec_with_price['new_price'] = new_price
        rec_with_price['all_prices'] = current_prices.get(room_kind_id, {})
        recommendations_with_prices.append(rec_with_price)

    # Pripravit i denni souhrn s cenami
    daily_with_prices = []
    for daily in recommendations_data.get('daily', []):
        daily_copy = {**daily}
        daily_with_prices.append(daily_copy)

    return {
        'recommendations_with_prices': recommendations_with_prices,
        'daily': daily_with_prices,
        'learned_holidays': recommendations_data.get('learned_holidays', {}),
        'count': len(recommendations_with_prices),
        'prices_loaded': len(current_prices) > 0
    }
