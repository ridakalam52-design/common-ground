"""Hand-written demo catalog for mock mode.

This is NOT Qloo data. Every entity, tag, score, and ID below was written by
hand (IDs are uuid5 hashes of the names) so the app can be built, tested, and
demoed before a Qloo key exists. The UI labels everything from here as
"demo data". Real Qloo responses are never stored in this repository.
"""
from __future__ import annotations

import uuid

_NS = uuid.UUID("5f0c3a52-8f43-4c4e-9a43-0c0ffee00000")


def mock_id(name: str) -> str:
    return str(uuid.uuid5(_NS, name.lower())).upper()


# Tags: short key -> (tag id, display name). Cross-domain "vibe" tags make the
# compare endpoint produce overlaps between, say, a film fan and a music fan.
TAGS: dict[str, tuple[str, str]] = {
    "feelgood": ("urn:tag:keyword:media:feel_good", "Feel-Good"),
    "friendship": ("urn:tag:keyword:media:friendship", "Friendship"),
    "roadtrip": ("urn:tag:keyword:media:road_trip", "Road Trip"),
    "comingofage": ("urn:tag:keyword:media:coming_of_age", "Coming Of Age"),
    "romance": ("urn:tag:genre:media:romance", "Romance"),
    "comedy": ("urn:tag:genre:media:comedy", "Comedy"),
    "drama": ("urn:tag:genre:media:drama", "Drama"),
    "scifi": ("urn:tag:genre:media:science_fiction", "Science Fiction"),
    "smalltown": ("urn:tag:keyword:media:small_town", "Small Town Life"),
    "underdog": ("urn:tag:keyword:media:underdog", "Underdog"),
    "music_story": ("urn:tag:keyword:media:music", "Music"),
    "hiphop": ("urn:tag:genre:music:hip_hop", "Hip Hop"),
    "indie": ("urn:tag:genre:music:indie", "Indie"),
    "indiepop": ("urn:tag:genre:music:indie_pop", "Indie Pop"),
    "acoustic": ("urn:tag:genre:music:singer_songwriter", "Singer-Songwriter"),
    "bollywood": ("urn:tag:genre:music:filmi", "Filmi"),
    "electronic": ("urn:tag:genre:music:electronic", "Electronic"),
    "rock": ("urn:tag:genre:music:alternative_rock", "Alternative Rock"),
    "melancholic": ("urn:tag:keyword:media:melancholy", "Melancholy"),
    "nostalgia": ("urn:tag:keyword:media:nostalgia", "Nostalgia"),
    "urban": ("urn:tag:keyword:media:urban_life", "Urban Life"),
    "epic": ("urn:tag:keyword:media:epic", "Epic"),
    "family": ("urn:tag:keyword:media:family_relationships", "Family Relationships"),
    "satire": ("urn:tag:keyword:media:satire", "Satire"),
    "northindian": ("urn:tag:genre:place:restaurant:north_indian", "North Indian Restaurant"),
    "mughlai": ("urn:tag:genre:place:restaurant:mughlai", "Mughlai Restaurant"),
    "modernindian": ("urn:tag:genre:place:restaurant:modern_indian", "Modern Indian Restaurant"),
    "cafe": ("urn:tag:genre:place:cafe", "Cafe"),
    "southindian": ("urn:tag:genre:place:restaurant:south_indian", "South Indian Restaurant"),
    "italian": ("urn:tag:genre:place:restaurant:italian", "Italian Restaurant"),
    "bar": ("urn:tag:genre:place:bar", "Bar"),
    "livemusic": ("urn:tag:amenity:place:live_music", "Live Music"),
    "streetfood": ("urn:tag:keyword:place:street_food", "Street Food"),
    "cozy": ("urn:tag:style:place:cozy", "Cozy"),
    "trendy": ("urn:tag:style:place:trendy", "Trendy"),
    "restaurant": ("urn:tag:genre:place:restaurant", "Restaurant"),
}

