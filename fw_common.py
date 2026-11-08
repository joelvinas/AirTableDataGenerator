"""Shared constants and deterministic helpers (standard library only)."""
import hashlib
import random
import string

DEFAULT_SEED = 20261108
B62 = string.digits + string.ascii_letters

STYLES = ["Modern Fit", "Luxury Outerwear", "Italian Cut", "Classic Business", "Black Tie",
          "Casual Luxury", "Heritage Wool", "Smart Casual", "Bespoke Tailoring", "Silk Formalwear"]

FIRST = ["Arthur", "Beatrice", "Cormac", "Delphine", "Evander", "Fiona", "Gideon", "Helena", "Ignatius",
         "Josephine", "Kasimir", "Linnea", "Magnus", "Nadia", "Orson", "Philippa", "Quentin", "Rosalind",
         "Silas", "Tamsin", "Ulrich", "Vivienne", "Wendell", "Xenia", "Yorick", "Zelda", "Alaric", "Brielle",
         "Caspian", "Daphne", "Elias", "Freya", "Gareth", "Honora", "Ilsa", "Jasper", "Kiera", "Lucian",
         "Marguerite", "Nolan", "Odette", "Percival", "Rhea", "Soren", "Thea", "Ulysse", "Valentina", "Wolfgang",
         "Ximena", "Yvette", "Zane", "Amara", "Bastian", "Celeste", "Dorian", "Esme", "Florian", "Greta",
         "Hugo", "Isolde"]
LAST = ["Ashcombe", "Blackwell", "Carrington", "Davenport", "Ellsworth", "Fairbanks", "Goldsmith", "Hartley",
        "Ingram", "Jessup", "Kingsbury", "Lockhart", "Montague", "Northcott", "Oakhurst", "Pemberton",
        "Quillfeather", "Radcliffe", "Stanhope", "Thackeray", "Underhill", "Vanterpool", "Whitlock", "Yarborough",
        "Zimmerman", "Abernathy", "Brightwater", "Calloway", "Draycott", "Everhart", "Fotheringay", "Grantham",
        "Hawthorne", "Islington", "Jarrow", "Kettleridge", "Langford", "Merriweather", "Nightingale", "Ormsby",
        "Prescott", "Rosewood", "Sinclair-Voss", "Tennyson", "Upton", "Villiers", "Wetherby", "Yeoman",
        "Zeller", "Aldridge", "Beaumaris", "Crowhurst", "Dunmore", "Eastwick", "Finchley", "Gallowglass",
        "Holloway", "Ironside", "Jessamine", "Kirkwall"]
CITIES = [("New York", "5th Ave & 57th St"), ("Beverly Hills", "Rodeo Dr & Wilshire Blvd"),
          ("Portland", "NW 23rd Ave & Lovejoy St"), ("Charlotte", "SouthPark Mall"), ("Tampa", "International Plaza"),
          ("Salt Lake City", "City Creek Center"), ("Kansas City", "Country Club Plaza"), ("St. Louis", "Plaza Frontenac"),
          ("Columbus", "Easton Town Center"), ("Indianapolis", "Fashion Mall at Keystone"), ("Detroit", "Somerset Collection"),
          ("Cleveland", "Beachwood Place"), ("Pittsburgh", "Ross Park Mall"), ("Baltimore", "Harbor East"),
          ("Richmond", "Short Pump Town Center"), ("Raleigh", "Crabtree Valley Mall"), ("Orlando", "The Mall at Millenia"),
          ("New Orleans", "Magazine St & Jackson Ave"), ("Phoenix", "Biltmore Fashion Park"), ("Albuquerque", "Nob Hill"),
          ("Honolulu", "Ala Moana Center"), ("Anchorage", "5th Ave Mall"), ("Boise", "The Village at Meridian"),
          ("Omaha", "Village Pointe"), ("Milwaukee", "Third Ward"), ("Louisville", "Oxmoor Center"),
          ("Memphis", "Saddle Creek"), ("Charleston", "King St & Wentworth St"), ("Savannah", "Broughton St"),
          ("Santa Fe", "Canyon Rd"), ("Aspen", "Mill St & Hyman Ave"), ("Palm Beach", "Worth Ave"),
          ("Napa", "Oxbow Public Market"), ("Seattle", "University Village"), ("Chicago", "Oak Street"),
          ("Boston", "Copley Place"), ("Miami", "Design District"), ("Dallas", "Highland Park Village"),
          ("Houston", "River Oaks District"), ("Los Angeles", "The Grove")]


def rng_for(seed, tag):
    return random.Random("%s:%s" % (seed, tag))


def make_id(prefix, material):
    """Deterministic 17-char Airtable-style id (prefix + 14 base62 chars)."""
    h = int(hashlib.sha256(material.encode("utf-8")).hexdigest(), 16)
    s = ""
    for _ in range(14):
        h, r = divmod(h, 62)
        s += B62[r]
    return prefix + s


def slug(s):
    out = "".join(c.lower() if c.isalnum() else "_" for c in s)
    while "__" in out:
        out = out.replace("__", "_")
    return out.strip("_")
