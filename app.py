from flask import Flask, render_template, request
import requests
import statistics
import numpy as np
from config import EBAY_CLIENT_ID, EBAY_CLIENT_SECRET, EBAY_AUTH_URL

app = Flask(__name__)

BROWSE_API_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
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
        if any(junk in title for junk in JUNK_KEYWORDS):
            continue
        is_cib = any(x in title for x in CIB_KEYWORDS)
        is_loose = any(x in title for x in LOOSE_KEYWORDS)
        is_sealed = any(x in title for x in SEALED_KEYWORDS)
        if ignore_sealed and is_sealed:
            continue
        if is_cib and not include_cib:
            continue
        if is_loose and not include_loose:
            continue
        if is_cib or is_loose:
            filtered.append(item)
    return filtered

# ---------- Live GBP → EUR ----------
def get_gbp_to_eur_rate():
    try:
        resp = requests.get("https://api.exchangerate.host/latest?base=GBP&symbols=EUR")
        resp.raise_for_status()
        return float(resp.json()["rates"]["EUR"])
    except:
        return 1.16

def convert_to_eur(price, currency, rate):
    if currency == "GBP":
        return round(float(price) * rate, 2)
    return float(price)

def calculate_stats(items, rate):
    prices = [convert_to_eur(item["price"]["value"], item["price"]["currency"], rate) for item in items]
    if not prices:
        return {"avg":0, "med":0, "count":0, "min":0, "max":0, "p25":0, "p75":0}
    avg = round(sum(prices)/len(prices),2)
    med = round(statistics.median(prices),2)
    count = len(prices)
    min_price = round(min(prices),2)
    max_price = round(max(prices),2)
    p25 = round(np.percentile(prices,25),2)
    p75 = round(np.percentile(prices,75),2)
    return {"avg":avg, "med":med,"count":count,"min":min_price,"max":max_price,"p25":p25,"p75":p75}

# ---------- Routes ----------
@app.route("/", methods=["GET", "POST"])
def index():
    output = ""
    recommendation = ""
    color = "black"

    if request.method == "POST":
        game = request.form.get("game")
        console = request.form.get("console")
        cex_price_str = request.form.get("cex_price")
        marketplace = request.form.get("marketplace")
        include_loose = request.form.get("loose") == "on"
        include_cib = request.form.get("cib") == "on"
        ignore_sealed = request.form.get("ignore_sealed") == "on"

        try:
            cex_price = float(cex_price_str)
        except:
            output = "Invalid CEX price, must be a number"
            return render_template("index.html", output=output, recommendation=recommendation, color=color)

        try:
            token = get_access_token()
            gbp_to_eur = get_gbp_to_eur_rate()
            query = f"{game} {console}"
            results = search_sold_items(token, query, marketplace)
            items = results.get("itemSummaries", [])
            items = filter_items(items, include_loose, include_cib, ignore_sealed)
            stats = calculate_stats(items, gbp_to_eur)

            output += f"Items found: {stats['count']}\n"
            output += f"Average Sold Price: €{stats['avg']}\n"
            output += f"Median Sold Price: €{stats['med']}\n"
            output += f"Min: €{stats['min']} | Max: €{stats['max']}\n"
            output += f"25th Percentile: €{stats['p25']} | 75th Percentile: €{stats['p75']}\n"

            if stats["med"] > cex_price*1.2:
                recommendation = "BUY ✅"
                color = "green"
            else:
                recommendation = "SKIP ❌"
                color = "red"

            output += f"CEX Price: €{cex_price}\n\nTop 5 listings:\n"
            for item in items[:5]:
                price_eur = convert_to_eur(item["price"]["value"], item["price"]["currency"], gbp_to_eur)
                link = item.get("itemWebUrl","No link")
                output += f"{item['title']} → €{price_eur}\nLink: {link}\n\n"

        except Exception as e:
            output = f"Error: {e}"
            recommendation = "N/A"

    return render_template("index.html", output=output, recommendation=recommendation, color=color)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