# (name, subtype, popularity, tag keys, short description, extra)
_MOVIES = [
    ("Zindagi Na Milegi Dobara", 0.94, ["roadtrip", "friendship", "feelgood", "comingofage", "comedy"], "2011 film directed by Zoya Akhtar", 2011),
    ("Dil Chahta Hai", 0.91, ["friendship", "comingofage", "romance", "comedy", "urban"], "2001 film directed by Farhan Akhtar", 2001),
    ("Gully Boy", 0.93, ["hiphop", "underdog", "music_story", "urban", "drama"], "2019 film directed by Zoya Akhtar", 2019),
    ("3 Idiots", 0.97, ["friendship", "comedy", "comingofage", "feelgood", "satire"], "2009 film directed by Rajkumar Hirani", 2009),
    ("The Lunchbox", 0.86, ["romance", "melancholic", "urban", "drama"], "2013 film directed by Ritesh Batra", 2013),
    ("Interstellar", 0.98, ["scifi", "epic", "family", "drama"], "2014 film directed by Christopher Nolan", 2014),
    ("Rocket Singh: Salesman of the Year", 0.78, ["underdog", "comedy", "urban", "satire"], "2009 film directed by Shimit Amin", 2009),
    ("Wake Up Sid", 0.84, ["comingofage", "urban", "romance", "feelgood"], "2009 film directed by Ayan Mukerji", 2009),
    ("Yeh Jawaani Hai Deewani", 0.92, ["friendship", "roadtrip", "romance", "feelgood"], "2013 film directed by Ayan Mukerji", 2013),
    ("Rockstar", 0.89, ["music_story", "melancholic", "romance", "drama"], "2011 film directed by Imtiaz Ali", 2011),
    ("Tamasha", 0.83, ["comingofage", "romance", "melancholic", "roadtrip"], "2015 film directed by Imtiaz Ali", 2015),
    ("Kapoor & Sons", 0.85, ["family", "drama", "comedy", "nostalgia"], "2016 film directed by Shakun Batra", 2016),
    ("Piku", 0.82, ["family", "roadtrip", "comedy", "feelgood"], "2015 film directed by Shoojit Sircar", 2015),
    ("Everything Everywhere All at Once", 0.95, ["scifi", "family", "comedy", "epic"], "2022 film directed by the Daniels", 2022),
    ("La La Land", 0.96, ["music_story", "romance", "melancholic", "urban"], "2016 film directed by Damien Chazelle", 2016),
    ("Laapataa Ladies", 0.87, ["smalltown", "comedy", "satire", "feelgood"], "2024 film directed by Kiran Rao", 2024),
    ("Swades", 0.86, ["smalltown", "drama", "family", "nostalgia"], "2004 film directed by Ashutosh Gowariker", 2004),
    ("12th Fail", 0.9, ["underdog", "smalltown", "drama", "comingofage"], "2023 film directed by Vidhu Vinod Chopra", 2023),
]
_TV = [
    ("Panchayat", 0.93, ["smalltown", "comedy", "feelgood", "satire"], "Indian comedy-drama web series", 2020),
    ("Kota Factory", 0.88, ["comingofage", "underdog", "drama", "smalltown"], "Indian drama web series", 2019),
    ("Made in Heaven", 0.84, ["urban", "drama", "romance", "satire"], "Indian drama web series", 2019),
    ("Little Things", 0.8, ["romance", "urban", "feelgood", "comingofage"], "Indian romantic web series", 2016),
]
_ARTISTS = [
    ("Prateek Kuhad", 0.9, ["acoustic", "indiepop", "romance", "melancholic"], "Indian singer-songwriter"),
    ("Ritviz", 0.86, ["electronic", "indiepop", "feelgood", "urban"], "Indian electronic producer"),
    ("Arijit Singh", 0.98, ["bollywood", "romance", "melancholic", "acoustic"], "Indian playback singer"),
    ("AP Dhillon", 0.92, ["hiphop", "urban", "romance"], "Indo-Canadian singer and rapper"),
    ("The Local Train", 0.82, ["rock", "indie", "nostalgia", "comingofage"], "Indian rock band from Delhi"),
    ("When Chai Met Toast", 0.78, ["indiepop", "feelgood", "acoustic", "roadtrip"], "Indian indie folk-pop band"),
    ("Lifafa", 0.7, ["electronic", "indie", "nostalgia", "urban"], "Delhi-based electronic artist"),
    ("Anuv Jain", 0.88, ["acoustic", "indiepop", "romance", "melancholic"], "Indian singer-songwriter"),
    ("Coldplay", 0.99, ["rock", "indiepop", "epic", "feelgood"], "British rock band"),
    ("Lucky Ali", 0.84, ["acoustic", "nostalgia", "roadtrip", "feelgood"], "Indian singer-songwriter"),
    ("Nucleya", 0.83, ["electronic", "urban", "hiphop"], "Indian electronic producer"),
    ("Seedhe Maut", 0.8, ["hiphop", "urban", "underdog"], "Delhi hip hop duo"),
    ("DIVINE", 0.87, ["hiphop", "urban", "underdog", "music_story"], "Mumbai rapper"),
    ("Shankar-Ehsaan-Loy", 0.89, ["bollywood", "friendship", "feelgood", "roadtrip"], "Indian composer trio"),
    ("A. R. Rahman", 0.97, ["bollywood", "epic", "romance", "music_story"], "Indian composer"),
    ("Hans Zimmer", 0.95, ["epic", "scifi", "electronic"], "German film composer"),
    ("Taba Chake", 0.68, ["acoustic", "indiepop", "feelgood", "smalltown"], "Indian singer-songwriter from Arunachal"),
]
_BOOKS = [
    ("The White Tiger", 0.85, ["satire", "urban", "underdog", "drama"], "2008 novel by Aravind Adiga"),
    ("Five Point Someone", 0.8, ["friendship", "comedy", "comingofage"], "2004 novel by Chetan Bhagat"),
    ("A Suitable Boy", 0.82, ["family", "romance", "drama", "nostalgia"], "1993 novel by Vikram Seth"),
    ("Project Hail Mary", 0.9, ["scifi", "friendship", "epic"], "2021 novel by Andy Weir"),
]
# Places by metro: (name, popularity, tags, address, price_level, business_rating)
_PLACES = {
    "delhi": [
        ("Indian Accent", 0.97, ["modernindian", "restaurant", "trendy"], "The Lodhi, Lodhi Road, New Delhi", 4, 4.7),
        ("Bukhara", 0.95, ["northindian", "restaurant", "nostalgia"], "ITC Maurya, Chanakyapuri, New Delhi", 4, 4.6),
        ("Karim's", 0.93, ["mughlai", "restaurant", "streetfood", "nostalgia"], "Gali Kababian, Jama Masjid, Old Delhi", 1, 4.3),
        ("Big Chill Cafe", 0.9, ["cafe", "italian", "cozy", "feelgood"], "Khan Market, New Delhi", 2, 4.5),
        ("Comorin", 0.88, ["modernindian", "bar", "trendy", "urban"], "Two Horizon Center, Gurugram", 3, 4.6),
        ("Perch Wine & Coffee Bar", 0.84, ["cafe", "bar", "cozy"], "Khan Market, New Delhi", 3, 4.4),
        ("Saravana Bhavan", 0.86, ["southindian", "restaurant", "family"], "Connaught Place, New Delhi", 1, 4.2),
        ("Hauz Khas Social", 0.89, ["bar", "livemusic", "trendy", "urban", "friendship"], "Hauz Khas Village, New Delhi", 2, 4.3),
        ("Diggin", 0.85, ["cafe", "italian", "cozy", "romance"], "Anand Lok, Chanakyapuri, New Delhi", 2, 4.4),
        ("Olive Bar & Kitchen", 0.87, ["italian", "bar", "romance", "trendy"], "One Style Mile, Mehrauli, New Delhi", 4, 4.5),
        ("Piano Man Jazz Club", 0.8, ["bar", "livemusic", "music_story", "melancholic"], "Safdarjung Enclave, New Delhi", 3, 4.6),
        ("Depot48", 0.78, ["bar", "livemusic", "indie", "cozy"], "Greater Kailash II, New Delhi", 2, 4.3),
        ("Chandni Chowk Paranthe Wali Gali", 0.82, ["streetfood", "northindian", "nostalgia", "smalltown"], "Chandni Chowk, Old Delhi", 1, 4.1),
        ("Kake Di Hatti", 0.79, ["northindian", "streetfood", "family"], "Chandni Chowk, Old Delhi", 1, 4.1),
    ],
    "mumbai": [
        ("The Bombay Canteen", 0.95, ["modernindian", "restaurant", "trendy", "nostalgia"], "Lower Parel, Mumbai", 3, 4.6),
        ("Leopold Cafe", 0.9, ["cafe", "bar", "nostalgia", "urban"], "Colaba Causeway, Mumbai", 2, 4.2),
        ("Britannia & Co.", 0.88, ["restaurant", "family", "nostalgia"], "Ballard Estate, Fort, Mumbai", 2, 4.5),
        ("Bastian", 0.86, ["restaurant", "trendy", "bar"], "Worli, Mumbai", 4, 4.4),
        ("Blue Frog", 0.8, ["bar", "livemusic", "indie", "urban"], "Lower Parel, Mumbai", 3, 4.2),
        ("Swati Snacks", 0.84, ["streetfood", "restaurant", "family"], "Tardeo, Mumbai", 1, 4.5),
    ],
    "bengaluru": [
        ("Toit", 0.93, ["bar", "friendship", "trendy", "urban"], "Indiranagar, Bengaluru", 2, 4.6),
        ("Mavalli Tiffin Rooms", 0.9, ["southindian", "restaurant", "nostalgia", "family"], "Lalbagh Road, Bengaluru", 1, 4.5),
        ("Vidyarthi Bhavan", 0.88, ["southindian", "restaurant", "nostalgia"], "Basavanagudi, Bengaluru", 1, 4.6),
        ("Hard Rock Cafe Bengaluru", 0.82, ["bar", "livemusic", "rock"], "St. Marks Road, Bengaluru", 3, 4.3),
        ("Third Wave Coffee", 0.8, ["cafe", "cozy", "urban"], "Koramangala, Bengaluru", 2, 4.4),
    ],
}
CITY_ALIASES = {
    "delhi": "delhi", "new delhi": "delhi", "delhi ncr": "delhi", "ncr": "delhi", "gurugram": "delhi",
    "gurgaon": "delhi", "noida": "delhi", "mumbai": "mumbai", "bombay": "mumbai",
    "bengaluru": "bengaluru", "bangalore": "bengaluru",
}
CITY_DISAMBIGUATION = {
    "delhi": "New Delhi, Delhi, India",
    "mumbai": "Mumbai, Maharashtra, India",
    "bengaluru": "Bengaluru, Karnataka, India",
}


