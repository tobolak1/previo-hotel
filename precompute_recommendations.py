#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Predpocitani doporuceni - spousti se cronem 1x denne.
Ulozi vysledky do Supabase pro rychle nacteni.
"""
import sys
import os
import json
import requests
from datetime import datetime, date, timedelta

# Cesty
sys.path.insert(0, os.path.dirname(__file__))

# Konfigurace
SUPABASE_URL = "https://kchbzmncwdidjzxnegck.supabase.co"
SUPABASE_KEY = "sb_secret_52w8jQGJ2qYNu6RLURvpDw_0R1tRBrQ"

REST_CONFIG = {
    "username": "api@vincentluhacovice.cz",
    "password": "2P0QHc9XPph7",
    "hotel_id": "731186",
    "api_url": "https://api.previo.app/rest/"
}


def get_rest_client():
    from previo_api_client import PrevioRestClient
    return PrevioRestClient(
        username=REST_CONFIG["username"],
        password=REST_CONFIG["password"],
        hotel_id=REST_CONFIG["hotel_id"],
        api_url=REST_CONFIG["api_url"]
    )


def get_price_optimizer():
    from smart_price_optimizer import SmartRoomPriceOptimizer
    return SmartRoomPriceOptimizer(hotel_id=REST_CONFIG["hotel_id"])


def compute_recommendations():
    """Vypocita doporuceni a vrati data."""
    print(f"[{datetime.now()}] Zacinam vypocet doporuceni...")

    optimizer = get_price_optimizer()
    client = get_rest_client()

    today = date.today()
    date_from = today.strftime("%Y-%m-%d")
    date_to = (today + timedelta(days=60)).strftime("%Y-%m-%d")

    print(f"[{datetime.now()}] Nacitam obsazenost z Previo...")
    occupancy_data = client.get_occupancy_data(date_from, date_to)

    print(f"[{datetime.now()}] Generuji doporuceni...")
    daily_recommendations = optimizer.generate_recommendations(occupancy_data, days_ahead=60)

    learned_holidays = optimizer.get_learned_holiday_impacts()

    # Pripravit data
    daily_list = []
    room_list = []

    for daily_rec in daily_recommendations:
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
            "holiday": holiday_name,
            "holiday_impact": holiday_impact,
            "holiday_effect": learned_holidays.get(holiday_name, {}).get("effect") if holiday_name else None,
            "season": daily_rec.season.get("name") if daily_rec.season else None,
            "season_type": daily_rec.season.get("type") if daily_rec.season else None,
            "days_until": daily_rec.days_until,
            "recommendation_type": daily_rec.recommendation_type,
            "recommended_change": daily_rec.recommended_change,
            "reason": daily_rec.reason,
            "confidence": daily_rec.confidence,
            "decision": daily_rec.decision,
            "room_count_with_recommendations": len([r for r in daily_rec.room_recommendations if r.recommendation_type != "no_change"])
        })

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
                    "holiday": room_rec.holiday_name,
                    "holiday_impact": room_rec.holiday_learned_impact,
                    "season": room_rec.season.get("name") if room_rec.season else None,
                    "days_until": room_rec.days_until,
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
        "learned_holidays": learned_holidays,
        "computed_at": datetime.now().isoformat()
    }


def save_to_supabase(data):
    """Ulozi predpocitana data do Supabase."""
    print(f"[{datetime.now()}] Ukladam do Supabase...")

    headers = {
        'apikey': SUPABASE_KEY,
        'Authorization': f'Bearer {SUPABASE_KEY}',
        'Content-Type': 'application/json',
        'Prefer': 'resolution=merge-duplicates'
    }

    # Ulozit jako jeden zaznam s ID = hotel_id
    record = {
        'id': f"{REST_CONFIG['hotel_id']}_recommendations",
        'hotel_id': REST_CONFIG['hotel_id'],
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
        print(f"[{datetime.now()}] Ulozeno uspesne!")
        return True
    else:
        print(f"[{datetime.now()}] Chyba: {response.status_code} {response.text[:200]}")
        return False


def main():
    print("=" * 60)
    print("PREDPOCITANI DOPORUCENI")
    print("=" * 60)

    try:
        data = compute_recommendations()
        print(f"[{datetime.now()}] Vypocitano {data['daily_count']} dni, {data['count']} pokoju")

        save_to_supabase(data)

        print("=" * 60)
        print("HOTOVO!")
        print("=" * 60)

    except Exception as e:
        print(f"[{datetime.now()}] CHYBA: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
