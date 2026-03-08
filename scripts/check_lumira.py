#!/usr/bin/env python3
"""Check Lumira's current state and recent creations."""

import json
from datetime import datetime
from pathlib import Path


def check_lumira_status():
    """Display Lumira's current personality state and recent works."""

    memory_file = Path("data/lumira_memory.json")

    if not memory_file.exists():
        print("🎨 Lumira hasn't created anything yet!")
        print("Run: python -m ai_artist.main --theme 'your theme'")
        return

    with open(memory_file) as f:
        memory = json.load(f)

    print("\n" + "=" * 60)
    print("✨ LUMIRA - Autonomous AI Artist")
    print("=" * 60)

    # Basic stats
    stats = memory.get("stats", {})
    total = stats.get("total_created", 0)
    best_score = stats.get("best_score", 0.0)

    print("\n📊 Creative Journey:")
    print(f"   Total Artworks: {total}")
    print(f"   Best Score: {best_score:.3f}")

    if total == 0:
        print("\n🌱 Lumira is just beginning her creative journey...")
        return

    # Recent works
    paintings = memory.get("paintings", [])
    recent = paintings[-5:] if paintings else []

    if recent:
        print("\n🎨 Recent Creations:")
        for i, painting in enumerate(recent, 1):
            timestamp = datetime.fromisoformat(painting["timestamp"])
            print(f"\n   {i}. {painting.get('subject', 'Unknown')}")
            print(f"      Mood: {painting.get('mood', 'Unknown')}")
            print(f"      Score: {painting.get('score', 0.0):.3f}")
            print(f"      Style: {painting.get('style', 'Unknown')}")
            print(f"      Created: {timestamp.strftime('%Y-%m-%d %H:%M')}")
            if "metadata" in painting and "reflection" in painting["metadata"]:
                print(f"      Reflection: {painting['metadata']['reflection'][:80]}...")

    # Preferences
    preferences = memory.get("preferences", {})
    fav_subjects = preferences.get("favorite_subjects", {})
    fav_styles = preferences.get("favorite_styles", {})

    if fav_subjects:
        top_subject = max(fav_subjects.items(), key=lambda x: x[1])
        print(f"\n💭 Favorite Subject: {top_subject[0]} ({top_subject[1]} times)")

    if fav_styles:
        top_style = max(fav_styles.items(), key=lambda x: x[1])
        print(f"   Favorite Style: {top_style[0]} ({top_style[1]} times)")

    print("\n" + "=" * 60)
    print("📖 Full memory at: data/lumira_memory.json")
    print("🖼️  Gallery at: gallery/")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    check_lumira_status()
