import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv

load_dotenv()

FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")
MARKETAUX_API_KEY = os.getenv("MARKETAUX_API_KEY")

FINNHUB_URL = "https://finnhub.io/api/v1/quote"
MARKETAUX_URL = "https://api.marketaux.com/v1/news/all"

NEWS_LIMIT = 10
NEWS_LOOKBACK_HOURS = 48
MAX_ARTICLES_PER_STOCK = 3
MAX_NEWS_HOLDINGS = 5
MAX_STRIP_ARTICLES_PER_HOLDING = 1
API_DELAY_SECONDS = 0.25

# Strict relevance threshold to ensure news is genuinely related to the target stock.
# Lowering this threshold can surface articles where the stock is only a minor or
# secondary mention, resulting in misleading explanations. It is preferable to
# return no explanation rather than provide one based on weak or unrelated news.
STRICT_RELEVANCE_THRESHOLD = 0.20


SECTORS = {
    "AAPL": "Technology",
    "MSFT": "Technology",
    "NVDA": "Technology",
    "AVGO": "Technology",
    "GOOGL": "Communication Services",
    "META": "Communication Services",
    "AMZN": "Consumer Discretionary",
    "TSLA": "Consumer Discretionary",
    "LLY": "Healthcare",
    "JNJ": "Healthcare",
    "JPM": "Financials",
    "V": "Financials",
}


FORCE_KEYWORDS = {
    "AI demand": [
        "artificial intelligence", "artificial-intelligence", "ai demand",
        "ai chip", "ai chips", "ai infrastructure", "generative ai",
        "gen ai", "data center", "data centre", "accelerator", "gpu",
        "azure", "cloud", "machine learning",
    ],
    "Earnings / revenue": [
        "earnings", "revenue", "profit", "profits", "sales", "guidance",
        "forecast", "outlook", "quarter", "quarterly", "eps",
    ],
    "Analyst / investor sentiment": [
        "analyst", "analysts", "price target", "upgrade", "downgrade",
        "investor sentiment", "investor confidence", "wall street",
    ],
    "Regulation": [
        "regulation", "regulatory", "regulator", "antitrust", "lawsuit",
        "government", "legislation", "compliance", "investigation",
        "probe", "ban", "restriction",
    ],
    "Product / technology developments": [
        "product launch", "new product", "technology",
        "technology development", "innovation", "software", "hardware",
        "device", "platform", "release",
    ],
    "Corporate / strategic activity": [
        "acquisition", "acquire", "merger", "partnership", "deal",
        "agreement", "strategic", "restructuring", "buyback", "dividend",
    ],
    "Healthcare / drug developments": [
        "drug", "drug trial", "clinical trial", "fda", "approval",
        "therapy", "treatment", "medicine", "pharmaceutical", "obesity",
        "diabetes",
    ],
    "Interest rates / monetary policy": [
        "interest rate", "interest rates", "federal reserve", "fed",
        "rate cut", "rate hike", "monetary policy", "inflation",
    ],
    "Consumer demand": [
        "consumer demand", "consumer spending", "retail sales",
        "customer demand", "e-commerce", "shopping", "consumer",
    ],
    "Supply chain / costs": [
        "supply chain", "shortage", "component costs", "costs",
        "cost pressure", "manufacturing", "production", "tariff", "tariffs",
    ],
}


# ============================================================
# VALIDATION / INPUT
# ============================================================

def validate_api_keys():
    missing = []

    if not FINNHUB_API_KEY:
        missing.append("FINNHUB_API_KEY")

    if not MARKETAUX_API_KEY:
        missing.append("MARKETAUX_API_KEY")

    if missing:
        raise RuntimeError(
            "Missing API key(s): "
            + ", ".join(missing)
            + ". Put them in environment variables or a .env file."
        )


def validate_portfolio(data):
    """Validate and normalize the portfolio JSON structure."""
    if not isinstance(data, dict):
        raise ValueError("Portfolio input must be a JSON object.")

    portfolio = data.get("portfolio")
    if not isinstance(portfolio, dict):
        raise ValueError("Portfolio JSON must contain a 'portfolio' object.")

    holdings = portfolio.get("holdings")
    if not isinstance(holdings, list):
        raise ValueError(
            "Portfolio JSON must contain 'portfolio.holdings' as a list."
        )

    if not holdings:
        raise ValueError("Portfolio must contain at least one holding.")

    normalized = []

    for index, holding in enumerate(holdings):
        if not isinstance(holding, dict):
            raise ValueError(f"Holding #{index + 1} must be an object.")

        ticker = str(holding.get("ticker", "")).strip().upper()
        company_name = str(holding.get("company_name", ticker)).strip()

        if not ticker:
            raise ValueError(f"Holding #{index + 1} is missing 'ticker'.")

        if "shares_owned" not in holding:
            raise ValueError(
                f"Holding {ticker} is missing 'shares_owned'."
            )

        try:
            shares = float(holding["shares_owned"])
        except (TypeError, ValueError):
            raise ValueError(
                f"Holding {ticker} has invalid 'shares_owned'."
            )

        if shares < 0:
            raise ValueError(
                f"Holding {ticker} has negative 'shares_owned'."
            )

        normalized.append({
            **holding,
            "ticker": ticker,
            "company_name": company_name,
            "shares_owned": shares,
        })

    return {
        **data,
        "portfolio": {
            **portfolio,
            "holdings": normalized,
        },
    }


