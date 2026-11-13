#!/usr/bin/env python3
"""
Daily Top 50 US Market Cap Report - Version Yahoo Mail
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec
import os
import warnings
warnings.filterwarnings("ignore")

# ============================================================
# CONFIGURATION (via Secrets GitHub)
# ============================================================
SENDER_EMAIL = os.environ.get("SENDER_EMAIL")
SENDER_PASSWORD = os.environ.get("SENDER_PASSWORD")
RECIPIENT_EMAIL = os.environ.get("RECIPIENT_EMAIL")

TICKERS = [
    "AAPL", "NVDA", "MSFT", "GOOGL", "AMZN", "AVGO", "META", "TSLA", "LLY", "BRK-B",
    "WMT", "AMD", "JPM", "MU", "V", "XOM", "JNJ", "MA", "ABBV", "COST",
    "KO", "CVX", "PG", "PLTR", "CSCO", "ORCL", "UNH", "HD", "BAC", "CRM",
    "MRK", "PEP", "TMO", "ABT", "ACN", "LIN", "NFLX", "DIS", "CMCSA", "ADBE",
    "TXN", "NEE", "PM", "INTU", "QCOM", "AMGN", "IBM", "GE", "CAT", "AXP"
]

# ============================================================
# FONCTIONS (identiques à la version précédente)
# ============================================================

def get_stock_data(ticker):
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1y")
        if hist.empty or len(hist) < 60:
            return None

        info = stock.info
        current = hist["Close"].iloc[-1]
        prev = hist["Close"].iloc[-2]
        change_pct = ((current - prev) / prev) * 100

        high_52 = hist["High"].max()
        low_52 = hist["Low"].min()
        dist_high = ((current - high_52) / high_52) * 100

        sma5  = hist["Close"].rolling(5).mean().iloc[-1]
        sma20 = hist["Close"].rolling(20).mean().iloc[-1]
        sma50 = hist["Close"].rolling(50).mean().iloc[-1]
        sma200 = hist["Close"].rolling(200).mean().iloc[-1] if len(hist) >= 200 else np.nan

        dist_sma200 = ((current - sma200) / sma200 * 100) if not np.isnan(sma200) else np.nan

        delta = hist["Close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs)).iloc[-1]

        vol_avg20 = hist["Volume"].rolling(20).mean().iloc[-1]
        vol_rel = hist["Volume"].iloc[-1] / vol_avg20 if vol_avg20 > 0 else 1
        vol_5j_avg = hist["Volume"].iloc[-6:-1].mean()
        vol_5j_change = ((hist["Volume"].iloc[-1] - vol_5j_avg) / vol_5j_avg * 100) if vol_5j_avg > 0 else 0

        # Score /10
        score_10 = 0.0
        if not np.isnan(dist_sma200):
            if dist_sma200 > 15: score_10 += 2.5
            elif dist_sma200 > 8: score_10 += 2.0
            elif dist_sma200 > 3: score_10 += 1.5
            elif dist_sma200 > 0: score_10 += 1.0
            elif dist_sma200 > -5: score_10 += 0.3

        if current > sma5 > sma20 > sma50: score_10 += 2.0
        elif current > sma20 > sma50: score_10 += 1.4
        elif current > sma50: score_10 += 0.8

        if 48 <= rsi <= 62: score_10 += 2.0
        elif 42 <= rsi < 48 or 62 < rsi <= 68: score_10 += 1.3
        elif 35 <= rsi < 42 or 68 < rsi <= 72: score_10 += 0.6

        if change_pct > 1.5 and vol_5j_change > 15: score_10 += 1.5
        elif change_pct > 0.5 and vol_5j_change > 5: score_10 += 1.0
        elif change_pct > 0: score_10 += 0.5

        if dist_high > -3: score_10 += 2.0
        elif dist_high > -7: score_10 += 1.4
        elif dist_high > -12: score_10 += 0.8
        elif dist_high > -20: score_10 += 0.3

        score_10 = round(min(score_10, 10.0), 1)

        if not np.isnan(sma200) and current > sma50 > sma200 and 40 <= rsi <= 68:
            signal, signal_color = "BULLISH", "#22c55e"
        elif not np.isnan(sma200) and current < sma50 < sma200 and rsi >= 32:
            signal, signal_color = "BEARISH", "#ef4444"
        else:
            signal, signal_color = "NEUTRAL", "#eab308"

        return {
            "Ticker": ticker,
            "Name": info.get("shortName", ticker)[:20],
            "Sector": info.get("sector", "N/A")[:15],
            "Price": round(current, 2),
            "Change%": round(change_pct, 2),
            "Dist High%": round(dist_high, 1),
            "Dist SMA200%": round(dist_sma200, 1) if not np.isnan(dist_sma200) else None,
            "RSI": round(rsi, 1),
            "Vol Rel": round(vol_rel, 2),
            "Vol 5j %": round(vol_5j_change, 1),
            "Signal": signal,
            "SignalColor": signal_color,
            "Score10": score_10,
            "MarketCap": info.get("marketCap", 0),
            "hist": hist[["Close"]].tail(40)
        }
    except Exception as e:
        print(f"Erreur {ticker}: {e}")
        return None


def color_pct(val):
    if val is None: return "N/A"
    if val > 0: return f'<span style="color:#16a34a;font-weight:bold">+{val}%</span>'
    if val < 0: return f'<span style="color:#dc2626;font-weight:bold">{val}%</span>'
    return f"{val}%"


def color_rsi(rsi):
    if rsi >= 70: return f'<span style="color:#dc2626;font-weight:bold">{rsi}</span>'
    if rsi <= 30: return f'<span style="color:#16a34a;font-weight:bold">{rsi}</span>'
    return str(rsi)


def create_top5_infographic(df_top5, filename="top5_favorable.png"):
    fig = plt.figure(figsize=(14, 10), facecolor="#0f172a")
    gs = GridSpec(6, 2, figure=fig, height_ratios=[0.12, 1, 1, 1, 1, 1], hspace=0.35, wspace=0.25)

    ax_title = fig.add_subplot(gs[0, :])
    ax_title.set_facecolor("#0f172a")
    ax_title.axis("off")
    ax_title.text(0.5, 0.7, "TOP 5 TICKERS LES PLUS FAVORABLES À L'ACHAT",
                  ha="center", va="center", fontsize=20, fontweight="bold", color="white")
    ax_title.text(0.5, 0.25, datetime.now().strftime("%d %B %Y"),
                  ha="center", va="center", fontsize=12, color="#94a3b8")

    for i, (_, row) in enumerate(df_top5.iterrows()):
        ax_info = fig.add_subplot(gs[i+1, 0])
        ax_info.set_facecolor("#1e293b")
        ax_info.axis("off")

        ax_info.text(0.05, 0.75, f"#{i+1}", fontsize=22, fontweight="bold",
                     color="#22c55e", transform=ax_info.transAxes)
        ax_info.text(0.18, 0.78, row["Ticker"], fontsize=18, fontweight="bold",
                     color="white", transform=ax_info.transAxes)
        ax_info.text(0.18, 0.55, row["Name"], fontsize=10, color="#94a3b8",
                     transform=ax_info.transAxes)

        score_color = "#22c55e" if row["Score10"] >= 7.5 else "#eab308" if row["Score10"] >= 5.5 else "#f97316"
        ax_info.text(0.05, 0.25, f"Score Achat : {row['Score10']}/10",
                     fontsize=14, fontweight="bold", color=score_color,
                     transform=ax_info.transAxes)

        metrics = (f"RSI {row['RSI']}  |  Dist SMA200 {row['Dist SMA200%']}%  |  "
                   f"Vol 5j {row['Vol 5j %']}%  |  {row['Signal']}")
        ax_info.text(0.05, 0.08, metrics, fontsize=9, color="#cbd5e1",
                     transform=ax_info.transAxes)

        ax_chart = fig.add_subplot(gs[i+1, 1])
        ax_chart.set_facecolor("#1e293b")
        prices = row["hist"]["Close"]
        ax_chart.plot(prices.values, color="#22c55e", linewidth=2)
        ax_chart.fill_between(range(len(prices)), prices.values, alpha=0.15, color="#22c55e")
        ax_chart.set_xticks([])
        ax_chart.set_yticks([])
        for spine in ax_chart.spines.values():
            spine.set_visible(False)
        ax_chart.text(0.98, 0.9, f"${row['Price']}", transform=ax_chart.transAxes,
                      ha="right", va="top", fontsize=11, fontweight="bold", color="white")
        color_chg = "#22c55e" if row["Change%"] >= 0 else "#ef4444"
        ax_chart.text(0.98, 0.7, f"{row['Change%']:+.1f}%", transform=ax_chart.transAxes,
                      ha="right", va="top", fontsize=10, color=color_chg)

    plt.savefig(filename, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()
    return filename


def generate_html(df):
    today = datetime.now().strftime("%d/%m/%Y %H:%M")
    html = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; background:#f8fafc; margin:0; padding:20px; }}
            h1 {{ color:#0f172a; }}
            table {{ border-collapse: collapse; width:100%; background:white; }}
            th {{ background:#0f172a; color:white; padding:9px 4px; font-size:11px; }}
            td {{ padding:6px 4px; font-size:11px; text-align:center; border-bottom:1px solid #e2e8f0; }}
            .bullish {{ background:#dcfce7; }}
            .bearish {{ background:#fee2e2; }}
            .neutral {{ background:#fef9c3; }}
        </style>
    </head>
    <body>
        <h1>Top 50 US – Rapport Quotidien</h1>
        <p><b>{today}</b></p>
        <table>
            <thead>
                <tr>
                    <th>Ticker</th><th>Nom</th><th>Secteur</th><th>Prix</th>
                    <th>Var %</th><th>Dist High</th><th>Dist SMA200</th>
                    <th>RSI</th><th>Vol 5j %</th><th>Score /10</th><th>Signal</th>
                </tr>
            </thead>
            <tbody>
    """
    for _, row in df.iterrows():
        html += f"""
            <tr class="{row['Signal'].lower()}">
                <td><b>{row['Ticker']}</b></td>
                <td style="text-align:left">{row['Name']}</td>
                <td>{row['Sector']}</td>
                <td>{row['Price']}</td>
                <td>{color_pct(row['Change%'])}</td>
                <td>{row['Dist High%']}%</td>
                <td>{color_pct(row['Dist SMA200%'])}</td>
                <td>{color_rsi(row['RSI'])}</td>
                <td>{color_pct(row['Vol 5j %'])}</td>
                <td><b>{row['Score10']}/10</b></td>
                <td style="background:{row['SignalColor']};color:white;font-weight:bold">{row['Signal']}</td>
            </tr>
        """
    html += """
            </tbody>
        </table>
    </body>
    </html>
    """
    return html


