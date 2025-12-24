#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Previo EQC API Client
=====================
Klient pro komunikaci s Previo EQC (Expedia QuickConnect) API.

EQC API umožňuje:
- Posílat ceny (rates) do Previo
- Posílat dostupnost (availability) do Previo
- Stahovat rezervace z Previo

EQC XML je kopie API používaného Expedia.com.
Previo používá verzi EQC/2007/08 (0.8.5).

Dokumentace: https://eqc.apidocs.previo.app/
"""

import requests
import xml.etree.ElementTree as ET
from xml.dom import minidom
import logging
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple, Any
import time

logger = logging.getLogger("previo_eqc")

# EQC API konfigurace
EQC_CONFIG = {
    'username': 'api@vincentluhacovice.cz',
    'password': '2P0QHc9XPph7',
    'hotel_id': '731186',
    # URL endpoint pro EQC API (eqc1 = správná verze)
    'ar_url': 'https://api.previo.app/eqc1/ar',  # AvailRateUpdate
    'br_url': 'https://api.previo.app/eqc1/br',  # BookingRetrieval
    'bc_url': 'https://api.previo.app/eqc1/bc',  # BookingConfirmation
}

# XML namespaces pro EQC
EQC_NAMESPACE = "http://www.expediaconnect.com/EQC/AR/2011/06"
EQC_BR_NAMESPACE = "http://www.expediaconnect.com/EQC/BR/2014/01"


class PrevioEqcClient:
    """
    Klient pro komunikaci s Previo EQC API.

    EQC API je založeno na Expedia QuickConnect formátu a umožňuje:
    - AvailRateUpdate (AR) - aktualizace cen a dostupnosti
    - BookingRetrieval (BR) - stažení rezervací
    - BookingConfirmation (BC) - potvrzení rezervací
    """

    def __init__(
        self,
        username: str = None,
        password: str = None,
        hotel_id: str = None,
        ar_url: str = None,
        br_url: str = None
    ):
        """
        Inicializace EQC klienta.

        Args:
            username: Přihlašovací jméno pro EQC API
            password: Heslo pro EQC API
            hotel_id: ID hotelu v Previo
            ar_url: URL pro AvailRateUpdate endpoint
            br_url: URL pro BookingRetrieval endpoint
        """
        self.username = username or EQC_CONFIG['username']
        self.password = password or EQC_CONFIG['password']
        self.hotel_id = hotel_id or EQC_CONFIG['hotel_id']
        self.ar_url = ar_url or EQC_CONFIG['ar_url']
        self.br_url = br_url or EQC_CONFIG['br_url']
        self.session = requests.Session()

        logger.info(f"EQC Client inicializován pro hotel {self.hotel_id}")

    def _prettify_xml(self, elem: ET.Element) -> str:
        """Formátuje XML pro lepší čitelnost."""
        rough_string = ET.tostring(elem, encoding='unicode')
        reparsed = minidom.parseString(rough_string)
        return reparsed.toprettyxml(indent="  ")

    def _create_ar_request(
        self,
        room_type_id: str,
        rate_plan_id: str,
        updates: List[Dict]
    ) -> str:
        """
        Vytvoří XML požadavek pro AvailRateUpdate.

        Formát podle EQC specifikace (Expedia QuickConnect):

        <AvailRateUpdateRQ xmlns="...">
            <Authentication username="..." password="..."/>
            <Hotel id="..."/>
            <AvailRateUpdate>
                <DateRange from="2025-01-15" to="2025-01-15"/>
                <RoomType id="...">
                    <RatePlan id="..." closed="false">
                        <Rate currency="CZK">
                            <PerDay rate="1500.00"/>
                        </Rate>
                    </RatePlan>
                </RoomType>
            </AvailRateUpdate>
        </AvailRateUpdateRQ>

        Args:
            room_type_id: ID typu pokoje (room_kind_id)
            rate_plan_id: ID cenového plánu
            updates: Seznam aktualizací [{date, rate, currency, closed}, ...]

        Returns:
            str: XML požadavek
        """
        # Root element s namespace
        root = ET.Element('AvailRateUpdateRQ')
        root.set('xmlns', EQC_NAMESPACE)

        # Authentication
        auth = ET.SubElement(root, 'Authentication')
        auth.set('username', self.username)
        auth.set('password', self.password)

        # Hotel
        hotel = ET.SubElement(root, 'Hotel')
        hotel.set('id', self.hotel_id)

        # Seskupit updates podle data pro efektivitu
        for update in updates:
            avail_rate_update = ET.SubElement(root, 'AvailRateUpdate')

            # DateRange
            date_range = ET.SubElement(avail_rate_update, 'DateRange')
            date_str = update.get('date')
            if isinstance(date_str, date):
                date_str = date_str.strftime('%Y-%m-%d')
            date_range.set('from', date_str)
            date_range.set('to', date_str)

            # RoomType
            room_type = ET.SubElement(avail_rate_update, 'RoomType')
            room_type.set('id', str(room_type_id))

            # RatePlan
            rate_plan = ET.SubElement(room_type, 'RatePlan')
            rate_plan.set('id', str(rate_plan_id))
            rate_plan.set('closed', 'true' if update.get('closed', False) else 'false')

            # Rate
            if 'rate' in update:
                rate_elem = ET.SubElement(rate_plan, 'Rate')
                rate_elem.set('currency', update.get('currency', 'CZK'))

                per_day = ET.SubElement(rate_elem, 'PerDay')
                per_day.set('rate', f"{update['rate']:.2f}")

        # Převod na string s XML deklarací
        xml_string = '<?xml version="1.0" encoding="UTF-8"?>\n'
        xml_string += ET.tostring(root, encoding='unicode')

        return xml_string

    def _create_br_request(
        self,
        status: str = 'pending',
        older_than_seconds: int = None
    ) -> str:
        """
        Vytvoří XML požadavek pro BookingRetrieval.

        Args:
            status: Status rezervací ('pending', 'confirmed', 'cancelled')
            older_than_seconds: Omezit na rezervace starší než X sekund

        Returns:
            str: XML požadavek
        """
        root = ET.Element('BookingRetrievalRQ')
        root.set('xmlns', EQC_BR_NAMESPACE)

        # Authentication
        auth = ET.SubElement(root, 'Authentication')
        auth.set('username', self.username)
        auth.set('password', self.password)

        # Hotel
        hotel = ET.SubElement(root, 'Hotel')
        hotel.set('id', self.hotel_id)

        # ParamSet
        param_set = ET.SubElement(root, 'ParamSet')

        status_elem = ET.SubElement(param_set, 'Status')
        status_elem.text = status

        if older_than_seconds:
            older_than = ET.SubElement(param_set, 'OlderThanSeconds')
            older_than.text = str(older_than_seconds)

        xml_string = '<?xml version="1.0" encoding="UTF-8"?>\n'
        xml_string += ET.tostring(root, encoding='unicode')

        return xml_string

    def _send_request(self, url: str, xml_request: str) -> Tuple[bool, Any]:
        """
        Odešle XML požadavek na EQC API.

        Args:
            url: URL endpoint
            xml_request: XML požadavek jako string

        Returns:
            Tuple[bool, Any]: (úspěch, odpověď nebo chybová zpráva)
        """
        logger.debug(f"Odesílám EQC požadavek na {url}")
        logger.debug(f"XML požadavek:\n{xml_request}")

        try:
            response = self.session.post(
                url,
                data=xml_request.encode('utf-8'),
                headers={
                    'Content-Type': 'application/xml; charset=utf-8',
                    'Accept': 'application/xml'
                },
                timeout=60
            )

            logger.debug(f"HTTP status: {response.status_code}")
            logger.debug(f"Odpověď: {response.text[:500]}")

            # Parsování odpovědi
            if response.status_code == 200:
                try:
                    root = ET.fromstring(response.content)

                    # Kontrola chyby v odpovědi
                    error = root.find('.//{%s}Error' % EQC_NAMESPACE)
                    if error is None:
                        error = root.find('.//Error')

                    if error is not None:
                        error_code = error.get('code', 'unknown')
                        error_msg = error.text or error.get('message', 'Unknown error')
                        logger.error(f"EQC API error {error_code}: {error_msg}")
                        return False, f"Error {error_code}: {error_msg}"

                    # Úspěšná odpověď
                    success = root.find('.//{%s}Success' % EQC_NAMESPACE)
                    if success is None:
                        success = root.find('.//Success')

                    if success is not None:
                        return True, root

                    # Vrátit celou odpověď pro další zpracování
                    return True, root

                except ET.ParseError as e:
                    logger.error(f"Chyba parsování XML odpovědi: {e}")
                    logger.error(f"Odpověď: {response.text}")
                    return False, f"XML parse error: {e}"

            elif response.status_code == 401:
                return False, "Unauthorized - neplatné přihlašovací údaje"
            elif response.status_code == 403:
                return False, "Forbidden - nemáte oprávnění k EQC API"
            elif response.status_code == 404:
                return False, f"Not Found - endpoint {url} neexistuje"
            else:
                return False, f"HTTP error {response.status_code}: {response.text[:200]}"

        except requests.exceptions.Timeout:
            logger.error("EQC požadavek timeout")
            return False, "Request timeout"
        except requests.exceptions.RequestException as e:
            logger.error(f"EQC request error: {e}")
            return False, f"Request error: {e}"

    def update_rate(
        self,
        room_type_id: int,
        rate_plan_id: int,
        target_date: date,
        new_rate: float,
        currency: str = 'CZK'
    ) -> Dict:
        """
        Aktualizuje cenu pro konkrétní pokoj a datum.

        Args:
            room_type_id: ID typu pokoje (room_kind_id)
            rate_plan_id: ID cenového plánu
            target_date: Datum pro aktualizaci
            new_rate: Nová cena
            currency: Měna (výchozí CZK)

        Returns:
            Dict: Výsledek operace
        """
        logger.info(f"Aktualizuji cenu: room={room_type_id}, date={target_date}, rate={new_rate} {currency}")

        updates = [{
            'date': target_date,
            'rate': new_rate,
            'currency': currency,
            'closed': False
        }]

        xml_request = self._create_ar_request(
            room_type_id=str(room_type_id),
            rate_plan_id=str(rate_plan_id),
            updates=updates
        )

        success, response = self._send_request(self.ar_url, xml_request)

        result = {
            'success': success,
            'room_type_id': room_type_id,
            'rate_plan_id': rate_plan_id,
            'date': target_date.strftime('%Y-%m-%d') if isinstance(target_date, date) else target_date,
            'new_rate': new_rate,
            'currency': currency
        }

        if not success:
            result['error'] = response

        return result

    def update_rates_batch(
        self,
        room_type_id: int,
        rate_plan_id: int,
        rate_updates: List[Dict]
    ) -> Dict:
        """
        Aktualizuje ceny hromadně pro více dat.

        Args:
            room_type_id: ID typu pokoje
            rate_plan_id: ID cenového plánu
            rate_updates: Seznam aktualizací [{date, rate, currency}, ...]

        Returns:
            Dict: Výsledek operace
        """
        logger.info(f"Hromadná aktualizace cen: room={room_type_id}, počet={len(rate_updates)}")

        xml_request = self._create_ar_request(
            room_type_id=str(room_type_id),
            rate_plan_id=str(rate_plan_id),
            updates=rate_updates
        )

        success, response = self._send_request(self.ar_url, xml_request)

        result = {
            'success': success,
            'room_type_id': room_type_id,
            'rate_plan_id': rate_plan_id,
            'updates_count': len(rate_updates)
        }

        if not success:
            result['error'] = response

        return result

    def close_room(
        self,
        room_type_id: int,
        rate_plan_id: int,
        target_date: date
    ) -> Dict:
        """
        Uzavře pokoj pro daný datum (stop-sell).

        Args:
            room_type_id: ID typu pokoje
            rate_plan_id: ID cenového plánu
            target_date: Datum pro uzavření

        Returns:
            Dict: Výsledek operace
        """
        logger.info(f"Uzavírám pokoj: room={room_type_id}, date={target_date}")

        updates = [{
            'date': target_date,
            'closed': True
        }]

        xml_request = self._create_ar_request(
            room_type_id=str(room_type_id),
            rate_plan_id=str(rate_plan_id),
            updates=updates
        )

        success, response = self._send_request(self.ar_url, xml_request)

        result = {
            'success': success,
            'room_type_id': room_type_id,
            'date': target_date.strftime('%Y-%m-%d') if isinstance(target_date, date) else target_date,
            'action': 'closed'
        }

        if not success:
            result['error'] = response

        return result

    def get_reservations(self, status: str = 'pending') -> Dict:
        """
        Stáhne rezervace z Previo.

        Args:
            status: Status rezervací ('pending', 'confirmed', 'cancelled')

        Returns:
            Dict: Rezervace
        """
        logger.info(f"Stahuji rezervace se statusem: {status}")

        xml_request = self._create_br_request(status=status)
        success, response = self._send_request(self.br_url, xml_request)

        result = {
            'success': success,
            'status_filter': status,
            'reservations': []
        }

        if success and isinstance(response, ET.Element):
            # Parsování rezervací z odpovědi
            for booking in response.findall('.//Booking'):
                reservation = {
                    'id': booking.get('id'),
                    'status': booking.get('status'),
                    'source': booking.get('source'),
                    'created': booking.get('createDateTime')
                }

                # Host
                primary_guest = booking.find('.//PrimaryGuest')
                if primary_guest is not None:
                    name = primary_guest.find('Name')
                    if name is not None:
                        reservation['guest_name'] = f"{name.get('givenName', '')} {name.get('surname', '')}".strip()

                # Pokoj a termín
                room_stay = booking.find('.//RoomStay')
                if room_stay is not None:
                    stay_date = room_stay.find('StayDate')
                    if stay_date is not None:
                        reservation['arrival'] = stay_date.get('arrival')
                        reservation['departure'] = stay_date.get('departure')

                    room_type = room_stay.find('RoomType')
                    if room_type is not None:
                        reservation['room_type_id'] = room_type.get('id')

                result['reservations'].append(reservation)
        elif not success:
            result['error'] = response

        result['count'] = len(result['reservations'])
        return result

    def test_connection(self) -> Dict:
        """
        Otestuje připojení k EQC API.

        Returns:
            Dict: Výsledek testu
        """
        logger.info("Testuji připojení k EQC API")

        result = {
            'success': False,
            'ar_endpoint': self.ar_url,
            'br_endpoint': self.br_url,
            'hotel_id': self.hotel_id,
            'username': self.username
        }

        # Test BR endpoint (méně invazivní než AR)
        try:
            xml_request = self._create_br_request(status='pending')
            success, response = self._send_request(self.br_url, xml_request)

            result['br_test'] = {
                'success': success,
                'response': str(response)[:200] if not success else 'OK'
            }

            if success:
                result['success'] = True
                result['message'] = "EQC API připojení funguje"
            else:
                result['message'] = f"EQC API test selhal: {response}"

        except Exception as e:
            result['error'] = str(e)
            result['message'] = f"Chyba při testování: {e}"

        return result


class PrevioRateManager:
    """
    Vysokoúrovňový manažer pro správu cen v Previo.

    Kombinuje EQC API s existujícím REST API pro:
    - Čtení aktuálních cen (REST API)
    - Aktualizaci cen (EQC API)
    - Výpočet nových cen podle doporučení
    """

    def __init__(
        self,
        eqc_client: PrevioEqcClient = None,
        rest_client = None
    ):
        """
        Inicializace manažera.

        Args:
            eqc_client: Instance PrevioEqcClient
            rest_client: Instance PrevioRestClient pro čtení dat
        """
        self.eqc_client = eqc_client or PrevioEqcClient()
        self.rest_client = rest_client

        # Cache pro rate plány
        self._rate_plans = None

    def get_rate_plans(self) -> Dict:
        """Získá seznam cenových plánů z REST API."""
        if self._rate_plans is not None:
            return self._rate_plans

        if self.rest_client:
            try:
                plans = self.rest_client.get_rate_plans()
                if isinstance(plans, list):
                    self._rate_plans = {
                        plan['ratePlanId']: plan
                        for plan in plans
                        if 'ratePlanId' in plan
                    }
                    return self._rate_plans
            except Exception as e:
                logger.error(f"Chyba při načítání rate plánů: {e}")

        return {}

    def get_base_rate_plan_id(self) -> Optional[int]:
        """Získá ID základního (base) cenového plánu."""
        rate_plans = self.get_rate_plans()

        for plan_id, plan in rate_plans.items():
            if plan.get('isBasePlan', False):
                return plan_id

        # Fallback - vrátit první plán
        if rate_plans:
            return list(rate_plans.keys())[0]

        return None

    def apply_price_change(
        self,
        room_kind_id: int,
        target_date: date,
        change_percent: float,
        current_price: float = None,
        rate_plan_id: int = None
    ) -> Dict:
        """
        Aplikuje procentuální změnu ceny.

        Args:
            room_kind_id: ID typu pokoje
            target_date: Datum pro změnu
            change_percent: Procentuální změna (-20 = sleva 20%, +15 = navýšení 15%)
            current_price: Aktuální cena (pokud není, získá se z API)
            rate_plan_id: ID cenového plánu (pokud není, použije se základní)

        Returns:
            Dict: Výsledek operace
        """
        logger.info(f"Aplikuji cenovou změnu: room={room_kind_id}, date={target_date}, change={change_percent}%")

        result = {
            'success': False,
            'room_kind_id': room_kind_id,
            'date': target_date.strftime('%Y-%m-%d') if isinstance(target_date, date) else target_date,
            'change_percent': change_percent
        }

        # Získat rate plan ID
        if rate_plan_id is None:
            rate_plan_id = self.get_base_rate_plan_id()
            if rate_plan_id is None:
                result['error'] = "Nepodařilo se získat rate plan ID"
                return result

        result['rate_plan_id'] = rate_plan_id

        # Získat aktuální cenu pokud není zadána
        if current_price is None:
            # TODO: Implementovat získání aktuální ceny z REST/XML API
            result['error'] = "Aktuální cena musí být zadána"
            return result

        result['current_price'] = current_price

        # Vypočítat novou cenu
        new_price = round(current_price * (1 + change_percent / 100))
        result['new_price'] = new_price

        # Aplikovat změnu přes EQC API
        eqc_result = self.eqc_client.update_rate(
            room_type_id=room_kind_id,
            rate_plan_id=rate_plan_id,
            target_date=target_date,
            new_rate=new_price,
            currency='CZK'
        )

        result['success'] = eqc_result.get('success', False)
        if not result['success']:
            result['error'] = eqc_result.get('error', 'Unknown error')

        return result

    def apply_recommendations(
        self,
        recommendations: List[Dict],
        current_prices: Dict[int, Dict]
    ) -> List[Dict]:
        """
        Aplikuje seznam cenových doporučení.

        Args:
            recommendations: Seznam doporučení z optimalizátoru
            current_prices: Aktuální ceny {room_kind_id: {occupancy: price}}

        Returns:
            List[Dict]: Výsledky aplikace pro každé doporučení
        """
        results = []
        rate_plan_id = self.get_base_rate_plan_id()

        for rec in recommendations:
            if rec.get('recommendation_type') == 'no_change':
                continue

            room_kind_id = rec.get('room_kind_id')
            target_date = rec.get('date')
            change_percent = rec.get('recommended_change', 0)

            # Převést datum
            if isinstance(target_date, str):
                target_date = datetime.strptime(target_date, '%Y-%m-%d').date()

            # Získat aktuální cenu
            current_price = None
            if room_kind_id in current_prices:
                room_prices = current_prices[room_kind_id]
                # Použít cenu pro 2 osoby nebo nejbližší dostupnou
                current_price = room_prices.get(2) or (list(room_prices.values())[0] if room_prices else None)

            if current_price is None:
                results.append({
                    'success': False,
                    'room_kind_id': room_kind_id,
                    'date': str(target_date),
                    'error': 'Nepodařilo se získat aktuální cenu'
                })
                continue

            # Aplikovat změnu
            result = self.apply_price_change(
                room_kind_id=room_kind_id,
                target_date=target_date,
                change_percent=change_percent,
                current_price=current_price,
                rate_plan_id=rate_plan_id
            )

            result['recommendation_id'] = rec.get('id')
            result['reason'] = rec.get('reason')
            results.append(result)

            # Pauza mezi požadavky
            time.sleep(0.5)

        return results


# Testování
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    print("=== Test PrevioEqcClient ===\n")

    client = PrevioEqcClient()

    # Test připojení
    print("1. Test připojení:")
    result = client.test_connection()
    print(f"   Success: {result.get('success')}")
    print(f"   Message: {result.get('message')}")

    if not result.get('success'):
        print(f"\n   Poznámka: EQC API vyžaduje speciální oprávnění.")
        print(f"   Kontaktujte Previo na info@previo.cz pro aktivaci EQC přístupu.")

    # Ukázka generování XML požadavku
    print("\n2. Ukázka XML požadavku pro aktualizaci ceny:")
    xml = client._create_ar_request(
        room_type_id='640240',
        rate_plan_id='125099',
        updates=[{
            'date': date.today() + timedelta(days=7),
            'rate': 1500.00,
            'currency': 'CZK',
            'closed': False
        }]
    )
    print(xml)
