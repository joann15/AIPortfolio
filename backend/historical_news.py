import os
import requests

from dotenv import load_dotenv


load_dotenv()


MARKETAUX_API_KEY = os.getenv("MARKETAUX_API_KEY")

MARKETAUX_URL = "https://api.marketaux.com/v1/news/all"

HISTORICAL_RELEVANCE_THRESHOLD = 0.20
MAX_HISTORICAL_ARTICLES = 3


def calculate_article_rank(article, ticker):
    """
    Calculate how useful an article is for explaining
    historical movement of a specific stock.
    """

    title = (article.get("title") or "").lower()
    summary = (article.get("summary") or "").lower()

    ticker_lower = ticker.lower()

    relevance_score = article.get("relevance_score") or 0
    sentiment_score = abs(article.get("sentiment_score") or 0)

    # Give extra weight when the ticker appears in the title.
    title_bonus = 0

    if ticker_lower in title:
        title_bonus = 0.30

    # Give extra weight to articles discussing
    # stock or market movement.
    movement_keywords = [
        "stock",
        "stocks",
        "share",
        "shares",
        "rise",
        "rises",
        "rose",
        "fall",
        "falls",
        "fell",
        "drop",
        "drops",
        "dropped",
        "selloff",
        "market",
        "price",
        "trading",
        "investors",
        "investment",
        "spending",
        "revenue",
        "earnings",
        "forecast",
        "analyst",
        "rating",
        "buy",
        "sell",
        "upgrade",
        "downgrade",
    ]

    movement_bonus = 0

    for keyword in movement_keywords:

        if keyword in title or keyword in summary:
            movement_bonus += 0.05

    # Slightly prioritize articles with stronger sentiment.
    sentiment_bonus = sentiment_score * 0.10

    return (
        relevance_score
        + title_bonus
        + movement_bonus
        + sentiment_bonus
    )


def get_historical_news(
    ticker,
    company_name,
    start_date,
    end_date,
    limit=50
):
    """
    Retrieve relevant historical news from Marketaux.

    start_date and end_date should use:

        YYYYMMDDTHHMM

    Example:

        20260914T0000
        20260915T2359
    """

    if not MARKETAUX_API_KEY:
        raise ValueError(
            "MARKETAUX_API_KEY is missing from the .env file."
        )

    # Convert:
    #
    # 20260914T0000
    #
    # into:
    #
    # 2026-09-14T00:00:00
    #
    published_after = (
        f"{start_date[0:4]}-"
        f"{start_date[4:6]}-"
        f"{start_date[6:8]}T"
        f"{start_date[9:11]}:"
        f"{start_date[11:13]}:00"
    )

    published_before = (
        f"{end_date[0:4]}-"
        f"{end_date[4:6]}-"
        f"{end_date[6:8]}T"
        f"{end_date[9:11]}:"
        f"{end_date[11:13]}:59"
    )

    params = {
        "api_token": MARKETAUX_API_KEY,
        "symbols": ticker,
        "language": "en",
        "filter_entities": "true",
        "published_after": published_after,
        "published_before": published_before,
        "limit": min(limit, 50),
    }

    response = requests.get(
        MARKETAUX_URL,
        params=params,
        timeout=30
    )

    response.raise_for_status()

    data = response.json()

    print("MARKETAUX HISTORICAL NEWS")
    print("Ticker:", ticker)
    print("Company:", company_name)
    print("Start:", published_after)
    print("End:", published_before)
    print("Status:", response.status_code)
    print("Response keys:", list(data.keys()))
    print("Article count:", len(data.get("data", [])))
    print("===============================================")

    articles = data.get("data", [])

    relevant_articles = []

    ticker_upper = ticker.upper()
    ticker_lower = ticker.lower()
    company_lower = company_name.lower()

    for article in articles:

        title = article.get("title") or ""
        description = article.get("description") or ""

        title_lower = title.lower()
        description_lower = description.lower()

        # ------------------------------------------------
        # Find the entity information for this ticker
        # ------------------------------------------------

        ticker_entity = None

        for entity in article.get("entities", []):

            symbol = (
                entity.get("symbol") or ""
            ).upper()

            if symbol == ticker_upper:
                ticker_entity = entity
                break

        # ------------------------------------------------
        # Calculate Marketaux relevance
        # ------------------------------------------------

        entity_match_score = 0

        if ticker_entity:

            try:
                entity_match_score = float(
                    ticker_entity.get(
                        "match_score",
                        0
                    )
                )
            except (TypeError, ValueError):

                entity_match_score = 0

        # Marketaux match_score is not necessarily 0-1.
        # Normalize it for our ranking system.

        normalized_entity_score = min(
            entity_match_score / 100,
            1.0
        )

        # ------------------------------------------------
        # Direct mention checks
        # ------------------------------------------------

        ticker_in_title = (
            ticker_lower in title_lower
        )

        company_in_title = (
            company_lower in title_lower
        )

        ticker_in_description = (
            ticker_lower in description_lower
        )

        company_in_description = (
            company_lower in description_lower
        )

        direct_mention = (
            ticker_in_title
            or company_in_title
            or ticker_in_description
            or company_in_description
        )

        # ------------------------------------------------
        # Determine relevance
        # ------------------------------------------------

        relevance_score = normalized_entity_score

        if direct_mention:
            relevance_score = max(
                relevance_score,
                0.50
            )

        # Keep only articles that are actually relevant
        # to the requested stock.

        is_relevant = (
            direct_mention
            or normalized_entity_score
            >= HISTORICAL_RELEVANCE_THRESHOLD
        )

        if not is_relevant:
            continue

        # ------------------------------------------------
        # Sentiment
        # ------------------------------------------------

        sentiment_score = None

        if ticker_entity:

            try:
                sentiment_score = float(
                    ticker_entity.get(
                        "sentiment_score",
                        0
                    )
                )

            except (TypeError, ValueError):

                sentiment_score = None

        sentiment_label = None

        if sentiment_score is not None:

            if sentiment_score > 0.15:
                sentiment_label = "Bullish"

            elif sentiment_score < -0.15:
                sentiment_label = "Bearish"

            else:
                sentiment_label = "Neutral"

        # ------------------------------------------------
        # Store in the same structure your frontend expects
        # ------------------------------------------------

        relevant_articles.append({
            "title": title,
            "summary": description,
            "url": article.get("url"),
            "source": article.get("source"),
            "published_at": article.get("published_at"),
            "relevance_score": relevance_score,
            "sentiment_score": sentiment_score,
            "sentiment_label": sentiment_label,
        })

    # ------------------------------------------------
    # Rank articles
    # ------------------------------------------------

    relevant_articles.sort(
        key=lambda article: calculate_article_rank(
            article,
            ticker
        ),
        reverse=True
    )

    # ------------------------------------------------
    # Return strongest articles only
    # ------------------------------------------------

    return relevant_articles[
        :MAX_HISTORICAL_ARTICLES
    ]