#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Previo API klient
=================
Univerzální klient pro přístup k Previo XML API a REST API.

Tento modul poskytuje třídy pro komunikaci s oběma API endpointy:
- PrevioXmlClient: Pro přístup k XML API
- PrevioRestClient: Pro přístup k REST API

FUNGUJÍCÍ ENDPOINTY (ověřeno 2025-12-06):

XML API (https://api.previo.app/x1/):
  - hotel/get                  - informace o hotelu
  - hotel/getRoomKinds         - typy pokojů
  - hotel/getObjectKinds       - typy objektů
  - hotel/getRates             - ceník/sazby (POZOR: case-sensitive URL!)
  - system/getReservationStatuses - stavy rezervací

REST API (https://api.previo.app/rest/):
  - rooms                      - seznam pokojů (15 pokojů)
  - rate-plan                  - cenové plány (3 plány)
  - calendar/availability      - dostupnost pokojů (HLAVNÍ ZDROJ OBSAZENOSTI!)
  - guests/                    - seznam hostů (22921 hostů)
  - guests/{id}                - detail hosta
  - billing/documents          - fakturační doklady

NEFUNGUJÍCÍ (chybí oprávnění):
  - reservation (REST), hotel/searchReservations (XML) - 403/1022 Unauthorized
  - hotel/getCurrencies, hotel/getConditions, hotel/getFees - Unauthorized

POZNÁMKA K OBSAZENOSTI:
  Obsazenost se počítá z calendar/availability - pro každý den vrací
  seznam typů pokojů s availability=0 (obsazeno) nebo availability=1 (volno).
  Nepotřebujeme endpoint reservation!

Autor: AI asistent (na základě původního kódu)
"""

import requests
import xml.etree.ElementTree as ET
import json
import logging
import datetime
from typing import Dict, List, Optional, Union, Any
import time
import os

# Konfigurační údaje pro XML API
# URL podle dokumentace: https://api.previo.app/x1/
XML_CONFIG = {
    'username': 'api@vincentluhacovice.cz',
    'password': '2P0QHc9XPph7',
    'previo_id': '731186',
    'api_url': 'https://api.previo.app/x1/'
}

# REST API konfigurační údaje
# URL podle dokumentace (previo_api_volani.md): https://api.previo.app/rest/
REST_CONFIG = {
    'username': 'api@vincentluhacovice.cz',
    'password': '2P0QHc9XPph7',
    'hotel_id': '731186',
    'api_url': 'https://api.previo.app/rest/'
}

# Nastavení loggeru
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("previo_api.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("previo_api")

class PrevioXmlClient:
    """Klient pro komunikaci s Previo XML API."""

    def __init__(self, username: str, password: str, previo_id: str, api_url: str = "https://api.previo.app/x1/"):
        """
        Inicializace klienta pro Previo XML API.
        
        Args:
            username (str): Uživatelské jméno pro API
            password (str): Heslo pro API
            previo_id (str): ID objektu v Previo systému
            api_url (str): URL adresa API (výchozí: "https://api.previo.cz/xml-api/")
        """
        self.username = username
        self.password = password
        self.previo_id = previo_id
        self.api_url = api_url
        self.session = requests.Session()
    
    def create_request_xml(self, method: str, params: Dict = None) -> str:
        """
        Vytvoří XML požadavek pro Previo API.

        Formát podle dokumentace Previo XML API:
        <request>
            <login>username</login>
            <password>password</password>
            <hotId>hotel_id</hotId>
            ... další parametry ...
        </request>

        Args:
            method (str): Název API metody (např. 'Hotel.get')
            params (dict, optional): Parametry požadavku

        Returns:
            str: XML požadavek jako řetězec
        """
        root = ET.Element('request')

        # Přidání přihlašovacích údajů podle Previo XML dokumentace
        ET.SubElement(root, 'login').text = self.username
        ET.SubElement(root, 'password').text = self.password
        ET.SubElement(root, 'hotId').text = self.previo_id

        # Přidání parametrů přímo do root elementu
        if params:
            for key, value in params.items():
                ET.SubElement(root, key).text = str(value)

        # Převod na řetězec
        xml_declaration = '<?xml version="1.0" encoding="UTF-8"?>\n'
        xml_body = ET.tostring(root, encoding='utf-8').decode('utf-8')
        return xml_declaration + xml_body

    def _method_to_url_path(self, method: str) -> str:
        """
        Převede název metody na URL path.
        Např. 'Hotel.get' -> 'hotel/get', 'Hotel.getRooms' -> 'hotel/getRooms'
        """
        parts = method.split('.')
        if len(parts) == 2:
            return f"{parts[0].lower()}/{parts[1]}"
        return method.lower()
    
    def call_api(self, method: str, params: Dict = None, debug: bool = True, max_retries: int = 3) -> ET.Element:
        """
        Provede požadavek na Previo XML API.

        URL se konstruuje jako: base_url + method_path
        Např. 'Hotel.get' -> 'https://api.previo.app/x1/hotel/get'

        Args:
            method (str): Název API metody (např. 'Hotel.get')
            params (dict, optional): Parametry požadavku
            debug (bool): Zda vypisovat debug informace
            max_retries (int): Maximální počet pokusů při selhání

        Returns:
            ET.Element: XML odpověď jako Element

        Raises:
            Exception: Při chybě požadavku nebo zpracování odpovědi
        """
        # Vytvoření XML požadavku
        xml_request = self.create_request_xml(method, params)

        # Sestavení URL podle dokumentace: base_url + method_path
        method_path = self._method_to_url_path(method)
        full_url = f"{self.api_url.rstrip('/')}/{method_path}"

        if debug:
            logger.debug(f"XML požadavek: {xml_request}")
            logger.debug(f"Odesílám požadavek na URL: {full_url}")

        # Počet provedených pokusů
        retries = 0

        while retries < max_retries:
            try:
                # Odeslání požadavku na správnou URL
                response = self.session.post(
                    full_url,
                    data=xml_request,
                    headers={'Content-Type': 'application/xml; charset=utf-8'},
                    timeout=30
                )
                
                if debug:
                    logger.debug(f"HTTP status: {response.status_code}")
                    logger.debug(f"Hlavičky odpovědi: {dict(response.headers)}")
                
                # Kontrola, zda odpověď obsahuje XML nebo HTML
                if '<html' in response.text.lower() or '<!DOCTYPE html>' in response.text:
                    error_msg = "API vrátilo HTML místo očekávaného XML. Endpoint může být nesprávný nebo autentizace selhala."
                    logger.error(error_msg)
                    logger.error(f"Odpověď (prvních 500 znaků): {response.text[:500]}")
                    
                    # Zkusíme alternativní endpoint při prvním pokusu
                    if retries == 0:
                        alt_url = self.api_url.replace("xml-api/", "xml/")
                        logger.info(f"Zkouším alternativní URL: {alt_url}")
                        
                        response = self.session.post(
                            alt_url,
                            data=xml_request,
                            headers={'Content-Type': 'application/xml; charset=utf-8'},
                            timeout=30
                        )
                        
                        if '<html' not in response.text.lower() and '<!DOCTYPE html>' not in response.text:
                            logger.info("Alternativní URL funguje! Aktualizuji použitou URL pro další požadavky.")
                            self.api_url = alt_url
                            # Pokud alternativní URL funguje, pokračujeme dále
                        else:
                            # Pokud nefunguje ani alternativní URL, zkusíme další endpoint
                            alt_url2 = self.api_url.replace("xml-api/", "xml-api")
                            logger.info(f"Zkouším další alternativní URL: {alt_url2}")
                            
                            response = self.session.post(
                                alt_url2,
                                data=xml_request,
                                headers={'Content-Type': 'application/xml; charset=utf-8'},
                                timeout=30
                            )
                            
                            if '<html' not in response.text.lower() and '<!DOCTYPE html>' not in response.text:
                                logger.info("Druhá alternativní URL funguje! Aktualizuji použitou URL pro další požadavky.")
                                self.api_url = alt_url2
                            else:
                                # Pokusíme se znovu s původní URL
                                retries += 1
                                if retries < max_retries:
                                    logger.info(f"Pokus {retries}/{max_retries}. Pokusím se znovu za 2 sekundy...")
                                    time.sleep(2)
                                    continue
                                else:
                                    raise Exception(error_msg)
                    else:
                        # Pokusíme se znovu
                        retries += 1
                        if retries < max_retries:
                            logger.info(f"Pokus {retries}/{max_retries}. Pokusím se znovu za 2 sekundy...")
                            time.sleep(2)
                            continue
                        else:
                            raise Exception(error_msg)
                
                # Kontrola HTTP kódu
                response.raise_for_status()
                
                if debug:
                    logger.debug(f"API odpověď pro metodu {method} (prvních 500 znaků):")
                    logger.debug(response.text[:500] + ('...' if len(response.text) > 500 else ''))
                
                # Zpracování odpovědi
                try:
                    root = ET.fromstring(response.content)
                except ET.ParseError as parse_error:
                    logger.error(f"Chyba při zpracování XML odpovědi: {parse_error}")
                    logger.error(f"Odpověď: {response.text[:1000]}")
                    
                    # Zkusíme opravit potenciální chyby v XML
                    if retries < max_retries:
                        retries += 1
                        logger.info(f"Pokus {retries}/{max_retries}. Pokusím se znovu za 2 sekundy...")
                        time.sleep(2)
                        continue
                    else:
                        raise
                
                # Kontrola chyby v odpovědi
                error = root.find('.//error')
                if error is not None:
                    error_msg = f"API vrátilo chybu: {error.text}"
                    if error.get('code'):
                        error_msg += f" (Kód chyby: {error.get('code')})"
                    logger.error(error_msg)
                    raise Exception(error_msg)
                
                return root
            
            except requests.exceptions.RequestException as e:
                logger.error(f"Chyba při připojení k XML API: {e}")
                retries += 1
                
                if retries < max_retries:
                    logger.info(f"Pokus {retries}/{max_retries}. Pokusím se znovu za 2 sekundy...")
                    time.sleep(2)
                else:
                    raise
    
    def get_hotel_info(self) -> Dict:
        """
        Získá základní informace o hotelu - metoda Hotel.get.
        
        Returns:
            Dict: Informace o hotelu
        """
        logger.info("Získávám informace o hotelu (Hotel.get)")
        
        try:
            # Zkusíme nejprve 'Hotel.get' podle dokumentace
            try:
                response = self.call_api('Hotel.get')
            except Exception as e:
                logger.warning(f"Hotel.get selhalo, zkouším alternativní metodu getHotel: {e}")
                response = self.call_api('getHotel')
            
            hotel = {}

            # Extrakce dat z XML - response může být přímo hotel element
            if response.tag == 'hotel':
                hotel = {child.tag: child.text for child in response if child.text}
            else:
                hotel_elem = response.find('.//hotel')
                if hotel_elem is not None:
                    hotel = {child.tag: child.text for child in hotel_elem if child.text}

            return hotel
        except Exception as e:
            logger.error(f"Chyba při získávání informací o hotelu: {e}")
            # Vrátíme prázdný slovník místo vyhození výjimky
            return {"error": str(e)}
    
    def get_room_kinds(self) -> List[Dict]:
        """
        Získá seznam typů pokojů - metoda Hotel.getRoomKinds.
        
        Returns:
            List[Dict]: Seznam typů pokojů
        """
        logger.info("Získávám seznam typů pokojů (Hotel.getRoomKinds)")
        
        try:
            # Zkusíme nejprve 'Hotel.getRoomKinds' podle dokumentace
            try:
                response = self.call_api('Hotel.getRoomKinds')
            except Exception as e:
                logger.warning(f"Hotel.getRoomKinds selhalo, zkouším alternativní metodu getRoomKinds: {e}")
                response = self.call_api('getRoomKinds')
            
            room_kinds = []
            
            # Extrakce dat z XML
            for room_kind in response.findall('.//roomKind'):
                room_data = {child.tag: child.text for child in room_kind if child.text}
                room_kinds.append(room_data)
            
            return room_kinds
        except Exception as e:
            logger.error(f"Chyba při získávání typů pokojů: {e}")
            # Vrátíme prázdný seznam místo vyhození výjimky
            return []
    
    def get_object_kinds(self) -> List[Dict]:
        """
        Získá seznam typů objektů - metoda Hotel.getObjectKinds.
        
        Returns:
            List[Dict]: Seznam typů objektů
        """
        logger.info("Získávám seznam typů objektů (Hotel.getObjectKinds)")
        
        try:
            # Zkusíme nejprve 'Hotel.getObjectKinds' podle dokumentace
            try:
                response = self.call_api('Hotel.getObjectKinds')
            except Exception as e:
                logger.warning(f"Hotel.getObjectKinds selhalo, zkouším alternativní metodu getObjectKinds: {e}")
                response = self.call_api('getObjectKinds')
            
            object_kinds = []
            
            # Extrakce dat z XML
            for object_kind in response.findall('.//objectKind'):
                object_data = {child.tag: child.text for child in object_kind if child.text}
                object_kinds.append(object_data)
            
            return object_kinds
        except Exception as e:
            logger.error(f"Chyba při získávání typů objektů: {e}")
            # Vrátíme prázdný seznam místo vyhození výjimky
            return []
    
    def get_objects(self) -> List[Dict]:
        """
        Získá seznam objektů (pokojů) - metoda Hotel.getObjects.

        POZNÁMKA: Tato metoda nemusí být dostupná pro všechny uživatele.
        Použijte get_object_kinds() pro získání typů pokojů.

        Returns:
            List[Dict]: Seznam pokojů
        """
        logger.info("Získávám seznam objektů/pokojů (Hotel.getObjects)")

        try:
            response = self.call_api('Hotel.getObjects')
            objects = []

            # Extrakce dat z XML
            for obj in response.findall('.//object'):
                obj_data = {}
                for child in obj:
                    if len(child) > 0:
                        obj_data[child.tag] = {subchild.tag: subchild.text for subchild in child}
                    else:
                        obj_data[child.tag] = child.text
                objects.append(obj_data)

            return objects
        except Exception as e:
            logger.error(f"Chyba při získávání seznamu objektů: {e}")
            return []

    # Alias pro zpětnou kompatibilitu
    def get_rooms(self) -> List[Dict]:
        """Alias pro get_objects() - vrací seznam pokojů."""
        return self.get_objects()
    
    def get_prices(self, date_from: str, date_to: str) -> List[Dict]:
        """
        Získá ceník pro zadané období - metoda getPrices.

        Args:
            date_from (str): Počáteční datum ve formátu YYYY-MM-DD
            date_to (str): Koncové datum ve formátu YYYY-MM-DD

        Returns:
            List[Dict]: Seznam cen pro dané období
        """
        logger.info(f"Získávám ceník pro období {date_from} až {date_to} (getPrices)")

        try:
            params = {
                'dateFrom': date_from,
                'dateTo': date_to
            }

            response = self.call_api('getPrices', params)
            prices = []

            # Extrakce dat z XML
            for price in response.findall('.//price'):
                price_data = {}
                for child in price:
                    price_data[child.tag] = child.text
                prices.append(price_data)

            return prices
        except Exception as e:
            logger.error(f"Chyba při získávání ceníku: {e}")
            # Vrátíme prázdný seznam místo vyhození výjimky
            return []

    def get_rates(self, date_from: str, date_to: str, currency: str = "CZK") -> Dict:
        """
        Získá sazby/ceník pro zadané období - metoda Hotel.getRates.

        POZOR: URL je case-sensitive! Musí být 'hotel/getRates' ne 'hotel/getrates'.

        Args:
            date_from (str): Počáteční datum ve formátu YYYY-MM-DD
            date_to (str): Koncové datum ve formátu YYYY-MM-DD
            currency (str): Kód měny (výchozí: "CZK")

        Returns:
            Dict: Sazby/ceník pro dané období
        """
        logger.info(f"Získávám sazby pro období {date_from} až {date_to} (Hotel.getRates)")

        try:
            # Speciální XML formát pro getRates
            root = ET.Element('request')
            ET.SubElement(root, 'login').text = self.username
            ET.SubElement(root, 'password').text = self.password
            ET.SubElement(root, 'hotId').text = self.previo_id

            # Term element s from/to
            term = ET.SubElement(root, 'term')
            ET.SubElement(term, 'from').text = date_from
            ET.SubElement(term, 'to').text = date_to

            # Currencies element
            currencies = ET.SubElement(root, 'currencies')
            currency_elem = ET.SubElement(currencies, 'currency')
            ET.SubElement(currency_elem, 'code').text = currency

            # Převod na řetězec
            xml_declaration = '<?xml version="1.0" encoding="UTF-8"?>\n'
            xml_body = ET.tostring(root, encoding='utf-8').decode('utf-8')
            xml_request = xml_declaration + xml_body

            # POZOR: URL musí být case-sensitive - getRates ne getrates!
            full_url = f"{self.api_url.rstrip('/')}/hotel/getRates"

            response = self.session.post(
                full_url,
                data=xml_request,
                headers={'Content-Type': 'application/xml; charset=utf-8'},
                timeout=30
            )

            response.raise_for_status()

            # Zpracování odpovědi
            result_root = ET.fromstring(response.content)

            # Kontrola chyby
            error = result_root.find('.//error')
            if error is not None:
                error_code = error.find('code')
                error_msg = error.find('message')
                raise Exception(f"API error {error_code.text if error_code is not None else 'unknown'}: {error_msg.text if error_msg is not None else 'unknown'}")

            # Extrakce dat
            rates_data = {
                'prmId': None,
                'ratePlans': []
            }

            prmId = result_root.find('.//prmId')
            if prmId is not None:
                rates_data['prmId'] = prmId.text

            for rate_plan in result_root.findall('.//ratePlan'):
                plan_data = {}
                for child in rate_plan:
                    if len(child) > 0:
                        # Nested element
                        plan_data[child.tag] = {subchild.tag: subchild.text for subchild in child}
                    else:
                        plan_data[child.tag] = child.text
                rates_data['ratePlans'].append(plan_data)

            logger.info(f"Získáno {len(rates_data['ratePlans'])} cenových plánů")
            return rates_data

        except Exception as e:
            logger.error(f"Chyba při získávání sazeb: {e}")
            return {"error": str(e)}
    
    def get_availability(self, date_from: str, date_to: str) -> Dict:
        """
        Získá dostupnost pokojů pro zadané období - metoda getAvailability.
        
        Args:
            date_from (str): Počáteční datum ve formátu YYYY-MM-DD
            date_to (str): Koncové datum ve formátu YYYY-MM-DD
        
        Returns:
            Dict: Informace o dostupnosti pokojů
        """
        logger.info(f"Získávám dostupnost pokojů pro období {date_from} až {date_to} (getAvailability)")
        
        try:
            params = {
                'dateFrom': date_from,
                'dateTo': date_to
            }
            
            response = self.call_api('getAvailability', params)
            availability = {}
            
            # Extrakce dat z XML
            for room in response.findall('.//room'):
                room_id = room.get('id')
                days = []
                
                for day in room.findall('.//day'):
                    day_data = {}
                    for child in day:
                        day_data[child.tag] = child.text
                    days.append(day_data)
                
                availability[room_id] = days
            
            return availability
        except Exception as e:
            logger.error(f"Chyba při získávání dostupnosti pokojů: {e}")
            # Vrátíme prázdný slovník místo vyhození výjimky
            return {}
    
    def search_reservations(self, term: str = "*") -> List[Dict]:
        """
        Vyhledá rezervace - metoda Hotel.searchReservations.

        POZNÁMKA: Tato metoda vyžaduje speciální oprávnění.
        Chyba 1022 = "Unauthorized access to method" znamená,
        že API uživatel nemá oprávnění k této metodě.

        Args:
            term (str): Vyhledávací termín (např. jméno hosta, číslo rezervace)

        Returns:
            List[Dict]: Seznam nalezených rezervací
        """
        logger.info(f"Vyhledávám rezervace s termínem '{term}' (Hotel.searchReservations)")

        try:
            params = {'term': term}

            response = self.call_api('Hotel.searchReservations', params)
            reservations = []

            # Extrakce dat z XML
            for reservation in response.findall('.//commission'):
                res_data = {}
                for child in reservation:
                    if len(child) > 0:
                        res_data[child.tag] = {subchild.tag: subchild.text for subchild in child}
                    else:
                        res_data[child.tag] = child.text
                reservations.append(res_data)

            return reservations
        except Exception as e:
            logger.error(f"Chyba při vyhledávání rezervací: {e}")
            return []

    # Alias pro zpětnou kompatibilitu
    def get_reservations(self, date_from: str = None, date_to: str = None) -> List[Dict]:
        """
        Alias pro search_reservations().

        POZNÁMKA: XML API nepoužívá datumový filtr.
        Pro rezervace s datumovým filtrem použijte REST API.
        """
        logger.warning("XML API get_reservations nepodporuje datumový filtr. Použijte REST API nebo search_reservations().")
        return self.search_reservations("*")

class PrevioRestClient:
    """Klient pro komunikaci s Previo REST API."""

    def __init__(self, username: str = None, password: str = None, api_key: str = None, hotel_id: str = None, api_url: str = "https://api.previo.app/rest/"):
        """
        Inicializace klienta pro Previo REST API.

        Podle dokumentace previo_api_volani.md:
        - URL: https://api.previo.app/rest/
        - Hlavičky: X-Previo-Hotel-Id, Authorization (Basic nebo Bearer)

        Args:
            username (str): Uživatelské jméno pro API (pokud se nepoužívá api_key)
            password (str): Heslo pro API (pokud se nepoužívá api_key)
            api_key (str): API klíč (pokud se nepoužívá username/password)
            hotel_id (str): ID hotelu/ubytování v Previo systému
            api_url (str): URL adresa REST API (výchozí: "https://api.previo.app/rest/")
        """
        self.username = username
        self.password = password
        self.api_key = api_key
        self.hotel_id = hotel_id
        self.api_url = api_url
        self.session = requests.Session()

        # Nastavení společných hlaviček podle dokumentace
        self.session.headers.update({
            "X-Previo-Hotel-Id": str(hotel_id),
            "Content-Type": "application/json",
            "Accept": "application/json"
        })

        # Nastavení autorizace - buď basic auth nebo API klíč
        if api_key:
            self.session.headers.update({"Authorization": f"Bearer {api_key}"})
        elif username and password:
            self.session.auth = (username, password)
    
    def call_api(self, endpoint: str, method: str = "GET", params: Dict = None, data: Dict = None, retry_count: int = 3, retry_delay: int = 2) -> Dict:
        """
        Provede požadavek na Previo REST API.
        
        Args:
            endpoint (str): Koncový bod API (bez základní URL)
            method (str): HTTP metoda (GET, POST, PUT)
            params (dict, optional): URL parametry
            data (dict, optional): Data pro odeslání (pro POST, PUT)
            retry_count (int): Počet opakování při selhání požadavku
            retry_delay (int): Prodleva mezi opakováními (sekundy)
        
        Returns:
            Dict: Odpověď API jako slovník
        
        Raises:
            Exception: Při chybě požadavku nebo zpracování odpovědi
        """
        if params is None:
            params = {}
        
        # Přidání API klíče do parametrů, pokud používáme API klíč místo auth
        if self.api_key and not self.session.auth:
            params['api_key'] = self.api_key
        
        # Sestavení plné URL
        url = f"{self.api_url}{endpoint}"
        
        attempt = 0
        while attempt < retry_count:
            try:
                logger.debug(f"REST API požadavek: {method} {url}")
                logger.debug(f"Parametry: {params}")
                if data:
                    logger.debug(f"Data: {json.dumps(data)[:500]}")
                
                if method == "GET":
                    response = self.session.get(url, params=params, timeout=30)
                elif method == "POST":
                    response = self.session.post(url, params=params, json=data, timeout=30)
                elif method == "PUT":
                    response = self.session.put(url, params=params, json=data, timeout=30)
                else:
                    raise ValueError(f"Nepodporovaná HTTP metoda: {method}")
                
                # Kontrola úspěšnosti požadavku
                response.raise_for_status()
                
                # Kontrola, zda odpověď obsahuje HTML místo JSON
                if response.headers.get('content-type', '').startswith('text/html'):
                    logger.error("REST API vrátilo HTML místo očekávaného JSON.")
                    logger.error(f"Odpověď (prvních 500 znaků): {response.text[:500]}")
                    raise requests.exceptions.RequestException("API vrátilo HTML místo očekávaného JSON.")
                
                # Parsování odpovědi jako JSON
                try:
                    json_data = response.json()
                except json.JSONDecodeError:
                    logger.error("Nepodařilo se parsovat odpověď jako JSON")
                    logger.error(f"Odpověď: {response.text[:1000]}")
                    raise
                
                logger.debug(f"REST API odpověď status: {response.status_code}")
                logger.debug(f"REST API odpověď (prvních 500 znaků): {json.dumps(json_data)[:500]}")
                
                return json_data
                
            except requests.exceptions.RequestException as e:
                logger.warning(f"Pokus {attempt+1}/{retry_count} selhal: {e}")
                attempt += 1
                
                if attempt < retry_count:
                    logger.info(f"Čekám {retry_delay} sekund před dalším pokusem...")
                    time.sleep(retry_delay)
                else:
                    logger.error(f"Chyba při komunikaci s REST API po {retry_count} pokusech: {e}")
                    raise
            except json.JSONDecodeError as e:
                logger.error(f"Chyba při parsování JSON odpovědi z REST API: {e}")
                if 'response' in locals():
                    logger.error(f"Odpověď: {response.text[:1000]}")
                raise
            except Exception as e:
                logger.error(f"Neočekávaná chyba při volání REST API: {e}")
                raise
    
    def get_hotel_info(self) -> Dict:
        """
        Získá informace o hotelu.
        Endpoint: GET /hotel

        Returns:
            Dict: Informace o hotelu
        """
        logger.info(f"Získávám informace o hotelu (REST API)")

        try:
            return self.call_api("hotel")
        except Exception as e:
            logger.error(f"Chyba při získávání informací o hotelu z REST API: {e}")
            return {"error": str(e)}

    def get_room_types(self) -> Dict:
        """
        Získá seznam typů pokojů.
        Endpoint: GET /room-type

        Returns:
            Dict: Seznam typů pokojů
        """
        logger.info(f"Získávám seznam typů pokojů (REST API)")

        try:
            return self.call_api("room-type")
        except Exception as e:
            logger.error(f"Chyba při získávání typů pokojů z REST API: {e}")
            return {"error": str(e)}

    def get_rate_plans(self) -> Dict:
        """
        Získá seznam cenových plánů.
        Endpoint: GET /rate-plan

        Returns:
            Dict: Seznam cenových plánů
        """
        logger.info(f"Získávám seznam cenových plánů (REST API)")

        try:
            return self.call_api("rate-plan")
        except Exception as e:
            logger.error(f"Chyba při získávání cenových plánů z REST API: {e}")
            return {"error": str(e)}

    def get_guest_categories(self) -> Dict:
        """
        Získá seznam kategorií hostů.
        Endpoint: GET /guest-category

        Returns:
            Dict: Seznam kategorií hostů
        """
        logger.info(f"Získávám seznam kategorií hostů (REST API)")

        try:
            return self.call_api("guest-category")
        except Exception as e:
            logger.error(f"Chyba při získávání kategorií hostů z REST API: {e}")
            return {"error": str(e)}

    def get_meal_types(self) -> Dict:
        """
        Získá seznam typů stravování.
        Endpoint: GET /meal-type

        Returns:
            Dict: Seznam typů stravování
        """
        logger.info(f"Získávám seznam typů stravování (REST API)")

        try:
            return self.call_api("meal-type")
        except Exception as e:
            logger.error(f"Chyba při získávání typů stravování z REST API: {e}")
            return {"error": str(e)}

    def get_rooms_availability(self, date_from: str, date_to: str) -> Dict:
        """
        Získá dostupnost pokojů pro zadané období.
        Endpoint: GET /calendar/availability

        Args:
            date_from (str): Počáteční datum ve formátu YYYY-MM-DD
            date_to (str): Koncové datum ve formátu YYYY-MM-DD

        Returns:
            Dict: Informace o dostupnosti pokojů
        """
        logger.info(f"Získávám dostupnost pokojů pro období {date_from} až {date_to} (REST API)")

        try:
            params = {
                'filterFrom': date_from,
                'filterTo': date_to
            }

            return self.call_api("calendar/availability", params=params)
        except Exception as e:
            logger.error(f"Chyba při získávání dostupnosti pokojů z REST API: {e}")
            return {"error": str(e)}

    def get_rates(self, date_from: str, date_to: str) -> Dict:
        """
        Získá ceník pro zadané období.
        Endpoint: GET /rate-plan (cenové plány jsou součástí rate-plan)

        Args:
            date_from (str): Počáteční datum ve formátu YYYY-MM-DD
            date_to (str): Koncové datum ve formátu YYYY-MM-DD

        Returns:
            Dict: Ceník pro dané období
        """
        logger.info(f"Získávám ceník pro období {date_from} až {date_to} (REST API)")

        try:
            return self.call_api("rate-plan")
        except Exception as e:
            logger.error(f"Chyba při získávání ceníku z REST API: {e}")
            return {"error": str(e)}

    def get_reservations(self, date_from: str, date_to: str) -> Dict:
        """
        Získá seznam rezervací pro zadané období.
        Endpoint: POST /reservations/ (POST s JSON filtrem)

        POZNÁMKA: Tento endpoint může vracet 405 chybu na některých serverech.
        V takovém případě použijte XML API (PrevioXmlClient.get_reservations).

        Args:
            date_from (str): Počáteční datum ve formátu YYYY-MM-DD
            date_to (str): Koncové datum ve formátu YYYY-MM-DD

        Returns:
            Dict: Seznam rezervací
        """
        logger.info(f"Získávám seznam rezervací pro období {date_from} až {date_to} (REST API)")

        try:
            # Rezervace se získávají přes POST s filtrem v JSON body
            request_body = {
                "filter": {
                    "from": date_from,
                    "to": date_to
                }
            }

            return self.call_api("reservations/", method="POST", data=request_body)
        except Exception as e:
            logger.error(f"Chyba při získávání rezervací z REST API: {e}")
            logger.warning("TIP: Pro rezervace použijte XML API (PrevioXmlClient.get_reservations)")
            return {"error": str(e)}

    def get_guests(self, limit: int = 100) -> Dict:
        """
        Získá seznam hostů.
        Endpoint: GET /guests/

        Args:
            limit (int): Maximální počet hostů (default 100)

        Returns:
            Dict: Seznam hostů s klíči 'foundRows' a 'guests'
        """
        logger.info(f"Získávám seznam hostů (REST API)")

        try:
            params = {'limit': limit}
            return self.call_api("guests/", params=params)
        except Exception as e:
            logger.error(f"Chyba při získávání seznamu hostů z REST API: {e}")
            return {"error": str(e)}

    def get_guest(self, guest_id: str) -> Dict:
        """
        Získá informace o hostovi.
        Endpoint: GET /guests/{id}

        Args:
            guest_id (str): ID hosta

        Returns:
            Dict: Informace o hostovi
        """
        logger.info(f"Získávám informace o hostovi {guest_id} (REST API)")

        try:
            return self.call_api(f"guests/{guest_id}")
        except Exception as e:
            logger.error(f"Chyba při získávání informací o hostovi z REST API: {e}")
            return {"error": str(e)}

    def search_guests(self, query: str = None, email: str = None, phone: str = None) -> Dict:
        """
        Vyhledá hosty podle různých kritérií.
        Endpoint: GET /guests/search

        Args:
            query (str): Vyhledávací dotaz (jméno)
            email (str): Email hosta
            phone (str): Telefon hosta

        Returns:
            Dict: Seznam nalezených hostů
        """
        logger.info(f"Vyhledávám hosty (REST API)")

        try:
            params = {}
            if query:
                params['query'] = query
            if email:
                params['email'] = email
            if phone:
                params['phone'] = phone

            return self.call_api("guests/search", params=params)
        except Exception as e:
            logger.error(f"Chyba při vyhledávání hostů z REST API: {e}")
            return {"error": str(e)}

    def get_billing_documents(self, date_from: str = None, date_to: str = None, date_type: str = "createDate") -> Dict:
        """
        Získá seznam fakturačních dokladů.
        Endpoint: GET /billing/documents

        Args:
            date_from (str): Počáteční datum (YYYY-MM-DD)
            date_to (str): Koncové datum (YYYY-MM-DD)
            date_type (str): Typ datumu pro filtrování ('createDate', 'dueDate', 'paymentDate')

        Returns:
            Dict: Seznam fakturačních dokladů
        """
        logger.info(f"Získávám seznam fakturačních dokladů (REST API)")

        try:
            params = {'filterDateType': date_type}
            if date_from:
                params['filterFrom'] = date_from
            if date_to:
                params['filterTo'] = date_to

            return self.call_api("billing/documents", params=params)
        except Exception as e:
            logger.error(f"Chyba při získávání fakturačních dokladů z REST API: {e}")
            return {"error": str(e)}

    def get_billing_document(self, document_id: str) -> Dict:
        """
        Získá konkrétní fakturační doklad.
        Endpoint: GET /billing/documents/{id}

        Args:
            document_id (str): ID dokladu

        Returns:
            Dict: Fakturační doklad
        """
        logger.info(f"Získávám fakturační doklad {document_id} (REST API)")

        try:
            return self.call_api(f"billing/documents/{document_id}")
        except Exception as e:
            logger.error(f"Chyba při získávání fakturačního dokladu z REST API: {e}")
            return {"error": str(e)}

    def get_price_suggestion(self, rooms_data: Dict, currency_id: int = 1) -> Dict:
        """
        Získá doporučení ceny pro zadané parametry rezervace.
        Endpoint: POST /reservations/accounts/suggester

        Args:
            rooms_data (Dict): Data o pokojích (formátováno pomocí format_price_request)
            currency_id (int): ID měny (1 = CZK)

        Returns:
            Dict: Doporučená cena
        """
        logger.info(f"Získávám doporučení ceny (REST API)")

        try:
            data = {
                "currencyId": currency_id,
                "rooms": rooms_data if isinstance(rooms_data, list) else [rooms_data]
            }

            return self.call_api("reservations/accounts/suggester", method="POST", data=data)
        except Exception as e:
            logger.error(f"Chyba při získávání doporučení ceny z REST API: {e}")
            return {"error": str(e)}

    def get_occupancy_data(self, date_from: str, date_to: str) -> Dict:
        """
        Získá data o obsazenosti pro zadané období.
        Endpoint: GET /calendar/availability

        Args:
            date_from (str): Počáteční datum ve formátu YYYY-MM-DD
            date_to (str): Koncové datum ve formátu YYYY-MM-DD

        Returns:
            Dict: Data o obsazenosti
        """
        logger.info(f"Získávám data o obsazenosti pro období {date_from} až {date_to} (REST API)")

        try:
            params = {
                'filterFrom': date_from,
                'filterTo': date_to
            }

            availability = self.call_api("calendar/availability", params=params)

            # Přidáme zpracované informace o obsazenosti
            result = {
                "availability": availability,
                "summary": self._calculate_occupancy_summary(availability)
            }

            return result
        except Exception as e:
            logger.error(f"Chyba při získávání dat o obsazenosti z REST API: {e}")
            return {"error": str(e)}
    
    def _calculate_occupancy_summary(self, availability_data) -> Dict:
        """
        Vypočítá souhrn obsazenosti z dat o dostupnosti.

        Data z calendar/availability mají strukturu:
        [
            {
                "ratePlanId": 125099,
                "availability": [
                    {
                        "date": "2025-12-01",
                        "roomKinds": [
                            {"id": 640240, "availability": 1},  # 1 = volno
                            {"id": 640238, "availability": 0},  # 0 = obsazeno
                            ...
                        ]
                    },
                    ...
                ]
            }
        ]

        Args:
            availability_data: Data o dostupnosti z API

        Returns:
            Dict: Souhrn obsazenosti s denními daty a průměrem
        """
        summary = {
            "total_rooms": 0,
            "average_occupancy": 0,
            "days": []
        }

        try:
            # Kontrola struktury dat
            if not availability_data or not isinstance(availability_data, list):
                return summary

            # Získáme první rate plan (obvykle jediný)
            rate_plan = availability_data[0] if availability_data else {}
            availability_list = rate_plan.get('availability', [])

            if not availability_list:
                return summary

            total_occupancy = 0
            days_count = 0

            for day_data in availability_list:
                date_str = day_data.get('date', '')
                room_kinds = day_data.get('roomKinds', [])

                if not room_kinds:
                    continue

                # Počet obsazených a volných pokojů
                occupied = sum(1 for r in room_kinds if r.get('availability') == 0)
                free = sum(1 for r in room_kinds if r.get('availability') == 1)
                total = occupied + free

                if total > 0:
                    occupancy_pct = (occupied / total) * 100
                else:
                    occupancy_pct = 0

                summary['days'].append({
                    'date': date_str,
                    'occupied': occupied,
                    'free': free,
                    'total': total,
                    'occupancy_percent': round(occupancy_pct, 1)
                })

                total_occupancy += occupancy_pct
                days_count += 1

                # Uložíme celkový počet pokojů (z prvního dne)
                if summary['total_rooms'] == 0:
                    summary['total_rooms'] = total

            # Průměrná obsazenost
            if days_count > 0:
                summary['average_occupancy'] = round(total_occupancy / days_count, 1)

        except Exception as e:
            logger.error(f"Chyba při výpočtu obsazenosti: {e}")

        return summary


def format_date(date_obj=None):
    """
    Formátuje datum do formátu YYYY-MM-DD.
    
    Args:
        date_obj: Objekt datetime.date (výchozí: dnešní datum)
    
    Returns:
        str: Formátované datum
    """
    if date_obj is None:
        date_obj = datetime.date.today()
    return date_obj.strftime("%Y-%m-%d")


def save_json_data(data, filename, directory="data"):
    """
    Uloží data do JSON souboru.
    
    Args:
        data: Data k uložení
        filename: Název souboru (bez přípony)
        directory: Cílový adresář
    
    Returns:
        str: Cesta k uloženému souboru
    """
    # Vytvoření adresáře, pokud neexistuje
    os.makedirs(directory, exist_ok=True)
    
    # Přidání časového razítka k názvu souboru
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = os.path.join(directory, f"{filename}_{timestamp}.json")
    
    # Uložení dat do souboru
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    logger.info(f"Data uložena do souboru: {file_path}")
    return file_path


# Příklad použití:
if __name__ == "__main__":
    # Inicializace XML klienta
    xml_client = PrevioXmlClient(
        username=XML_CONFIG['username'],
        password=XML_CONFIG['password'],
        previo_id=XML_CONFIG['previo_id'],
        api_url=XML_CONFIG['api_url']
    )
    
    # Inicializace REST klienta
    rest_client = PrevioRestClient(
        username=REST_CONFIG['username'],
        password=REST_CONFIG['password'],
        hotel_id=REST_CONFIG['hotel_id'],
        api_url=REST_CONFIG['api_url']
    )
    
    try:
        # Test API
        print("Testuji přístup k API...")
        
        # Test XML API
        print("\n==== Test XML API ====")
        try:
            print(f"Používám URL: {xml_client.api_url}")
            hotel_info = xml_client.get_hotel_info()
            print("Získány informace o hotelu:", bool(hotel_info and "error" not in hotel_info))
            
            rooms = xml_client.get_rooms()
            print(f"Získáno {len(rooms)} pokojů")
            
            # Testování dalších metod pouze pokud základní komunikace funguje
            if rooms:
                # Datum pro testování
                today = datetime.date.today()
                next_month = today + datetime.timedelta(days=30)
                
                prices = xml_client.get_prices(format_date(today), format_date(next_month))
                print(f"Získáno {len(prices)} záznamů o cenách")
                
                availability = xml_client.get_availability(format_date(today), format_date(next_month))
                print(f"Získána dostupnost pro {len(availability)} pokojů")
                
                reservations = xml_client.get_reservations(format_date(today), format_date(next_month))
                print(f"Získáno {len(reservations)} rezervací")
                
                # Uložit úspěšnou konfiguraci URL do logu
                logger.info(f"Úspěšný test s URL: {xml_client.api_url}")
        except Exception as e:
            print(f"Test XML API selhal: {e}")
        
        # Test REST API
        print("\n==== Test REST API ====")
        try:
            hotel_info = rest_client.get_hotel_info()
            print("Získány informace o hotelu:", bool(hotel_info and "error" not in hotel_info))
            
            room_types = rest_client.get_room_types()
            print("Získány typy pokojů:", bool(room_types and "error" not in room_types))
            
            # Testování dalších metod pouze pokud základní komunikace funguje
            if room_types and "error" not in room_types:
                # Datum pro testování
                today = datetime.date.today()
                next_month = today + datetime.timedelta(days=30)
                
                availability = rest_client.get_rooms_availability(format_date(today), format_date(next_month))
                print("Získána dostupnost pokojů:", bool(availability and "error" not in availability))
                
                rates = rest_client.get_rates(format_date(today), format_date(next_month))
                print("Získány ceny:", bool(rates and "error" not in rates))
                
                reservations = rest_client.get_reservations(format_date(today), format_date(next_month))
                print("Získány rezervace:", bool(reservations and "error" not in reservations))
        except Exception as e:
            print(f"Test REST API selhal: {e}")
            
    except Exception as e:
        logger.error(f"Chyba při testování API klientů: {e}")
        import traceback
        traceback.print_exc()
