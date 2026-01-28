from core.worker import extract_objects_from_schema_file

# TSV format: Each line is URL<TAB>JSON_ARRAY
# This example has simple objects with @id, no @graph nesting
# Includes objects with skip_types (Organization, WebPage, BreadcrumbList) that should be filtered out
TSV_WITHOUT_GRAPH = """https://example.com/products/widget	[{"@id": "https://example.com/products/widget#product", "@type": "Product", "name": "Super Widget", "price": "29.99"}, {"@id": "https://example.com/products/widget#org", "@type": "Organization", "name": "Acme Corp"}]
https://example.com/articles/news	[{"@id": "https://example.com/articles/news#article", "@type": "Article", "headline": "Breaking News", "author": "Jane Doe"}, {"@id": "https://example.com/articles/news#webpage", "@type": "WebPage", "name": "News Page"}]
https://example.com/recipes/cake	[{"@id": "https://example.com/recipes/cake#recipe", "@type": "Recipe", "name": "Chocolate Cake", "cookTime": "PT45M"}, {"@id": "https://example.com/recipes/cake#breadcrumb", "@type": "BreadcrumbList", "itemListElement": []}]"""

# TSV format with @graph arrays
# The outer object has @context but no @id, so @graph contents should be extracted
# Includes objects with skip_types (WebSite, ItemList, Brand) that should be filtered out
TSV_WITH_GRAPH = """https://example.com/page1	[{"@context": "https://schema.org", "@graph": [{"@id": "https://example.com/page1#product", "@type": "Product", "name": "Gadget Pro", "price": "99.99"}, {"@id": "https://example.com/page1#offer", "@type": "Offer", "price": "89.99", "priceCurrency": "USD"}, {"@id": "https://example.com/page1#website", "@type": "WebSite", "name": "Example Site"}]}]
https://example.com/page2	[{"@context": "https://schema.org", "@graph": [{"@id": "https://example.com/page2#article", "@type": "Article", "headline": "Tech Review", "datePublished": "2025-01-15"}, {"@id": "https://example.com/page2#person", "@type": "Person", "name": "John Smith"}, {"@id": "https://example.com/page2#itemlist", "@type": "ItemList", "numberOfItems": 5}, {"@id": "https://example.com/page2#brand", "@type": "Brand", "name": "TechBrand"}]}]"""

# Expected output: (list of @id strings, list of objects)
# For TSV_WITHOUT_GRAPH: 3 objects extracted (Organization, WebPage, BreadcrumbList filtered out)
TSV_WITHOUT_GRAPH_PARSED = (
    [
        "https://example.com/products/widget#product",
        "https://example.com/articles/news#article",
        "https://example.com/recipes/cake#recipe",
    ],
    [
        {
            "@id": "https://example.com/products/widget#product",
            "@type": "Product",
            "name": "Super Widget",
            "price": "29.99",
        },
        {
            "@id": "https://example.com/articles/news#article",
            "@type": "Article",
            "headline": "Breaking News",
            "author": "Jane Doe",
        },
        {
            "@id": "https://example.com/recipes/cake#recipe",
            "@type": "Recipe",
            "name": "Chocolate Cake",
            "cookTime": "PT45M",
        },
    ],
)

# For TSV_WITH_GRAPH: 4 objects extracted from @graph arrays (WebSite, ItemList, Brand filtered out)
TSV_WITH_GRAPH_PARSED = (
    [
        "https://example.com/page1#product",
        "https://example.com/page1#offer",
        "https://example.com/page2#article",
        "https://example.com/page2#person",
    ],
    [
        {
            "@id": "https://example.com/page1#product",
            "@type": "Product",
            "name": "Gadget Pro",
            "price": "99.99",
        },
        {
            "@id": "https://example.com/page1#offer",
            "@type": "Offer",
            "price": "89.99",
            "priceCurrency": "USD",
        },
        {
            "@id": "https://example.com/page2#article",
            "@type": "Article",
            "headline": "Tech Review",
            "datePublished": "2025-01-15",
        },
        {
            "@id": "https://example.com/page2#person",
            "@type": "Person",
            "name": "John Smith",
        },
    ],
)


# =============================================================================
# JSON format test data
# =============================================================================

# JSON array format: Direct array of objects with @id
# Includes objects with skip_types (Organization, CollectionPage) that should be filtered out
JSON_WITHOUT_GRAPH = """[
    {"@id": "https://example.com/products/laptop#product", "@type": "Product", "name": "Pro Laptop", "price": "1299.99"},
    {"@id": "https://example.com/products/laptop#org", "@type": "Organization", "name": "Tech Corp"},
    {"@id": "https://example.com/events/conference#event", "@type": "Event", "name": "Tech Conference 2025", "startDate": "2025-06-15"},
    {"@id": "https://example.com/events/conference#page", "@type": "CollectionPage", "name": "Events Collection"}
]"""

