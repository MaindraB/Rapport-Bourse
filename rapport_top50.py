#!/usr/bin/env python3
"""
Rapport Top 50 US - Version Momentum + Double Score (A Conservateur / B Opportuniste)
Top 5 classé sur Momentum Composite + Score B
Objectif : +20% en max 90 jours
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
import os
import warnings
warnings.filterwarnings("ignore")

# ============================================================
# CONFIGURATION (Secrets GitHub)
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
# FONCTIONS
# ============================================================

def get_stock_data(ticker):
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1y")
        if hist.empty or len(hist) < 70:
            return None

        info = stock.info
        current = hist["Close"].iloc[-1]
        prev = hist["Close"].iloc[-2]
        change_pct = ((current - prev) / prev) * 100

        # ========== MOMENTUMS ==========
        mom_5j = ((current / hist["Close"].iloc[-6]) - 1) * 100 if len(hist) >= 6 else 0
        mom_30j = ((current / hist["Close"].iloc[-31]) - 1) * 100 if len(hist) >= 31 else 0
        mom_trim = ((current / hist["Close"].iloc[-64]) - 1) * 100 if len(hist) >= 64 else 0

        # Momentum composite (pondéré)
        mom_composite = (mom_5j * 0.25) + (mom_30j * 0.40) + (mom_trim * 0.35)

        high_52 = hist["High"].max()
        dist_high = ((current - high_52) / high_52) * 100

        sma20 = hist["Close"].rolling(20).mean().iloc[-1]
        sma50 = hist["Close"].rolling(50).mean().iloc[-1]
        sma200 = hist["Close"].rolling(200).mean().iloc[-1] if len(hist) >= 200 else np.nan
        dist_sma200 = ((current - sma200) / sma200 * 100) if not np.isnan(sma200) else np.nan

        # RSI 14
        delta = hist["Close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs)).iloc[-1]

        # Volume 5j
        vol_5j_avg = hist["Volume"].iloc[-6:-1].mean()
        vol_5j_change = ((hist["Volume"].iloc[-1] - vol_5j_avg) / vol_5j_avg * 100) if vol_5j_avg > 0 else 0

        # ========== SCORE A (Conservateur) ==========
        score_a = 0.0
        if not np.isnan(dist_sma200) and dist_sma200 > 0:
            score_a += 2.0
        if current > sma50 > sma200:
            score_a += 2.5
        if 45 <= rsi <= 60:
            score_a += 2.0
        elif 40 <= rsi <= 65:
            score_a += 1.2
        if -12 < dist_high < -3:
            score_a += 1.8
        if vol_5j_change > 0:
            score_a += 1.0
        if mom_30j > 5 and mom_trim > 8:
            score_a += 1.5
        score_a = round(min(score_a, 10), 1)

        # ========== SCORE B (Opportuniste) ==========
        score_b = 0.0
        if mom_composite > 12:
            score_b += 3.0
        elif mom_composite > 7:
            score_b += 2.2
        elif mom_composite > 3:
            score_b += 1.3

        if mom_5j > 3:
            score_b += 1.5
        elif mom_5j > 1:
            score_b += 0.8

        if current > sma20 > sma50:
            score_b += 2.0
        if 48 <= rsi <= 68:
            score_b += 1.8
        if vol_5j_change > 10:
            score_b += 1.2
        if dist_high > -15:
            score_b += 1.0
        score_b = round(min(score_b, 10), 1)

        # Signal
        if current > sma50 > sma200 and rsi < 70:
            signal, signal_color = "BULLISH", "#22c55e"
        elif current < sma50 < sma200:
            signal, signal_color = "BEARISH", "#ef4444"
        else:
            signal, signal_color = "NEUTRAL", "#eab308"

        return {
            "Ticker": ticker,
            "Name": info.get("shortName", ticker)[:18],
            "Sector": info.get("sector", "N/A")[:14],
            "Price": round(current, 2),
            "Change%": round(change_pct, 2),
            "Mom5j": round(mom_5j, 1),
            "Mom30j": round(mom_30j, 1),
            "MomTrim": round(mom_trim, 1),
            "MomComp": round(mom_composite, 1),
            "Dist High%": round(dist_high, 1),
            "Dist SMA200%": round(dist_sma200, 1) if not np.isnan(dist_sma200) else None,
            "RSI": round(rsi, 1),
            "Vol 5j %": round(vol_5j_change, 1),
            "ScoreA": score_a,
            "ScoreB": score_b,
            "Signal": signal,
            "SignalColor": signal_color,
            "MarketCap": info.get("marketCap", 0),
            "hist": hist[["Close"]].tail(40)
        }
    except Exception as e:
        print(f"Erreur {ticker}: {e}")
        return None


def color_pct(val):
    if val is None:
        return "N/A"
    if val > 0:
        return f'<span style="color:#16a34a;font-weight:bold">+{val}%</span>'
    if val < 0:
        return f'<span style="color:#dc2626;font-weight:bold">{val}%</span>'
    return f"{val}%"


def color_rsi(rsi):
    if rsi >= 70:
        return f'<span style="color:#dc2626;font-weight:bold">{rsi}</span>'
    if rsi <= 30:
        return f'<span style="color:#16a34a;font-weight:bold">{rsi}</span>'
    return str(rsi)


def create_top5_infographic(df_top5, filename="top5_favorable.png"):
    fig, axes = plt.subplots(5, 1, figsize=(11, 13), facecolor="#0f172a")
    fig.suptitle("TOP 5 MOMENTUM + SCORE B (Opportuniste)\n" + datetime.now().strftime("%d/%m/%Y"),
                 color="white", fontsize=16, fontweight="bold", y=0.98)

    for i, (_, row) in enumerate(df_top5.iterrows()):
        ax = axes[i]
        ax.set_facecolor("#1e293b")

        score_color = "#22c55e" if row["ScoreB"] >= 7.5 else "#eab308" if row["ScoreB"] >= 5.5 else "#f97316"
        title = f"#{i+1}  {row['Ticker']}   |   Score B: {row['ScoreB']}/10   |   Mom Comp: {row['MomComp']}%   |   {row['Signal']}"
        ax.set_title(title, color=score_color, fontsize=12, fontweight="bold", loc="left", pad=6)

        prices = row["hist"]["Close"].values
        ax.plot(prices, color="#22c55e", linewidth=2)
        ax.fill_between(range(len(prices)), prices, alpha=0.2, color="#22c55e")

        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_visible(False)

        info_text = (f"Prix: ${row['Price']}  |  RSI: {row['RSI']}  |  "
                     f"Mom 5j: {row['Mom5j']}%  |  Mom 30j: {row['Mom30j']}%  |  "
                     f"Mom Trim: {row['MomTrim']}%  |  Score A: {row['ScoreA']}")
        ax.text(0.01, -0.18, info_text, transform=ax.transAxes, color="#94a3b8", fontsize=9)

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    plt.savefig(filename, dpi=120, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()
    print(f"Infographie sauvegardée : {filename}")
    return filename


def generate_html(df):
    today = datetime.now().strftime("%d/%m/%Y %H:%M")
    html = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; background:#f8fafc; margin:0; padding:15px; }}
            h1 {{ color:#0f172a; font-size:20px; }}
            table {{ border-collapse: collapse; width:100%; background:white; font-size:11px; }}
            th {{ background:#0f172a; color:white; padding:7px 3px; }}
            td {{ padding:5px 3px; text-align:center; border-bottom:1px solid #e2e8f0; }}
            .bullish {{ background:#dcfce7; }}
            .bearish {{ background:#fee2e2; }}
            .neutral {{ background:#fef9c3; }}
        </style>
    </head>
    <body>
        <h1>Top 50 US – Momentum + Double Score</h1>
        <p><b>{today}</b> | Top 5 classé sur Momentum Composite + Score B (Opportuniste)</p>
        <p>Score A = Conservateur | Score B = Opportuniste | Objectif : +20% en ≤ 90 jours</p>
        
        <table>
            <thead>
                <tr>
                    <th>Ticker</th>
                    <th>Nom</th>
                    <th>Prix</th>
                    <th>Var%</th>
                    <th>Mom5j</th>
                    <th>Mom30j</th>
                    <th>MomTrim</th>
                    <th>MomComp</th>
                    <th>RSI</th>
                    <th>ScoreA</th>
                    <th>ScoreB</th>
                    <th>Signal</th>
                </tr>
            </thead>
            <tbody>
    """
    for _, row in df.iterrows():
        html += f"""
            <tr class="{row['Signal'].lower()}">
                <td><b>{row['Ticker']}</b></td>
                <td style="text-align:left">{row['Name']}</td>
                <td>{row['Price']}</td>
                <td>{color_pct(row['Change%'])}</td>
                <td>{color_pct(row['Mom5j'])}</td>
                <td>{color_pct(row['Mom30j'])}</td>
                <td>{color_pct(row['MomTrim'])}</td>
                <td><b>{color_pct(row['MomComp'])}</b></td>
                <td>{color_rsi(row['RSI'])}</td>
                <td>{row['ScoreA']}</td>
                <td><b>{row['ScoreB']}</b></td>
                <td style="background:{row['SignalColor']};color:white;font-weight:bold">{row['Signal']}</td>
            </tr>
        """
    html += """
            </tbody>
        </table>
        <p style="margin-top:15px;font-size:11px;color:#64748b;">
            MomComp = 25% Mom5j + 40% Mom30j + 35% MomTrim<br>
            Top 5 trié sur : (MomComp × 0.6) + (ScoreB × 0.4)
        </p>
    </body>
    </html>
    """
    return html


