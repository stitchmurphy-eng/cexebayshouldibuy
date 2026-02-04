from flask import Flask, render_template, request
import requests
import statistics
import os

app = Flask(__name__)

# ---------------- eBay OAuth ---------------- #
EBAY_CLIENT_ID = os.environ.get("EBAY_CLIENT_ID")
EBAY_CLIENT_SECRET = os.environ.get("EBAY_CLIENT_SECRET")
EBAY_AUTH_URL = os.environ.get("EBAY_AUTH_URL")

BROWSE_API_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"

JUNK_KEYWORDS = [
    "guide", "manual", "see description", "box only",
    "repro", "poster", "strategy", "pristine"
]

# ---------- Get eBay access token ----------
def get_access_token():
    auth = (EBAY_CLIENT_ID, EBAY_CLIENT_SECRET)
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {"grant_type": "client_credentials",
            "scope": "https://api.ebay.com/oauth/api_scope"}
    response = requests.post(EBAY_AUTH_URL, headers=headers, data=data, auth=auth)
    response.raise_for_status()
    return response.json()["access_token"]

# ---------- Search sold items ----------
def search_sold_items(token, query, marketplace="EBAY-IE"):
    headers = {
        "Authorization": f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": marketplace,
    }
    params = {
        "q": query,
        "limit": 50,
        "filter": "soldItemsOnly:true"
    }
    response = requests.get(BROWSE_API_URL, headers=headers, params=params)
    response.raise_for_status()
    return response.json()

# ---------- Convert GBP → EUR ----------
def convert_to_eur(price_gbp):
    try:
        response = requests.get("https://api.exchangerate.host/latest?base=GBP&symbols=EUR")
        rate = response.json()["rates"]["EUR"]
        return round(price_gbp * rate, 2)
    except:
        # fallback: 1 GBP = 1.17 EUR
        return round(price_gbp * 1.17, 2)

# ---------- Flask route ----------
@app.route("/", methods=["GET", "POST"])
def index():
    output = ""
    recommendation = ""
    color = "black"

    if request.method == "POST":
        game = request.form.get("game")
        console = request.form.get("console")
        cex_price_str = request.form.get("cex_price")
        marketplace = request.form.get("marketplace") or "EBAY-IE"
        include_loose = "loose" in request.form
        include_cib = "cib" in request.form
        ignore_sealed = "ignore_sealed" in request.form

        # Validate CEX price
        try:
            cex_price = float(cex_price_str)
        except ValueError:
            return render_template("index.html", output="Invalid CEX price.", recommendation="", color="black")

        # Get eBay data
        try:
            token = get_access_token()
            query = f"{game} {console}"
            results = search_sold_items(token, query, marketplace)
            items = results.get("itemSummaries", [])
        except Exception as e:
            return render_template("index.html", output=f"Error accessing eBay:\n{e}", recommendation="", color="black")

        # Filter items
        filtered = []
        for item in items:
            title = item["title"].lower()
            if not include_cib and "cib" in title: continue
            if not include_loose and "loose" in title: continue
            if ignore_sealed and "sealed" in title: continue
            if any(junk in title for junk in JUNK_KEYWORDS): continue
            filtered.append(item)

        # Calculate stats
        prices = [float(item["price"]["value"]) for item in filtered]
        if prices:
            avg_gbp = round(sum(prices)/len(prices), 2)
            med_gbp = round(statistics.median(prices), 2)
            avg_eur = convert_to_eur(avg_gbp)
            med_eur = convert_to_eur(med_gbp)
        else:
            avg_gbp = med_gbp = avg_eur = med_eur = 0

        # Recommendation
        if med_eur > cex_price * 1.2:
            recommendation = "BUY ✅"
            color = "green"
        else:
            recommendation = "SKIP ❌"
            color = "red"

        # Prepare output
        output += f"Items found: {len(filtered)}\n"
        output += f"Average Sold Price: €{avg_eur}\n"
        output += f"Median Sold Price: €{med_eur}\n"
        output += f"CEX Price: €{cex_price}\nRecommendation: {recommendation}\n\n"

        output += "Top 5 recent sold listings:\n"
        for item in filtered[:5]:
            title = item["title"]
            price_eur = convert_to_eur(float(item["price"]["value"]))
            link = item["itemWebUrl"]
            output += f"{title} → €{price_eur} → {link}\n"

    return render_template("index.html", output=output, recommendation=recommendation, color=color)

# ---------- Run app ----------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
