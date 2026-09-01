import json
import os
import re
import time
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv


# ============================================================
# PORTFOLIO ANALYSIS
# ============================================================
#
# What this program does:
#
# 1. Loads the user's portfolio
# 2. Retrieves current stock prices from Finnhub
# 3. Calculates the actual dollar impact of each holding
# 4. Retrieves recent financial news from Marketaux
# 5. Filters news for relevance
# 6. Identifies possible "forces" affecting each company
# 7. Groups those forces by sector
# 8. Calculates portfolio and sector contributions
# 9. Creates two JSON files:
#
#       portfolio_analysis.json
#       portfolio_evidence.json
#
# portfolio_analysis.json
#     -> clean portfolio / market analysis
#
# portfolio_evidence.json
#     -> structured evidence for the future RAG + LLM stage
#
# IMPORTANT:
# This program does NOT claim that a news article caused
# a stock's price movement.
#
# Instead, it records:
#
#     OBSERVED MARKET IMPACT
#         +
#     AVAILABLE NEWS EVIDENCE
#
# The future LLM will use this evidence to produce the
# manager-style explanation.
#
# ============================================================


# ============================================================
# LOAD ENVIRONMENT VARIABLES
# ============================================================

load_dotenv()

FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")
MARKETAUX_API_KEY = os.getenv("MARKETAUX_API_KEY")


# ============================================================
# API URLS
# ============================================================

FINNHUB_URL = "https://finnhub.io/api/v1/quote"

MARKETAUX_URL = "https://api.marketaux.com/v1/news/all"


# ============================================================
# BASIC SETTINGS
# ============================================================

# Number of news articles to request per company.
NEWS_LIMIT = 10

# How far back we search for news.
#
# We use 48 hours rather than exactly 24 hours because:
#
# - news can be published at different times
# - markets may be closed
# - some relevant articles can appear shortly before
#   the trading day
#
NEWS_LOOKBACK_HOURS = 48

# Maximum number of articles retained for each company
# after relevance filtering.
MAX_ARTICLES_PER_STOCK = 5

# Small delay between API requests.
#
# This helps avoid hitting API rate limits unnecessarily.
API_DELAY_SECONDS = 0.25


# ============================================================
# SECTOR MAPPING
# ============================================================

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
    "V": "Financials"
}


# ============================================================
# FORCE / DRIVER DEFINITIONS
# ============================================================
#
# These are simple transparent rules.
#
# We are NOT asking an LLM to invent drivers yet.
#
# We search the article title + description for keywords.
#
# Later, the RAG + LLM stage can provide a more sophisticated
# interpretation of these forces.
#
# ============================================================

FORCE_KEYWORDS = {

    "AI demand": [
        "artificial intelligence",
        "artificial-intelligence",
        "ai demand",
        "ai chip",
        "ai chips",
        "ai infrastructure",
        "generative ai",
        "gen ai",
        "data center",
        "data centre",
        "accelerator",
        "gpu"
    ],

    "Earnings / revenue": [
        "earnings",
        "revenue",
        "profit",
        "profits",
        "sales",
        "guidance",
        "forecast",
        "outlook",
        "quarter",
        "quarterly",
        "eps"
    ],

    "Analyst / investor sentiment": [
        "analyst",
        "analysts",
        "price target",
        "upgrade",
        "downgrade",
        "investor sentiment",
        "investor confidence",
        "wall street"
    ],

    "Regulation": [
        "regulation",
        "regulatory",
        "regulator",
        "antitrust",
        "lawsuit",
        "government",
        "legislation",
        "compliance",
        "investigation",
        "probe",
        "ban",
        "restriction"
    ],

    "Product / technology developments": [
        "product launch",
        "new product",
        "technology",
        "technology development",
        "innovation",
        "software",
        "hardware",
        "device",
        "platform",
        "release"
    ],

    "Corporate / strategic activity": [
        "acquisition",
        "acquire",
        "merger",
        "partnership",
        "deal",
        "agreement",
        "strategic",
        "restructuring",
        "buyback",
        "dividend"
    ],

    "Healthcare / drug developments": [
        "drug",
        "drug trial",
        "clinical trial",
        "fda",
        "approval",
        "therapy",
        "treatment",
        "medicine",
        "pharmaceutical",
        "obesity",
        "diabetes"
    ],

    "Interest rates / monetary policy": [
        "interest rate",
        "interest rates",
        "federal reserve",
        "fed",
        "rate cut",
        "rate hike",
        "monetary policy",
        "inflation"
    ],

    "Consumer demand": [
        "consumer demand",
        "consumer spending",
        "retail sales",
        "customer demand",
        "e-commerce",
        "shopping",
        "consumer"
    ],

    "Supply chain / costs": [
        "supply chain",
        "shortage",
        "component costs",
        "costs",
        "cost pressure",
        "manufacturing",
        "production",
        "tariff",
        "tariffs"
    ]
}


