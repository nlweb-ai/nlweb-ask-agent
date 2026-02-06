"""
RSS/Atom feed parser that converts feeds to schema.org Article format.

Converts RSS/Atom feed entries into schema.org Article objects for
consistent processing in the crawler pipeline.
"""

import html
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import feedparser
import requests

logger = logging.getLogger("rss2schema")


def parse_rss_to_schema(feed_url: str, timeout: int = 30) -> List[Dict[str, Any]]:
    """
    Parse RSS/Atom feed and convert to schema.org Article format.

    Args:
        feed_url: URL or path to RSS/Atom feed
        timeout: Timeout in seconds for fetching the feed (default: 30)

    Returns:
        List of schema.org Article dicts

    Example:
        articles = parse_rss_to_schema("https://example.com/feed.xml")
    """
    try:
        logger.info(f"Fetching RSS feed from {feed_url}")

        # Fetch feed content with timeout
        try:
            response = requests.get(
                feed_url, timeout=timeout, headers={"User-Agent": "NLWeb-Crawler/1.0"}
            )

            logger.debug(f"HTTP status: {response.status_code}")

            if response.status_code >= 400:
                logger.error(f"HTTP {response.status_code} when fetching feed")
                return []

            feed_content = response.text
            logger.debug(f"Downloaded {len(feed_content)} bytes")

            # Parse the downloaded content
            feed = feedparser.parse(feed_content)
        except requests.Timeout:
            logger.error(f"Timeout after {timeout}s fetching feed")
            return []
        except requests.RequestException as e:
            logger.error(f"Network error fetching feed: {e}")
            return []

        # Check for parsing errors
        if hasattr(feed, "bozo") and feed.bozo:
            logger.warning("Feed has bozo flag set")
            if hasattr(feed, "bozo_exception"):
                logger.warning(f"Bozo exception: {feed.bozo_exception}")

        # Check for entries
        if not hasattr(feed, "entries") or not feed.entries:
            logger.warning(f"No entries found in feed: {feed_url}")
            logger.debug(f"Feed keys: {list(feed.keys())}")
            if hasattr(feed, "feed") and hasattr(feed.feed, "keys"):
                logger.debug(f"Feed.feed keys: {list(feed.feed.keys())}")
                if hasattr(feed.feed, "title"):
                    logger.debug(f"Feed title: {feed.feed.title}")
            return []

        logger.info(f"Parsed {len(feed.entries)} entries from {feed_url}")

        # Convert each entry to schema.org Article
        articles = []
        for entry in feed.entries:
            article = _entry_to_schema_article(entry, feed)
            if article:
                articles.append(article)

        logger.info(f"Converted {len(articles)} entries to schema.org format")
        return articles

    except Exception as e:
        logger.error(f"Error parsing feed {feed_url}: {type(e).__name__}: {str(e)}")
        import traceback

        logger.debug(traceback.format_exc())
        return []


def _entry_to_schema_article(entry, feed) -> Optional[Dict[str, Any]]:
    """
    Convert a feed entry to schema.org Article format.

    Args:
        entry: feedparser entry object
        feed: feedparser feed object (for fallback metadata)

    Returns:
        schema.org Article dict or None if required fields missing
    """
    # Required fields
    url = entry.get("link") or entry.get("id")
    if not url:
        logger.warning("Entry missing both 'link' and 'id', skipping")
        return None

    # Article title
    title = entry.get("title", "Untitled")

    # Article description/summary
    description = (
        entry.get("summary")
        or entry.get("description")
        or entry.get("content", [{}])[0].get("value", "")
    )

    # Clean HTML from description if present
    if description:
        description = _clean_html(description)

    # Publication date
    date_published = _parse_date(entry.get("published") or entry.get("updated"))

    # Author
    author_name = None
    if entry.get("author"):
        author_name = entry.author
    elif entry.get("author_detail"):
        author_name = entry.author_detail.get("name")

    # Build schema.org Article
    article = {
        "@context": "http://schema.org",
        "@type": "Article",
        "@id": url,  # Use URL as the @id
        "url": url,
        "name": title,
        "headline": title,
    }

    # Add optional fields if available
    if description:
        article["description"] = description
        article["articleBody"] = description

    if date_published:
        article["datePublished"] = date_published

    if author_name:
        article["author"] = {"@type": "Person", "name": author_name}

    # Add publisher info from feed metadata
    if hasattr(feed, "feed") and feed.feed.get("title"):
        article["publisher"] = {"@type": "Organization", "name": feed.feed.title}
        if feed.feed.get("link"):
            article["publisher"]["url"] = feed.feed.link

    # Add tags/categories if available
    if entry.get("tags"):
        keywords = [tag.get("term") for tag in entry.tags if tag.get("term")]
        if keywords:
            article["keywords"] = ", ".join(keywords)

    # Add image if available (check custom image_url field first)
    if entry.get("image_url"):
        article["image"] = {"@type": "ImageObject", "url": entry.image_url}
    elif entry.get("media_content"):
        # RSS media:content
        for media in entry.media_content:
            if media.get("medium") == "image" or "image" in media.get("type", ""):
                article["image"] = {"@type": "ImageObject", "url": media["url"]}
                break
    elif entry.get("enclosures"):
        # RSS enclosures
        for enclosure in entry.enclosures:
            if "image" in enclosure.get("type", ""):
                article["image"] = {"@type": "ImageObject", "url": enclosure["url"]}
                break

    return article


def _clean_html(text: str) -> str:
    """
    Remove HTML tags from text.

    Args:
        text: Text that may contain HTML

    Returns:
        Clean text without HTML tags
    """
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", "", text)

    # Decode HTML entities
    text = html.unescape(text)

    # Remove extra whitespace
    text = " ".join(text.split())

    return text


def _parse_date(date_str: str) -> Optional[str]:
    """
    Parse date string to ISO format.

    Args:
        date_str: Date string in various formats

    Returns:
        ISO formatted date string (YYYY-MM-DD) or None
    """
    if not date_str:
        return None

    try:
        # feedparser provides time_struct for parsed dates
        if hasattr(date_str, "timetuple"):
            dt = datetime(*(date_str.timetuple()[:6]))  # type: ignore
            return dt.strftime("%Y-%m-%d")
        return date_str
    except Exception:
        return None