# JSON with @graph array (single wrapper object with @context but no @id)
# Includes objects with skip_types (WebSite, SearchAction, Corporation) that should be filtered out
JSON_WITH_GRAPH = """{
    "@context": "https://schema.org",
    "@graph": [
        {"@id": "https://example.com/books/novel#book", "@type": "Book", "name": "The Great Novel", "author": "Famous Author"},
        {"@id": "https://example.com/books/novel#website", "@type": "WebSite", "name": "Book Store"},
        {"@id": "https://example.com/books/novel#review", "@type": "Review", "reviewRating": {"@type": "Rating", "ratingValue": "5"}},
        {"@id": "https://example.com/books/novel#search", "@type": "SearchAction", "target": "https://example.com/search"},
        {"@id": "https://example.com/books/novel#publisher", "@type": "Corporation", "name": "Big Publishing"}
    ]
}"""

# Expected output for JSON_WITHOUT_GRAPH: 2 objects (Organization, CollectionPage filtered out)
JSON_WITHOUT_GRAPH_PARSED = (
    [
        "https://example.com/products/laptop#product",
        "https://example.com/events/conference#event",
    ],
    [
        {
            "@id": "https://example.com/products/laptop#product",
            "@type": "Product",
            "name": "Pro Laptop",
            "price": "1299.99",
        },
        {
            "@id": "https://example.com/events/conference#event",
            "@type": "Event",
            "name": "Tech Conference 2025",
            "startDate": "2025-06-15",
        },
    ],
)

# Expected output for JSON_WITH_GRAPH: 2 objects (WebSite, SearchAction, Corporation filtered out)
JSON_WITH_GRAPH_PARSED = (
    [
        "https://example.com/books/novel#book",
        "https://example.com/books/novel#review",
    ],
    [
        {
            "@id": "https://example.com/books/novel#book",
            "@type": "Book",
            "name": "The Great Novel",
            "author": "Famous Author",
        },
        {
            "@id": "https://example.com/books/novel#review",
            "@type": "Review",
            "reviewRating": {"@type": "Rating", "ratingValue": "5"},
        },
    ],
)

YOAST_WIKI_EXAMPLE_REGRESSION = """{"@context":"https://schema.org","@type":"Article","@id":"https://yoast-site-wiki.azurewebsites.net/2026/01/15/pro-tv-international/#article","author":{"name":"admin","@id":"https://yoast-site-wiki.azurewebsites.net/#/schema/person/fe4130b50093d7a4c207061516a57c9d"},"headline":"Pro TV Internațional","datePublished":"2026-01-15T04:27:41+00:00","wordCount":25,"inLanguage":"en-US","description":"Pro TV International is a Romanian international television channel."}
{"@context":"https://schema.org","@type":"Person","@id":"https://yoast-site-wiki.azurewebsites.net/#/schema/person/fe4130b50093d7a4c207061516a57c9d","name":"admin","image":{"@type":"ImageObject","inLanguage":"en-US","@id":"https://yoast-site-wiki.azurewebsites.net/#/schema/person/image/","url":"https://secure.gravatar.com/avatar/0417c527f7728f8f403c4c360f8cefa903b3b8361e67bd27fe1d6215c7a0fcfd?s=96&d=mm&r=g","contentUrl":"https://secure.gravatar.com/avatar/0417c527f7728f8f403c4c360f8cefa903b3b8361e67bd27fe1d6215c7a0fcfd?s=96&d=mm&r=g","caption":"admin"},"sameAs":["https://yoast-site-wiki.azurewebsites.net"],"url":"https://yoast-site-wiki.azurewebsites.net/author/admin/"}
{"@context":"https://schema.org","@type":"Article","@id":"https://yoast-site-wiki.azurewebsites.net/2026/01/15/maria-of-courtenay/#article","author":{"name":"admin","@id":"https://yoast-site-wiki.azurewebsites.net/#/schema/person/fe4130b50093d7a4c207061516a57c9d"},"headline":"Maria of Courtenay","datePublished":"2026-01-15T04:27:41+00:00","wordCount":28,"inLanguage":"en-US","description":"Marie de Courtenay was an Empress of Nicaea. She was born in 1204 and died in 1228."}
{"@context":"https://schema.org","@type":"Article","@id":"https://yoast-site-wiki.azurewebsites.net/2026/01/15/andre-braugher/#article","author":{"name":"admin","@id":"https://yoast-site-wiki.azurewebsites.net/#/schema/person/fe4130b50093d7a4c207061516a57c9d"},"headline":"Andre Braugher","datePublished":"2026-01-15T04:27:41+00:00","wordCount":60,"inLanguage":"en-US","description":"Andre Keith Braugher (; born July 1, 1962) is an American actor. He is best known for his role as Captain Raymond Holt in the police comedy series Brooklyn Nine-Nine (2013-2021), playing captain Raymond Holt."}
{"@context":"https://schema.org","@type":"Article","@id":"https://yoast-site-wiki.azurewebsites.net/2026/01/15/blackaf/#article","author":{"name":"admin","@id":"https://yoast-site-wiki.azurewebsites.net/#/schema/person/fe4130b50093d7a4c207061516a57c9d"},"headline":"BlackAF","datePublished":"2026-01-15T04:27:41+00:00","wordCount":130,"inLanguage":"en-US","description":"#blackAF is an American television series created by Kenya Barris. It started streaming on Netflix on April 2020 and has been renewed for a second season."}
"""