# ============================================================
# CHECK API KEYS
# ============================================================

def validate_api_keys():

    """
    Make sure the required API keys exist.

    We do not print the actual keys.
    """

    missing = []

    if not FINNHUB_API_KEY:
        missing.append("FINNHUB_API_KEY")

    if not MARKETAUX_API_KEY:
        missing.append("MARKETAUX_API_KEY")

    if missing:

        raise RuntimeError(
            "Missing API key(s): "
            + ", ".join(missing)
            + "\n\n"
            "Please check your .env file."
        )


# ============================================================
# LOAD PORTFOLIO
# ============================================================

def load_portfolio():

    """
    Load portfolio.json.

    Expected structure:

    {
        "portfolio": {
            "account_id": "...",
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
    """

    filename = "portfolio.json"

    if not os.path.exists(filename):

        raise FileNotFoundError(
            f"Could not find {filename}."
        )

    with open(
        filename,
        "r",
        encoding="utf-8"
    ) as file:

        data = json.load(file)

    if "portfolio" not in data:

        raise ValueError(
            "portfolio.json does not contain "
            "'portfolio'."
        )

    if "holdings" not in data["portfolio"]:

        raise ValueError(
            "portfolio.json does not contain "
            "'portfolio.holdings'."
        )

    return data


# ============================================================
# FINNHUB: GET STOCK QUOTE
# ============================================================

def get_finnhub_quote(ticker):

    """
    Retrieve the current quote from Finnhub.

    Finnhub returns:

        c  = current price
        pc = previous close
        dp = daily percentage change

    We authenticate using the X-Finnhub-Token header.
    """

    params = {
        "symbol": ticker
    }

    headers = {
        "X-Finnhub-Token": FINNHUB_API_KEY
    }

    try:

        response = requests.get(
            FINNHUB_URL,
            params=params,
            headers=headers,
            timeout=15
        )

        # ----------------------------------------------------
        # Authentication error
        # ----------------------------------------------------

        if response.status_code == 401:

            raise RuntimeError(
                "\nFinnhub returned HTTP 401 Unauthorized.\n\n"
                "Check your FINNHUB_API_KEY in .env.\n"
                "Make sure you are using the API key itself,\n"
                "not the Finnhub webhook secret.\n"
                "Also make sure the key was regenerated after\n"
                "the previous credential exposure."
            )

        # ----------------------------------------------------
        # Rate limit
        # ----------------------------------------------------

        if response.status_code == 429:

            print(
                f"WARNING: Finnhub rate limit reached for {ticker}."
            )

            return None

        response.raise_for_status()

        data = response.json()

        current_price = data.get("c")
        previous_price = data.get("pc")
        daily_change_percent = data.get("dp")

        # ----------------------------------------------------
        # Validate returned data
        # ----------------------------------------------------

        if current_price is None:
            print(
                f"WARNING: No current price returned for {ticker}."
            )
            return None

        if previous_price is None:
            print(
                f"WARNING: No previous close returned for {ticker}."
            )
            return None

        return {

            "current_price": float(current_price),

            "previous_price": float(previous_price),

            "daily_change_percent": (
                float(daily_change_percent)
                if daily_change_percent is not None
                else None
            )
        }

    except requests.exceptions.RequestException as error:

        print(
            f"WARNING: Finnhub request failed for "
            f"{ticker}: {error}"
        )

        return None


# ============================================================
# MARKETAX: GET NEWS
# ============================================================

def get_marketaux_news(ticker):
    """
    Retrieve recent financial news for a stock from Marketaux.
    """

    published_after = (
        datetime.now(timezone.utc) - timedelta(days=2)
    ).strftime("%Y-%m-%dT%H:%M:%S")

    params = {
        "api_token": MARKETAUX_API_KEY,
        "symbols": ticker,
        "language": "en",
        "filter_entities": "true",
        "published_after": published_after,
        "limit": 10
    }

    try:
        response = requests.get(
            MARKETAUX_URL,
            params=params,
            timeout=15
        )

        if response.status_code != 200:
            print(
                f"WARNING: Marketaux returned "
                f"HTTP {response.status_code} for {ticker}"
            )

            print(
                "Marketaux response:",
                response.text
            )

            return []

        data = response.json()

        return data.get("data", [])

    except requests.RequestException as e:

        print(
            f"WARNING: Marketaux request failed "
            f"for {ticker}: {e}"
        )

        return []

# ============================================================
# TEXT NORMALIZATION
# ============================================================

def normalize_text(text):

    """
    Convert text into a simple lowercase representation.

    This makes keyword matching easier.
    """

    if not text:
        return ""

    return re.sub(
        r"\s+",
        " ",
        text.lower()
    ).strip()


