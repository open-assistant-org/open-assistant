"""Google Places and Routes API client for location and navigation operations."""

import time
from typing import Any, Dict, List, Optional

import requests

from src.utils.logger import get_logger

logger = get_logger(__name__)

# Google API base URLs
PLACES_BASE_URL = "https://places.googleapis.com/v1"
DIRECTIONS_BASE_URL = "https://maps.googleapis.com/maps/api/directions/json"
GEOCODING_BASE_URL = "https://maps.googleapis.com/maps/api/geocode/json"


class GooglePlacesClient:
    """Client for Google Places (New) and Directions APIs."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = requests.Session()
        logger.info("Google Places client initialized")

    # ========================================================================
    # PLACES OPERATIONS
    # ========================================================================

    def search_places(
        self,
        query: str,
        location: Optional[str] = None,
        radius: Optional[int] = None,
        max_results: int = 10,
        language: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search for places using text query via Google Places API (New).

        Args:
            query: Text search query
            location: Lat,lng to bias results (e.g. "52.3676,4.9041")
            radius: Search radius in meters
            max_results: Maximum results to return
            language: Language code for results

        Returns:
            List of place results
        """
        try:
            logger.info(f"Searching places: query='{query}', location={location}")

            url = f"{PLACES_BASE_URL}/places:searchText"

            headers = {
                "Content-Type": "application/json",
                "X-Goog-Api-Key": self.api_key,
                "X-Goog-FieldMask": (
                    "places.id,places.displayName,places.formattedAddress,"
                    "places.location,places.rating,places.userRatingCount,"
                    "places.types,places.businessStatus,places.priceLevel,"
                    "places.websiteUri,places.nationalPhoneNumber,"
                    "places.currentOpeningHours,places.regularOpeningHours"
                ),
            }

            body: Dict[str, Any] = {
                "textQuery": query,
                "maxResultCount": min(max_results, 20),
            }

            if language:
                body["languageCode"] = language

            if location:
                # Try to parse as lat,lng coordinates
                try:
                    parts = location.split(",")
                    if len(parts) == 2:
                        lat, lng = float(parts[0].strip()), float(parts[1].strip())
                        location_bias: Dict[str, Any] = {
                            "circle": {
                                "center": {"latitude": lat, "longitude": lng},
                                "radius": float(radius) if radius else 5000.0,
                            }
                        }
                        body["locationBias"] = location_bias
                    else:
                        # Not valid coordinates, treat as place name in the query
                        body["textQuery"] = f"{query} in {location}"
                except (ValueError, IndexError):
                    # Not coordinates, treat as place name in the query
                    body["textQuery"] = f"{query} in {location}"

            response = self.session.post(url, json=body, headers=headers, timeout=15)
            response.raise_for_status()

            data = response.json()
            places = data.get("places", [])

            results = []
            for place in places:
                parsed = self._parse_place(place)
                results.append(parsed)

            logger.info(f"Found {len(results)} places")
            return results

        except requests.exceptions.HTTPError as e:
            logger.error(f"Places API HTTP error: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to search places: {e}")
            raise

    def get_place_details(
        self,
        place_id: str,
        language: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get detailed information about a specific place.

        Args:
            place_id: Google Maps Place ID
            language: Language code for results

        Returns:
            Place details
        """
        try:
            logger.info(f"Getting place details: {place_id}")

            url = f"{PLACES_BASE_URL}/places/{place_id}"

            headers = {
                "Content-Type": "application/json",
                "X-Goog-Api-Key": self.api_key,
                "X-Goog-FieldMask": (
                    "id,displayName,formattedAddress,location,rating,"
                    "userRatingCount,types,businessStatus,priceLevel,"
                    "websiteUri,nationalPhoneNumber,internationalPhoneNumber,"
                    "currentOpeningHours,regularOpeningHours,"
                    "reviews,editorialSummary,accessibilityOptions,"
                    "parkingOptions,paymentOptions,googleMapsUri"
                ),
            }

            params: Dict[str, str] = {}
            if language:
                params["languageCode"] = language

            response = self.session.get(url, headers=headers, params=params, timeout=15)
            response.raise_for_status()

            place = response.json()
            result = self._parse_place_details(place)

            logger.info(f"Retrieved details for place: {place_id}")
            return result

        except requests.exceptions.HTTPError as e:
            logger.error(f"Place details API error: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to get place details: {e}")
            raise

    def nearby_places(
        self,
        location: str,
        radius: int = 1000,
        place_type: Optional[str] = None,
        max_results: int = 10,
        language: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search for places near a location by type.

        Args:
            location: Lat,lng center point (e.g. "52.3676,4.9041")
            radius: Search radius in meters
            place_type: Place type filter (e.g. "restaurant")
            max_results: Maximum results
            language: Language code

        Returns:
            List of nearby places
        """
        try:
            logger.info(f"Searching nearby places: location={location}, type={place_type}")

            url = f"{PLACES_BASE_URL}/places:searchNearby"

            headers = {
                "Content-Type": "application/json",
                "X-Goog-Api-Key": self.api_key,
                "X-Goog-FieldMask": (
                    "places.id,places.displayName,places.formattedAddress,"
                    "places.location,places.rating,places.userRatingCount,"
                    "places.types,places.businessStatus,places.priceLevel,"
                    "places.nationalPhoneNumber,places.currentOpeningHours"
                ),
            }

            lat, lng = [float(x.strip()) for x in location.split(",")]

            body: Dict[str, Any] = {
                "locationRestriction": {
                    "circle": {
                        "center": {"latitude": lat, "longitude": lng},
                        "radius": float(radius),
                    }
                },
                "maxResultCount": min(max_results, 20),
            }

            if place_type:
                body["includedTypes"] = [place_type]

            if language:
                body["languageCode"] = language

            response = self.session.post(url, json=body, headers=headers, timeout=15)
            response.raise_for_status()

            data = response.json()
            places = data.get("places", [])

            results = []
            for place in places:
                parsed = self._parse_place(place)
                results.append(parsed)

            logger.info(f"Found {len(results)} nearby places")
            return results

        except requests.exceptions.HTTPError as e:
            logger.error(f"Nearby places API error: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to search nearby places: {e}")
            raise

    # ========================================================================
    # DIRECTIONS / ROUTING
    # ========================================================================

    def get_directions(
        self,
        origin: str,
        destination: str,
        mode: str = "driving",
        departure_time: Optional[str] = None,
        avoid: Optional[str] = None,
        waypoints: Optional[List[str]] = None,
        alternatives: bool = False,
        units: str = "metric",
        language: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get directions and travel time between locations.

        Args:
            origin: Starting point (address or lat,lng)
            destination: End point (address or lat,lng)
            mode: Travel mode (driving, walking, bicycling, transit)
            departure_time: Departure time (RFC3339 or 'now')
            avoid: Features to avoid (tolls, highways, ferries)
            waypoints: Intermediate stops
            alternatives: Return alternative routes
            units: metric or imperial
            language: Language code

        Returns:
            Directions with routes, duration, distance, and steps
        """
        try:
            logger.info(f"Getting directions: {origin} -> {destination} ({mode})")

            params: Dict[str, Any] = {
                "origin": origin,
                "destination": destination,
                "mode": mode,
                "units": units,
                "key": self.api_key,
            }

            if departure_time:
                if departure_time.lower() == "now":
                    params["departure_time"] = "now"
                else:
                    # Convert RFC3339 to Unix timestamp
                    from datetime import datetime

                    dt = datetime.fromisoformat(departure_time.replace("Z", "+00:00"))
                    params["departure_time"] = str(int(dt.timestamp()))

            if avoid:
                params["avoid"] = avoid

            if waypoints:
                params["waypoints"] = "|".join(waypoints)

            if alternatives:
                params["alternatives"] = "true"

            if language:
                params["language"] = language

            response = self.session.get(DIRECTIONS_BASE_URL, params=params, timeout=15)
            response.raise_for_status()

            data = response.json()

            if data.get("status") != "OK":
                error_msg = data.get("error_message", data.get("status", "Unknown error"))
                raise ValueError(f"Directions API error: {error_msg}")

            result = self._parse_directions(data, mode)
            logger.info(f"Retrieved {len(result.get('routes', []))} route(s)")
            return result

        except requests.exceptions.HTTPError as e:
            logger.error(f"Directions API HTTP error: {e}")
            raise
        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Failed to get directions: {e}")
            raise

    # ========================================================================
    # GEOCODING
    # ========================================================================

    def geocode(
        self,
        address: str,
        language: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Geocode an address to coordinates.

        Args:
            address: Address or place name
            language: Language code

        Returns:
            Geocoding result with coordinates and formatted address
        """
        try:
            logger.info(f"Geocoding address: {address}")

            params: Dict[str, Any] = {
                "address": address,
                "key": self.api_key,
            }

            if language:
                params["language"] = language

            response = self.session.get(GEOCODING_BASE_URL, params=params, timeout=15)
            response.raise_for_status()

            data = response.json()

            if data.get("status") != "OK":
                error_msg = data.get("error_message", data.get("status", "No results"))
                raise ValueError(f"Geocoding error: {error_msg}")

            results = data.get("results", [])
            if not results:
                return {"error": "No results found", "formatted_address": None}

            top = results[0]
            loc = top.get("geometry", {}).get("location", {})

            return {
                "formatted_address": top.get("formatted_address"),
                "latitude": loc.get("lat"),
                "longitude": loc.get("lng"),
                "place_id": top.get("place_id"),
                "address_components": [
                    {
                        "name": c.get("long_name"),
                        "short_name": c.get("short_name"),
                        "types": c.get("types", []),
                    }
                    for c in top.get("address_components", [])
                ],
            }

        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Failed to geocode: {e}")
            raise

    def reverse_geocode(
        self,
        latitude: float,
        longitude: float,
        language: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Reverse geocode coordinates to an address.

        Args:
            latitude: Latitude
            longitude: Longitude
            language: Language code

        Returns:
            Address information for the given coordinates
        """
        try:
            logger.info(f"Reverse geocoding: {latitude},{longitude}")

            params: Dict[str, Any] = {
                "latlng": f"{latitude},{longitude}",
                "key": self.api_key,
            }

            if language:
                params["language"] = language

            response = self.session.get(GEOCODING_BASE_URL, params=params, timeout=15)
            response.raise_for_status()

            data = response.json()

            if data.get("status") != "OK":
                error_msg = data.get("error_message", data.get("status", "No results"))
                raise ValueError(f"Reverse geocoding error: {error_msg}")

            results = data.get("results", [])
            if not results:
                return {"error": "No results found"}

            top = results[0]

            return {
                "formatted_address": top.get("formatted_address"),
                "place_id": top.get("place_id"),
                "address_components": [
                    {
                        "name": c.get("long_name"),
                        "short_name": c.get("short_name"),
                        "types": c.get("types", []),
                    }
                    for c in top.get("address_components", [])
                ],
                "location_type": top.get("geometry", {}).get("location_type"),
            }

        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Failed to reverse geocode: {e}")
            raise

    # ========================================================================
    # PARSING HELPERS
    # ========================================================================

    def _parse_place(self, place: Dict[str, Any]) -> Dict[str, Any]:
        """Parse a place result from the Places API (New)."""
        location = place.get("location", {})
        display_name = place.get("displayName", {})
        opening_hours = place.get("currentOpeningHours") or place.get("regularOpeningHours")

        parsed: Dict[str, Any] = {
            "place_id": place.get("id", "").replace("places/", ""),
            "name": display_name.get("text", ""),
            "address": place.get("formattedAddress", ""),
            "latitude": location.get("latitude"),
            "longitude": location.get("longitude"),
            "rating": place.get("rating"),
            "total_ratings": place.get("userRatingCount"),
            "types": place.get("types", []),
            "business_status": place.get("businessStatus"),
            "price_level": place.get("priceLevel"),
            "phone": place.get("nationalPhoneNumber"),
            "website": place.get("websiteUri"),
        }

        if opening_hours:
            parsed["open_now"] = opening_hours.get("openNow")
            weekday_text = opening_hours.get("weekdayDescriptions", [])
            if weekday_text:
                parsed["opening_hours"] = weekday_text

        return parsed

    def _parse_place_details(self, place: Dict[str, Any]) -> Dict[str, Any]:
        """Parse detailed place information."""
        parsed = self._parse_place(place)

        # Add extra detail fields
        parsed["international_phone"] = place.get("internationalPhoneNumber")
        parsed["google_maps_url"] = place.get("googleMapsUri")

        # Editorial summary
        editorial = place.get("editorialSummary", {})
        if editorial:
            parsed["description"] = editorial.get("text")

        # Reviews (top 3)
        reviews = place.get("reviews", [])
        if reviews:
            parsed["reviews"] = [
                {
                    "rating": r.get("rating"),
                    "text": r.get("text", {}).get("text", ""),
                    "author": r.get("authorAttribution", {}).get("displayName", ""),
                    "time": r.get("publishTime"),
                }
                for r in reviews[:3]
            ]

        # Parking
        parking = place.get("parkingOptions")
        if parking:
            parsed["parking"] = parking

        # Accessibility
        accessibility = place.get("accessibilityOptions")
        if accessibility:
            parsed["accessibility"] = accessibility

        return parsed

    def _parse_directions(self, data: Dict[str, Any], mode: str) -> Dict[str, Any]:
        """Parse directions API response into a clean format."""
        routes = data.get("routes", [])

        parsed_routes = []
        for route in routes:
            legs = route.get("legs", [])

            parsed_legs = []
            for leg in legs:
                parsed_leg: Dict[str, Any] = {
                    "start_address": leg.get("start_address"),
                    "end_address": leg.get("end_address"),
                    "distance": leg.get("distance", {}).get("text"),
                    "distance_meters": leg.get("distance", {}).get("value"),
                    "duration": leg.get("duration", {}).get("text"),
                    "duration_seconds": leg.get("duration", {}).get("value"),
                }

                # Traffic-aware duration (driving only)
                duration_in_traffic = leg.get("duration_in_traffic")
                if duration_in_traffic:
                    parsed_leg["duration_in_traffic"] = duration_in_traffic.get("text")
                    parsed_leg["duration_in_traffic_seconds"] = duration_in_traffic.get("value")

                # Condensed step-by-step directions
                steps = leg.get("steps", [])
                parsed_steps = []
                for step in steps:
                    parsed_step: Dict[str, Any] = {
                        "instruction": step.get("html_instructions", "")
                        .replace("<b>", "")
                        .replace("</b>", "")
                        .replace("<div>", " ")
                        .replace("</div>", "")
                        .replace('<div style="font-size:0.9em">', " ")
                        .strip(),
                        "distance": step.get("distance", {}).get("text"),
                        "duration": step.get("duration", {}).get("text"),
                        "travel_mode": step.get("travel_mode"),
                    }

                    # Transit details
                    transit = step.get("transit_details")
                    if transit:
                        line = transit.get("line", {})
                        parsed_step["transit"] = {
                            "line_name": line.get("name"),
                            "line_short_name": line.get("short_name"),
                            "vehicle_type": line.get("vehicle", {}).get("type"),
                            "departure_stop": transit.get("departure_stop", {}).get("name"),
                            "arrival_stop": transit.get("arrival_stop", {}).get("name"),
                            "num_stops": transit.get("num_stops"),
                        }

                    parsed_steps.append(parsed_step)

                parsed_leg["steps"] = parsed_steps
                parsed_legs.append(parsed_leg)

            parsed_route: Dict[str, Any] = {
                "summary": route.get("summary"),
                "legs": parsed_legs,
                "warnings": route.get("warnings", []),
            }

            # Total distance and duration across all legs
            total_distance_m = sum(leg.get("distance_meters", 0) for leg in parsed_legs)
            total_duration_s = sum(leg.get("duration_seconds", 0) for leg in parsed_legs)

            parsed_route["total_distance"] = _format_distance(total_distance_m)
            parsed_route["total_duration"] = _format_duration(total_duration_s)

            parsed_routes.append(parsed_route)

        return {
            "origin": (
                routes[0]["legs"][0]["start_address"] if routes and routes[0].get("legs") else None
            ),
            "destination": (
                routes[0]["legs"][-1]["end_address"] if routes and routes[0].get("legs") else None
            ),
            "travel_mode": mode,
            "routes": parsed_routes,
        }


def _format_distance(meters: int) -> str:
    """Format distance in meters to human-readable string."""
    if meters >= 1000:
        return f"{meters / 1000:.1f} km"
    return f"{meters} m"


def _format_duration(seconds: int) -> str:
    """Format duration in seconds to human-readable string."""
    if seconds >= 3600:
        hours = seconds // 3600
        mins = (seconds % 3600) // 60
        return f"{hours}h {mins}min" if mins else f"{hours}h"
    elif seconds >= 60:
        return f"{seconds // 60} min"
    return f"{seconds} sec"
