import base64
import requests
import statistics
import numpy as np
import PySimpleGUI as sg
from config import EBAY_CLIENT_ID, EBAY_CLIENT_SECRET, EBAY_AUTH_URL

BROWSE_API_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"

# ---------- Keywords ----------
JUNK_KEYWORDS = ["guide", "manual", "see description", "box only", "repro", "poster", "strategy"]
CIB_KEYWORDS = ["cib", "complete in box", "complete set", "pristine", "full set", "full package", "complete"]
LOOSE_KEYWORDS = ["loose", "cartridge only", "tested"]
SEALED_KEYWORDS = ["sealed", "mint sealed", "new in box"]

# ---------- eBay OAuth ----------
def get_access_token():
    auth = (EBAY_CLIENT_ID, EBAY_CLIENT_SECRET)
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"}

    response = requests.post(EBAY_AUTH_URL, headers=headers, data=data, auth=auth)
    response.raise_for_status()
    return response.json()["access_token"]

# ---------- Search sold items ----------
def search_sold_items(token, query, marketplace_id):
    headers = {
        "Authorization": f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": marketplace_id,
    }
    params = {"q": query, "limit": 50, "filter": "soldItemsOnly:true"}
    response = requests.get(BROWSE_API_URL, headers=headers, params=params)
    response.raise_for_status()
    return response.json()

# ---------- Filter items ----------
def filter_items(items, include_loose=True, include_cib=True, ignore_sealed=True):
    filtered = []
    for item in items:
        title = item["title"].lower()

        # ignore junk
        if any(junk in title for junk in JUNK_KEYWORDS):
            continue

        # detect type
        is_cib = any(x in title for x in CIB_KEYWORDS)
        is_loose = any(x in title for x in LOOSE_KEYWORDS)
        is_sealed = any(x in title for x in SEALED_KEYWORDS)

        # ignore sealed
        if ignore_sealed and is_sealed:
            continue

        # skip if user disabled that type
        if is_cib and not include_cib:
            continue
        if is_loose and not include_loose:
            continue

        if is_cib or is_loose:
            filtered.append(item)
    return filtered

# ---------- Get live GBP → EUR rate ----------
def get_gbp_to_eur_rate():
    try:
        resp = requests.get("https://api.exchangerate.host/latest?base=GBP&symbols=EUR")
        resp.raise_for_status()
        data = resp.json()
        return float(data["rates"]["EUR"])
    except:
        return 1.16  # fallback

# ---------- Convert price ----------
def convert_to_eur(price, currency, rate):
    if currency == "GBP":
        return round(float(price) * rate, 2)
    return float(price)

# ---------- Calculate stats ----------
def calculate_stats(items, rate):
    prices = [convert_to_eur(item["price"]["value"], item["price"]["currency"], rate) for item in items]
    if not prices:
        return {
            "avg": 0, "med": 0, "count": 0, 
            "min": 0, "max": 0, "p25": 0, "p75": 0
        }
    avg = round(sum(prices)/len(prices), 2)
    med = round(statistics.median(prices), 2)
    count = len(prices)
    min_price = round(min(prices), 2)
    max_price = round(max(prices), 2)
    p25 = round(np.percentile(prices, 25), 2)
    p75 = round(np.percentile(prices, 75), 2)
    return {
        "avg": avg, "med": med, "count": count, 
        "min": min_price, "max": max_price, "p25": p25, "p75": p75
    }

# ---------- GUI Layout ----------
sg.theme("DarkBlue3")
layout = [
    [sg.Text("Game Name"), sg.Input(key="-GAME-")],
    [sg.Text("Console"), sg.Input(key="-CONSOLE-")],
    [sg.Text("CEX Price (€)"), sg.Input(key="-CEX-")],
    [sg.Text("Marketplace"), sg.Combo(["EBAY-IE", "EBAY-DE"], default_value="EBAY-IE", key="-MARKET-")],
    [sg.Checkbox("Include Loose", default=True, key="-LOOSE-"),
     sg.Checkbox("Include CIB", default=True, key="-CIB-"),
     sg.Checkbox("Ignore Sealed", default=True, key="-IGNORESEALED-")],
    [sg.Button("Check eBay"), sg.Exit()],
    [sg.Multiline(size=(70,25), key="-OUTPUT-", autoscroll=True, disabled=True)],
    [sg.Text("Recommendation:", key="-RECO-", font=("Arial", 14))]
]

window = sg.Window("CEX ↔ eBay Checker", layout)

# ---------- Main Loop ----------
try:
    token = get_access_token()
except Exception as e:
    sg.popup_error(f"Error getting eBay token:\n{e}")
    exit()

gbp_to_eur = get_gbp_to_eur_rate()

while True:
    event, values = window.read()
    if event in (sg.WIN_CLOSED, "Exit"):
        break
    if event == "Check eBay":
        game = values["-GAME-"]
        console = values["-CONSOLE-"]
        marketplace = values["-MARKET-"]
        cex_price_str = values["-CEX-"]
        output = ""
        
        # Validate CEX price
        try:
            cex_price = float(cex_price_str)
        except ValueError:
            window["-OUTPUT-"].update("Invalid CEX price, must be a number")
            continue
        
        query = f"{game} {console}"
        output += f"Searching for: {query} ({marketplace})\n"

        try:
            results = search_sold_items(token, query, marketplace)
            items = results.get("itemSummaries", [])
            items = filter_items(
                items,
                include_loose=values["-LOOSE-"],
                include_cib=values["-CIB-"],
                ignore_sealed=values["-IGNORESEALED-"]
            )

            stats = calculate_stats(items, gbp_to_eur)

            output += f"Items found: {stats['count']}\n"
            output += f"Average Sold Price: €{stats['avg']}\n"
            output += f"Median Sold Price: €{stats['med']}\n"
            output += f"Min: €{stats['min']} | Max: €{stats['max']}\n"
            output += f"25th Percentile: €{stats['p25']} | 75th Percentile: €{stats['p75']}\n"

            if stats["med"] > cex_price * 1.2:
                recommendation = "BUY ✅"
                color = "green"
            else:
                recommendation = "SKIP ❌"
                color = "red"

            output += f"CEX Price: €{cex_price}\n\n"
            
            # Top 5 recent listings with URL
            output += "Top 5 recent sold listings (converted to €):\n"
            for item in items[:5]:
                price_eur = convert_to_eur(item["price"]["value"], item["price"]["currency"], gbp_to_eur)
                link = item.get("itemWebUrl", "No link available")
                output += f"{item['title']} → €{price_eur}\nLink: {link}\n\n"

            window["-OUTPUT-"].update(output)
            window["-RECO-"].update(f"Recommendation: {recommendation}", text_color=color)

        except Exception as e:
            window["-OUTPUT-"].update(f"Error searching eBay:\n{e}")
            window["-RECO-"].update("Recommendation: N/A", text_color="black")

window.close()
