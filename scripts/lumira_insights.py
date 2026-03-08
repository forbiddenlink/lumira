#!/usr/bin/env python3
"""Display Lumira's insights, profile, and what she's learning."""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ai_artist.personality.enhanced_memory import EnhancedMemorySystem
from src.ai_artist.personality.profile import ArtisticProfile


def show_profile():
    """Display Lumira's artistic profile and identity."""
    print("\n" + "=" * 70)
    print("✨ LUMIRA'S ARTISTIC IDENTITY")
    print("=" * 70)

    profile = ArtisticProfile()
    print(f"\n{profile.describe_self()}")

    print("\n📜 Artist Statement:")
    print(f"   {profile.artist_statement}")

    print("\n🎨 Signature Elements:")
    for element in profile.signature_elements:
        print(f"   • {element}")

    print("\n💭 Artistic Philosophy:")
    for key, value in profile.philosophy.items():
        print(f"   {key.title()}: {value}")


def show_insights():
    """Display what Lumira has learned from her experiences."""
    print("\n" + "=" * 70)
    print("🧠 LUMIRA'S LEARNING & INSIGHTS")
    print("=" * 70)

    memory = EnhancedMemorySystem()
    insights = memory.generate_insights()

    # Total creations
    print(f"\n📊 Total Creations: {insights['total_creations']}")

    # Style effectiveness
    if insights["style_effectiveness"]:
        print("\n🎨 Style Effectiveness (avg scores):")
        for style, avg_score in sorted(
            insights["style_effectiveness"].items(), key=lambda x: x[1], reverse=True
        ):
            print(f"   {style}: {avg_score:.3f}")

    # Mood patterns
    if insights["mood_patterns"]:
        print("\n💭 Mood Distribution:")
        for mood, count in sorted(
            insights["mood_patterns"].items(), key=lambda x: x[1], reverse=True
        ):
            print(f"   {mood}: {count} creations")

    # Best performing mood
    if insights["best_performing_mood"]:
        mood_data = insights["best_performing_mood"]
        print(f"\n⭐ Best Performing Mood: {mood_data['mood']}")
        print(f"   Avg Score: {mood_data['avg_score']:.3f}")
        print(f"   Count: {mood_data['count']}")

    # Recent episodes
    recent = memory.episodic.get_recent_episodes(count=5)
    if recent:
        print(f"\n📖 Recent Creative Episodes ({len(recent)}):")
        for episode in recent:
            timestamp = episode["timestamp"][:19]  # Remove microseconds
            event_type = episode["event_type"]
            mood = episode["emotional_state"].get("mood", "unknown")

            details = episode["details"]
            if "style" in details:
                style = details["style"]
                score = details.get("score", 0)
                print(f"   [{timestamp}] {event_type} ({mood})")
                print(f"      Style: {style}, Score: {score:.3f}")
                if "reflection" in details:
                    reflection = details["reflection"][:60]
                    print(f"      Reflection: {reflection}...")


def show_working_memory():
    """Display Lumira's current session context."""
    print("\n" + "=" * 70)
    print("🔄 WORKING MEMORY (Current Session)")
    print("=" * 70)

    memory = EnhancedMemorySystem()

    if memory.working.current_context:
        print("\n📝 Current Context:")
        for key, value in memory.working.current_context.items():
            print(f"   {key}: {value}")
    else:
        print("\n   (No active session context)")

    if memory.working.active_goals:
        print("\n🎯 Active Goals:")
        for goal in memory.working.active_goals:
            print(f"   • {goal}")
    else:
        print("\n   (No active goals set)")


def main():
    """Main entry point."""
    print("\n" + "=" * 70)
    print("🎨 LUMIRA - AUTONOMOUS AI ARTIST")
    print("=" * 70)

    # Show all sections
    show_profile()
    show_insights()
    show_working_memory()

    print("\n" + "=" * 70)
    print("✨ Keep creating, Lumira!")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
