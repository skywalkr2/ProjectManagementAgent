"""Extract bounded reservation records from embedded structured mail markup."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from html.parser import HTMLParser
from urllib.parse import urlsplit

type When = date | datetime

#: Elements nested deeper than this are read as flat, so hostile markup cannot exhaust the stack.
MAX_DEPTH = 200


@dataclass(frozen=True)
class Place:
    name: str | None
    address: str | None


@dataclass(frozen=True)
class Booking:
    kind: str
    start: When | None
    end: When | None
    time_zone: str | None
    end_time_zone: str | None
    place: Place | None
    destination: Place | None
    confirmation_code: str | None
    provider: str | None
    source: str


@dataclass(frozen=True)
class Issue:
    source: str
    field: str
    note: str


@dataclass(frozen=True)
class BookingRead:
    bookings: tuple[Booking, ...]
    issues: tuple[Issue, ...]


@dataclass
class _Node:
    tag: str
    attrs: dict[str, str]
    children: list[_Node] = field(default_factory=list)
    text: list[str] = field(default_factory=list)


def _term(value: str) -> str:
    if value.startswith("schema:"):
        return value[7:]
    if "://" in value:
        try:
            parsed = urlsplit(value)
            return parsed.path.rstrip("/").rsplit("/", 1)[-1] if parsed.hostname == "schema.org" else ""
        except ValueError:
            return ""
    return value


def read_bookings(html: str) -> BookingRead:
    """Extract six reservation types using HTMLParser and the JSON decoder.

    No network, files, current clock, inferred time zone, or natural-language
    parsing is used. Offset-free DATE-TIME values stay naive. Missing start,
    end, place, provider and code are individually reported, with partial data
    retained. Results from distinct blocks are not silently merged or deduplicated.
    Local @id references are resolved only inside their own JSON-LD block.
    """
    issues = []
    bookings = []

    def report(source: str, name: str, note: str) -> None:
        issues.append(Issue(source, name, note))

    class Parser(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.root = _Node("root", {})
            self.stack = [self.root]
            self.too_deep = False

        def handle_starttag(self, tag, attrs):
            node = _Node(tag, {key: value or "" for key, value in attrs})
            self.stack[-1].children.append(node)
            if len(self.stack) > MAX_DEPTH:
                if not self.too_deep:
                    self.too_deep = True
                    report("html", tag, "Markup nested too deeply; deeper elements were read as flat.")
                return
            if tag not in {
                "area",
                "base",
                "br",
                "col",
                "embed",
                "hr",
                "img",
                "input",
                "link",
                "meta",
                "param",
                "source",
                "track",
                "wbr",
            }:
                self.stack.append(node)

        def handle_startendtag(self, tag, attrs):
            self.handle_starttag(tag, attrs)
            if self.stack[-1].tag == tag:
                self.stack.pop()

        def handle_endtag(self, tag):
            for index in range(len(self.stack) - 1, 0, -1):
                if self.stack[index].tag == tag:
                    for node in self.stack[index + 1 :]:
                        if "itemscope" in node.attrs or node.tag == "script":
                            report("html", node.tag, "Structured element closed out of order; data may be partial.")
                    del self.stack[index:]
                    return

        def handle_data(self, data):
            for node in self.stack:
                node.text.append(data)

    parser = Parser()
    try:
        parser.feed(html)
        parser.close()
    except (ValueError, RecursionError) as error:
        report("html", "markup", f"Malformed markup: {type(error).__name__}.")
    for node in parser.stack[1:]:
        if "itemscope" in node.attrs or node.tag == "script":
            report("html", node.tag, "Unclosed structured element; data may be partial.")

    kinds = {
        "FlightReservation": ("flight", "departureTime", "arrivalTime", "departureAirport", "arrivalAirport"),
        "LodgingReservation": ("lodging", "checkinTime", "checkoutTime", None, None),
        "EventReservation": ("event", "startDate", "endDate", "location", None),
        "FoodEstablishmentReservation": ("restaurant", "startTime", "endTime", None, None),
        "RentalCarReservation": ("rental_car", "pickupTime", "dropoffTime", "pickupLocation", "dropoffLocation"),
        "TrainReservation": ("train", "departureTime", "arrivalTime", "departureStation", "arrivalStation"),
    }

    def one(node: dict, name: str, source: str):
        value = node.get(name)
        if isinstance(value, list):
            if len(value) != 1:
                report(source, name, "Multiple values; no value was selected.")
                return None
            return value[0]
        return value

    def scalar(value, source: str, name: str) -> str | None:
        if value is None:
            return None
        if isinstance(value, str) and value.strip():
            return value.strip()
        report(source, name, "Expected nonempty text.")
        return None

    def named(value, source: str, name: str) -> str | None:
        if isinstance(value, dict):
            return scalar(one(value, "name", source), source, name)
        return scalar(value, source, name)

    def place(value, source: str, name: str) -> Place | None:
        if value is None:
            return None
        if isinstance(value, str):
            return Place(scalar(value, source, name), None)
        if not isinstance(value, dict):
            report(source, name, "Expected a structured place or text.")
            return None
        label = scalar(one(value, "name", source), source, name + ".name")
        address = one(value, "address", source)
        if isinstance(address, dict):
            parts = []
            for part in ("streetAddress", "addressLocality", "addressRegion", "postalCode", "addressCountry"):
                component = one(address, part, source)
                if part == "addressCountry" and isinstance(component, dict):
                    component = one(component, "name", source)
                if text := scalar(component, source, name + ".address." + part):
                    parts.append(text)
            address = ", ".join(parts) or None
        else:
            address = scalar(address, source, name + ".address")
        if label is None and address is None:
            report(source, name, "Place has no name or address.")
            return None
        return Place(label, address)

    def when(value, source: str, name: str) -> When | None:
        text = scalar(value, source, name)
        if text is None:
            return None
        try:
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
                return date.fromisoformat(text)
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})?", text):
                raise ValueError
            result = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if result.tzinfo is None:
                report(source, name, "No offset supplied; local wall time retained without an inferred zone.")
            return result
        except ValueError:
            report(source, name, "Malformed or unsupported date/time; no value was inferred.")
            return None

    def extract(node: dict, source: str) -> None:
        raw_types = node.get("@type", [])
        types = raw_types if isinstance(raw_types, list) else [raw_types]
        supported = [value for value in types if isinstance(value, str) and value in kinds]
        if len(supported) > 1:
            report(source, "@type", "Conflicting reservation types; block not extracted.")
            return
        if not supported:
            if any(isinstance(value, str) and value.endswith("Reservation") for value in types):
                report(source, "@type", "Unsupported reservation type; no type was inferred.")
            return
        kind, start_name, end_name, place_name, destination_name = kinds[supported[0]]
        reserved = one(node, "reservationFor", source)
        if not isinstance(reserved, dict):
            report(source, "reservationFor", "Missing or unresolved reserved item.")
            reserved = {}
        owner = node if kind in {"lodging", "restaurant", "rental_car"} else reserved
        start = when(one(owner, start_name, source), source, start_name)
        end = when(one(owner, end_name, source), source, end_name)
        if place_name:
            main_place = place(one(owner, place_name, source), source, place_name)
        else:
            main_place = place(reserved, source, "place")
        destination = (
            place(one(owner, destination_name, source), source, destination_name) if destination_name else None
        )
        if destination_name and destination is None:
            report(source, destination_name, "Missing or unusable destination; partial reservation retained.")
        provider_value = one(node, "provider", source)
        if provider_value is None:
            provider_value = one(reserved, "provider", source)
        if provider_value is None and kind == "flight":
            provider_value = one(reserved, "airline", source)
        provider = named(provider_value, source, "provider")
        code = scalar(one(node, "reservationId", source), source, "reservationId")
        start_zone = scalar(one(owner, "timeZone", source), source, "timeZone")
        end_zone = scalar(one(owner, "endTimeZone", source), source, "endTimeZone")
        schedule = one(owner, "eventSchedule", source)
        if start_zone is None and isinstance(schedule, dict):
            start_zone = scalar(one(schedule, "scheduleTimezone", source), source, "scheduleTimezone")
        if isinstance(start, datetime) and start.tzinfo is not None:
            start_zone = start_zone or start.isoformat()[-6:]
        if isinstance(end, datetime) and end.tzinfo is not None:
            end_zone = end_zone or end.isoformat()[-6:]
        if start is not None and end is not None:
            compatible = isinstance(start, datetime) == isinstance(end, datetime)
            if isinstance(start, datetime) and isinstance(end, datetime):
                compatible = compatible and (start.tzinfo is None) == (end.tzinfo is None)
            if not compatible:
                report(
                    source, "end", "Start and end have incompatible date/time types; end retained without comparison."
                )
            elif end < start:
                report(source, "end", "End precedes start; supplied values retained without correction.")
        for name, value in (
            ("start", start),
            ("end", end),
            ("place", main_place),
            ("provider", provider),
            ("confirmation_code", code),
        ):
            if value is None:
                report(source, name, "Missing or unusable value; partial reservation retained.")
        bookings.append(
            Booking(kind, start, end, start_zone, end_zone, main_place, destination, code, provider, source)
        )

    def walk(node: _Node):
        pending = [node]
        while pending:
            current = pending.pop()
            yield current
            pending.extend(reversed(current.children))

    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON property")
            result[key] = value
        return result

    def json_nodes(value):
        if isinstance(value, dict):
            yield value
            for key, child in value.items():
                if key != "@context":
                    yield from json_nodes(child)
        elif isinstance(value, list):
            for child in value:
                yield from json_nodes(child)

    def microdata(node: _Node, source: str) -> dict:
        result = {"@type": [_term(value) for value in node.attrs.get("itemtype", "").split()]}
        if "itemref" in node.attrs:
            report(source, "itemref", "External microdata references are unsupported; block may be partial.")

        def collect(child: _Node) -> None:
            properties = child.attrs.get("itemprop", "").split()
            if "itemscope" in child.attrs:
                if properties:
                    value = microdata(child, source)
                else:
                    return
            else:
                attribute = {
                    "meta": "content",
                    "time": "datetime",
                    "data": "value",
                    "a": "href",
                    "link": "href",
                    "img": "src",
                }.get(child.tag)
                value = (
                    child.attrs.get(attribute, "".join(child.text).strip())
                    if attribute
                    else "".join(child.text).strip()
                )
            for prop in properties:
                prop = _term(prop)
                if prop in result:
                    previous = result[prop]
                    result[prop] = previous + [value] if isinstance(previous, list) else [previous, value]
                else:
                    result[prop] = value
            if "itemscope" not in child.attrs:
                for descendant in child.children:
                    collect(descendant)

        for child in node.children:
            collect(child)
        return result

    for index, element in enumerate(walk(parser.root)):
        source = f"element-{index}"
        if (
            element.tag == "script"
            and element.attrs.get("type", "").split(";", 1)[0].strip().lower() == "application/ld+json"
        ):
            try:
                value = json.loads(
                    "".join(element.text),
                    object_pairs_hook=unique_pairs,
                    parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Invalid JSON constant")),
                )
            except (ValueError, RecursionError):
                report(source, "json", "Malformed JSON-LD block; not extracted.")
                continue
            if not isinstance(value, (dict, list)):
                report(source, "json", "JSON-LD must contain an object or array.")
                continue
            try:
                nodes = list(json_nodes(value))
            except RecursionError:
                report(source, "json", "Structured nesting is too deep; block not extracted.")
                continue
            contexts = [node["@context"] for node in nodes if "@context" in node]
            valid_context = True
            for context in contexts:
                if isinstance(context, str):
                    candidates = [context]
                elif isinstance(context, dict) and set(context) <= {"@vocab", "schema"}:
                    candidates = list(context.values())
                else:
                    valid_context = False
                    break
                for candidate in candidates:
                    try:
                        if not isinstance(candidate, str) or not (
                            candidate == "schema:" or urlsplit(candidate).hostname == "schema.org"
                        ):
                            valid_context = False
                    except ValueError:
                        valid_context = False
            if not valid_context:
                report(source, "@context", "Unsupported context or aliases; no schema vocabulary was inferred.")
                continue
            identifiers = {}
            for node in nodes:
                if isinstance(node.get("@id"), str) and len(node) > 1:
                    identifier = node["@id"]
                    if identifier in identifiers and identifiers[identifier] != node:
                        report(source, "@id", "Conflicting definitions for an identifier.")
                        identifiers[identifier] = None
                    else:
                        identifiers[identifier] = node

            def expanded(value, trail=frozenset(), identifiers=identifiers, source=source):
                if isinstance(value, list):
                    return [expanded(item, trail) for item in value]
                if not isinstance(value, dict):
                    return value
                if set(value) == {"@id"}:
                    identifier = value["@id"]
                    target = identifiers.get(identifier)
                    if target is None or identifier in trail:
                        report(source, "@id", "Unresolved or cyclic reference; no value inferred.")
                        return None
                    return expanded(target, trail | {identifier})
                result = {}
                for key, item in value.items():
                    if key == "@context":
                        continue
                    if key == "@type":
                        result[key] = (
                            [_term(part) for part in item]
                            if isinstance(item, list)
                            else _term(item)
                            if isinstance(item, str)
                            else None
                        )
                    else:
                        result[_term(key) if not key.startswith("@") else key] = expanded(item, trail)
                return result

            for node in nodes:
                if "@type" in node:
                    try:
                        extract(expanded(node), source)
                    except (ValueError, TypeError, AttributeError, RecursionError):
                        report(source, "structure", "Malformed structured fields; block could not be fully extracted.")
        if "itemscope" in element.attrs:
            types = [_term(value) for value in element.attrs.get("itemtype", "").split()]
            if any(value in kinds or value.endswith("Reservation") for value in types):
                extract(microdata(element, source), source)
    return BookingRead(tuple(bookings), tuple(issues))