# ============================================================
# COMPANY NAME RELEVANCE
# ============================================================

def calculate_relevance(
    article,
    ticker,
    company_name
):

    """
    Calculate how relevant an article is to the company.

    Score components:

        +5 ticker appears in title
        +5 company name appears in title
        +3 company name appears in description
        + Marketaux entity match score

    We deliberately do NOT give points for every individual
    word in the company name.

    That caused false positives in the earlier version.

    Example:
        "Apple Inc."
    should not receive points just because the word
    "company" appears somewhere in an article.
    """

    title = article.get("title") or ""

    description = article.get("description") or ""

    title_lower = normalize_text(title)

    description_lower = normalize_text(description)

    company_lower = normalize_text(company_name)

    ticker_pattern = (
        r"\b"
        + re.escape(ticker.lower())
        + r"\b"
    )

    score = 0.0

    # Ticker in title
    if re.search(
        ticker_pattern,
        title_lower
    ):
        score += 5

    # Full company name in title
    if company_lower and company_lower in title_lower:
        score += 5

    # Full company name in description
    if company_lower and company_lower in description_lower:
        score += 3

    # Marketaux entity match score
    entity_match_score = 0.0

    for entity in article.get("entities", []):

        if entity.get("symbol") == ticker:

            value = entity.get("match_score")

            if value is not None:

                try:
                    entity_match_score = float(value)

                except (TypeError, ValueError):
                    entity_match_score = 0.0

            break

    # Convert Marketaux match score into a small bonus.
    score += min(
        entity_match_score * 2,
        2
    )

    # Normalize to 0-1
    relevance = min(
        score / 15,
        1
    )

    return round(
        relevance,
        3
    )


# ============================================================
# GET COMPANY-SPECIFIC SENTIMENT
# ============================================================

def get_entity_sentiment(
    article,
    ticker
):

    """
    Find the Marketaux sentiment specifically associated
    with our ticker.

    Marketaux can return several entities in one article,
    so we must make sure we use the sentiment belonging
    to the stock we are analysing.
    """

    for entity in article.get("entities", []):

        if entity.get("symbol") == ticker:

            sentiment = entity.get(
                "sentiment_score"
            )

            if sentiment is not None:

                try:

                    return float(sentiment)

                except (
                    TypeError,
                    ValueError
                ):

                    return None

    return None


# ============================================================
# CLASSIFY FORCES
# ============================================================

def identify_forces(
    article
):

    """
    Identify possible economic/business forces from the
    article text.

    This is intentionally transparent and simple.

    An article can contain more than one force.

    Example:

        "Microsoft raises AI spending as cloud revenue grows"

    could identify:

        AI demand
        Earnings / revenue

    We return the force names that appear in the article.
    """

    title = article.get("title") or ""

    description = article.get("description") or ""

    combined_text = normalize_text(
        f"{title} {description}"
    )

    detected_forces = []

    for force, keywords in FORCE_KEYWORDS.items():

        for keyword in keywords:

            if keyword.lower() in combined_text:

                detected_forces.append(force)

                break

    return detected_forces


# ============================================================
# SENTIMENT DIRECTION
# ============================================================

def sentiment_direction(sentiment):

    """
    Convert a numerical sentiment score into a readable
    direction.

    Marketaux sentiment ranges from -1 to +1.

    We use a small neutral band so tiny values are not
    treated as strong signals.
    """

    if sentiment is None:

        return "unknown"

    if sentiment >= 0.10:

        return "positive"

    if sentiment <= -0.10:

        return "negative"

    return "neutral"


# ============================================================
# OBSERVED PRICE DIRECTION
# ============================================================

def price_direction(daily_change_percent):

    """
    Determine the actual market direction of the stock.
    """

    if daily_change_percent is None:

        return "unknown"

    if daily_change_percent > 0:

        return "up"

    if daily_change_percent < 0:

        return "down"

    return "flat"


# ============================================================
# COMPARE NEWS WITH MARKET MOVEMENT
# ============================================================

def determine_alignment(
    sentiment,
    daily_change_percent
):

    """
    Compare the news sentiment with the actual stock movement.

    Examples:

        Positive news + stock up
            -> aligned positive

        Negative news + stock down
            -> aligned negative

        Positive news + stock down
            -> conflicting

    IMPORTANT:

    This does NOT prove causation.

    It simply tells us whether the retrieved news and
    observed price movement point in the same direction.
    """

    if (
        sentiment is None
        or daily_change_percent is None
    ):

        return "unknown"

    news_direction = sentiment_direction(
        sentiment
    )

    market_direction = price_direction(
        daily_change_percent
    )

    if (
        news_direction == "positive"
        and market_direction == "up"
    ):

        return "aligned_positive"

    if (
        news_direction == "negative"
        and market_direction == "down"
    ):

        return "aligned_negative"

    if (
        news_direction == "positive"
        and market_direction == "down"
    ):

        return "conflicting"

    if (
        news_direction == "negative"
        and market_direction == "up"
    ):

        return "conflicting"

    return "neutral_or_unclear"