def parse_portfolio_input(portfolio_json=None, portfolio_file=None):
    """
    Load portfolio data from:
      - a Python dict passed to analyze_portfolio()
      - a JSON string
      - a file
      - stdin

    CLI convenience:
      --portfolio-json '{"portfolio": {...}}'
      --portfolio-file portfolio.json
      echo '{...}' | python portfolio_analyzer_v6.py
    """
    if portfolio_json and portfolio_file:
        raise ValueError(
            "Use either --portfolio-json or --portfolio-file, not both."
        )

    if portfolio_json:
        try:
            return validate_portfolio(json.loads(portfolio_json))
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"--portfolio-json is not valid JSON: {exc}"
            )

    if portfolio_file:
        with open(portfolio_file, "r", encoding="utf-8") as file:
            return validate_portfolio(json.load(file))

    if not sys.stdin.isatty():
        raw = sys.stdin.read().strip()
        if raw:
            try:
                return validate_portfolio(json.loads(raw))
            except json.JSONDecodeError as exc:
                raise ValueError(f"stdin is not valid JSON: {exc}")

    # Backwards-compatible fallback.
    legacy_file = "portfolio.json"
    if os.path.exists(legacy_file):
        with open(legacy_file, "r", encoding="utf-8") as file:
            return validate_portfolio(json.load(file))

    raise ValueError(
        "No portfolio supplied. Use --portfolio-json, --portfolio-file, "
        "stdin, or provide portfolio.json."
    )


# ============================================================
# MARKET DATA
# ============================================================

def get_finnhub_quote(ticker):
    params = {"symbol": ticker}
    headers = {"X-Finnhub-Token": FINNHUB_API_KEY}

    try:
        response = requests.get(
            FINNHUB_URL,
            params=params,
            headers=headers,
            timeout=15,
        )

        if response.status_code == 401:
            raise RuntimeError(
                "Finnhub returned HTTP 401 Unauthorized. "
                "Check FINNHUB_API_KEY."
            )

        if response.status_code == 429:
            print(
                f"WARNING: Finnhub rate limit reached for {ticker}.",
                file=sys.stderr,
            )
            return None

        response.raise_for_status()
        data = response.json()

        current_price = data.get("c")
        previous_price = data.get("pc")
        daily_change_percent = data.get("dp")

        if current_price is None or previous_price is None:
            print(
                f"WARNING: Missing price data for {ticker}.",
                file=sys.stderr,
            )
            return None

        return {
            "current_price": float(current_price),
            "previous_price": float(previous_price),
            "daily_change_percent": (
                float(daily_change_percent)
                if daily_change_percent is not None
                else None
            ),
        }

    except requests.exceptions.RequestException as error:
        print(
            f"WARNING: Finnhub request failed for {ticker}: {error}",
            file=sys.stderr,
        )
        return None


# ============================================================
# NEWS
# ============================================================

def get_marketaux_news(ticker, lookback_hours=NEWS_LOOKBACK_HOURS):
    """Retrieve recent news, widening the search if the first query is empty."""

    def request_news(params):
        try:
            response = requests.get(MARKETAUX_URL, params=params, timeout=15)

            if response.status_code == 401:
                raise RuntimeError(
                    "Marketaux returned HTTP 401 Unauthorized. "
                    "Check MARKETAUX_API_KEY."
                )

            if response.status_code == 429:
                print(
                    f"WARNING: Marketaux rate limit reached for {ticker}.",
                    file=sys.stderr,
                )
                return []

            if response.status_code != 200:
                print(
                    f"WARNING: Marketaux returned HTTP "
                    f"{response.status_code} for {ticker}",
                    file=sys.stderr,
                )
                return []

            return response.json().get("data", [])

        except requests.RequestException as error:
            print(
                f"WARNING: Marketaux request failed for {ticker}: {error}",
                file=sys.stderr,
            )
            return []

    def build_params(hours=None):
        params = {
            "api_token": MARKETAUX_API_KEY,
            "symbols": ticker,
            "language": "en",
            "filter_entities": "true",
            "limit": NEWS_LIMIT,
        }

        if hours is not None:
            published_after = (
                datetime.now(timezone.utc) - timedelta(hours=hours)
            ).strftime("%Y-%m-%dT%H:%M:%S")
            params["published_after"] = published_after

        return params

    articles = request_news(build_params(lookback_hours))
    if articles:
        return articles

    if lookback_hours < 24 * 7:
        print(
            f"  No recent Marketaux news for {ticker}; "
            f"retrying with 7-day lookback...",
            file=sys.stderr,
        )
        articles = request_news(build_params(24 * 7))
        if articles:
            return articles

    print(
        f"  Still no Marketaux news for {ticker}; "
        f"retrying without published_after...",
        file=sys.stderr,
    )
    return request_news(build_params(None))


