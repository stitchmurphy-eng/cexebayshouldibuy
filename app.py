from flask import Flask, render_template, request
import requests
import statistics
import os
from collections import namedtuple

# ---------- Flask App ----------
app = Flask(__name__)

# ---------- eBay Configuration ----------
EBAY_CLIENT_ID = os.environ.get("EBAY_CLIENT_ID")
EBAY_CLIENT_SECRET = os.environ.get("EBAY_CLIENT_SECRET")
EBAY_AUTH_URL = "https://api.ebay.com/identity/v1/oauth2/token"
BROWSE_API_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
JUNK_KEYWORDS = ["guide", "manual", "see description", "box only", "repro", "poster", "strategy", "pristine"]

# ---------- eBay OAuth ----------
def get_access_token():
    auth = (EBAY_CLIENT_ID, EBAY_CLIENT_SECRET)
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"}
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

# ---------- Convert GBP to EUR ----------
def convert_to_eur(price_gbp):
    try:
        response = requests.get("https://api.exchangerate.host/latest?base=GBP&symbols=EUR")
        rate = response.json()["rates"]["EUR"]
        return round(price_gbp * rate, 2)
    except Exception:
        return round(price_gbp, 2)  # fallback if exchange fails

# ---------- Main Route ----------
@app.route("/", methods=["GET", "POST"])
def index():
    output = ""
    recommendation = ""
    color = "black"
    count = avg = med = cex_price = 0
    top_items = []

    # Default form values
    form_values = {
        "game": "",
        "console": "",
        "cex_price": "",
        "marketplaces": ["EBAY-IE"],
        "include_loose": False,
        "include_cib": False,
        "ignore_sealed": False
    }

    if request.method == "POST":
        game = request.form.get("game", "").strip()
        console = request.form.get("console", "").strip()
        cex_price_str = request.form.get("cex_price", "").strip()
        marketplaces = request.form.getlist("marketplace") or ["EBAY-IE"]
        include_loose = "loose" in request.form
        include_cib = "cib" in request.form
        ignore_sealed = "ignore_sealed" in request.form

        # Save form values to redisplay
        form_values.update({
            "game": game,
            "console": console,
            "cex_price": cex_price_str,
            "marketplaces": marketplaces,
            "include_loose": include_loose,
            "include_cib": include_cib,
            "ignore_sealed": ignore_sealed
        })

        # Validate CEX price
        try:
            cex_price = float(cex_price_str)
        except ValueError:
            output = "Invalid CEX price."
            return render_template("index.html", output=output, recommendation="", color="black", top_items=[], **form_values)

        # --- Search eBay ---
        try:
            token = get_access_token()
            query = f"{game} {console}"
            all_items = []
            for marketplace in marketplaces:
                results = search_sold_items(token, query, marketplace)
                all_items.extend(results.get("itemSummaries", []))
            items = all_items
        except Exception as e:
            output = f"Error accessing eBay:\n{e}"
            return render_template("index.html", output=output, recommendation="", color="black", top_items=[], **form_values)

        # --- Filter items ---
        filtered = []
        for item in items:
            title = item["title"].lower()
            if not include_cib and "cib" in title: continue
            if not include_loose and "loose" in title: continue
            if ignore_sealed and "sealed" in title: continue
            if any(junk in title for junk in JUNK_KEYWORDS): continue
            filtered.append(item)

        # Debug: if nothing matched
        if not filtered:
            output = f"No items found matching your filters for '{query}' on {', '.join(marketplaces)}."
            top_items = []
        else:
            output = f"Searched: '{query}' on {', '.join(marketplaces)}"

        # --- Stats ---
        prices = [float(item["price"]["value"]) for item in filtered]
        count = len(prices)
        if prices:
            avg_gbp = round(sum(prices)/len(prices), 2)
            med_gbp = round(statistics.median(prices), 2)
            avg = convert_to_eur(avg_gbp)
            med = convert_to_eur(med_gbp)
        else:
            avg = med = 0

        # --- Recommendation ---
        if med > cex_price * 1.2:
            recommendation = "BUY ✅"
            color = "green"
        else:
            recommendation = "SKIP ❌"
            color = "red"

        # --- Top 5 listings ---
        TopItem = namedtuple("TopItem", ["title", "price", "link"])
        top_items = [
            TopItem(
                title=item["title"],
                price=convert_to_eur(float(item["price"]["value"])),
                link=item.get("itemWebUrl", "#")
            )
            for item in filtered[:5]
        ]

    return render_template("index.html",
                           output=output,
                           recommendation=recommendation,
                           color=color,
                           count=count,
                           avg=avg,
                           med=med,
                           cex_price=cex_price,
                           top_items=top_items,
                           **form_values)

# ---------- Run ----------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