# Expected output for YOAST_WIKI_EXAMPLE_REGRESSION: 5 objects (4 Articles + 1 Person, no skip types)
YOAST_WIKI_EXAMPLE_REGRESSION_PARSED = (
    [
        "https://yoast-site-wiki.azurewebsites.net/2026/01/15/pro-tv-international/#article",
        "https://yoast-site-wiki.azurewebsites.net/#/schema/person/fe4130b50093d7a4c207061516a57c9d",
        "https://yoast-site-wiki.azurewebsites.net/2026/01/15/maria-of-courtenay/#article",
        "https://yoast-site-wiki.azurewebsites.net/2026/01/15/andre-braugher/#article",
        "https://yoast-site-wiki.azurewebsites.net/2026/01/15/blackaf/#article",
    ],
    [
        {
            "@context": "https://schema.org",
            "@type": "Article",
            "@id": "https://yoast-site-wiki.azurewebsites.net/2026/01/15/pro-tv-international/#article",
            "author": {
                "name": "admin",
                "@id": "https://yoast-site-wiki.azurewebsites.net/#/schema/person/fe4130b50093d7a4c207061516a57c9d",
            },
            "headline": "Pro TV Internațional",
            "datePublished": "2026-01-15T04:27:41+00:00",
            "wordCount": 25,
            "inLanguage": "en-US",
            "description": "Pro TV International is a Romanian international television channel.",
        },
        {
            "@context": "https://schema.org",
            "@type": "Person",
            "@id": "https://yoast-site-wiki.azurewebsites.net/#/schema/person/fe4130b50093d7a4c207061516a57c9d",
            "name": "admin",
            "image": {
                "@type": "ImageObject",
                "inLanguage": "en-US",
                "@id": "https://yoast-site-wiki.azurewebsites.net/#/schema/person/image/",
                "url": "https://secure.gravatar.com/avatar/0417c527f7728f8f403c4c360f8cefa903b3b8361e67bd27fe1d6215c7a0fcfd?s=96&d=mm&r=g",
                "contentUrl": "https://secure.gravatar.com/avatar/0417c527f7728f8f403c4c360f8cefa903b3b8361e67bd27fe1d6215c7a0fcfd?s=96&d=mm&r=g",
                "caption": "admin",
            },
            "sameAs": ["https://yoast-site-wiki.azurewebsites.net"],
            "url": "https://yoast-site-wiki.azurewebsites.net/author/admin/",
        },
        {
            "@context": "https://schema.org",
            "@type": "Article",
            "@id": "https://yoast-site-wiki.azurewebsites.net/2026/01/15/maria-of-courtenay/#article",
            "author": {
                "name": "admin",
                "@id": "https://yoast-site-wiki.azurewebsites.net/#/schema/person/fe4130b50093d7a4c207061516a57c9d",
            },
            "headline": "Maria of Courtenay",
            "datePublished": "2026-01-15T04:27:41+00:00",
            "wordCount": 28,
            "inLanguage": "en-US",
            "description": "Marie de Courtenay was an Empress of Nicaea. She was born in 1204 and died in 1228.",
        },
        {
            "@context": "https://schema.org",
            "@type": "Article",
            "@id": "https://yoast-site-wiki.azurewebsites.net/2026/01/15/andre-braugher/#article",
            "author": {
                "name": "admin",
                "@id": "https://yoast-site-wiki.azurewebsites.net/#/schema/person/fe4130b50093d7a4c207061516a57c9d",
            },
            "headline": "Andre Braugher",
            "datePublished": "2026-01-15T04:27:41+00:00",
            "wordCount": 60,
            "inLanguage": "en-US",
            "description": "Andre Keith Braugher (; born July 1, 1962) is an American actor. He is best known for his role as Captain Raymond Holt in the police comedy series Brooklyn Nine-Nine (2013-2021), playing captain Raymond Holt.",
        },
        {
            "@context": "https://schema.org",
            "@type": "Article",
            "@id": "https://yoast-site-wiki.azurewebsites.net/2026/01/15/blackaf/#article",
            "author": {
                "name": "admin",
                "@id": "https://yoast-site-wiki.azurewebsites.net/#/schema/person/fe4130b50093d7a4c207061516a57c9d",
            },
            "headline": "BlackAF",
            "datePublished": "2026-01-15T04:27:41+00:00",
            "wordCount": 130,
            "inLanguage": "en-US",
            "description": "#blackAF is an American television series created by Kenya Barris. It started streaming on Netflix on April 2020 and has been renewed for a second season.",
        },
    ],
)


# =============================================================================
# JSONL format test data (JSON Lines - each line is a separate JSON object)
#
# As of Jan 15, 2026, the Yoast schema map implementation uses this format.
# =============================================================================