def send_email(html_content, image_path):
    msg = MIMEMultipart("related")
    msg["Subject"] = f"Top 50 US – Momentum + Score B – {datetime.now().strftime('%d/%m/%Y')}"
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECIPIENT_EMAIL
    msg.attach(MIMEText(html_content, "html"))

    with open(image_path, "rb") as f:
        img = MIMEImage(f.read())
        img.add_header("Content-Disposition", "attachment", filename="Top5_Momentum_ScoreB.png")
        msg.attach(img)

    try:
        with smtplib.SMTP_SSL("smtp.mail.yahoo.com", 465) as server:
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, RECIPIENT_EMAIL, msg.as_string())
        print("✅ E-mail envoyé avec succès !")
    except Exception as e:
        print(f"❌ Erreur envoi : {e}")


# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    print("Récupération des données Top 50 US...\n")
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
        print("Aucune donnée récupérée.")
        exit()

    df = pd.DataFrame(data)
    df = df.sort_values("MarketCap", ascending=False).reset_index(drop=True)

    # Top 5 classé sur Momentum Composite + Score B
    df["RankScore"] = df["MomComp"] * 0.6 + df["ScoreB"] * 0.4
    df_top5 = df.sort_values("RankScore", ascending=False).head(5)

    print("\n=== TOP 5 (Momentum + Score B) ===")
    print(df_top5[["Ticker", "MomComp", "ScoreB", "ScoreA", "RSI", "Signal"]].to_string(index=False))

    img_path = create_top5_infographic(df_top5)
    html = generate_html(df)

    send_email(html, img_path)
    print("\nTerminé avec succès.")