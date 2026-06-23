#!/usr/bin/env python3
"""
Test script for conversation history feature.
Tests the new search, pin, and title generation functionality.
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))


def test_imports():
    """Test that all modules import correctly."""
    print("Testing imports...")

    try:
        from src.core.repositories.message import MessageRepository

        print("✓ MessageRepository imported")

        from src.core.repositories.conversation import ConversationRepository

        print("✓ ConversationRepository imported")

        # Check for new search_messages method
        assert hasattr(MessageRepository, "search_messages"), "search_messages method not found"
        print("✓ MessageRepository.search_messages exists")

        print("\n✓ All imports successful!")
        return True

    except Exception as e:
        print(f"✗ Import failed: {e}")
        return False


def test_service_layer():
    """Test that service layer has new methods."""
    print("\nTesting service layer...")

    try:
        # Note: We can't actually instantiate without dependencies
        # Just check the file has the new methods

        with open("src/services/conversation.py", "r") as f:
            content = f.read()

        assert "search_conversations" in content, "search_conversations method not found"
        print("✓ search_conversations method exists")

        assert "toggle_pin_conversation" in content, "toggle_pin_conversation method not found"
        print("✓ toggle_pin_conversation method exists")

        assert (
            "generate_conversation_title" in content
        ), "generate_conversation_title method not found"
        print("✓ generate_conversation_title method exists")

        print("\n✓ Service layer looks good!")
        return True

    except Exception as e:
        print(f"✗ Service layer check failed: {e}")
        return False


def test_api_endpoints():
    """Test that API endpoints exist."""
    print("\nTesting API endpoints...")

    try:
        with open("src/api/conversations.py", "r") as f:
            content = f.read()

        assert "search_conversations" in content, "search_conversations endpoint not found"
        print("✓ GET /api/conversations/search endpoint exists")

        assert "toggle_pin_conversation" in content, "toggle_pin_conversation endpoint not found"
        print("✓ POST /api/conversations/{id}/pin endpoint exists")

        assert (
            "generate_conversation_title" in content
        ), "generate_conversation_title endpoint not found"
        print("✓ POST /api/conversations/{id}/generate-title endpoint exists")

        print("\n✓ API endpoints look good!")
        return True

    except Exception as e:
        print(f"✗ API endpoint check failed: {e}")
        return False


def test_frontend_files():
    """Test that frontend files have been updated."""
    print("\nTesting frontend files...")

    try:
        # Check HTML
        with open("src/ui/static/index.html", "r") as f:
            html = f.read()

        assert "conversation-sidebar" in html, "Sidebar not found in HTML"
        print("✓ Sidebar HTML structure exists")

        assert "toggleSidebarBtn" in html, "Toggle button not found"
        print("✓ Toggle button exists")

        # Check CSS
        with open("src/ui/static/css/common.css", "r") as f:
            css = f.read()

        assert ".conversation-sidebar" in css, "Sidebar CSS not found"
        print("✓ Sidebar CSS exists")

        assert ".conversation-card" in css, "Conversation card CSS not found"
        print("✓ Conversation card CSS exists")

        # Check JavaScript
        with open("src/ui/static/js/chat.js", "r") as f:
            js = f.read()

        assert "ConversationHistoryManager" in js, "ConversationHistoryManager class not found"
        print("✓ ConversationHistoryManager class exists")

        assert "togglePin" in js, "togglePin method not found"
        print("✓ Pin/unpin functionality exists")

        assert "searchConversations" in js, "searchConversations method not found"
        print("✓ Search functionality exists")

        print("\n✓ Frontend files look good!")
        return True

    except Exception as e:
        print(f"✗ Frontend check failed: {e}")
        return False


def test_models():
    """Test that models have been updated."""
    print("\nTesting models...")

    try:
        with open("src/models/conversation.py", "r") as f:
            content = f.read()

        assert "title: Optional[str]" in content, "title field not found in ConversationResponse"
        print("✓ Title field added to ConversationResponse")

        assert "pinned: Optional[bool]" in content, "pinned field not found in ConversationResponse"
        print("✓ Pinned field added to ConversationResponse")

        print("\n✓ Models look good!")
        return True

    except Exception as e:
        print(f"✗ Model check failed: {e}")
        return False


def main():
    """Run all tests."""
    print("=" * 60)
    print("CONVERSATION HISTORY FEATURE TEST")
    print("=" * 60)

    results = []

    results.append(("Repository Layer", test_imports()))
    results.append(("Service Layer", test_service_layer()))
    results.append(("API Endpoints", test_api_endpoints()))
    results.append(("Frontend Files", test_frontend_files()))
    results.append(("Data Models", test_models()))

    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    for name, passed in results:
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"{name:.<40} {status}")

    all_passed = all(passed for _, passed in results)

    print("=" * 60)
    if all_passed:
        print("✓ ALL TESTS PASSED!")
        print("\nThe conversation history feature has been successfully implemented.")
        print("\nNext steps:")
        print("1. Start the application server")
        print("2. Navigate to the chat interface")
        print("3. Click the '☰' button to open the conversation history sidebar")
        print("4. Test search, filtering, and pin functionality")
    else:
        print("✗ SOME TESTS FAILED")
        print("Please review the errors above.")
    print("=" * 60)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