# ============================================================
# TEXT / RELEVANCE / SENTIMENT
# ============================================================

def normalize_text(text):
    if not text:
        return ""
    return re.sub(r"\s+", " ", str(text).lower()).strip()


def calculate_relevance(article, ticker, company_name):
    """Score article relevance, while distinguishing direct mentions from weak API matches."""
    title = article.get("title") or ""
    description = article.get("description") or ""

    title_lower = normalize_text(title)
    description_lower = normalize_text(description)
    company_lower = normalize_text(company_name)
    ticker_pattern = r"\b" + re.escape(ticker.lower()) + r"\b"

    ticker_in_title = bool(re.search(ticker_pattern, title_lower))
    ticker_in_description = bool(re.search(ticker_pattern, description_lower))
    company_in_title = bool(company_lower and company_lower in title_lower)
    company_in_description = bool(company_lower and company_lower in description_lower)

    entity_match_score = 0.0
    entity_found = False
    for entity in article.get("entities", []):
        if str(entity.get("symbol", "")).upper() == ticker.upper():
            entity_found = True
            value = entity.get("match_score")
            try:
                entity_match_score = float(value) if value is not None else 0.0
            except (TypeError, ValueError):
                entity_match_score = 0.0
            break

    # Hard relevance gate: Marketaux can occasionally return an article because
    # the requested symbol is a weak/secondary match. Do not surface those as
    # explanations unless the article actually mentions the company/ticker or
    # has a strong entity match.
    directly_relevant = (
        ticker_in_title
        or company_in_title
        or ticker_in_description
        or company_in_description
        or (entity_found and entity_match_score >= 0.50)
    )

    score = 0.0
    if ticker_in_title:
        score += 8
    if company_in_title:
        score += 7
    if ticker_in_description:
        score += 4
    if company_in_description:
        score += 4
    if entity_found:
        score += min(entity_match_score * 3, 3)

    relevance = min(score / 22, 1.0)
    return round(relevance, 3), directly_relevant


def get_entity_sentiment(article, ticker):
    for entity in article.get("entities", []):
        if entity.get("symbol") == ticker:
            sentiment = entity.get("sentiment_score")
            if sentiment is not None:
                try:
                    return float(sentiment)
                except (TypeError, ValueError):
                    return None
    return None


def sentiment_direction(sentiment):
    if sentiment is None:
        return "unknown"
    if sentiment >= 0.10:
        return "positive"
    if sentiment <= -0.10:
        return "negative"
    return "neutral"


def price_direction(daily_change_percent):
    if daily_change_percent is None:
        return "unknown"
    if daily_change_percent > 0:
        return "up"
    if daily_change_percent < 0:
        return "down"
    return "flat"


def determine_alignment(sentiment, daily_change_percent):
    if sentiment is None or daily_change_percent is None:
        return "unknown"

    news_direction = sentiment_direction(sentiment)
    market_direction = price_direction(daily_change_percent)

    if news_direction == "positive" and market_direction == "up":
        return "aligned_positive"

    if news_direction == "negative" and market_direction == "down":
        return "aligned_negative"

    if news_direction in {"positive", "negative"}:
        if (
            (news_direction == "positive" and market_direction == "down")
            or (news_direction == "negative" and market_direction == "up")
        ):
            return "conflicting"

    return "neutral_or_unclear"


def identify_forces(article):
    title = article.get("title") or ""
    description = article.get("description") or ""

    combined_text = normalize_text(f"{title} {description}")
    detected_forces = []

    for force, keywords in FORCE_KEYWORDS.items():
        if any(keyword.lower() in combined_text for keyword in keywords):
            detected_forces.append(force)

    return detected_forces


# ============================================================
# PROCESS NEWS FOR ONE HOLDING
# ============================================================

