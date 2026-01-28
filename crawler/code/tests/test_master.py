#!/usr/bin/env python3
"""Test script for master.py with local test data"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'core'))

import master

def test_schema_map_parsing():
    """Test parsing of our generated schema_map.xml files"""

    # Test with a local server URL
    test_sites = [
        "http://localhost:8000/hebbarskitchen_com",
        "http://localhost:8000/hebbarskitchen_com/schema_map.xml",
        "http://localhost:8000/imdb_com"
    ]

    print("Testing schema URL extraction:\n")

    for site_url in test_sites:
        print(f"Testing: {site_url}")
        urls = master.get_schema_urls_from_robots(site_url)

        if urls:
            print(f"  Found {len(urls)} schema files:")
            for url in urls:
                print(f"    - {url}")
        else:
            print(f"  No schema files found")
        print()

def test_xml_parsing_directly():
    """Test XML parsing with actual content from our files"""

    localhost_port_format = """<?xml version="1.0" encoding="utf-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url contentType="structuredData/schema.org">
    <loc>http://localhost:8000/test_site/1.json</loc>
  </url>
  <url contentType="structuredData/schema.org">
    <loc>http://localhost:8000/test_site/2.json</loc>
  </url>
</urlset>"""

    # It is important to have an example without a port, as `urllib.parse.urlparse`
    # is slightly unintuitive--something like `subdomain.domain.com:80` is recognized
    # as a domain-port pair, but `subdomain.domain.com` is actually treated as a path
    # with no other segments.
    remote_with_tsv_format = """<?xml version="1.0" encoding="utf-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url contentType="structuredData/schema.org+tsv">
    <loc>https://yoast-site-recipes.azurewebsites.net/wp-json/yoast/v1/schema-aggregator/get-schema/post</loc>
  </url>
</urlset>"""

    urls: list[str] = master.parse_schema_map_xml(localhost_port_format, "http://localhost:8000/test_site/")
    assert urls == [
        ("http://localhost:8000/test_site/1.json", "structuredData/schema.org"),
        ("http://localhost:8000/test_site/2.json", "structuredData/schema.org"),
    ]
    
    urls = master.parse_schema_map_xml(remote_with_tsv_format, "https://yoast-site-recipes.azurewebsites.net/wp-json/yoast/v1/schema-aggregator/get-schema/post")
    assert urls == [
        ("https://yoast-site-recipes.azurewebsites.net/wp-json/yoast/v1/schema-aggregator/get-schema/post", "structuredData/schema.org+tsv")
    ]

if __name__ == "__main__":
    print("=" * 60)
    print("Testing Master.py with Schema Map Support")
    print("=" * 60)
    print()

    # Test direct XML parsing
    test_xml_parsing_directly()

    print("\n" + "=" * 60)
    print("To test with actual local data:")
    print("1. In another terminal: cd data/ && python3 -m http.server 8000")
    print("2. Then run this script again")
    print("=" * 60)

    # Uncomment to test with local server
    # test_schema_map_parsing()