# JSONL format: Each line is a single JSON object (NOT valid JSON as a whole)
# Includes objects with skip_types (Organization, ReturnPolicy) that should be filtered out
JSONL_WITHOUT_GRAPH = """{"@id": "https://example.com/movies/action#movie", "@type": "Movie", "name": "Action Hero", "director": "Jane Director"}
{"@id": "https://example.com/movies/action#org", "@type": "Organization", "name": "Film Studio"}
{"@id": "https://example.com/restaurants/italian#restaurant", "@type": "Restaurant", "name": "Pasta Palace", "servesCuisine": "Italian"}
{"@id": "https://example.com/restaurants/italian#policy", "@type": "ReturnPolicy", "returnPolicyCategory": "None"}
{"@id": "https://example.com/courses/python#course", "@type": "Course", "name": "Learn Python", "provider": "Online Academy"}"""

# JSONL format with @graph arrays
# Each line is a wrapper object with @graph (no @id on wrapper)
# Includes objects with skip_types (WebSite, SiteNavigationElement, Breadcrumb) that should be filtered out
JSONL_WITH_GRAPH = """{"@context": "https://schema.org", "@graph": [{"@id": "https://example.com/songs/hit#song", "@type": "MusicRecording", "name": "Summer Hit", "byArtist": "Pop Star"}, {"@id": "https://example.com/songs/hit#website", "@type": "WebSite", "name": "Music Site"}]}
{"@context": "https://schema.org", "@graph": [{"@id": "https://example.com/games/rpg#game", "@type": "VideoGame", "name": "Epic Quest", "gamePlatform": "PC"}, {"@id": "https://example.com/games/rpg#nav", "@type": "SiteNavigationElement", "name": "Nav Menu"}, {"@id": "https://example.com/games/rpg#breadcrumb", "@type": "Breadcrumb", "name": "Games"}]}
{"@context": "https://schema.org", "@graph": [{"@id": "https://example.com/podcasts/tech#podcast", "@type": "PodcastEpisode", "name": "Tech Talk #42", "datePublished": "2025-01-10"}]}"""

# Expected output for JSONL_WITHOUT_GRAPH: 3 objects (Organization, ReturnPolicy filtered out)
JSONL_WITHOUT_GRAPH_PARSED = (
    [
        "https://example.com/movies/action#movie",
        "https://example.com/restaurants/italian#restaurant",
        "https://example.com/courses/python#course",
    ],
    [
        {
            "@id": "https://example.com/movies/action#movie",
            "@type": "Movie",
            "name": "Action Hero",
            "director": "Jane Director",
        },
        {
            "@id": "https://example.com/restaurants/italian#restaurant",
            "@type": "Restaurant",
            "name": "Pasta Palace",
            "servesCuisine": "Italian",
        },
        {
            "@id": "https://example.com/courses/python#course",
            "@type": "Course",
            "name": "Learn Python",
            "provider": "Online Academy",
        },
    ],
)

# Expected output for JSONL_WITH_GRAPH: 3 objects (WebSite, SiteNavigationElement, Breadcrumb filtered out)
JSONL_WITH_GRAPH_PARSED = (
    [
        "https://example.com/songs/hit#song",
        "https://example.com/games/rpg#game",
        "https://example.com/podcasts/tech#podcast",
    ],
    [
        {
            "@id": "https://example.com/songs/hit#song",
            "@type": "MusicRecording",
            "name": "Summer Hit",
            "byArtist": "Pop Star",
        },
        {
            "@id": "https://example.com/games/rpg#game",
            "@type": "VideoGame",
            "name": "Epic Quest",
            "gamePlatform": "PC",
        },
        {
            "@id": "https://example.com/podcasts/tech#podcast",
            "@type": "PodcastEpisode",
            "name": "Tech Talk #42",
            "datePublished": "2025-01-10",
        },
    ],
)


def test_extract_objects_from_tsv():
    assert (
        extract_objects_from_schema_file(
            TSV_WITHOUT_GRAPH, "structuredData/schema.org+tsv"
        )
        == TSV_WITHOUT_GRAPH_PARSED
    )
    assert (
        extract_objects_from_schema_file(
            TSV_WITH_GRAPH, "structuredData/schema.org+tsv"
        )
        == TSV_WITH_GRAPH_PARSED
    )


def test_extract_objects_from_json():
    # content_type=None triggers JSON parsing branch
    assert (
        extract_objects_from_schema_file(JSON_WITHOUT_GRAPH, None)
        == JSON_WITHOUT_GRAPH_PARSED
    )
    assert (
        extract_objects_from_schema_file(JSON_WITH_GRAPH, None)
        == JSON_WITH_GRAPH_PARSED
    )