def _score_and_build_article(article, ticker, daily_change_percent):
    sentiment = get_entity_sentiment(article, ticker)
    forces = identify_forces(article)

    return {
        "title": article.get("title"),
        "source": article.get("source"),
        "published_at": article.get("published_at"),
        "description": article.get("description"),
        "url": article.get("url"),
        "sentiment": sentiment,
        "sentiment_direction": sentiment_direction(sentiment),
        "relevance_score": article["_relevance_score"],
        "market_alignment": determine_alignment(
            sentiment,
            daily_change_percent,
        ),
        "identified_forces": forces,
        # Kept for forward-compatibility with any future fallback tier;
        # every article that reaches here has passed the strict gate.
        "match_strength": "strong",
    }


def _article_rank(item):
    published_at = item.get("published_at") or ""

    try:
        published_dt = datetime.fromisoformat(
            published_at.replace("Z", "+00:00")
        )
        age_hours = max(
            0,
            (datetime.now(timezone.utc) - published_dt).total_seconds()
            / 3600,
        )
    except (ValueError, TypeError):
        age_hours = 9999

    recency_bonus = max(0.0, 1.0 - age_hours / (24 * 7))

    return (
        item["relevance_score"] * 10
        + recency_bonus * 2
        + abs(item["sentiment"] or 0)
    )


def process_news(
    ticker,
    company_name,
    sector,
    daily_change_percent,
):
    raw_articles = get_marketaux_news(ticker)

    strict_matches = []

    for article in raw_articles:
        relevance, directly_relevant = calculate_relevance(
            article,
            ticker,
            company_name,
        )
        article["_relevance_score"] = relevance

        # Never treat a weak/secondary Marketaux match as explanatory
        # news: a low entity match_score is not enough on its own, and
        # in practice such articles are often about a different company
        # entirely. Only direct mentions (ticker/company in title or
        # description) or a strong entity match count.
        if directly_relevant and relevance >= STRICT_RELEVANCE_THRESHOLD:
            strict_matches.append(article)

    news_results = []
    match_tier = "strong" if strict_matches else None

    for article in strict_matches:
        news_results.append(
            _score_and_build_article(article, ticker, daily_change_percent)
        )
    news_results.sort(key=_article_rank, reverse=True)
    news_results = news_results[:MAX_ARTICLES_PER_STOCK]

    force_evidence = {}

    for article in news_results:
        for force in article["identified_forces"]:
            if force not in force_evidence:
                force_evidence[force] = {
                    "force": force,
                    "sector": sector,
                    "ticker": ticker,
                    "evidence_count": 0,
                    "positive_evidence": 0,
                    "negative_evidence": 0,
                    "neutral_evidence": 0,
                    "articles": [],
                }

            record = force_evidence[force]
            record["evidence_count"] += 1

            direction = article["sentiment_direction"]

            if direction == "positive":
                record["positive_evidence"] += 1
            elif direction == "negative":
                record["negative_evidence"] += 1
            else:
                record["neutral_evidence"] += 1

            record["articles"].append({
                "title": article["title"],
                "source": article["source"],
                "published_at": article["published_at"],
                "url": article["url"],
                "sentiment": article["sentiment"],
                "relevance_score": article["relevance_score"],
                "market_alignment": article["market_alignment"],
                "match_strength": article["match_strength"],
            })

    return news_results, force_evidence, match_tier


def determine_force_direction(force_record):
    positive = force_record["positive_evidence"]
    negative = force_record["negative_evidence"]

    if positive + negative == 0:
        return "unknown"

    if positive > 0 and negative > 0:
        return "mixed"

    if positive > negative:
        return "positive"

    if negative > positive:
        return "negative"

    return "mixed"


# ============================================================
# OUTPUT HELPERS
# ============================================================

def create_sector_record():
    return {
        "holdings": [],
        "previous_value": 0.0,
        "current_value": 0.0,
        "daily_impact": 0.0,
        "daily_return_percent": 0.0,
        "forces": {},
    }


