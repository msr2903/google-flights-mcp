
#!/usr/bin/env python
import asyncio
import json
import datetime
import sys
import os
from typing import Any, Optional, Dict

# --- fast_flights should now be in the same directory ---
try:
    from fast_flights import FlightData, Passengers, get_flights
except ImportError as e:
    print(f"Error importing fast_flights: {e}", file=sys.stderr)
    print(f"Ensure the 'fast_flights' directory is present alongside server.py.", file=sys.stderr)
    sys.exit(1)

from mcp.server.fastmcp import FastMCP

# Initialize FastMCP server
mcp = FastMCP("google-flights-cheapest-finder")

# --- Helper functions adapted from find_cheapest_may.py ---

def flight_to_dict(flight):
    """Converts a flight object to a dictionary, handling potential missing attributes."""
    return {
        "is_best": getattr(flight, 'is_best', None),
        "name": getattr(flight, 'name', None),
        "departure": getattr(flight, 'departure', None),
        "arrival": getattr(flight, 'arrival', None),
        "arrival_time_ahead": getattr(flight, 'arrival_time_ahead', None),
        "duration": getattr(flight, 'duration', None),
        "stops": getattr(flight, 'stops', None),
        "delay": getattr(flight, 'delay', None),
        "price": getattr(flight, 'price', None),
    }

def parse_price(price_str):
    """Extracts integer price from a string like '$268'."""
    if not price_str or not isinstance(price_str, str):
        return float('inf') # Return infinity if price is missing or invalid
    try:
        return int(price_str.replace('$', '').replace(',', ''))
    except ValueError:
        return float('inf') # Return infinity if conversion fails

def get_date_range(year, month):
    """Generates all dates within a given month."""
    try:
        start_date = datetime.date(year, month, 1)
        # Find the first day of the next month, then subtract one day
        if month == 12:
            end_date = datetime.date(year + 1, 1, 1) - datetime.timedelta(days=1)
        else:
            end_date = datetime.date(year, month + 1, 1) - datetime.timedelta(days=1)
    except ValueError: # Handle invalid year/month
        return []

    current_date = start_date
    while current_date <= end_date:
        yield current_date
        current_date += datetime.timedelta(days=1)

# --- MCP Tool Implementations ---

@mcp.tool()
async def get_flights_on_date(
    origin: str,
    destination: str,
    date: str,
    adults: int = 1,
    seat_type: str = "economy",
    sort_cheapest: bool = False,
    stops: Optional[int] = None,
    limit: Optional[int] = 10
) -> str:
    """
    Fetches available one-way flights for a specific date between two airports.
    Optionally sorts by cheapest price.

    Args:
        origin: Origin airport code (e.g., "DEN").
        destination: Destination airport code (e.g., "LAX").
        date: The specific date to search (YYYY-MM-DD format).
        adults: Number of adult passengers (default: 1).
        seat_type: Fare class (e.g., "economy", "business", default: "economy").
        sort_cheapest: If True, results are sorted by price ascending (default: False).
        stops: Number of stops to filter (e.g., 0 for non-stop). If None, no stop filtering is applied (default: None).
        limit: Maximum number of flights to return (default: 10).

    Example Args:
        {"origin": "SFO", "destination": "JFK", "date": "2025-07-20"}
        {"origin": "SFO", "destination": "JFK", "date": "2025-07-20", "sort_cheapest": true}
    """
    print(f"MCP Tool: Getting flights {origin}->{destination} for {date}...", file=sys.stderr)
    try:
        # Validate date format
        datetime.datetime.strptime(date, '%Y-%m-%d')

        flight_data = [
            FlightData(date=date, from_airport=origin, to_airport=destination),
        ]
        passengers_info = Passengers(adults=adults)

        result = get_flights(
            flight_data=flight_data,
            trip="one-way", # Explicitly one-way for this tool
            seat=seat_type,
            passengers=passengers_info,
        )

        # Filter by number of stops if provided
        flights_list = result.flights if result and result.flights else []
        if stops is not None:
            flights_list = [f for f in flights_list if getattr(f, "stops", None) == stops]

        if sort_cheapest:
            flights_list = sorted(flights_list, key=lambda f: parse_price(f.price))
        processed_flights = [flight_to_dict(f) for f in flights_list[:limit]]
        output_data = {"flights": processed_flights}
        if flights_list:
            return json.dumps(output_data, indent=2)
        else:
            return json.dumps({
                "message": f"No flights found for {origin} -> {destination} on {date}."
             })

    except ValueError as e:
         # Return structured error
         error_payload = {"error": {"message": f"Invalid date format: '{date}'. Please use YYYY-MM-DD.", "type": "ValueError"}}
         return json.dumps(error_payload)
    except Exception as e:
        print(f"MCP Tool Error in get_flights_on_date: {e}", file=sys.stderr)
        # Return structured error
        error_payload = {"error": {"message": f"An unexpected error occurred.", "type": type(e).__name__}}
        return json.dumps(error_payload)