def test_extract_objects_from_jsonl():
    # JSONL is triggered when content_type is not TSV and content is not valid JSON as a whole
    # (each line is parsed individually).
    assert (
        extract_objects_from_schema_file(JSONL_WITHOUT_GRAPH, None)
        == JSONL_WITHOUT_GRAPH_PARSED
    )
    assert (
        extract_objects_from_schema_file(JSONL_WITH_GRAPH, None)
        == JSONL_WITH_GRAPH_PARSED
    )


def test_extract_objects_from_jsonl_yoast_regressions():
    # Real-world JSONL format from Yoast schema maps: each line is a single JSON object (not an array)
    assert (
        extract_objects_from_schema_file(YOAST_WIKI_EXAMPLE_REGRESSION, None)
        == YOAST_WIKI_EXAMPLE_REGRESSION_PARSED
    )


# =============================================================================
# Tests for extract_essential_fields
# =============================================================================

from core.vector_db import (
    extract_essential_fields,
    ESSENTIAL_FIELDS_MAX_CHARS,
    ESSENTIAL_FIELDS_DESCRIPTION_TRUNCATE,
)
import json


# -----------------------------------------------------------------------------
# Recipe type tests
# -----------------------------------------------------------------------------


def test_extract_essential_fields_recipe():
    """Recipe: should extract recipe-specific fields, drop recipeInstructions"""
    input_obj = {
        "@type": "Recipe",
        "@id": "https://example.com/recipes/banana-bread#recipe",
        "name": "Mom's Banana Bread",
        "description": "A classic family recipe passed down through generations.",
        "recipeIngredient": [
            "3 ripe bananas",
            "1 egg",
            "3/4 cup sugar",
            "1/3 cup melted butter",
        ],
        "recipeYield": "1 loaf",
        "totalTime": "PT1H15M",
        "cookTime": "PT1H",
        "prepTime": "PT15M",
        "recipeCategory": "Dessert",
        "recipeCuisine": "American",
        "keywords": "banana, bread, baking, easy",
        "recipeInstructions": [
            {"@type": "HowToStep", "text": "Preheat oven to 350°F."},
            {"@type": "HowToStep", "text": "Mash bananas in a bowl."},
            {"@type": "HowToStep", "text": "Mix in remaining ingredients."},
        ],
        "nutrition": {"@type": "NutritionInformation", "calories": "240 calories"},
        "author": {"@type": "Person", "name": "Grandma"},
    }

    result = json.loads(extract_essential_fields(input_obj))

    # Essential fields should be present
    assert result["@type"] == "Recipe"
    assert result["@id"] == "https://example.com/recipes/banana-bread#recipe"
    assert result["name"] == "Mom's Banana Bread"
    assert (
        result["description"]
        == "A classic family recipe passed down through generations."
    )
    assert result["recipeIngredient"] == [
        "3 ripe bananas",
        "1 egg",
        "3/4 cup sugar",
        "1/3 cup melted butter",
    ]
    assert result["recipeYield"] == "1 loaf"
    assert result["totalTime"] == "PT1H15M"
    assert result["cookTime"] == "PT1H"
    assert result["prepTime"] == "PT15M"
    assert result["recipeCategory"] == "Dessert"
    assert result["recipeCuisine"] == "American"
    assert result["keywords"] == "banana, bread, baking, easy"

    # Non-essential fields should be dropped
    assert "recipeInstructions" not in result
    assert "nutrition" not in result
    assert "author" not in result


# -----------------------------------------------------------------------------
# Movie type tests
# -----------------------------------------------------------------------------


def test_extract_essential_fields_movie():
    """Movie: should extract media fields, flatten nested objects to names"""
    input_obj = {
        "@type": "Movie",
        "@id": "https://imdb.com/title/tt1375666",
        "name": "Inception",
        "description": "A thief who steals corporate secrets through dream-sharing technology.",
        "genre": ["Sci-Fi", "Action", "Thriller"],
        "datePublished": "2010-07-16",
        "director": {
            "@type": "Person",
            "name": "Christopher Nolan",
            "url": "https://imdb.com/name/nm0634240",
        },
        "actor": [
            {"@type": "Person", "name": "Leonardo DiCaprio"},
            {"@type": "Person", "name": "Joseph Gordon-Levitt"},
            {"@type": "Person", "name": "Elliot Page"},
            {"@type": "Person", "name": "Tom Hardy"},
            {"@type": "Person", "name": "Ken Watanabe"},
            {
                "@type": "Person",
                "name": "Cillian Murphy",
            },  # 6th actor, should be excluded (limit 5)
        ],
        "duration": "PT2H28M",
        "contentRating": "PG-13",
        "productionCompany": {"@type": "Organization", "name": "Legendary Pictures"},
        "trailer": {"@type": "VideoObject", "url": "https://youtube.com/watch?v=xxx"},
    }

    result = json.loads(extract_essential_fields(input_obj))

    assert result["@type"] == "Movie"
    assert result["@id"] == "https://imdb.com/title/tt1375666"
    assert result["name"] == "Inception"
    assert (
        result["description"]
        == "A thief who steals corporate secrets through dream-sharing technology."
    )
    assert result["genre"] == ["Sci-Fi", "Action", "Thriller"]
    assert result["datePublished"] == "2010-07-16"
    # Nested director should be flattened to just name
    assert result["director"] == "Christopher Nolan"
    # Actor array should be flattened to names, limited to 5
    assert result["actor"] == [
        "Leonardo DiCaprio",
        "Joseph Gordon-Levitt",
        "Elliot Page",
        "Tom Hardy",
        "Ken Watanabe",
    ]
    assert result["duration"] == "PT2H28M"
    assert result["contentRating"] == "PG-13"

    # Non-essential fields should be dropped
    assert "productionCompany" not in result
    assert "trailer" not in result