def build_news_explanation(ticker, daily_change_percent, article):
    """Create a concise, non-causal explanation for the dashboard strip."""

    move = (
        f"{daily_change_percent:+.2f}%"
        if daily_change_percent is not None
        else "unknown"
    )

    # No article at all for this focus ticker.
    if article is None:
        return (
            f"{ticker} {move} — no relevant news explanation found for "
            f"this move."
        )

    direction = article.get("sentiment_direction", "unknown")
    forces = article.get("identified_forces") or []
    force_text = ", ".join(forces[:2])
    alignment = article.get("market_alignment")

    if force_text:
        if alignment == "aligned_positive":
            return (
                f"{ticker} {move} — positive coverage around "
                f"{force_text.lower()} is consistent with the move."
            )
        if alignment == "aligned_negative":
            return (
                f"{ticker} {move} — negative coverage around "
                f"{force_text.lower()} is consistent with the move."
            )
        if alignment == "conflicting":
            return (
                f"{ticker} {move} — coverage highlights "
                f"{force_text.lower()}, but article sentiment conflicts "
                f"with the price direction."
            )
        return f"{ticker} {move} — recent coverage highlights {force_text.lower()}."

    if alignment == "aligned_positive":
        return f"{ticker} {move} — recent coverage is positive and consistent with the move."

    if alignment == "aligned_negative":
        return f"{ticker} {move} — recent coverage is negative and consistent with the move."

    if alignment == "conflicting":
        return (
            f"{ticker} {move} — article sentiment conflicts with the price "
            f"direction; the news is not a clear explanation."
        )

    if direction == "positive":
        return f"{ticker} {move} — recent coverage is positive, though the link to the move is unclear."

    if direction == "negative":
        return f"{ticker} {move} — recent coverage is negative, though the link to the move is unclear."

    return f"{ticker} {move} — relevant coverage found, but no clear directional signal."


def build_news_strip(analysis_results, news_focus_tickers):
    """
    Compact frontend payload.

    Every ticker in news_focus_tickers gets exactly one entry (or, if it
    has multiple articles, up to MAX_STRIP_ARTICLES_PER_HOLDING). If a
    focus ticker has no qualifying article at all, it still gets a
    placeholder entry so the strip never silently drops the stock that
    moved the portfolio the most.
    """
    strip = []

    by_ticker = {
        item["ticker"]: item
        for item in analysis_results
    }

    for ticker in news_focus_tickers:
        holding = by_ticker.get(ticker)
        if not holding:
            continue

        market = holding["market_data"]
        articles = holding["financial_news"][:MAX_STRIP_ARTICLES_PER_HOLDING]

        if not articles:
            # Placeholder: keep the ticker visible in the strip even when
            # no article cleared either relevance bar.
            strip.append({
                "ticker": ticker,
                "company_name": holding["company_name"],
                "impact": market["portfolio_impact"],
                "daily_change_percent": market["daily_change_percent"],
                "title": None,
                "source": None,
                "published_at": None,
                "url": None,
                "sentiment": None,
                "sentiment_direction": "unknown",
                "market_alignment": "unknown",
                "identified_forces": [],
                "match_strength": None,
                "has_news": False,
                "explanation": build_news_explanation(
                    ticker=ticker,
                    daily_change_percent=market["daily_change_percent"],
                    article=None,
                ),
            })
            continue

        for article in articles:
            strip.append({
                "ticker": ticker,
                "company_name": holding["company_name"],
                "impact": market["portfolio_impact"],
                "daily_change_percent": market["daily_change_percent"],
                "title": article["title"],
                "source": article["source"],
                "published_at": article["published_at"],
                "url": article["url"],
                "sentiment": article["sentiment"],
                "sentiment_direction": article["sentiment_direction"],
                "market_alignment": article["market_alignment"],
                "identified_forces": article["identified_forces"],
                "match_strength": article["match_strength"],
                "has_news": True,
                "explanation": build_news_explanation(
                    ticker=ticker,
                    daily_change_percent=market["daily_change_percent"],
                    article=article,
                ),
            })


    strip.sort(
        key=lambda item: (
            abs(item["impact"] or 0),
            abs(item["sentiment"] or 0),
        ),
        reverse=True,
    )

    return strip




