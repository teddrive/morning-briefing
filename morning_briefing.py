import anthropic
import requests
import os
import time
import html
from concurrent.futures import ThreadPoolExecutor

# ── ENVIRONMENT VARIABLES (from GitHub Secrets) ────────
def get_env(name):
    value = os.environ.get(name)
    if not value:
        raise EnvironmentError(f"Missing required environment variable: {name}")
    return value

TELEGRAM_BOT_TOKEN = get_env("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID   = get_env("TELEGRAM_CHAT_ID")
CLAUDE_API_KEY     = get_env("CLAUDE_API_KEY")
NEWS_API_KEY       = get_env("NEWS_API_KEY")
# ──────────────────────────────────────────────────────


def get_top_news():
    try:
        url = (
            "https://newsapi.org/v2/top-headlines"
            f"?language=en&pageSize=10&apiKey={NEWS_API_KEY}"
        )
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return f"World news unavailable (HTTP {response.status_code})"
        articles = response.json().get("articles", [])
        headlines = [f"- {a.get('title', 'Untitled')}" for a in articles[:10] if a.get("title")]
        return "\n".join(headlines) if headlines else "No headlines available"
    except Exception as e:
        return f"Could not fetch world news: {str(e)}"


def get_tech_news():
    try:
        url = (
            "https://newsapi.org/v2/top-headlines"
            f"?category=technology&language=en&pageSize=5&apiKey={NEWS_API_KEY}"
        )
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return f"Tech news unavailable (HTTP {response.status_code})"
        articles = response.json().get("articles", [])
        headlines = [f"- {a.get('title', 'Untitled')}" for a in articles[:5] if a.get("title")]
        return "\n".join(headlines) if headlines else "No tech headlines available"
    except Exception as e:
        return f"Could not fetch tech news: {str(e)}"


def get_crypto_prices():
    try:
        url = (
            "https://api.coingecko.com/api/v3/simple/price"
            "?ids=bitcoin,dogecoin,official-trump"
            "&vs_currencies=usd"
            "&include_24hr_change=true"
        )
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return f"Crypto data unavailable (HTTP {response.status_code})"
        data = response.json()

        def fmt(coin_id, label, decimals=4):
            coin = data.get(coin_id, {})
            price  = coin.get("usd")
            change = coin.get("usd_24h_change")
            if price is None:
                return f"{label}: Data unavailable"
            if change is None:
                direction = "N/A"
                change_str = "N/A"
            elif change > 0:
                direction = "🔺"
                change_str = f"{change:.2f}%"
            elif change < 0:
                direction = "🔻"
                change_str = f"{abs(change):.2f}%"
            else:
                direction = "↔️"
                change_str = "0.00%"
            return f"{label}: ${price:,.{decimals}f} {direction} {change_str} (24h)"

        btc   = fmt("bitcoin",        "BTC",   decimals=2)
        doge  = fmt("dogecoin",       "DOGE",  decimals=4)
        trump = fmt("official-trump", "TRUMP", decimals=4)
        return f"{btc}\n{doge}\n{trump}"
    except Exception as e:
        return f"Could not fetch crypto prices: {str(e)}"


def get_stock_overview():
    try:
        import yfinance as yf
        tickers = {
            "S&P 500":   "^GSPC",
            "NASDAQ":    "^IXIC",
            "DOW":       "^DJI",
            "Apple":     "AAPL",
            "Tesla":     "TSLA",
            "NVIDIA":    "NVDA",
            "Microsoft": "MSFT",
            "Amazon":    "AMZN",
            "Meta":      "META",
            "Google":    "GOOGL",
        }
        lines = []
        for name, symbol in tickers.items():
            try:
                ticker  = yf.Ticker(symbol)
                history = ticker.history(period="2d")
                if len(history) >= 2:
                    prev  = history["Close"].iloc[-2]
                    price = history["Close"].iloc[-1]
                    change = ((price - prev) / prev) * 100
                    direction = "🔺" if change > 0 else "🔻"
                    lines.append(f"{name}: ${price:,.2f} {direction} {abs(change):.2f}%")
                else:
                    lines.append(f"{name}: Data unavailable")
            except Exception as e:
                lines.append(f"{name}: Unavailable ({str(e)})")
        return "\n".join(lines)
    except Exception as e:
        return f"Could not fetch stock data: {str(e)}"


def get_briefing(tech_news, crypto, top_news, stocks):
    # Trim each section to avoid exceeding model input limits
    def trim(text, max_chars=800):
        return text[:max_chars] + "..." if len(text) > max_chars else text

    prompt = f"""You are my personal morning briefing assistant. Give me a concise, scannable morning summary based on the live data below:

LIVE TECH HEADLINES:
{trim(tech_news)}

LIVE CRYPTO PRICES:
{trim(crypto)}

LIVE WORLD HEADLINES:
{trim(top_news)}

LIVE US EQUITIES:
{trim(stocks)}

Format your response as:

1. Tech News — top 3-5 stories today
2. Crypto — BTC, TRUMP token, DOGE: price, sentiment, key news
3. World News — only the 2-3 most critical global stories
4. US Equities — market overview + key movers across all sectors (exclude commodities), include pre-market signals if available

Keep it sharp and digestible."""

    client  = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]
    )
    return message.content[0].text


def send_telegram_message(text, retries=1):
    # Trim to Telegram's 4096 character limit
    if len(text) > 4096:
        text = text[:4090] + "..."

    # Escape HTML special characters
    safe_text = html.escape(text)

    url     = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id":                  TELEGRAM_CHAT_ID,
        "text":                     safe_text,
        "parse_mode":               "HTML",
        "disable_web_page_preview": True
    }
    for attempt in range(retries + 1):
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            print("Telegram message sent successfully!")
            return
        print(f"Telegram error (attempt {attempt+1}): {response.status_code} - {response.text}")
        if attempt < retries:
            time.sleep(3)
    print("Failed to send Telegram message after retries.")


def morning_briefing():
    print("Fetching live data in parallel...")

    # Fetch all data sources simultaneously for speed
    with ThreadPoolExecutor(max_workers=4) as executor:
        future_tech   = executor.submit(get_tech_news)
        future_crypto = executor.submit(get_crypto_prices)
        future_news   = executor.submit(get_top_news)
        future_stocks = executor.submit(get_stock_overview)

        tech_news = future_tech.result()
        crypto    = future_crypto.result()
        top_news  = future_news.result()
        stocks    = future_stocks.result()

    print("Generating briefing with Claude...")
    briefing     = get_briefing(tech_news, crypto, top_news, stocks)
    full_message = f"🌅 Good Morning! Here's your briefing:\n\n{briefing}"
    send_telegram_message(full_message)
    print("Done!")


morning_briefing()