@mcp.tool()
async def get_round_trip_flights(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str,
    adults: int = 1,
    seat_type: str = "economy",
    sort_cheapest: bool = False,
    stops: Optional[int] = None,
    limit: Optional[int] = 10
) -> str:
    """
    Fetches available round-trip flights for specific departure and return dates.
    Optionally sorts by cheapest price.

    Args:
        origin: Origin airport code (e.g., "DEN").
        destination: Destination airport code (e.g., "LAX").
        departure_date: The specific departure date (YYYY-MM-DD format).
        return_date: The specific return date (YYYY-MM-DD format).
        adults: Number of adult passengers (default: 1).
        seat_type: Fare class (e.g., "economy", "business", default: "economy").
        sort_cheapest: If True, results are sorted by price ascending (default: False).
        stops: Number of stops to filter (e.g., 0 for non-stop). If None, no stop filtering is applied (default: None).
        limit: Maximum number of flights to return (default: 10).

    Example Args:
        {"origin": "DEN", "destination": "LAX", "departure_date": "2025-08-01", "return_date": "2025-08-08"}
        {"origin": "DEN", "destination": "LAX", "departure_date": "2025-08-01", "return_date": "2025-08-08", "sort_cheapest": true}
    """
    print(f"MCP Tool: Getting round trip {origin}<->{destination} for {departure_date} to {return_date}...", file=sys.stderr)
    try:
        # Validate date formats
        datetime.datetime.strptime(departure_date, '%Y-%m-%d')
        datetime.datetime.strptime(return_date, '%Y-%m-%d')

        flight_data = [
            FlightData(date=departure_date, from_airport=origin, to_airport=destination),
            FlightData(date=return_date, from_airport=destination, to_airport=origin),
        ]
        passengers_info = Passengers(adults=adults)

        result = get_flights(
            flight_data=flight_data,
            trip="round-trip",
            seat=seat_type,
            passengers=passengers_info,
        )

        # Filter by number of stops if provided
        flights_list = result.flights if result and result.flights else []
        if stops is not None:
            flights_list = [f for f in flights_list if getattr(f, "stops", None) == stops]

        if sort_cheapest:
            flights_list = sorted(flights_list, key=lambda f: parse_price(f.price))
        processed_flights = [flight_to_dict(f) for f in flights_list[:limit]]
        output_data = {"round_trip_options": processed_flights}
        if flights_list:
            return json.dumps(output_data, indent=2)
        else:
             return json.dumps({
                "message": f"No round trip flights found for {origin} <-> {destination} from {departure_date} to {return_date}."
            })

    except ValueError as e:
         # Return structured error
         error_payload = {"error": {"message": f"Invalid date format provided. Use YYYY-MM-DD.", "type": "ValueError"}}
         return json.dumps(error_payload)
    except Exception as e:
        print(f"MCP Tool Error in get_round_trip_flights: {e}", file=sys.stderr)
        # Return structured error
        error_payload = {"error": {"message": f"An unexpected error occurred.", "type": type(e).__name__}}
        return json.dumps(error_payload)