def analyze_portfolio(portfolio_data):
    """
    Analyze a portfolio supplied as a Python dict.

    This is the main entry point for a UI, API endpoint, notebook,
    or another Python application.

    Expected input:

    {
        "portfolio": {
            "account_id": "optional",
            "currency": "USD",
            "holdings": [
                {
                    "ticker": "AAPL",
                    "company_name": "Apple Inc.",
                    "shares_owned": 100
                }
            ]
        }
    }

    Returns a Python dict containing portfolio analysis, including
    a compact news_strip for the frontend.
    """
    validate_api_keys()
    portfolio_data = validate_portfolio(portfolio_data)

    portfolio = portfolio_data["portfolio"]
    holdings = portfolio["holdings"]

    analysis_results = []
    sector_summary = {}
    force_summary = {}
    skipped_holdings = []

    # --------------------------------------------------------
    # PHASE 1: Get market data for ALL holdings.
    #
    # We must do this before requesting news because "top five
    # most impacted" is based on actual dollar impact.
    # --------------------------------------------------------

    for holding in holdings:
        ticker = holding["ticker"]
        company_name = holding["company_name"]
        shares = float(holding["shares_owned"])
        sector = SECTORS.get(ticker, "Unknown")

        print(f"Analyzing market data for {ticker}...")

        market_data = get_finnhub_quote(ticker)

        if market_data is None:
            skipped_holdings.append(ticker)
            time.sleep(API_DELAY_SECONDS)
            continue

        current_price = market_data["current_price"]
        previous_price = market_data["previous_price"]
        daily_change_percent = market_data["daily_change_percent"]

        current_value = shares * current_price
        previous_value = shares * previous_price
        daily_change_amount = current_value - previous_value

        stock_result = {
            "ticker": ticker,
            "company_name": company_name,
            "sector": sector,
            "shares_owned": shares,
            "market_data": {
                "current_price": round(current_price, 4),
                "previous_price": round(previous_price, 4),
                "daily_change_percent": (
                    round(daily_change_percent, 4)
                    if daily_change_percent is not None
                    else None
                ),
                "previous_value": round(previous_value, 2),
                "current_value": round(current_value, 2),
                "daily_change_amount": round(daily_change_amount, 2),
                "portfolio_impact": round(daily_change_amount, 2),
            },

            # Filled in only for the top five most impacted holdings.
            "financial_news": [],
            "identified_forces": [],
            "news_analyzed": False,
        }

        analysis_results.append(stock_result)

        if sector not in sector_summary:
            sector_summary[sector] = create_sector_record()

        sector_record = sector_summary[sector]
        sector_record["holdings"].append(ticker)
        sector_record["previous_value"] += previous_value
        sector_record["current_value"] += current_value
        sector_record["daily_impact"] += daily_change_amount

        time.sleep(API_DELAY_SECONDS)

    # --------------------------------------------------------
    # PHASE 2: Select the five most impacted holdings
    # --------------------------------------------------------

    impact_ranked = sorted(
        analysis_results,
        key=lambda item: abs(
            item["market_data"]["daily_change_amount"]
        ),
        reverse=True,
    )

    news_focus = impact_ranked[:MAX_NEWS_HOLDINGS]
    news_focus_tickers = [item["ticker"] for item in news_focus]

    print(
        "\nNews focus: "
        + (", ".join(news_focus_tickers) if news_focus_tickers else "none")
    )

    # --------------------------------------------------------
    # PHASE 3: Retrieve news only for those five holdings.
    # --------------------------------------------------------

    for item in news_focus:
        ticker = item["ticker"]

        print(f"Retrieving news for {ticker}...")

        news_results, force_evidence, match_tier = process_news(
            ticker=ticker,
            company_name=item["company_name"],
            sector=item["sector"],
            daily_change_percent=item["market_data"][
                "daily_change_percent"
            ],
        )

        item["financial_news"] = news_results
        item["identified_forces"] = list(force_evidence.keys())
        item["news_analyzed"] = True
        item["news_match_tier"] = match_tier

        if match_tier == "strong":
            item["news_status"] = "relevant_news_found"
        else:
            item["news_status"] = (
                "No sufficiently relevant Marketaux article was found "
                "for the selected lookback windows."
            )

        daily_change_amount = item["market_data"]["daily_change_amount"]
        daily_change_percent = item["market_data"]["daily_change_percent"]

        for force, evidence in force_evidence.items():
            force_direction = determine_force_direction(evidence)

            if force not in force_summary:
                force_summary[force] = {
                    "force": force,
                    "direction": force_direction,
                    "affected_holdings": [],
                    "sectors": [],
                    "evidence_count": 0,
                    "observed_stock_impacts": [],
                    "articles": [],
                }

            force_record = force_summary[force]

            if ticker not in force_record["affected_holdings"]:
                force_record["affected_holdings"].append(ticker)

            if item["sector"] not in force_record["sectors"]:
                force_record["sectors"].append(item["sector"])

            force_record["evidence_count"] += evidence["evidence_count"]

            force_record["observed_stock_impacts"].append({
                "ticker": ticker,
                "impact": round(daily_change_amount, 2),
                "daily_change_percent": (
                    round(daily_change_percent, 4)
                    if daily_change_percent is not None
                    else None
                ),
            })

            force_record["articles"].extend(evidence["articles"])

        time.sleep(API_DELAY_SECONDS)

    # --------------------------------------------------------
    # Portfolio totals
    # --------------------------------------------------------

    previous_portfolio_value = sum(
        item["market_data"]["previous_value"]
        for item in analysis_results
    )

    current_portfolio_value = sum(
        item["market_data"]["current_value"]
        for item in analysis_results
    )

    total_portfolio_impact = (
        current_portfolio_value - previous_portfolio_value
    )

    if previous_portfolio_value:
        portfolio_change_percent = (
            total_portfolio_impact / previous_portfolio_value
        ) * 100
    else:
        portfolio_change_percent = 0.0

    # --------------------------------------------------------
    # Sector calculations
    # --------------------------------------------------------

    for sector, data in sector_summary.items():
        previous_value = data["previous_value"]
        current_value = data["current_value"]
        daily_impact = data["daily_impact"]

        if previous_value:
            daily_return = daily_impact / previous_value * 100
        else:
            daily_return = 0.0

        data["previous_value"] = round(previous_value, 2)
        data["current_value"] = round(current_value, 2)
        data["daily_impact"] = round(daily_impact, 2)
        data["daily_return_percent"] = round(daily_return, 4)

    # --------------------------------------------------------
    # Force cleanup
    # --------------------------------------------------------

    for force, data in force_summary.items():
        positive_count = 0
        negative_count = 0

        for article in data["articles"]:
            direction = sentiment_direction(article.get("sentiment"))

            if direction == "positive":
                positive_count += 1
            elif direction == "negative":
                negative_count += 1

        if positive_count and negative_count:
            final_direction = "mixed"
        elif positive_count > negative_count:
            final_direction = "positive"
        elif negative_count > positive_count:
            final_direction = "negative"
        else:
            final_direction = "unknown"

        data["direction"] = final_direction

    # --------------------------------------------------------
    # Contributors
    # --------------------------------------------------------

    sorted_holdings = sorted(
        analysis_results,
        key=lambda item: item["market_data"]["daily_change_amount"],
        reverse=True,
    )

    top_positive = [
        {
            "ticker": item["ticker"],
            "impact": item["market_data"]["daily_change_amount"],
        }
        for item in sorted_holdings
        if item["market_data"]["daily_change_amount"] > 0
    ][:5]

    top_negative = [
        {
            "ticker": item["ticker"],
            "impact": item["market_data"]["daily_change_amount"],
        }
        for item in sorted_holdings
        if item["market_data"]["daily_change_amount"] < 0
    ][:5]

    # --------------------------------------------------------
    # Force buckets
    # --------------------------------------------------------

    forces_up = []
    forces_down = []
    forces_mixed = []

    for force, data in force_summary.items():
        item = {
            "force": force,
            "direction": data["direction"],
            "affected_holdings": data["affected_holdings"],
            "sectors": data["sectors"],
            "evidence_count": data["evidence_count"],
            "observed_stock_impacts": data["observed_stock_impacts"],
        }

        if data["direction"] == "positive":
            forces_up.append(item)
        elif data["direction"] == "negative":
            forces_down.append(item)
        elif data["direction"] == "mixed":
            forces_mixed.append(item)

    # --------------------------------------------------------
    # Compact news strip
    # --------------------------------------------------------

    news_strip = build_news_strip(
        analysis_results,
        news_focus_tickers,
    )

    portfolio_analysis = {
        "generated_at": datetime.now(timezone.utc).isoformat(),

        "portfolio": {
            "account_id": portfolio.get("account_id"),
            "currency": portfolio.get("currency"),
        },

        "portfolio_summary": {
            "previous_portfolio_value": round(
                previous_portfolio_value, 2
            ),
            "current_portfolio_value": round(
                current_portfolio_value, 2
            ),
            "total_daily_impact": round(
                total_portfolio_impact, 2
            ),
            "daily_change_percent": round(
                portfolio_change_percent, 4
            ),
            "holdings_analyzed": len(analysis_results),
            "holdings_skipped": len(skipped_holdings),
            "skipped_tickers": skipped_holdings,
        },

        # Frontend can render this directly as a horizontal strip.
        # Guaranteed to contain one entry per focus ticker (real
        # article or "no news found" placeholder).
        "news_strip": {
            "max_holdings": MAX_NEWS_HOLDINGS,
            "focus_tickers": news_focus_tickers,
            "articles": news_strip,
        },

        "top_positive_contributors": top_positive,
        "top_negative_contributors": top_negative,
        "sector_summary": sector_summary,
        "holdings": analysis_results,
    }

    # --------------------------------------------------------
    # RAG / evidence output
    # --------------------------------------------------------

    rag_evidence = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "method": (
            "retrieval + relevance filtering "
            "+ rule-based force identification"
        ),
        "important_note": (
            "Observed stock/portfolio impacts are calculated from "
            "market prices. News evidence does not by itself prove "
            "causation. A holding with news_analyzed=true but no "
            "news_evidence means no article cleared the relevance bar "
            "for this move; no low-confidence guesses are substituted."
        ),
        "news_scope": {
            "strategy": "top_absolute_dollar_impact",
            "max_holdings": MAX_NEWS_HOLDINGS,
            "focus_tickers": news_focus_tickers,
        },
        "portfolio": {
            "account_id": portfolio.get("account_id"),
            "currency": portfolio.get("currency"),
            "previous_value": round(previous_portfolio_value, 2),
            "current_value": round(current_portfolio_value, 2),
            "daily_impact": round(total_portfolio_impact, 2),
            "daily_change_percent": round(
                portfolio_change_percent, 4
            ),
        },
        "forces_pushing_up": forces_up,
        "forces_pushing_down": forces_down,
        "forces_mixed_or_unclear": forces_mixed,
        "sector_evidence": {},
        "holding_evidence": [],
    }

    for sector, data in sector_summary.items():
        sector_forces = []

        for force, force_data in force_summary.items():
            if sector in force_data["sectors"]:
                sector_forces.append({
                    "force": force,
                    "direction": force_data["direction"],
                    "affected_holdings": [
                        ticker
                        for ticker in force_data["affected_holdings"]
                        if ticker in data["holdings"]
                    ],
                    "evidence_count": force_data["evidence_count"],
                    "observed_stock_impacts": [
                        item
                        for item in force_data["observed_stock_impacts"]
                        if item["ticker"] in data["holdings"]
                    ],
                })

        rag_evidence["sector_evidence"][sector] = {
            "sector_return_percent": data["daily_return_percent"],
            "sector_daily_impact": data["daily_impact"],
            "holdings": data["holdings"],
            "forces": sector_forces,
        }

    for holding in analysis_results:
        market = holding["market_data"]

        rag_evidence["holding_evidence"].append({
            "ticker": holding["ticker"],
            "company_name": holding["company_name"],
            "sector": holding["sector"],
            "shares_owned": holding["shares_owned"],
            "observed_market_move": {
                "price_change_percent": market["daily_change_percent"],
                "portfolio_impact": market["portfolio_impact"],
            },
            "news_analyzed": holding["news_analyzed"],
            "news_status": holding.get("news_status"),
            "news_match_tier": holding.get("news_match_tier"),
            "identified_forces": holding["identified_forces"],
            "news_evidence": holding["financial_news"],
        })

    return {
        "portfolio_analysis": portfolio_analysis,
        "rag_evidence": rag_evidence,
    }


