#!/usr/bin/env python3
"""Generate a large synthetic vault for performance testing."""
import json
import random
import string
import time
from pathlib import Path

DOMAINS = [
    "github.com", "google.com", "amazon.com", "twitter.com", "x.com",
    "facebook.com", "instagram.com", "linkedin.com", "reddit.com", "netflix.com",
    "spotify.com", "apple.com", "microsoft.com", "dropbox.com", "slack.com",
    "discord.com", "zoom.us", "notion.so", "figma.com", "vercel.com",
    "stripe.com", "paypal.com", "ebay.com", "etsy.com", "airbnb.com",
    "uber.com", "lyft.com", "doordash.com", "grubhub.com", "twitch.tv",
    "youtube.com", "gmail.com", "outlook.com", "yahoo.com", "protonmail.com",
    "gitlab.com", "bitbucket.org", "jira.com", "confluence.com", "trello.com",
    "aws.amazon.com", "azure.microsoft.com", "cloud.google.com", "digitalocean.com",
    "heroku.com", "vercel.com", "netlify.com", "cloudflare.com", "fastly.com",
]

NAMES = [
    "GitHub", "Google", "Amazon", "Twitter", "X", "Facebook", "Instagram",
    "LinkedIn", "Reddit", "Netflix", "Spotify", "Apple", "Microsoft",
    "Dropbox", "Slack", "Discord", "Zoom", "Notion", "Figma", "Vercel",
    "Stripe", "PayPal", "eBay", "Etsy", "Airbnb", "Uber", "Lyft",
    "DoorDash", "Grubhub", "Twitch", "YouTube", "Gmail", "Outlook",
    "Yahoo", "ProtonMail", "GitLab", "Bitbucket", "Jira", "Confluence",
    "Trello", "AWS", "Azure", "GCP", "DigitalOcean", "Heroku", "Netlify",
    "Cloudflare", "Fastly", "Work", "Personal", "Old", "Main", "Backup",
    "Secondary", "Primary", "Dev", "Staging", "Prod", "Test", "Demo",
]

def rand_str(n=8):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=n))

def make_item(i, duplicate_of=None):
    """Generate a login item. If duplicate_of is set, create a variant."""
    if duplicate_of is not None:
        base = DOMAINS[duplicate_of % len(DOMAINS)]
        name = NAMES[duplicate_of % len(NAMES)]
        username = f"user{duplicate_of % 200}"
        password = f"password{duplicate_of % 500}"
        # Create variation: www subdomain, different URI path, or name suffix
        variants = [
            {"uri": f"https://{base}/login", "name": name},
            {"uri": f"https://www.{base}/login", "name": f"{name} Old"},
            {"uri": f"https://{base}/signin", "name": f"{name} Work"},
            {"uri": f"https://app.{base}/auth", "name": f"{name} Dev"},
        ]
        v = variants[i % len(variants)]
        return {
            "id": f"item-{i:05d}",
            "type": 1,
            "name": v["name"],
            "favorite": random.random() < 0.1,
            "login": {
                "uris": [{"uri": v["uri"]}],
                "username": username,
                "password": password,
                "totp": "otpauth://totp/secret" if random.random() < 0.3 else None,
            }
        }
    else:
        # Unique item
        domain = random.choice(DOMAINS)
        return {
            "id": f"item-{i:05d}",
            "type": 1,
            "name": f"{random.choice(NAMES)} {rand_str(4)}",
            "favorite": random.random() < 0.1,
            "login": {
                "uris": [{"uri": f"https://{domain}/{rand_str(6)}"}],
                "username": f"user{rand_str(5)}",
                "password": rand_str(12),
                "totp": "otpauth://totp/secret" if random.random() < 0.3 else None,
            }
        }

def generate_vault(n_items=5000, dup_ratio=0.3):
    """Generate vault with dup_ratio% duplicates."""
    items = []
    unique_count = int(n_items * (1 - dup_ratio))
    dup_count = n_items - unique_count
    
    # Generate unique items
    for i in range(unique_count):
        items.append(make_item(i))
    
    # Generate duplicates (2-4 copies per base)
    dup_idx = 0
    i = unique_count
    while i < n_items:
        base = dup_idx % unique_count
        copies = random.randint(2, 4)
        for c in range(copies):
            if i >= n_items:
                break
            items.append(make_item(i, duplicate_of=base))
            i += 1
        dup_idx += 1
    
    random.shuffle(items)
    
    return {
        "encrypted": False,
        "folders": [],
        "items": items
    }

if __name__ == "__main__":
    sizes = [500, 1000, 2000, 5000]
    for size in sizes:
        vault = generate_vault(size, dup_ratio=0.35)
        path = Path(f"stress_vault_{size}.json")
        with open(path, "w") as f:
            json.dump(vault, f)
        print(f"Generated {path} with {len(vault['items'])} items")