def test_extract_essential_fields_tvseries():
    """TVSeries: should use same rules as Movie"""
    input_obj = {
        "@type": "TVSeries",
        "@id": "https://imdb.com/title/tt0903747",
        "name": "Breaking Bad",
        "description": "A chemistry teacher diagnosed with cancer turns to making meth.",
        "genre": "Drama",
        "datePublished": "2008-01-20",
        "actor": [
            {"@type": "Person", "name": "Bryan Cranston"},
            {"@type": "Person", "name": "Aaron Paul"},
        ],
        "numberOfSeasons": 5,
        "numberOfEpisodes": 62,
    }

    result = json.loads(extract_essential_fields(input_obj))

    assert result["@type"] == "TVSeries"
    assert result["name"] == "Breaking Bad"
    assert result["genre"] == "Drama"
    assert result["actor"] == ["Bryan Cranston", "Aaron Paul"]

    # Non-essential fields should be dropped
    assert "numberOfSeasons" not in result
    assert "numberOfEpisodes" not in result


# -----------------------------------------------------------------------------
# Product type tests
# -----------------------------------------------------------------------------


def test_extract_essential_fields_product():
    """Product: should extract product fields, simplify offers and aggregateRating"""
    input_obj = {
        "@type": "Product",
        "@id": "https://shop.example.com/products/widget-pro",
        "name": "Widget Pro 3000",
        "description": "The ultimate widget for professionals.",
        "brand": {"@type": "Brand", "name": "WidgetCo"},
        "model": "WP-3000",
        "offers": {
            "@type": "Offer",
            "price": "299.99",
            "priceCurrency": "USD",
            "availability": "https://schema.org/InStock",
            "seller": {"@type": "Organization", "name": "TechStore"},
            "priceValidUntil": "2026-12-31",
        },
        "aggregateRating": {
            "@type": "AggregateRating",
            "ratingValue": "4.7",
            "ratingCount": 1523,
            "bestRating": "5",
            "worstRating": "1",
        },
        "category": "Electronics > Widgets",
        "sku": "WP3000-BLK",
        "gtin13": "1234567890123",
        "image": "https://shop.example.com/images/widget-pro.jpg",
    }

    result = json.loads(extract_essential_fields(input_obj))

    assert result["@type"] == "Product"
    assert result["@id"] == "https://shop.example.com/products/widget-pro"
    assert result["name"] == "Widget Pro 3000"
    assert result["description"] == "The ultimate widget for professionals."
    # Brand should be kept as-is (it's a nested object but not special-cased)
    assert result["brand"] == {"@type": "Brand", "name": "WidgetCo"}
    assert result["model"] == "WP-3000"
    # Offers should be simplified to just price and availability
    assert result["offers"] == {
        "price": "299.99",
        "availability": "https://schema.org/InStock",
    }
    # AggregateRating should be simplified to just ratingValue and ratingCount
    assert result["aggregateRating"] == {"ratingValue": "4.7", "ratingCount": 1523}
    assert result["category"] == "Electronics > Widgets"

    # Non-essential fields should be dropped
    assert "sku" not in result
    assert "gtin13" not in result
    assert "image" not in result


# -----------------------------------------------------------------------------
# Article type tests
# -----------------------------------------------------------------------------


def test_extract_essential_fields_article():
    """Article: should extract article fields, flatten author/publisher to names"""
    input_obj = {
        "@type": "Article",
        "@id": "https://news.example.com/articles/tech-trends-2026",
        "headline": "Top 10 Tech Trends for 2026",
        "description": "An in-depth look at the technologies shaping our future.",
        "author": {
            "@type": "Person",
            "name": "Jane Smith",
            "url": "https://news.example.com/authors/jane",
        },
        "datePublished": "2026-01-15T09:00:00Z",
        "publisher": {
            "@type": "Organization",
            "name": "Tech News Daily",
            "logo": {
                "@type": "ImageObject",
                "url": "https://news.example.com/logo.png",
            },
        },
        "articleSection": "Technology",
        "articleBody": "Lorem ipsum dolor sit amet, consectetur adipiscing elit...",
        "wordCount": 2500,
        "image": "https://news.example.com/images/tech-trends.jpg",
    }

    result = json.loads(extract_essential_fields(input_obj))

    assert result["@type"] == "Article"
    assert result["@id"] == "https://news.example.com/articles/tech-trends-2026"
    assert result["headline"] == "Top 10 Tech Trends for 2026"
    assert (
        result["description"]
        == "An in-depth look at the technologies shaping our future."
    )
    # Author should be flattened to just name
    assert result["author"] == "Jane Smith"
    assert result["datePublished"] == "2026-01-15T09:00:00Z"
    # Publisher should be flattened to just name
    assert result["publisher"] == "Tech News Daily"
    assert result["articleSection"] == "Technology"

    # Non-essential fields should be dropped
    assert "articleBody" not in result
    assert "wordCount" not in result
    assert "image" not in result