@mcp.tool(name="find_all_flights_in_range") # Renamed tool
async def find_all_flights_in_range( # Renamed function
    origin: str,
    destination: str,
    start_date_str: str,
    end_date_str: str,
    min_stay_days: Optional[int] = None,
    max_stay_days: Optional[int] = None,
    adults: int = 1,
    seat_type: str = "economy",
    sort_cheapest: bool = False,
    stops: Optional[int] = None,
    limit: Optional[int] = 10
) -> str:
    """
    Finds available round-trip flights within a specified date range.
    Optionally sorts by cheapest price for each date pair.

    Args:
        origin: Origin airport code (e.g., "DEN").
        destination: Destination airport code (e.g., "LAX").
        start_date_str: Start date of the search range (YYYY-MM-DD format).
        end_date_str: End date of the search range (YYYY-MM-DD format).
        min_stay_days: Minimum number of days for the stay (optional).
        max_stay_days: Maximum number of days for the stay (optional).
        adults: Number of adult passengers (default: 1).
        seat_type: Fare class (e.g., "economy", "business", default: "economy").
        sort_cheapest: If True, results are sorted by price ascending for each date pair (default: False).
        stops: Number of stops to filter (e.g., 0 for non-stop). If None, no stop filtering is applied (default: None).
        limit: Maximum number of flights to return per date pair (default: 10).

    Example Args:
        {"origin": "JFK", "destination": "MIA", "start_date_str": "2025-09-10", "end_date_str": "2025-09-20", "min_stay_days": 5}
        {"origin": "JFK", "destination": "MIA", "start_date_str": "2025-09-10", "end_date_str": "2025-09-20", "min_stay_days": 5, "sort_cheapest": true}
    """
    # Adjust print message based on mode
    search_mode = "sorted by cheapest" if sort_cheapest else "all flights"
    print(f"MCP Tool: Finding {search_mode} {origin}<->{destination} between {start_date_str} and {end_date_str}...", file=sys.stderr)

    # Initialize list to store results based on mode
    results_data = []
    error_messages = []

    try:
        start_date = datetime.datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.datetime.strptime(end_date_str, '%Y-%m-%d').date()
    except ValueError as e:
        # Return structured error
        error_payload = {"error": {"message": f"Invalid date format. Use YYYY-MM-DD.", "type": "ValueError"}}
        return json.dumps(error_payload)

    if start_date > end_date:
        # Return structured error
        error_payload = {"error": {"message": "Start date cannot be after end date.", "type": "ValueError"}}
        return json.dumps(error_payload)

    date_list = []
    current_date = start_date
    while current_date <= end_date:
        date_list.append(current_date)
        current_date += datetime.timedelta(days=1)

    if not date_list:
         return json.dumps({"error": "No valid dates in the specified range."})

    total_combinations = 0
    date_pairs_to_check = []
    for i, depart_date in enumerate(date_list):
        for j, return_date in enumerate(date_list[i:]):
            stay_duration = (return_date - depart_date).days
            valid_stay = True
            if min_stay_days is not None and stay_duration < min_stay_days:
                valid_stay = False
            if max_stay_days is not None and stay_duration > max_stay_days:
                valid_stay = False

            if valid_stay:
                total_combinations += 1
                date_pairs_to_check.append((depart_date, return_date))

    print(f"MCP Tool: Checking {total_combinations} valid date combinations in range...", file=sys.stderr)
    count = 0

    for depart_date, return_date in date_pairs_to_check:
        count += 1
        if count % 10 == 0: # Log progress
            print(f"MCP Tool Progress: Checking {depart_date.strftime('%Y-%m-%d')} -> {return_date.strftime('%Y-%m-%d')} ({count}/{total_combinations})", file=sys.stderr)

        try:
            flight_data = [
                FlightData(date=depart_date.strftime('%Y-%m-%d'), from_airport=origin, to_airport=destination),
                FlightData(date=return_date.strftime('%Y-%m-%d'), from_airport=destination, to_airport=origin),
            ]
            passengers_info = Passengers(adults=adults)

            result = get_flights(
                flight_data=flight_data,
                trip="round-trip",
                seat=seat_type,
                passengers=passengers_info,
            )

            # Filter by number of stops if provided
            flights_list = result.flights if result and result.flights else []
            if stops is not None:
                flights_list = [f for f in flights_list if getattr(f, "stops", None) == stops]

            if sort_cheapest:
                flights_list = sorted(flights_list, key=lambda f: parse_price(f.price))
            processed_flights = [flight_to_dict(f) for f in flights_list[:limit]]
            results_data.append({
                "departure_date": depart_date.strftime('%Y-%m-%d'),
                "return_date": return_date.strftime('%Y-%m-%d'),
                "flights": processed_flights
            })

        except Exception as e:
            # Log the specific error message to stderr for better debugging
            print(f"MCP Tool Error fetching for {depart_date.strftime('%Y-%m-%d')} -> {return_date.strftime('%Y-%m-%d')}: {type(e).__name__} - {str(e)}", file=sys.stderr)
            # Add a slightly more informative message to the results
            err_msg = f"Error fetching flights for {depart_date.strftime('%Y-%m-%d')} -> {return_date.strftime('%Y-%m-%d')}: {type(e).__name__}. Check server logs for details: {str(e)[:100]}..." # Include first 100 chars of error
            if err_msg not in error_messages:
                 error_messages.append(err_msg)

    print("MCP Tool: Range search complete.", file=sys.stderr)

    # Return collected flight data
    if results_data or error_messages: # Return even if only errors were found
        output_data = {
            "all_round_trip_options": results_data,
            "errors_encountered": error_messages if error_messages else None
        }
        return json.dumps(output_data, indent=2)
    else:
        # This case should ideally not be reached if the loop runs and finds nothing,
        # but kept as a fallback.
        return json.dumps({
            "message": f"No flights found and no errors encountered for {origin} -> {destination} in the range {start_date_str} to {end_date_str}.",
            "errors_encountered": error_messages if error_messages else None
        })

# --- Run the server ---
if __name__ == "__main__":
    # Run the server using stdio transport
    mcp.run(transport='stdio')