def _entity(name: str, subtype: str, popularity: float, tag_keys: list[str], desc: str, **props) -> dict:
    tags = [{"id": TAGS[k][0], "name": TAGS[k][1], "type": TAGS[k][0].rsplit(":", 1)[0]} for k in tag_keys]
    return {
        "entity_id": mock_id(name),
        "name": name,
        "subtype": subtype,
        "types": [subtype],
        "popularity": popularity,
        "tags": tags,
        "properties": {"short_descriptions": [{"value": desc, "languages": ["en"]}], **props},
    }


def build_catalog() -> list[dict]:
    cat: list[dict] = []
    for n, p, t, d, y in _MOVIES:
        cat.append(_entity(n, "urn:entity:movie", p, t, d, release_year=y))
    for n, p, t, d, y in _TV:
        cat.append(_entity(n, "urn:entity:tv_show", p, t, d, release_year=y))
    for n, p, t, d in _ARTISTS:
        cat.append(_entity(n, "urn:entity:artist", p, t, d))
    for n, p, t, d in _BOOKS:
        cat.append(_entity(n, "urn:entity:book", p, t, d))
    for city, rows in _PLACES.items():
        for n, p, t, addr, price, rating in rows:
            e = _entity(n, "urn:entity:place", p, t, f"Place in {CITY_DISAMBIGUATION[city]}",
                        address=addr, price_level=price, business_rating=rating)
            e["_city"] = city
            cat.append(e)
    return cat


CATALOG = build_catalog()
