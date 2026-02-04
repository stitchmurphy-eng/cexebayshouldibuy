from flask import Flask, render_template, request
import requests
import statistics
import os

app = Flask(__name__)

# eBay OAuth and browsing code as before
# Make sure config.py reads keys from environment variables

# Example function to convert GBP → EUR (you can adjust later)
def convert_to_eur(price_gbp):
    response = requests.get("https://api.exchangerate.host/latest?base=GBP&symbols=EUR")
    rate = response.json()["rates"]["EUR"]
    return round(price_gbp * rate, 2)

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
        include_loose = "loose" in request.form
        include_cib = "cib" in request.form
        ignore_sealed = "ignore_sealed" in request.form

        try:
            cex_price = float(cex_price_str)
        except ValueError:
            output = "Invalid CEX price."
            return render_template("index.html", output=output)

        # --- Search eBay ---
        token = get_access_token()
        query = f"{game} {console}"
        results = search_sold_items(token, query)
        items = results.get("itemSummaries", [])

        # --- Filter items ---
        filtered = []
        for item in items:
            title = item["title"].lower()
            # remove unwanted items
            if not include_cib and "cib" in title:
                continue
            if not include_loose and "loose" in title:
                continue
            if ignore_sealed and "sealed" in title:
                continue
            # extra junk filtering
            junk_keywords = ["guide", "manual", "see description", "box only", "repro", "poster", "strategy", "pristine"]
            if any(junk in title for junk in junk_keywords):
                continue
            filtered.append(item)

        # --- Calculate stats ---
        prices = [float(item["price"]["value"]) for item in filtered]
        if prices:
            avg_gbp = round(sum(prices)/len(prices), 2)
            med_gbp = round(statistics.median(prices), 2)
            avg_eur = convert_to_eur(avg_gbp)
            med_eur = convert_to_eur(med_gbp)
        else:
            avg_gbp = med_gbp = avg_eur = med_eur = 0

        # --- Recommendation ---
        if med_eur > cex_price * 1.2:
            recommendation = "BUY ✅"
            color = "green"
        else:
            recommendation = "SKIP ❌"
            color = "red"

        # --- Prepare output ---
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