# ============================================================
# PROCESS NEWS FOR ONE STOCK
# ============================================================

def process_news(
    ticker,
    company_name,
    sector,
    daily_change_percent
):

    """
    Retrieve, filter and structure news for one stock.

    Returns:

        news_results
        force_evidence
    """

    raw_articles = get_marketaux_news(
        ticker
    )

    news_results = []

    for article in raw_articles:

        title = article.get("title")

        description = article.get(
            "description"
        )

        relevance = calculate_relevance(
            article,
            ticker,
            company_name
        )

        # Ignore extremely weak matches.
        if relevance < 0.15:

            continue

        sentiment = get_entity_sentiment(
            article,
            ticker
        )

        forces = identify_forces(
            article
        )

        alignment = determine_alignment(
            sentiment,
            daily_change_percent
        )

        news_results.append({

            "title": title,

            "source": article.get(
                "source"
            ),

            "published_at": article.get(
                "published_at"
            ),

            "description": description,

            "url": article.get(
                "url"
            ),

            "sentiment": sentiment,

            "sentiment_direction": sentiment_direction(
                sentiment
            ),

            "relevance_score": relevance,

            "market_alignment": alignment,

            "identified_forces": forces
        })

    # --------------------------------------------------------
    # Sort strongest evidence first
    # --------------------------------------------------------

    news_results.sort(
        key=lambda item: (
            item["relevance_score"],
            abs(item["sentiment"] or 0)
        ),
        reverse=True
    )

    # --------------------------------------------------------
    # Keep only strongest evidence
    # --------------------------------------------------------

    news_results = news_results[
        :MAX_ARTICLES_PER_STOCK
    ]

    # --------------------------------------------------------
    # Build force evidence
    # --------------------------------------------------------

    force_evidence = {}

    for article in news_results:

        for force in article[
            "identified_forces"
        ]:

            if force not in force_evidence:

                force_evidence[force] = {

                    "force": force,

                    "sector": sector,

                    "ticker": ticker,

                    "evidence_count": 0,

                    "positive_evidence": 0,

                    "negative_evidence": 0,

                    "neutral_evidence": 0,

                    "articles": []
                }

            record = force_evidence[
                force
            ]

            record[
                "evidence_count"
            ] += 1

            direction = article[
                "sentiment_direction"
            ]

            if direction == "positive":

                record[
                    "positive_evidence"
                ] += 1

            elif direction == "negative":

                record[
                    "negative_evidence"
                ] += 1

            else:

                record[
                    "neutral_evidence"
                ] += 1

            record[
                "articles"
            ].append({

                "title": article[
                    "title"
                ],

                "source": article[
                    "source"
                ],

                "published_at": article[
                    "published_at"
                ],

                "url": article[
                    "url"
                ],

                "sentiment": article[
                    "sentiment"
                ],

                "relevance_score": article[
                    "relevance_score"
                ],

                "market_alignment": article[
                    "market_alignment"
                ]
            })

    return (
        news_results,
        force_evidence
    )


# ============================================================
# DETERMINE FORCE DIRECTION
# ============================================================

def determine_force_direction(
    force_record
):

    """
    Determine whether the evidence surrounding a force is
    mainly positive, negative, mixed or unknown.

    We use the number of positive/negative articles.

    Example:

        positive = 3
        negative = 1

        -> positive

    If both sides are substantial:

        -> mixed
    """

    positive = force_record[
        "positive_evidence"
    ]

    negative = force_record[
        "negative_evidence"
    ]

    total = positive + negative

    if total == 0:

        return "unknown"

    if positive > 0 and negative > 0:

        return "mixed"

    if positive > negative:

        return "positive"

    if negative > positive:

        return "negative"

    return "mixed"


# ============================================================
# CREATE EMPTY SECTOR
# ============================================================

def create_sector_record():

    """
    Create the structure used for sector analysis.
    """

    return {

        "holdings": [],

        "previous_value": 0.0,

        "current_value": 0.0,

        "daily_impact": 0.0,

        "daily_return_percent": 0.0,

        "forces": {}
    }


# ============================================================
# MAIN ANALYSIS
# ============================================================

