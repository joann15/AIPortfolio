import os
import requests

from dotenv import load_dotenv


load_dotenv()


ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY")

ALPHA_VANTAGE_URL = "https://www.alphavantage.co/query"

HISTORICAL_RELEVANCE_THRESHOLD = 0.80
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

    # Give extra weight to articles that discuss
    # stock/market movement.
    movement_keywords = [
        "stock",
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
        "spending concerns",
        "stock movement",
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
    Retrieve relevant historical news for one ticker.

    start_date and end_date must use:

        YYYYMMDDTHHMM

    Example:

        20260914T0000
        20260915T2359
    """

    if not ALPHA_VANTAGE_API_KEY:
        raise ValueError(
            "ALPHA_VANTAGE_API_KEY is missing from the .env file."
        )

    params = {
        "function": "NEWS_SENTIMENT",
        "tickers": ticker,
        "time_from": start_date,
        "time_to": end_date,
        "sort": "EARLIEST",
        "limit": limit,
        "apikey": ALPHA_VANTAGE_API_KEY,
    }

    response = requests.get(
        ALPHA_VANTAGE_URL,
        params=params,
        timeout=30
    )

    response.raise_for_status()

    data = response.json()

    # Alpha Vantage may return these instead of normal data
    # when the API limit is reached or another issue occurs.
    if "Note" in data:
        raise RuntimeError(data["Note"])

    if "Information" in data:
        raise RuntimeError(data["Information"])

    articles = data.get("feed", [])

    relevant_articles = []

    ticker_upper = ticker.upper()
    ticker_lower = ticker.lower()
    company_lower = company_name.lower()

    for article in articles:

        title = article.get("title", "")
        summary = article.get("summary", "")

        title_lower = title.lower()
        summary_lower = summary.lower()

        # Find Alpha Vantage's ticker-specific sentiment data.
        ticker_sentiment = None

        for item in article.get("ticker_sentiment", []):

            if item.get("ticker", "").upper() == ticker_upper:
                ticker_sentiment = item
                break

        relevance_score = 0

        if ticker_sentiment:

            relevance_score = float(
                ticker_sentiment.get(
                    "relevance_score",
                    0
                )
            )

        # Check whether the stock is directly mentioned
        # in the article title.
        ticker_in_title = ticker_lower in title_lower

        company_in_title = company_lower in title_lower

        # Strong Alpha Vantage relevance.
        strong_relevance = (
            relevance_score >= HISTORICAL_RELEVANCE_THRESHOLD
        )

        # Keep the article if:
        #
        # 1. The ticker is in the title
        # OR
        # 2. The company name is in the title
        # OR
        # 3. Alpha Vantage gives it a strong relevance score.
        is_relevant = (
            ticker_in_title
            or company_in_title
            or strong_relevance
        )

        if not is_relevant:
            continue

        sentiment_score = None
        sentiment_label = None

        if ticker_sentiment:

            sentiment_score = float(
                ticker_sentiment.get(
                    "ticker_sentiment_score",
                    0
                )
            )

            sentiment_label = ticker_sentiment.get(
                "ticker_sentiment_label"
            )

        relevant_articles.append({
            "title": title,
            "summary": summary,
            "url": article.get("url"),
            "source": article.get("source"),
            "published_at": article.get(
                "time_published"
            ),
            "relevance_score": relevance_score,
            "sentiment_score": sentiment_score,
            "sentiment_label": sentiment_label,
        })

    # Rank the relevant articles so that the most useful
    # articles for explaining price movement appear first.
    relevant_articles.sort(
        key=lambda article: calculate_article_rank(
            article,
            ticker
        ),
        reverse=True
    )

    # Return only the strongest articles.
    return relevant_articles[
        :MAX_HISTORICAL_ARTICLES
    ]