# ============================================================
# FILE OUTPUT
# ============================================================

def save_results(results, analysis_path="portfolio_analysis.json",
                 evidence_path="portfolio_evidence.json"):
    with open(analysis_path, "w", encoding="utf-8") as file:
        json.dump(
            results["portfolio_analysis"],
            file,
            indent=4,
            ensure_ascii=False,
        )

    with open(evidence_path, "w", encoding="utf-8") as file:
        json.dump(
            results["rag_evidence"],
            file,
            indent=4,
            ensure_ascii=False,
        )


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Analyze a portfolio and explain major moves with news."
    )

    parser.add_argument(
        "--portfolio-json",
        help="Portfolio JSON supplied directly as a JSON string.",
    )

    parser.add_argument(
        "--portfolio-file",
        help="Path to a JSON file containing the portfolio.",
    )

    parser.add_argument(
        "--analysis-output",
        default="portfolio_analysis.json",
        help="Output path for the portfolio analysis JSON.",
    )

    parser.add_argument(
        "--evidence-output",
        default="portfolio_evidence.json",
        help="Output path for the RAG evidence JSON.",
    )

    args = parser.parse_args()

    try:
        portfolio_data = parse_portfolio_input(
            portfolio_json=args.portfolio_json,
            portfolio_file=args.portfolio_file,
        )

        results = analyze_portfolio(portfolio_data)

        save_results(
            results,
            analysis_path=args.analysis_output,
            evidence_path=args.evidence_output,
        )

        analysis = results["portfolio_analysis"]
        summary = analysis["portfolio_summary"]

        print("\n" + "=" * 60)
        print("PORTFOLIO ANALYSIS COMPLETED")
        print("=" * 60)
        print(
            f"Previous portfolio value: "
            f"${summary['previous_portfolio_value']:,.2f}"
        )
        print(
            f"Current portfolio value:  "
            f"${summary['current_portfolio_value']:,.2f}"
        )
        print(
            f"Daily portfolio impact:    "
            f"${summary['total_daily_impact']:,.2f}"
        )
        print(
            f"Daily portfolio change:    "
            f"{summary['daily_change_percent']:.3f}%"
        )

        print(
            "\nNews analyzed for: "
            + (
                ", ".join(analysis["news_strip"]["focus_tickers"])
                if analysis["news_strip"]["focus_tickers"]
                else "none"
            )
        )

        print(f"\nCreated: {args.analysis_output}")
        print(f"Created: {args.evidence_output}")
        print("\nRESULT_JSON")
        print(json.dumps(analysis, ensure_ascii=False))

    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()