def send_email(html_content, image_path):
    msg = MIMEMultipart("related")
    msg["Subject"] = f"Top 50 US + Top 5 Score Achat /10 – {datetime.now().strftime('%d/%m/%Y')}"
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECIPIENT_EMAIL
    msg.attach(MIMEText(html_content, "html"))

    with open(image_path, "rb") as f:
        img = MIMEImage(f.read())
        img.add_header("Content-Disposition", "attachment", filename="Top5_Score_Achat.png")
        msg.attach(img)

    # Yahoo Mail SMTP
    try:
        with smtplib.SMTP_SSL("smtp.mail.yahoo.com", 465) as server:
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, RECIPIENT_EMAIL, msg.as_string())
        print("✅ E-mail envoyé avec succès via Yahoo !")
    except Exception as e:
        print(f"❌ Erreur envoi : {e}")


# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    print("Récupération des données...\n")
    data = []
    for i, ticker in enumerate(TICKERS, 1):
        print(f"[{i:02d}/50] {ticker}...", end=" ")
        result = get_stock_data(ticker)
        if result:
            data.append(result)
            print("OK")
        else:
            print("Échec")

    if not data:
        exit()

    df = pd.DataFrame(data)
    df = df.sort_values("MarketCap", ascending=False).reset_index(drop=True)

    df_top5 = df.sort_values("Score10", ascending=False).head(5)
    print("\n=== TOP 5 SCORE ACHAT /10 ===")
    print(df_top5[["Ticker", "Score10", "RSI", "Dist SMA200%", "Vol 5j %", "Signal"]].to_string(index=False))

    img_path = create_top5_infographic(df_top5)
    html = generate_html(df)

    send_email(html, img_path)
    print("\nTerminé.")