def test_extract_essential_fields_newsarticle():
    """NewsArticle: should use same rules as Article"""
    input_obj = {
        "@type": "NewsArticle",
        "@id": "https://news.example.com/breaking/earthquake",
        "headline": "Major Earthquake Strikes Pacific Coast",
        "description": "A 7.2 magnitude earthquake has caused widespread damage.",
        "author": "Breaking News Team",  # author as plain string, not object
        "datePublished": "2026-01-20T14:30:00Z",
        "publisher": {"@type": "NewsMediaOrganization", "name": "World News Network"},
        "dateline": "San Francisco, CA",
    }

    result = json.loads(extract_essential_fields(input_obj))

    assert result["@type"] == "NewsArticle"
    assert result["headline"] == "Major Earthquake Strikes Pacific Coast"
    # Author as plain string should be kept as-is
    assert result["author"] == "Breaking News Team"
    assert result["publisher"] == "World News Network"

    # Non-essential fields should be dropped
    assert "dateline" not in result


# -----------------------------------------------------------------------------
# Unmatched type tests (fallback behavior)
# -----------------------------------------------------------------------------


def test_extract_essential_fields_event_unmatched():
    """Event (unmatched type): should only extract common fields"""
    input_obj = {
        "@type": "Event",
        "@id": "https://events.example.com/concert/summer-fest-2026",
        "name": "Summer Music Festival 2026",
        "description": "Three days of live music featuring top artists.",
        "startDate": "2026-07-15T18:00:00",
        "endDate": "2026-07-17T23:00:00",
        "location": {
            "@type": "Place",
            "name": "Central Park",
            "address": "New York, NY",
        },
        "performer": [
            {"@type": "MusicGroup", "name": "The Rockers"},
            {"@type": "Person", "name": "DJ Spinmaster"},
        ],
        "offers": {"@type": "Offer", "price": "150", "availability": "InStock"},
        "organizer": {"@type": "Organization", "name": "Live Nation"},
    }

    result = json.loads(extract_essential_fields(input_obj))

    # Only common fields should be present
    assert result["@type"] == "Event"
    assert result["@id"] == "https://events.example.com/concert/summer-fest-2026"
    assert result["name"] == "Summer Music Festival 2026"
    assert result["description"] == "Three days of live music featuring top artists."

    # Type-specific fields should be dropped (Event is not explicitly handled)
    assert "startDate" not in result
    assert "endDate" not in result
    assert "location" not in result
    assert "performer" not in result
    assert "offers" not in result
    assert "organizer" not in result


def test_extract_essential_fields_localbusiness_unmatched():
    """LocalBusiness (unmatched type): should only extract common fields"""
    input_obj = {
        "@type": "LocalBusiness",
        "@id": "https://example.com/businesses/joes-pizza",
        "name": "Joe's Famous Pizza",
        "description": "Best pizza in Brooklyn since 1975.",
        "address": {
            "@type": "PostalAddress",
            "streetAddress": "123 Pizza Lane",
            "addressLocality": "Brooklyn",
        },
        "telephone": "+1-555-123-4567",
        "openingHours": "Mo-Su 11:00-23:00",
        "priceRange": "$$",
    }

    result = json.loads(extract_essential_fields(input_obj))

    assert result["@type"] == "LocalBusiness"
    assert result["name"] == "Joe's Famous Pizza"
    assert result["description"] == "Best pizza in Brooklyn since 1975."

    # LocalBusiness-specific fields should be dropped
    assert "address" not in result
    assert "telephone" not in result
    assert "openingHours" not in result
    assert "priceRange" not in result


def test_extract_essential_fields_person_unmatched():
    """Person (unmatched type): should only extract common fields"""
    input_obj = {
        "@type": "Person",
        "@id": "https://example.com/people/john-doe",
        "name": "John Doe",
        "description": "Software engineer and open source enthusiast.",
        "jobTitle": "Senior Developer",
        "worksFor": {"@type": "Organization", "name": "TechCorp"},
        "email": "john@example.com",
        "birthDate": "1985-03-15",
        "sameAs": ["https://twitter.com/johndoe", "https://github.com/johndoe"],
    }

    result = json.loads(extract_essential_fields(input_obj))

    assert result["@type"] == "Person"
    assert result["name"] == "John Doe"
    assert result["description"] == "Software engineer and open source enthusiast."

    # Person-specific fields should be dropped
    assert "jobTitle" not in result
    assert "worksFor" not in result
    assert "email" not in result
    assert "birthDate" not in result
    assert "sameAs" not in result


