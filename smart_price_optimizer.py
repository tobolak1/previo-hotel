#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SAASPrevio - Smart Price Optimizer v4
=====================================
Pokročilý cenový optimalizátor s UČENÍM:
- Automaticky zjistí vliv svátků z historických dat (ne předpoklady)
- Učí se z rozhodnutí uživatele (approved/rejected)
- Volitelně používá Claude pro komplexní analýzu
- Párování dnů v týdnu
- 2 měsíce dopředu
"""

import logging
import requests
import os
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
import json

logger = logging.getLogger("smart_price_optimizer")

# Konfigurace
SUPABASE_URL = "https://kchbzmncwdidjzxnegck.supabase.co"
SUPABASE_KEY = "sb_secret_52w8jQGJ2qYNu6RLURvpDw_0R1tRBrQ"
HOTEL_ID = "731186"

# Claude API (volitelné)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# Kategorie pokojů
ROOM_CATEGORIES = {
    "economy": {"base_modifier": 0.8, "name": "Economy"},
    "standard": {"base_modifier": 1.0, "name": "Standard"},
    "premium": {"base_modifier": 1.3, "name": "Premium"},
    "apartment": {"base_modifier": 1.5, "name": "Apartmán"}
}

ROOM_KINDS = {
    640240: {"name": "101", "category": "standard", "capacity": 3},
    640238: {"name": "201", "category": "premium", "capacity": 6},
    816827: {"name": "202", "category": "standard", "capacity": 4},
    540820: {"name": "203", "category": "standard", "capacity": 3},
    924427: {"name": "204", "category": "standard", "capacity": 3},
    924455: {"name": "205", "category": "standard", "capacity": 3},
    537702: {"name": "301", "category": "economy", "capacity": 3},
    924459: {"name": "302", "category": "economy", "capacity": 3},
    640234: {"name": "303", "category": "standard", "capacity": 4},
    640236: {"name": "304", "category": "standard", "capacity": 3},
    924463: {"name": "305", "category": "economy", "capacity": 3},
    924467: {"name": "306", "category": "economy", "capacity": 3},
    640232: {"name": "307", "category": "economy", "capacity": 2},
    902136: {"name": "Apt A", "category": "apartment", "capacity": 4},
    924723: {"name": "Apt B", "category": "apartment", "capacity": 4},
}


# =============================================================================
# SVÁTKY - DEFINICE (bez předpokladů o vlivu)
# =============================================================================

class CzechHolidays:
    """České svátky - jen definice, vliv se učí z dat."""

    FIXED_HOLIDAYS = {
        (1, 1): "Nový rok",
        (5, 1): "Svátek práce",
        (5, 8): "Den vítězství",
        (7, 5): "Cyril a Metoděj",
        (7, 6): "Jan Hus",
        (9, 28): "Den české státnosti",
        (10, 28): "Vznik Československa",
        (11, 17): "Den boje za svobodu",
        (12, 24): "Štědrý den",
        (12, 25): "1. svátek vánoční",
        (12, 26): "2. svátek vánoční",
        (12, 31): "Silvestr",
    }

    @staticmethod
    def get_easter(year: int) -> date:
        """Vypočítá datum Velikonočního pondělí."""
        a = year % 19
        b = year // 100
        c = year % 100
        d = b // 4
        e = b % 4
        f = (b + 8) // 25
        g = (b - f + 1) // 3
        h = (19 * a + b - d - g + 15) % 30
        i = c // 4
        k = c % 4
        l = (32 + 2 * e + 2 * i - h - k) % 7
        m = (a + 11 * h + 22 * l) // 451
        month = (h + l - 7 * m + 114) // 31
        day = ((h + l - 7 * m + 114) % 31) + 1
        easter_sunday = date(year, month, day)
        return easter_sunday + timedelta(days=1)

    @classmethod
    def get_holidays_for_year(cls, year: int) -> Dict[date, str]:
        """Vrátí všechny svátky pro daný rok."""
        holidays = {}

        for (month, day), name in cls.FIXED_HOLIDAYS.items():
            try:
                holidays[date(year, month, day)] = name
            except ValueError:
                pass

        easter_monday = cls.get_easter(year)
        holidays[easter_monday] = "Velikonoční pondělí"
        holidays[easter_monday - timedelta(days=2)] = "Velký pátek"

        # Otevírání pramenů Luhačovice (víkend před Letnicemi / Svatodušní nedělí)
        # Letnice = 49 dní po Velikonoční neděli
        easter_sunday = easter_monday - timedelta(days=1)
        pentecost = easter_sunday + timedelta(days=49)  # Svatodušní neděle
        # Otevírání pramenů = sobota týden před Letnicemi
        otevirani_saturday = pentecost - timedelta(days=8)  # Sobota před
        otevirani_sunday = pentecost - timedelta(days=7)    # Neděle před
        holidays[otevirani_saturday] = "Otevírání pramenů"
        holidays[otevirani_sunday] = "Otevírání pramenů"

        return holidays

    @classmethod
    def get_holiday_info(cls, check_date: date) -> Optional[str]:
        """Vrátí název svátku pro dané datum."""
        holidays = cls.get_holidays_for_year(check_date.year)
        return holidays.get(check_date)

    @classmethod
    def get_season(cls, check_date: date) -> Dict:
        """Vrátí sezónu."""
        month = check_date.month
        if month in [12, 1, 2]:
            return {"name": "zima", "type": "low"}
        elif month in [3, 4]:
            return {"name": "jaro", "type": "shoulder"}
        elif month in [5, 6]:
            return {"name": "předsezóna", "type": "high"}
        elif month in [7, 8]:
            return {"name": "hlavní sezóna", "type": "peak"}
        elif month in [9, 10]:
            return {"name": "posezóna", "type": "high"}
        else:
            return {"name": "podzim", "type": "low"}


# =============================================================================
# DATOVÉ STRUKTURY
# =============================================================================

@dataclass
class RoomRecommendation:
    """Cenové doporučení pro pokoj."""
    id: str
    date: str
    room_kind_id: int
    room_name: str
    room_category: str
    capacity: int
    is_occupied: bool
    # Historická data
    historical_occupancy_rate: float
    same_weekday_occupancy: float
    last_year_same_weekday: bool
    # Kontext
    days_until: int
    weekday: int
    weekday_name: str
    is_weekend: bool
    # Svátky (s naučeným vlivem)
    holiday_name: Optional[str]
    holiday_learned_impact: float  # Naučený vliv z dat (-1 až +1)
    season: Dict
    # Doporučení
    recommendation_type: str
    recommended_change: float
    reason: str
    confidence: float
    # Faktory pro vysvětlení
    factors: Dict = field(default_factory=dict)
    decision: str = "pending"


@dataclass
class DailyRecommendation:
    """Souhrnné doporučení pro den."""
    id: str
    date: str
    weekday: int
    weekday_name: str
    is_weekend: bool
    total_rooms: int
    occupied_rooms: int
    free_rooms: int
    occupancy_percent: float
    # Historická data
    historical_avg: float
    same_weekday_historical: float
    last_year_same_weekday: float
    # Svátek s naučeným vlivem
    holiday_name: Optional[str]
    holiday_learned_impact: float
    season: Dict
    days_until: int
    # Doporučení
    recommendation_type: str
    recommended_change: float
    reason: str
    confidence: float
    room_recommendations: List[RoomRecommendation] = field(default_factory=list)
    decision: str = "pending"


# =============================================================================
# DATA PROVIDER
# =============================================================================

class SupabaseDataProvider:
    """Poskytovatel dat ze Supabase."""

    def __init__(self, url: str = SUPABASE_URL, key: str = SUPABASE_KEY):
        self.url = url
        self.key = key
        self.headers = {
            'apikey': key,
            'Authorization': f'Bearer {key}',
            'Content-Type': 'application/json'
        }
        self._cache = {}
        self._cache_time = {}
        self._cache_ttl = 300

    def _fetch_all(self, endpoint: str, params: dict = None) -> List[Dict]:
        """Načte všechny záznamy."""
        all_data = []
        offset = 0
        batch_size = 1000

        while True:
            headers = self.headers.copy()
            headers['Range'] = f'{offset}-{offset + batch_size - 1}'

            try:
                r = requests.get(
                    f'{self.url}/rest/v1/{endpoint}',
                    headers=headers,
                    params=params,
                    timeout=30
                )
                if r.status_code in [200, 206]:
                    batch = r.json()
                    all_data.extend(batch)
                    if len(batch) < batch_size:
                        break
                    offset += batch_size
                else:
                    break
            except Exception as e:
                logger.error(f"Supabase error: {e}")
                break

        return all_data

    def get_room_occupancy_data(self, hotel_id: str = HOTEL_ID) -> List[Dict]:
        """Načte všechna data o obsazenosti pokojů."""
        cache_key = f"room_occupancy_{hotel_id}"
        now = datetime.now()

        if (cache_key in self._cache and cache_key in self._cache_time and
            (now - self._cache_time[cache_key]).seconds < self._cache_ttl):
            return self._cache[cache_key]

        params = {
            'hotel_id': f'eq.{hotel_id}',
            'order': 'date.asc,room_kind_id.asc'
        }

        data = self._fetch_all('previo_room_occupancy', params)

        self._cache[cache_key] = data
        self._cache_time[cache_key] = now

        return data

    def get_user_decisions(self, hotel_id: str = HOTEL_ID) -> List[Dict]:
        """Načte rozhodnutí uživatele z databáze."""
        cache_key = f"decisions_{hotel_id}"
        now = datetime.now()

        if (cache_key in self._cache and cache_key in self._cache_time and
            (now - self._cache_time[cache_key]).seconds < self._cache_ttl):
            return self._cache[cache_key]

        params = {
            'hotel_id': f'eq.{hotel_id}',
            'order': 'created_at.desc'
        }

        data = self._fetch_all('previo_recommendations', params)

        self._cache[cache_key] = data
        self._cache_time[cache_key] = now

        return data

    def save_decision(self, recommendation_id: str, decision: str,
                     user_change: float = None, hotel_id: str = HOTEL_ID) -> bool:
        """Uloží rozhodnutí uživatele."""
        headers = self.headers.copy()
        headers['Prefer'] = 'resolution=merge-duplicates'

        data = {
            'id': recommendation_id,
            'hotel_id': hotel_id,
            'decision': decision,
            'user_change': user_change,
            'decided_at': datetime.now().isoformat()
        }

        try:
            r = requests.post(
                f'{self.url}/rest/v1/previo_recommendations',
                headers=headers,
                json=data,
                timeout=30
            )
            return r.status_code in [200, 201, 409]
        except Exception as e:
            logger.error(f"Error saving decision: {e}")
            return False


# =============================================================================
# HOLIDAY IMPACT LEARNER
# =============================================================================

class HolidayImpactLearner:
    """Učí se vliv svátků z historických dat."""

    def __init__(self, room_data: Dict[int, Dict[str, Dict]]):
        self.room_data = room_data
        self._holiday_impacts = None

    def learn_holiday_impacts(self) -> Dict[str, Dict]:
        """
        Naučí se vliv svátků porovnáním obsazenosti během svátku
        vs. průměrná obsazenost ve stejný den v týdnu.

        Vrací: {holiday_name: {impact: float, sample_count: int, avg_occupancy: float}}
        """
        if self._holiday_impacts is not None:
            return self._holiday_impacts

        # Shromáždit data pro každý svátek
        holiday_data = defaultdict(list)
        weekday_baseline = defaultdict(list)  # Baseline pro každý den v týdnu

        for room_id, dates in self.room_data.items():
            for date_str, values in dates.items():
                try:
                    d = datetime.strptime(date_str, '%Y-%m-%d').date()
                    is_occupied = values.get('is_occupied', False)
                    weekday = d.weekday()

                    # Zjistit, zda je svátek
                    holiday_name = CzechHolidays.get_holiday_info(d)

                    if holiday_name:
                        holiday_data[holiday_name].append({
                            'date': d,
                            'is_occupied': is_occupied,
                            'weekday': weekday
                        })
                    else:
                        # Ne-svátek - použít jako baseline
                        weekday_baseline[weekday].append(is_occupied)

                except ValueError:
                    continue

        # Vypočítat baseline obsazenost pro každý den v týdnu
        weekday_avg = {}
        for weekday, occupancies in weekday_baseline.items():
            if occupancies:
                weekday_avg[weekday] = sum(1 for o in occupancies if o) / len(occupancies) * 100

        # Vypočítat vliv svátků
        self._holiday_impacts = {}

        for holiday_name, records in holiday_data.items():
            if len(records) < 5:  # Potřebujeme aspoň 5 vzorků
                continue

            # Průměrná obsazenost během svátku
            holiday_occupancy = sum(1 for r in records if r['is_occupied']) / len(records) * 100

            # Baseline pro dny v týdnu, kdy svátek připadá
            weekdays_in_holiday = [r['weekday'] for r in records]
            baseline_values = [weekday_avg.get(wd, 50) for wd in weekdays_in_holiday if wd in weekday_avg]

            if baseline_values:
                baseline_avg = sum(baseline_values) / len(baseline_values)
            else:
                baseline_avg = 50

            # Impact: rozdíl mezi svátkem a baseline (normalizováno na -1 až +1)
            if baseline_avg > 0:
                raw_impact = (holiday_occupancy - baseline_avg) / baseline_avg
            else:
                raw_impact = 0

            # Omezit na -1 až +1
            impact = max(-1, min(1, raw_impact))

            self._holiday_impacts[holiday_name] = {
                'impact': round(impact, 2),
                'holiday_occupancy': round(holiday_occupancy, 1),
                'baseline_occupancy': round(baseline_avg, 1),
                'sample_count': len(records),
                'effect': 'positive' if impact > 0.1 else ('negative' if impact < -0.1 else 'neutral')
            }

        logger.info(f"Naučeno {len(self._holiday_impacts)} svátků")
        return self._holiday_impacts

    def get_holiday_impact(self, holiday_name: str) -> float:
        """Vrátí naučený vliv svátku (-1 až +1)."""
        impacts = self.learn_holiday_impacts()
        if holiday_name in impacts:
            return impacts[holiday_name]['impact']
        return 0  # Neznámý svátek - neutrální


# =============================================================================
# DECISION LEARNER
# =============================================================================

class DecisionLearner:
    """Učí se z rozhodnutí uživatele."""

    def __init__(self, decisions: List[Dict]):
        self.decisions = decisions
        self._patterns = None

    def learn_patterns(self) -> Dict:
        """
        Analyzuje rozhodnutí uživatele a hledá vzorce.
        """
        if self._patterns is not None:
            return self._patterns

        self._patterns = {
            'approval_rate': 0,
            'avg_user_adjustment': 0,
            'by_weekday': {},
            'by_season': {},
            'by_occupancy_level': {}
        }

        if not self.decisions:
            return self._patterns

        approved = [d for d in self.decisions if d.get('decision') == 'approved']
        rejected = [d for d in self.decisions if d.get('decision') == 'rejected']
        modified = [d for d in self.decisions if d.get('decision') == 'modified']

        total = len(approved) + len(rejected) + len(modified)
        if total > 0:
            self._patterns['approval_rate'] = len(approved) / total

        # Průměrná úprava uživatelem
        user_changes = [d.get('user_change', 0) for d in modified if d.get('user_change')]
        if user_changes:
            self._patterns['avg_user_adjustment'] = sum(user_changes) / len(user_changes)

        return self._patterns

    def adjust_recommendation(self, recommendation_type: str, change: float,
                              context: Dict) -> Tuple[str, float]:
        """
        Upraví doporučení na základě naučených vzorců.
        """
        patterns = self.learn_patterns()

        # Pokud uživatel většinou zamítá, být konzervativnější
        if patterns['approval_rate'] < 0.5 and len(self.decisions) > 10:
            change = change * 0.8  # Zmírnit o 20%

        # Pokud uživatel typicky upravuje, aplikovat průměrnou úpravu
        avg_adj = patterns.get('avg_user_adjustment', 0)
        if abs(avg_adj) > 2:
            change = change + (avg_adj * 0.3)  # Částečně aplikovat

        return (recommendation_type, change)


# =============================================================================
# HLAVNÍ OPTIMALIZÁTOR
# =============================================================================

class SmartRoomPriceOptimizer:
    """Pokročilý cenový optimalizátor s učením."""

    WEEKDAY_NAMES = ['Po', 'Út', 'St', 'Čt', 'Pá', 'So', 'Ne']

    def __init__(self, hotel_id: str = HOTEL_ID):
        self.hotel_id = hotel_id
        self.data_provider = SupabaseDataProvider()
        self._room_data = None
        self._weekday_patterns = None
        self._holiday_learner = None
        self._decision_learner = None

    def _load_room_data(self) -> Dict[int, Dict[str, Dict]]:
        """Načte a indexuje data po pokojích."""
        if self._room_data is not None:
            return self._room_data

        raw_data = self.data_provider.get_room_occupancy_data(self.hotel_id)

        self._room_data = defaultdict(dict)
        for record in raw_data:
            room_kind_id = record.get('room_kind_id')
            date_str = record.get('date')

            if date_str and room_kind_id:
                if hasattr(date_str, 'isoformat'):
                    date_str = date_str.isoformat()
                elif hasattr(date_str, 'strftime'):
                    date_str = date_str.strftime('%Y-%m-%d')

                try:
                    d = datetime.strptime(date_str, '%Y-%m-%d').date()
                    weekday = d.weekday()
                except:
                    weekday = 0

                self._room_data[room_kind_id][date_str] = {
                    'is_occupied': record.get('is_occupied', False),
                    'room_name': record.get('room_name', ''),
                    'room_category': record.get('room_category', 'unknown'),
                    'capacity': record.get('capacity', 0),
                    'weekday': weekday
                }

        # Inicializovat holiday learner
        self._holiday_learner = HolidayImpactLearner(self._room_data)

        # Inicializovat decision learner
        decisions = self.data_provider.get_user_decisions(self.hotel_id)
        self._decision_learner = DecisionLearner(decisions)

        return self._room_data

    def _calculate_weekday_patterns(self) -> Dict[int, Dict[int, Dict]]:
        """Vypočítá vzorce obsazenosti podle dne v týdnu."""
        if self._weekday_patterns is not None:
            return self._weekday_patterns

        room_data = self._load_room_data()
        current_year = date.today().year

        self._weekday_patterns = {}

        for room_kind_id, dates in room_data.items():
            weekday_data = defaultdict(list)

            for date_str, values in dates.items():
                try:
                    d = datetime.strptime(date_str, '%Y-%m-%d').date()
                    weekday = d.weekday()
                    year = d.year

                    # Váha podle stáří
                    age = current_year - year
                    weight = 1.0 / (1 + age * 0.3)

                    weekday_data[weekday].append({
                        'is_occupied': values['is_occupied'],
                        'weight': weight,
                        'year': year
                    })
                except ValueError:
                    continue

            room_patterns = {}
            for weekday, records in weekday_data.items():
                if records:
                    total_weight = sum(r['weight'] for r in records)
                    weighted_occupancy = sum(
                        (1 if r['is_occupied'] else 0) * r['weight']
                        for r in records
                    ) / total_weight * 100

                    room_patterns[weekday] = {
                        'weighted_occupancy': round(weighted_occupancy, 1),
                        'sample_count': len(records),
                        'years': sorted(set(r['year'] for r in records))
                    }

            self._weekday_patterns[room_kind_id] = room_patterns

        return self._weekday_patterns

    def _get_same_weekday_history(self, room_kind_id: int, target_date: date,
                                   years_back: int = 5) -> List[Dict]:
        """Vrátí historii pro stejný den v týdnu."""
        room_data = self._load_room_data()
        if room_kind_id not in room_data:
            return []

        target_weekday = target_date.weekday()
        target_week = target_date.isocalendar()[1]

        results = []

        for year in range(target_date.year - years_back, target_date.year):
            try:
                jan4 = date(year, 1, 4)
                start_of_year = jan4 - timedelta(days=jan4.weekday())
                target_week_start = start_of_year + timedelta(weeks=target_week - 1)
                same_weekday_date = target_week_start + timedelta(days=target_weekday)

                date_str = same_weekday_date.strftime('%Y-%m-%d')

                if date_str in room_data[room_kind_id]:
                    results.append({
                        'year': year,
                        'date': date_str,
                        'is_occupied': room_data[room_kind_id][date_str]['is_occupied'],
                        'weekday': target_weekday
                    })
            except:
                continue

        return sorted(results, key=lambda x: x['year'], reverse=True)

    def generate_recommendations(self, current_occupancy_data: Dict,
                                  days_ahead: int = 60) -> List[DailyRecommendation]:
        """Generuje cenová doporučení s učením."""
        recommendations = []
        today = date.today()

        if 'availability' not in current_occupancy_data:
            return recommendations

        self._load_room_data()
        weekday_patterns = self._calculate_weekday_patterns()

        # Naučit se vliv svátků
        holiday_impacts = self._holiday_learner.learn_holiday_impacts()

        availability_list = []
        for rate_plan in current_occupancy_data.get('availability', []):
            availability_list.extend(rate_plan.get('availability', []))

        for day_data in availability_list:
            date_str = day_data.get('date', '')
            try:
                target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                continue

            days_until = (target_date - today).days
            if days_until <= 0 or days_until > days_ahead:
                continue

            weekday = target_date.weekday()
            weekday_name = self.WEEKDAY_NAMES[weekday]
            is_weekend = weekday >= 5

            # Svátek s naučeným vlivem
            holiday_name = CzechHolidays.get_holiday_info(target_date)
            holiday_impact = self._holiday_learner.get_holiday_impact(holiday_name) if holiday_name else 0

            season = CzechHolidays.get_season(target_date)

            room_kinds_data = day_data.get('roomKinds', [])
            room_recs = []
            total_rooms = len(room_kinds_data)
            occupied_count = 0

            for room_kind in room_kinds_data:
                room_kind_id = room_kind.get('id')
                is_occupied = room_kind.get('availability') == 0

                if is_occupied:
                    occupied_count += 1

                room_info = ROOM_KINDS.get(room_kind_id, {})
                room_name = room_info.get('name', str(room_kind_id))
                room_category = room_info.get('category', 'unknown')
                capacity = room_info.get('capacity', 0)

                weekday_history = self._get_same_weekday_history(room_kind_id, target_date)
                weekday_pattern = weekday_patterns.get(room_kind_id, {}).get(weekday, {})
                same_weekday_occupancy = weekday_pattern.get('weighted_occupancy', 50)

                last_year_same_weekday = False
                if weekday_history:
                    last_year_record = next((h for h in weekday_history if h['year'] == target_date.year - 1), None)
                    if last_year_record:
                        last_year_same_weekday = last_year_record['is_occupied']

                # Rozhodnutí
                rec_type, change, reason, factors = self._decide_room_price(
                    is_occupied=is_occupied,
                    room_category=room_category,
                    same_weekday_occupancy=same_weekday_occupancy,
                    last_year_same_weekday=last_year_same_weekday,
                    days_until=days_until,
                    is_weekend=is_weekend,
                    holiday_name=holiday_name,
                    holiday_impact=holiday_impact,
                    season=season
                )

                # Upravit podle naučených vzorců z rozhodnutí
                if self._decision_learner:
                    rec_type, change = self._decision_learner.adjust_recommendation(
                        rec_type, change, factors
                    )

                confidence = self._calculate_confidence(
                    weekday_pattern, days_until, len(weekday_history),
                    holiday_name, holiday_impacts
                )

                room_rec = RoomRecommendation(
                    id=f"{date_str}_{room_kind_id}",
                    date=date_str,
                    room_kind_id=room_kind_id,
                    room_name=room_name,
                    room_category=room_category,
                    capacity=capacity,
                    is_occupied=is_occupied,
                    historical_occupancy_rate=round(same_weekday_occupancy, 1),
                    same_weekday_occupancy=round(same_weekday_occupancy, 1),
                    last_year_same_weekday=last_year_same_weekday,
                    days_until=days_until,
                    weekday=weekday,
                    weekday_name=weekday_name,
                    is_weekend=is_weekend,
                    holiday_name=holiday_name,
                    holiday_learned_impact=round(holiday_impact, 2),
                    season=season,
                    recommendation_type=rec_type,
                    recommended_change=round(change, 1),
                    reason=reason,
                    confidence=round(confidence, 2),
                    factors=factors
                )
                room_recs.append(room_rec)

            # Denní souhrn
            occupancy_pct = (occupied_count / total_rooms * 100) if total_rooms > 0 else 0
            historical_avg = self._get_daily_historical_avg(target_date)
            same_weekday_hist = historical_avg
            last_year_occ = self._get_last_year_same_weekday_occupancy(target_date)

            day_rec_type, day_change, day_reason = self._decide_daily_price(
                occupancy_pct, historical_avg, same_weekday_hist,
                last_year_occ, days_until, is_weekend,
                holiday_name, holiday_impact, season
            )

            day_confidence = 0.7
            if holiday_name and holiday_name in holiday_impacts:
                day_confidence += 0.1

            daily_rec = DailyRecommendation(
                id=f"{date_str}_daily",
                date=date_str,
                weekday=weekday,
                weekday_name=weekday_name,
                is_weekend=is_weekend,
                total_rooms=total_rooms,
                occupied_rooms=occupied_count,
                free_rooms=total_rooms - occupied_count,
                occupancy_percent=round(occupancy_pct, 1),
                historical_avg=round(historical_avg, 1),
                same_weekday_historical=round(same_weekday_hist, 1),
                last_year_same_weekday=round(last_year_occ, 1),
                holiday_name=holiday_name,
                holiday_learned_impact=round(holiday_impact, 2),
                season=season,
                days_until=days_until,
                recommendation_type=day_rec_type,
                recommended_change=round(day_change, 1),
                reason=day_reason,
                confidence=round(day_confidence, 2),
                room_recommendations=room_recs
            )
            recommendations.append(daily_rec)

        recommendations.sort(key=lambda r: r.date)
        return recommendations

    def _decide_room_price(self, is_occupied: bool, room_category: str,
                           same_weekday_occupancy: float, last_year_same_weekday: bool,
                           days_until: int, is_weekend: bool,
                           holiday_name: Optional[str], holiday_impact: float,
                           season: Dict) -> Tuple[str, float, str, Dict]:
        """Rozhodne o cenové změně s naučeným vlivem svátků."""

        factors = {
            'is_occupied': is_occupied,
            'same_weekday_occupancy': same_weekday_occupancy,
            'last_year_same_weekday': last_year_same_weekday,
            'days_until': days_until,
            'is_weekend': is_weekend,
            'holiday_name': holiday_name,
            'holiday_impact': holiday_impact,
            'season': season['name']
        }

        if is_occupied:
            return ("no_change", 0, "Pokoj je obsazený", factors)

        category_mod = ROOM_CATEGORIES.get(room_category, {}).get('base_modifier', 1.0)

        # === SVÁTKY S NAUČENÝM VLIVEM ===

        if holiday_name and holiday_impact != 0:
            if holiday_impact > 0.2:
                # Pozitivní svátek - zvýšit cenu
                markup = 15 * (1 + holiday_impact) * category_mod
                return ("markup", markup,
                        f"Svátek ({holiday_name}) má pozitivní vliv (+{holiday_impact*100:.0f}%)",
                        factors)
            elif holiday_impact < -0.2:
                # Negativní svátek - snížit cenu
                discount = -15 * (1 + abs(holiday_impact)) * category_mod
                return ("discount", discount,
                        f"Svátek ({holiday_name}) má negativní vliv ({holiday_impact*100:.0f}%)",
                        factors)

        # === VÍKENDY ===

        if is_weekend:
            if same_weekday_occupancy > 70:
                markup = 12 * category_mod
                return ("markup", markup,
                        f"Víkend s vysokou historickou obsazeností ({same_weekday_occupancy}%)",
                        factors)
            elif same_weekday_occupancy < 40 and days_until <= 7:
                discount = -12 * category_mod
                return ("discount", discount,
                        f"Víkend s nízkou obsazeností ({same_weekday_occupancy}%)",
                        factors)

        # === BLÍZKÝ TERMÍN ===

        if days_until <= 3:
            if same_weekday_occupancy < 40:
                discount = -20 * category_mod
                return ("discount", discount,
                        f"Blízký termín ({days_until}d), nízká hist. obsazenost ({same_weekday_occupancy}%)",
                        factors)
            elif same_weekday_occupancy < 60:
                discount = -15 * category_mod
                return ("discount", discount,
                        f"Blízký termín ({days_until}d)",
                        factors)

        if days_until <= 7:
            if same_weekday_occupancy < 50:
                discount = -12 * category_mod
                return ("discount", discount,
                        f"Pokoj obvykle obsazený jen {same_weekday_occupancy}% času",
                        factors)
            if last_year_same_weekday:
                discount = -10 * category_mod
                return ("discount", discount,
                        f"Loni byl v tento {self.WEEKDAY_NAMES[factors.get('weekday', 0)]} obsazený",
                        factors)

        # === SEZÓNNÍ ÚPRAVY ===

        if season['type'] == 'peak' and same_weekday_occupancy > 70:
            markup = 12 * category_mod
            return ("markup", markup,
                    f"Hlavní sezóna, vysoká poptávka ({same_weekday_occupancy}%)",
                    factors)

        if season['type'] == 'low' and same_weekday_occupancy < 40:
            discount = -10 * category_mod
            return ("discount", discount,
                    f"Mimo sezónu, nízká hist. obsazenost ({same_weekday_occupancy}%)",
                    factors)

        # === STŘEDNÍ TERMÍN ===

        if days_until <= 14 and same_weekday_occupancy < 50:
            discount = -10 * category_mod
            return ("discount", discount,
                    f"Hist. obsazenost {same_weekday_occupancy}%",
                    factors)

        # === VYSOKÁ POPTÁVKA ===

        if same_weekday_occupancy > 80:
            markup = 12 * category_mod
            return ("markup", markup,
                    f"Vysoká historická poptávka ({same_weekday_occupancy}%)",
                    factors)

        return ("no_change", 0, "", factors)

    def _decide_daily_price(self, occupancy_pct: float, historical_avg: float,
                            same_weekday_hist: float, last_year_occ: float,
                            days_until: int, is_weekend: bool,
                            holiday_name: Optional[str], holiday_impact: float,
                            season: Dict) -> Tuple[str, float, str]:
        """Rozhodne o celkové cenové změně pro den."""

        # Svátky s naučeným vlivem
        if holiday_name and holiday_impact != 0:
            if holiday_impact > 0.2 and occupancy_pct > 70:
                return ("markup", 20 * (1 + holiday_impact),
                        f"Svátek ({holiday_name}) + vysoká obsazenost")
            elif holiday_impact < -0.2 and days_until <= 14:
                return ("discount", -15 * (1 + abs(holiday_impact)),
                        f"Svátek ({holiday_name}) - historicky nízká poptávka")

        # Kriticky nízká obsazenost
        if occupancy_pct < 20 and days_until <= 7:
            return ("discount", -20, f"Kriticky nízká obsazenost ({occupancy_pct}%)")

        if occupancy_pct < 35 and days_until <= 7:
            return ("discount", -15, f"Nízká obsazenost ({occupancy_pct}%)")

        # Porovnání s historií
        diff_from_weekday = occupancy_pct - same_weekday_hist

        if diff_from_weekday < -20:
            return ("discount", -15, f"Pod průměrem ({occupancy_pct}% vs {same_weekday_hist}%)")

        if diff_from_weekday < -10 and days_until <= 14:
            return ("discount", -10, f"Pod historickým průměrem")

        # Vysoká obsazenost
        if occupancy_pct > 85:
            return ("markup", 15, f"Vysoká obsazenost ({occupancy_pct}%)")

        if occupancy_pct > 70 and diff_from_weekday > 10:
            return ("markup", 10, f"Nad historickým průměrem")

        return ("no_change", 0, "")

    def _calculate_confidence(self, weekday_pattern: Dict, days_until: int,
                               history_count: int, holiday_name: Optional[str],
                               holiday_impacts: Dict) -> float:
        """Vypočítá jistotu doporučení."""
        confidence = 0.5

        sample_count = weekday_pattern.get('sample_count', 0)
        if sample_count >= 50:
            confidence += 0.2
        elif sample_count >= 20:
            confidence += 0.15
        elif sample_count >= 10:
            confidence += 0.1

        if history_count >= 4:
            confidence += 0.1

        if days_until <= 7:
            confidence += 0.1
        elif days_until <= 14:
            confidence += 0.05

        # Vyšší confidence pro naučené svátky
        if holiday_name and holiday_name in holiday_impacts:
            impact_data = holiday_impacts[holiday_name]
            if impact_data.get('sample_count', 0) >= 10:
                confidence += 0.1

        return min(confidence, 0.95)

    def _get_daily_historical_avg(self, target_date: date) -> float:
        """Průměrná obsazenost pro daný den."""
        weekday_patterns = self._calculate_weekday_patterns()
        weekday = target_date.weekday()

        total = 0
        count = 0
        for room_id, patterns in weekday_patterns.items():
            if weekday in patterns:
                total += patterns[weekday]['weighted_occupancy']
                count += 1

        return total / count if count > 0 else 50

    def _get_last_year_same_weekday_occupancy(self, target_date: date) -> float:
        """Obsazenost loni ve stejný den v týdnu."""
        room_data = self._load_room_data()
        target_weekday = target_date.weekday()
        target_week = target_date.isocalendar()[1]
        last_year = target_date.year - 1

        occupied = 0
        total = 0

        for room_id in ROOM_KINDS.keys():
            if room_id not in room_data:
                continue

            try:
                jan4 = date(last_year, 1, 4)
                start_of_year = jan4 - timedelta(days=jan4.weekday())
                target_week_start = start_of_year + timedelta(weeks=target_week - 1)
                same_weekday_date = target_week_start + timedelta(days=target_weekday)
                date_str = same_weekday_date.strftime('%Y-%m-%d')

                if date_str in room_data[room_id]:
                    total += 1
                    if room_data[room_id][date_str]['is_occupied']:
                        occupied += 1
            except:
                continue

        return (occupied / total * 100) if total > 0 else 50

    def get_learned_holiday_impacts(self) -> Dict:
        """Vrátí naučený vliv svátků."""
        self._load_room_data()
        return self._holiday_learner.learn_holiday_impacts()

    def get_year_comparison(self, current_data: Dict) -> Dict:
        """Meziroční srovnání."""
        today = date.today()
        week_start = today - timedelta(days=today.weekday())

        holiday_impacts = self.get_learned_holiday_impacts()

        comparison = {
            'current_week_avg': 0,
            'last_year_week_avg': 0,
            'historical_avg': 0,
            'difference': 0,
            'days': [],
            'season': CzechHolidays.get_season(today),
            'learned_holidays': holiday_impacts
        }

        current_values = []
        last_year_values = []

        for i in range(7):
            day = week_start + timedelta(days=i)
            day_str = day.strftime('%Y-%m-%d')
            weekday_name = self.WEEKDAY_NAMES[day.weekday()]

            current_occ = None
            last_year_occ = self._get_last_year_same_weekday_occupancy(day)

            if current_occ is not None:
                current_values.append(current_occ)
            last_year_values.append(last_year_occ)

            holiday = CzechHolidays.get_holiday_info(day)
            holiday_impact = self._holiday_learner.get_holiday_impact(holiday) if holiday else 0

            comparison['days'].append({
                'date': day_str,
                'day_name': weekday_name,
                'current': current_occ,
                'last_year': round(last_year_occ, 1),
                'is_weekend': day.weekday() >= 5,
                'holiday': holiday,
                'holiday_impact': round(holiday_impact, 2) if holiday else None
            })

        if current_values:
            comparison['current_week_avg'] = round(sum(current_values) / len(current_values), 1)
        if last_year_values:
            comparison['last_year_week_avg'] = round(sum(last_year_values) / len(last_year_values), 1)

        comparison['historical_avg'] = round(self._get_daily_historical_avg(today), 1)
        comparison['difference'] = round(
            comparison['current_week_avg'] - comparison['last_year_week_avg'], 1
        )

        return comparison

    def get_statistics(self) -> Dict:
        """Statistiky o datech a učení."""
        room_data = self._load_room_data()
        weekday_patterns = self._calculate_weekday_patterns()
        holiday_impacts = self.get_learned_holiday_impacts()

        total_records = sum(len(dates) for dates in room_data.values())

        years = set()
        for dates in room_data.values():
            for date_str in dates.keys():
                try:
                    years.add(int(date_str[:4]))
                except:
                    pass

        stats = {
            'total_records': total_records,
            'rooms_count': len(room_data),
            'years_of_data': len(years),
            'years': sorted(years),
            'learned_holidays': holiday_impacts,
            'by_weekday': {},
            'by_category': {}
        }

        for weekday in range(7):
            weekday_occs = []
            for room_id, patterns in weekday_patterns.items():
                if weekday in patterns:
                    weekday_occs.append(patterns[weekday]['weighted_occupancy'])

            if weekday_occs:
                stats['by_weekday'][self.WEEKDAY_NAMES[weekday]] = {
                    'avg_occupancy': round(sum(weekday_occs) / len(weekday_occs), 1),
                    'is_weekend': weekday >= 5
                }

        for category, info in ROOM_CATEGORIES.items():
            category_rooms = [r for r, rinfo in ROOM_KINDS.items() if rinfo['category'] == category]
            stats['by_category'][category] = {
                'name': info['name'],
                'room_count': len(category_rooms)
            }

        return stats


class SmartOccupancyPredictor:
    """Predikce obsazenosti."""

    def __init__(self, optimizer: SmartRoomPriceOptimizer):
        self.optimizer = optimizer

    def get_predictions_for_period(self, occupancy_data: Dict, days_ahead: int = 60) -> List[Dict]:
        """Generuje predikce."""
        predictions = []
        today = date.today()

        # Získat naučený vliv svátků
        holiday_impacts = self.optimizer.get_learned_holiday_impacts()

        availability_list = []
        for rate_plan in occupancy_data.get('availability', []):
            availability_list.extend(rate_plan.get('availability', []))

        for day_data in availability_list:
            date_str = day_data.get('date', '')
            try:
                target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                continue

            days_until = (target_date - today).days
            if days_until <= 0 or days_until > days_ahead:
                continue

            room_kinds = day_data.get('roomKinds', [])
            occupied = sum(1 for r in room_kinds if r.get('availability') == 0)
            total = len(room_kinds)
            current_occ = (occupied / total * 100) if total > 0 else 0

            historical_avg = self.optimizer._get_daily_historical_avg(target_date)
            holiday = CzechHolidays.get_holiday_info(target_date)
            holiday_impact = holiday_impacts.get(holiday, {}).get('impact', 0) if holiday else 0
            season = CzechHolidays.get_season(target_date)

            # Predikce fill rate
            if days_until <= 3:
                expected_fill = 5
            elif days_until <= 7:
                expected_fill = 15
            elif days_until <= 14:
                expected_fill = 25
            else:
                expected_fill = 35

            # Úpravy podle naučeného vlivu svátku
            if holiday_impact > 0:
                expected_fill *= (1 + holiday_impact * 0.5)
            elif holiday_impact < 0:
                expected_fill *= (1 + holiday_impact * 0.5)

            if target_date.weekday() >= 5:
                expected_fill *= 1.1

            predicted_final = min(current_occ + expected_fill, 100)

            predictions.append({
                'date': date_str,
                'weekday': SmartRoomPriceOptimizer.WEEKDAY_NAMES[target_date.weekday()],
                'current_occupancy': round(current_occ, 1),
                'predicted_final': round(predicted_final, 1),
                'historical_avg': round(historical_avg, 1),
                'days_until': days_until,
                'is_weekend': target_date.weekday() >= 5,
                'holiday': holiday,
                'holiday_impact': round(holiday_impact, 2) if holiday else None,
                'season': season['name'],
                'confidence': 0.7 if days_until <= 7 else 0.5
            })

        return predictions


# Test
if __name__ == "__main__":
    print("Test SmartRoomPriceOptimizer v4 s učením...")

    optimizer = SmartRoomPriceOptimizer()
    stats = optimizer.get_statistics()

    print(f"\n=== STATISTIKY ===")
    print(f"Celkem záznamů: {stats['total_records']}")
    print(f"Let dat: {stats['years_of_data']}")

    print(f"\n=== NAUČENÝ VLIV SVÁTKŮ ===")
    for holiday, data in stats['learned_holidays'].items():
        effect = data['effect']
        impact = data['impact']
        emoji = "📈" if effect == 'positive' else ("📉" if effect == 'negative' else "➖")
        print(f"{emoji} {holiday}: {impact*100:+.0f}% ({data['holiday_occupancy']:.0f}% vs {data['baseline_occupancy']:.0f}% baseline)")