def main():

    # --------------------------------------------------------
    # Validate keys
    # --------------------------------------------------------

    validate_api_keys()

    # --------------------------------------------------------
    # Load portfolio
    # --------------------------------------------------------

    portfolio_data = load_portfolio()

    portfolio = portfolio_data[
        "portfolio"
    ]

    holdings = portfolio[
        "holdings"
    ]

    # --------------------------------------------------------
    # Storage
    # --------------------------------------------------------

    analysis_results = []

    sector_summary = {}

    force_summary = {}

    skipped_holdings = []

    # --------------------------------------------------------
    # Process every holding
    # --------------------------------------------------------

    for holding in holdings:

        ticker = holding[
            "ticker"
        ]

        company_name = holding[
            "company_name"
        ]

        shares = float(
            holding[
                "shares_owned"
            ]
        )

        sector = SECTORS.get(
            ticker,
            "Unknown"
        )

        print(
            f"\nAnalyzing {ticker}..."
        )

        # ====================================================
        # GET MARKET DATA
        # ====================================================

        market_data = get_finnhub_quote(
            ticker
        )

        if market_data is None:

            print(
                f"Skipping {ticker} because "
                "valid market data was not returned."
            )

            skipped_holdings.append(
                ticker
            )

            time.sleep(
                API_DELAY_SECONDS
            )

            continue

        current_price = market_data[
            "current_price"
        ]

        previous_price = market_data[
            "previous_price"
        ]

        daily_change_percent = market_data[
            "daily_change_percent"
        ]

        # ====================================================
        # CALCULATE ACTUAL HOLDING IMPACT
        # ====================================================

        current_value = (
            shares * current_price
        )

        previous_value = (
            shares * previous_price
        )

        daily_change_amount = (
            current_value
            - previous_value
        )

        # ====================================================
        # GET NEWS
        # ====================================================

        (
            news_results,
            force_evidence
        ) = process_news(

            ticker,

            company_name,

            sector,

            daily_change_percent
        )

        # ====================================================
        # CREATE STOCK RESULT
        # ====================================================

        stock_result = {

            "ticker": ticker,

            "company_name": company_name,

            "sector": sector,

            "shares_owned": shares,

            "market_data": {

                "current_price": round(
                    current_price,
                    4
                ),

                "previous_price": round(
                    previous_price,
                    4
                ),

                "daily_change_percent": (
                    round(
                        daily_change_percent,
                        4
                    )
                    if daily_change_percent
                    is not None
                    else None
                ),

                "previous_value": round(
                    previous_value,
                    2
                ),

                "current_value": round(
                    current_value,
                    2
                ),

                "daily_change_amount": round(
                    daily_change_amount,
                    2
                ),

                "portfolio_impact": round(
                    daily_change_amount,
                    2
                )
            },

            "financial_news": news_results,

            "identified_forces": list(
                force_evidence.keys()
            )
        }

        analysis_results.append(
            stock_result
        )

        # ====================================================
        # SECTOR SUMMARY
        # ====================================================

        if sector not in sector_summary:

            sector_summary[
                sector
            ] = create_sector_record()

        sector_record = sector_summary[
            sector
        ]

        sector_record[
            "holdings"
        ].append(ticker)

        sector_record[
            "previous_value"
        ] += previous_value

        sector_record[
            "current_value"
        ] += current_value

        sector_record[
            "daily_impact"
        ] += daily_change_amount

        # ====================================================
        # FORCE SUMMARY
        # ====================================================
        #
        # IMPORTANT:
        #
        # We do NOT add the same stock's dollar impact to
        # every force and then pretend those values add up
        # to the portfolio.
        #
        # A single article can mention several forces.
        #
        # Therefore each force records:
        #
        #     affected stock
        #     evidence
        #     sentiment
        #     observed stock impact
        #
        # But the portfolio impact remains measured from
        # actual stock price movements.
        #
        # ====================================================

        for force, evidence in force_evidence.items():

            force_direction = (
                determine_force_direction(
                    evidence
                )
            )

            force_key = force

            if force_key not in force_summary:

                force_summary[
                    force_key
                ] = {

                    "force": force_key,

                    "direction": force_direction,

                    "affected_holdings": [],

                    "sectors": [],

                    "evidence_count": 0,

                    "observed_stock_impacts": [],

                    "articles": []
                }

            force_record = force_summary[
                force_key
            ]

            if ticker not in force_record[
                "affected_holdings"
            ]:

                force_record[
                    "affected_holdings"
                ].append(ticker)

            if sector not in force_record[
                "sectors"
            ]:

                force_record[
                    "sectors"
                ].append(sector)

            force_record[
                "evidence_count"
            ] += evidence[
                "evidence_count"
            ]

            force_record[
                "observed_stock_impacts"
            ].append({

                "ticker": ticker,

                "impact": round(
                    daily_change_amount,
                    2
                ),

                "daily_change_percent": (
                    round(
                        daily_change_percent,
                        4
                    )
                    if daily_change_percent
                    is not None
                    else None
                )
            })

            force_record[
                "articles"
            ].extend(
                evidence[
                    "articles"
                ]
            )

        # ----------------------------------------------------
        # API delay
        # ----------------------------------------------------

        time.sleep(
            API_DELAY_SECONDS
        )

    # ========================================================
    # PORTFOLIO TOTALS
    # ========================================================

    previous_portfolio_value = sum(

        item[
            "market_data"
        ][
            "previous_value"
        ]

        for item in analysis_results
    )

    current_portfolio_value = sum(

        item[
            "market_data"
        ][
            "current_value"
        ]

        for item in analysis_results
    )

    total_portfolio_impact = (
        current_portfolio_value
        - previous_portfolio_value
    )

    if previous_portfolio_value != 0:

        portfolio_change_percent = (

            total_portfolio_impact
            / previous_portfolio_value

        ) * 100

    else:

        portfolio_change_percent = 0.0

    # ========================================================
    # SECTOR CALCULATIONS
    # ========================================================

    for sector, data in sector_summary.items():

        previous_value = data[
            "previous_value"
        ]

        current_value = data[
            "current_value"
        ]

        daily_impact = data[
            "daily_impact"
        ]

        if previous_value != 0:

            daily_return = (

                daily_impact
                / previous_value

            ) * 100

        else:

            daily_return = 0.0

        data[
            "previous_value"
        ] = round(
            previous_value,
            2
        )

        data[
            "current_value"
        ] = round(
            current_value,
            2
        )

        data[
            "daily_impact"
        ] = round(
            daily_impact,
            2
        )

        data[
            "daily_return_percent"
        ] = round(
            daily_return,
            4
        )

    # ========================================================
    # FORCE DIRECTION CLEANUP
    # ========================================================

    for force, data in force_summary.items():

        # Recalculate direction using all evidence.
        positive_count = 0
        negative_count = 0

        for article in data[
            "articles"
        ]:

            sentiment = article.get(
                "sentiment"
            )

            direction = sentiment_direction(
                sentiment
            )

            if direction == "positive":

                positive_count += 1

            elif direction == "negative":

                negative_count += 1

        if (
            positive_count > 0
            and negative_count > 0
        ):

            final_direction = "mixed"

        elif positive_count > negative_count:

            final_direction = "positive"

        elif negative_count > positive_count:

            final_direction = "negative"

        else:

            final_direction = "unknown"

        data[
            "direction"
        ] = final_direction

    # ========================================================
    # TOP CONTRIBUTORS
    # ========================================================

    sorted_holdings = sorted(

        analysis_results,

        key=lambda item:
            item[
                "market_data"
            ][
                "daily_change_amount"
            ],

        reverse=True
    )

    top_positive = [

        {

            "ticker": item[
                "ticker"
            ],

            "impact": item[
                "market_data"
            ][
                "daily_change_amount"
            ]

        }

        for item in sorted_holdings
        if item[
            "market_data"
        ][
            "daily_change_amount"
        ] > 0
    ][:5]

    top_negative = [

        {

            "ticker": item[
                "ticker"
            ],

            "impact": item[
                "market_data"
            ][
                "daily_change_amount"
            ]

        }

        for item in sorted_holdings
        if item[
            "market_data"
        ][
            "daily_change_amount"
        ] < 0
    ][:5]

    # ========================================================
    # PORTFOLIO FORCES
    # ========================================================
    #
    # A force is considered "up" or "down" based on the
    # direction of the available news evidence.
    #
    # This is NOT a causal attribution.
    #
    # We therefore keep:
    #
    #     evidence_direction
    #
    # separate from:
    #
    #     observed_stock_impacts
    #
    # ========================================================

    forces_up = []
    forces_down = []
    forces_mixed = []

    for force, data in force_summary.items():

        item = {

            "force": force,

            "direction": data[
                "direction"
            ],

            "affected_holdings": data[
                "affected_holdings"
            ],

            "sectors": data[
                "sectors"
            ],

            "evidence_count": data[
                "evidence_count"
            ],

            "observed_stock_impacts": data[
                "observed_stock_impacts"
            ]
        }

        if data[
            "direction"
        ] == "positive":

            forces_up.append(item)

        elif data[
            "direction"
        ] == "negative":

            forces_down.append(item)

        elif data[
            "direction"
        ] == "mixed":

            forces_mixed.append(item)

    # ========================================================
    # CREATE PORTFOLIO ANALYSIS
    # ========================================================

    portfolio_analysis = {

        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),

        "portfolio": {

            "account_id": portfolio.get(
                "account_id"
            ),

            "currency": portfolio.get(
                "currency"
            )
        },

        "portfolio_summary": {

            "previous_portfolio_value": round(
                previous_portfolio_value,
                2
            ),

            "current_portfolio_value": round(
                current_portfolio_value,
                2
            ),

            "total_daily_impact": round(
                total_portfolio_impact,
                2
            ),

            "daily_change_percent": round(
                portfolio_change_percent,
                4
            ),

            "holdings_analyzed": len(
                analysis_results
            ),

            "holdings_skipped": len(
                skipped_holdings
            ),

            "skipped_tickers": skipped_holdings
        },

        "top_positive_contributors":
            top_positive,

        "top_negative_contributors":
            top_negative,

        "sector_summary":
            sector_summary,

        "holdings":
            analysis_results
    }

    # ========================================================
    # CREATE RAG EVIDENCE
    # ========================================================
    #
    # This is the most important new output.
    #
    # The future LLM will use THIS FILE rather than
    # receiving the raw API responses.
    #
    # ========================================================

    rag_evidence = {

        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),

        "method": (
            "retrieval + relevance filtering "
            "+ rule-based force identification"
        ),

        "important_note": (
            "Observed stock/portfolio impacts are "
            "calculated from market prices. "
            "News evidence does not by itself prove "
            "causation."
        ),

        "portfolio": {

            "account_id": portfolio.get(
                "account_id"
            ),

            "currency": portfolio.get(
                "currency"
            ),

            "previous_value": round(
                previous_portfolio_value,
                2
            ),

            "current_value": round(
                current_portfolio_value,
                2
            ),

            "daily_impact": round(
                total_portfolio_impact,
                2
            ),

            "daily_change_percent": round(
                portfolio_change_percent,
                4
            )
        },

        "forces_pushing_up": forces_up,

        "forces_pushing_down": forces_down,

        "forces_mixed_or_unclear": forces_mixed,

        "sector_evidence": {},

        "holding_evidence": []
    }

    # ========================================================
    # BUILD SECTOR EVIDENCE
    # ========================================================

    for sector, data in sector_summary.items():

        sector_forces = []

        for force, force_data in force_summary.items():

            if sector in force_data[
                "sectors"
            ]:

                sector_forces.append({

                    "force": force,

                    "direction": force_data[
                        "direction"
                    ],

                    "affected_holdings": [

                        ticker

                        for ticker in force_data[
                            "affected_holdings"
                        ]

                        if ticker in data[
                            "holdings"
                        ]
                    ],

                    "evidence_count":
                        force_data[
                            "evidence_count"
                        ],

                    "observed_stock_impacts": [

                        item

                        for item in force_data[
                            "observed_stock_impacts"
                        ]

                        if item[
                            "ticker"
                        ] in data[
                            "holdings"
                        ]
                    ]
                })

        rag_evidence[
            "sector_evidence"
        ][
            sector
        ] = {

            "sector_return_percent":
                data[
                    "daily_return_percent"
                ],

            "sector_daily_impact":
                data[
                    "daily_impact"
                ],

            "holdings":
                data[
                    "holdings"
                ],

            "forces":
                sector_forces
        }

    # ========================================================
    # BUILD HOLDING EVIDENCE
    # ========================================================

    for holding in analysis_results:

        market = holding[
            "market_data"
        ]

        rag_evidence[
            "holding_evidence"
        ].append({

            "ticker": holding[
                "ticker"
            ],

            "company_name": holding[
                "company_name"
            ],

            "sector": holding[
                "sector"
            ],

            "shares_owned": holding[
                "shares_owned"
            ],

            "observed_market_move": {

                "price_change_percent":
                    market[
                        "daily_change_percent"
                    ],

                "portfolio_impact":
                    market[
                        "portfolio_impact"
                    ]
            },

            "identified_forces":
                holding[
                    "identified_forces"
                ],

            "news_evidence":
                holding[
                    "financial_news"
                ]
        })

    # ========================================================
    # SAVE PORTFOLIO ANALYSIS
    # ========================================================

    with open(
        "portfolio_analysis.json",
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            portfolio_analysis,
            file,
            indent=4,
            ensure_ascii=False
        )

    # ========================================================
    # SAVE RAG EVIDENCE
    # ========================================================

    with open(
        "portfolio_evidence.json",
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            rag_evidence,
            file,
            indent=4,
            ensure_ascii=False
        )

    # ========================================================
    # DISPLAY RESULTS
    # ========================================================

    print("\n")
    print("=" * 60)
    print("PORTFOLIO ANALYSIS COMPLETED")
    print("=" * 60)

    print("\nPORTFOLIO SUMMARY")
    print("-" * 60)

    print(
        f"Previous portfolio value: "
        f"${previous_portfolio_value:,.2f}"
    )

    print(
        f"Current portfolio value:  "
        f"${current_portfolio_value:,.2f}"
    )

    print(
        f"Daily portfolio impact:    "
        f"${total_portfolio_impact:,.2f}"
    )

    print(
        f"Daily portfolio change:    "
        f"{portfolio_change_percent:.3f}%"
    )

    print(
        f"\nHoldings analyzed: "
        f"{len(analysis_results)}"
    )

    if skipped_holdings:

        print(
            "Holdings skipped: "
            + ", ".join(skipped_holdings)
        )

    # ========================================================
    # POSITIVE CONTRIBUTORS
    # ========================================================

    print("\n")
    print("TOP POSITIVE CONTRIBUTORS")
    print("-" * 60)

    if top_positive:

        for item in top_positive:

            print(
                f"{item['ticker']:<8}"
                f"+${item['impact']:>10,.2f}"
            )

    else:

        print("None")

    # ========================================================
    # NEGATIVE CONTRIBUTORS
    # ========================================================

    print("\n")
    print("TOP NEGATIVE CONTRIBUTORS")
    print("-" * 60)

    if top_negative:

        for item in top_negative:

            print(
                f"{item['ticker']:<8}"
                f"${item['impact']:>10,.2f}"
            )

    else:

        print("None")

    # ========================================================
    # SECTOR ANALYSIS
    # ========================================================

    print("\n")
    print("SECTOR ANALYSIS")
    print("-" * 60)

    for sector, data in sector_summary.items():

        print(f"\n{sector}")

        print(
            f"  Impact: "
            f"${data['daily_impact']:,.2f}"
        )

        print(
            f"  Return: "
            f"{data['daily_return_percent']:.3f}%"
        )

        print(
            "  Holdings: "
            + ", ".join(
                data["holdings"]
            )
        )

        # Show forces affecting this sector
        sector_force_names = [

            force

            for force, force_data
            in force_summary.items()

            if sector in force_data[
                "sectors"
            ]
        ]

        if sector_force_names:

            print("  Evidence-based forces:")

            for force in sector_force_names:

                direction = force_summary[
                    force
                ][
                    "direction"
                ]

                evidence_count = force_summary[
                    force
                ][
                    "evidence_count"
                ]

                print(
                    f"    - {force} "
                    f"({direction}) "
                    f"[{evidence_count} articles]"
                )

        else:

            print(
                "  Evidence-based forces: None identified"
            )

    # ========================================================
    # PORTFOLIO FORCES
    # ========================================================

    print("\n")
    print("PORTFOLIO FORCES / EVIDENCE")
    print("-" * 60)

    print("\nFORCES WITH POSITIVE EVIDENCE")

    if forces_up:

        for force in forces_up:

            print(
                f"  + {force['force']}"
            )

            print(
                "    Holdings: "
                + ", ".join(
                    force[
                        "affected_holdings"
                    ]
                )
            )

            print(
                f"    Evidence: "
                f"{force['evidence_count']} articles"
            )

    else:

        print(
            "  None identified"
        )

    print("\nFORCES WITH NEGATIVE EVIDENCE")

    if forces_down:

        for force in forces_down:

            print(
                f"  - {force['force']}"
            )

            print(
                "    Holdings: "
                + ", ".join(
                    force[
                        "affected_holdings"
                    ]
                )
            )

            print(
                f"    Evidence: "
                f"{force['evidence_count']} articles"
            )

    else:

        print(
            "  None identified"
        )

    print("\nFORCES WITH MIXED / UNCLEAR EVIDENCE")

    if forces_mixed:

        for force in forces_mixed:

            print(
                f"  ? {force['force']}"
            )

            print(
                "    Holdings: "
                + ", ".join(
                    force[
                        "affected_holdings"
                    ]
                )
            )

            print(
                f"    Evidence: "
                f"{force['evidence_count']} articles"
            )

    else:

        print(
            "  None identified"
        )

    # ========================================================
    # INDIVIDUAL HOLDINGS
    # ========================================================

    print("\n")
    print("INDIVIDUAL HOLDINGS")
    print("-" * 60)

    for holding in analysis_results:

        market = holding[
            "market_data"
        ]

        print(
            f"\n{holding['ticker']} "
            f"({holding['company_name']})"
        )

        print(
            f"  Sector: "
            f"{holding['sector']}"
        )

        print(
            f"  Daily change: "
            f"{market['daily_change_percent']:.3f}%"
        )

        print(
            f"  Portfolio impact: "
            f"${market['portfolio_impact']:,.2f}"
        )

        print(
            f"  Relevant articles: "
            f"{len(holding['financial_news'])}"
        )

        if holding[
            "identified_forces"
        ]:

            print(
                "  Possible forces:"
            )

            for force in holding[
                "identified_forces"
            ]:

                print(
                    f"    - {force}"
                )

    # ========================================================
    # FINAL OUTPUT
    # ========================================================

    print("\n")
    print("=" * 60)
    print("FILES CREATED")
    print("=" * 60)

    print(
        "portfolio_analysis.json"
    )

    print(
        "portfolio_evidence.json"
    )

    print("\n")
    print(
        "The evidence file is ready for the "
        "next RAG + LLM stage."
    )

    print("=" * 60)


# ============================================================
# RUN PROGRAM
# ============================================================

if __name__ == "__main__":

    main()