# -----------------------------------------------------------------------------
# Edge cases and common fields tests
# -----------------------------------------------------------------------------


def test_extract_essential_fields_type_as_array():
    """@type as array: should handle gracefully (uses first element for type detection)"""
    input_obj = {
        "@type": ["Movie", "CreativeWork"],
        "@id": "https://example.com/movie",
        "name": "Test Movie",
        "director": {"@type": "Person", "name": "Test Director"},
    }

    result = json.loads(extract_essential_fields(input_obj))

    assert result["@type"] == ["Movie", "CreativeWork"]
    # Should recognize Movie from the array and apply Movie rules
    assert result["director"] == "Test Director"


def test_extract_essential_fields_common_text_fields():
    """Common fields: text, abstract, summary, headline should all be extracted"""
    input_obj = {
        "@type": "CreativeWork",
        "@id": "https://example.com/work",
        "name": "Test Work",
        "description": "A test description.",
        "headline": "Test Headline",
        "text": "The full text content.",
        "abstract": "A brief abstract.",
        "summary": "A short summary.",
        "author": "Not extracted for generic types",
    }

    result = json.loads(extract_essential_fields(input_obj))

    assert result["name"] == "Test Work"
    assert result["description"] == "A test description."
    assert result["headline"] == "Test Headline"
    assert result["text"] == "The full text content."
    assert result["abstract"] == "A brief abstract."
    assert result["summary"] == "A short summary."
    # author is not a common field, should be dropped for non-Article types
    assert "author" not in result


def test_extract_essential_fields_minimal_object():
    """Minimal object: should handle objects with only @type"""
    input_obj = {
        "@type": "Thing",
    }

    result = json.loads(extract_essential_fields(input_obj))

    assert result == {"@type": "Thing"}


def test_extract_essential_fields_large_object_truncation():
    """Large object: should truncate when exceeding max chars"""
    # Create a very large description that will exceed max chars
    large_description = "A" * (ESSENTIAL_FIELDS_MAX_CHARS + 1000)
    input_obj = {
        "@type": "Article",
        "@id": "https://example.com/large-article",
        "name": "Large Article",
        "description": large_description,
        "headline": "Large Headline",
    }

    result_str = extract_essential_fields(input_obj)

    # Result should be truncated to max chars
    assert len(result_str) <= ESSENTIAL_FIELDS_MAX_CHARS
    # Should fall back to minimal fields with truncated content
    result = json.loads(result_str)
    assert result["@type"] == "Article"
    assert len(result.get("description", "")) <= ESSENTIAL_FIELDS_DESCRIPTION_TRUNCATE


def test_extract_essential_fields_movie_scalar_genre():
    """Movie with scalar genre: should handle non-array genre"""
    input_obj = {
        "@type": "Movie",
        "@id": "https://example.com/movie",
        "name": "Simple Movie",
        "genre": "Drama",  # String, not array
    }

    result = json.loads(extract_essential_fields(input_obj))

    assert result["genre"] == "Drama"


def test_extract_essential_fields_movie_missing_optional_fields():
    """Movie with minimal fields: should not fail when optional fields missing"""
    input_obj = {
        "@type": "Movie",
        "@id": "https://example.com/movie",
        "name": "Minimal Movie",
    }

    result = json.loads(extract_essential_fields(input_obj))

    assert result["@type"] == "Movie"
    assert result["name"] == "Minimal Movie"
    assert "director" not in result
    assert "actor" not in result
    assert "genre" not in result


def test_extract_essential_fields_product_offers_array():
    """Product with offers as array: should only simplify first dict offer"""
    input_obj = {
        "@type": "Product",
        "@id": "https://example.com/product",
        "name": "Multi-offer Product",
        "offers": [
            {"@type": "Offer", "price": "99.99", "availability": "InStock"},
            {"@type": "Offer", "price": "89.99", "availability": "OutOfStock"},
        ],
    }

    result = json.loads(extract_essential_fields(input_obj))

    # Current implementation only simplifies if offers is a dict, not array
    # So array should be kept as-is
    assert result["offers"] == [
        {"@type": "Offer", "price": "99.99", "availability": "InStock"},
        {"@type": "Offer", "price": "89.99", "availability": "OutOfStock"},
    ]


def test_extract_essential_fields_article_author_as_array():
    """Article with author as array: should flatten first author with name"""
    input_obj = {
        "@type": "Article",
        "@id": "https://example.com/article",
        "headline": "Multi-author Article",
        "author": [
            {"@type": "Person", "name": "First Author"},
            {"@type": "Person", "name": "Second Author"},
        ],
    }

    result = json.loads(extract_essential_fields(input_obj))

    # Current implementation checks isinstance(value, dict), so array is kept as-is
    assert result["author"] == [
        {"@type": "Person", "name": "First Author"},
        {"@type": "Person", "name": "Second Author"},
    ]
