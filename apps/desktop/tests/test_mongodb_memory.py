"""
Test suite for MongoDB memory integration.
Tests connection, collection initialization, index creation, VaultMemory operations,
ConversationMemory session tracking, UserProfile/Preferences, screen events, action logging,
and WebSocket memory review handlers.
"""

import sys
import os
import time
import asyncio
import json
import unittest
from unittest.mock import MagicMock, patch

# Fix cp1252 print encoding issues on Windows
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Add backend to path
backend_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
sys.path.insert(0, backend_path)

# Mock environment variables before importing memory
os.environ["ADELE_MONGODB_URI"] = "mongodb://mock_connection:27017"
os.environ["ADELE_MONGODB_DB"] = "test_adele"

import mongomock
import pymongo

# Monkeypatch MongoClient to use mongomock
pymongo.MongoClient = mongomock.MongoClient

from agent.memory import (
    get_mongo_db,
    _initialize_mongo_collections,
    VaultMemory,
    ConversationMemory,
    UserPreferences,
    UserProfile,
    TaskStore,
    WorkingMemory,
)
import agent.perception as perception
from agent.core_v2 import AdeleAgentV2


class TestMongoDBMemory(unittest.TestCase):

    def setUp(self):
        # Reset memory globals
        import agent.memory as memory
        memory._mongo_client = None
        memory._mongo_db = None
        
        # Clear mongomock database
        self.db = get_mongo_db()
        self.assertIsNotNone(self.db, "Database connection should not be None under mongomock")
        
        # Drop collections to start fresh
        for col_name in self.db.list_collection_names():
            self.db[col_name].drop()
            
        # Re-initialize
        _initialize_mongo_collections(self.db)

    def test_database_initialization(self):
        """Test that all required collections are created successfully."""
        collections = self.db.list_collection_names()
        expected = [
            "users", "sessions", "screen_events", "memories", 
            "actions", "skills", "mistakes", "documents", 
            "embeddings", "memory_reviews", "projects", 
            "memory_edges", "workflows", "app_profiles", 
            "agent_runs", "checklists", "tasks"
        ]
        for col in expected:
            self.assertIn(col, collections, f"Collection {col} should have been initialized")

    def test_vault_memory_store_and_recall(self):
        """Test saving, recalling, searching, and deleting memories in VaultMemory."""
        vault = VaultMemory()
        
        # Store approved memory candidate
        # By default require_memory_approval is True, so let's temporarily mock preferences to make it False
        # or verify it saves as pending.
        res = vault.store(
            category="notes",
            title="Important Server Configurations",
            content="Port 8000 is the main backend port, Port 3000 is frontend.",
            tags=["server", "port", "config"]
        )
        self.assertTrue(res["ok"])
        self.assertEqual(res["action"], "created")
        entry_id = res["id"]
        
        # Ensure it was saved as pending review by default
        mem_doc = self.db.memories.find_one({"_id": mongomock.ObjectId(entry_id)})
        self.assertIsNotNone(mem_doc)
        self.assertEqual(mem_doc["review_status"], "pending_review")
        
        # Ensure it is also in the memory_reviews collection
        review_doc = self.db.memory_reviews.find_one({"memory_id": entry_id})
        self.assertIsNotNone(review_doc)
        self.assertEqual(review_doc["status"], "pending_review")
        
        # Set to approved directly to test recall
        self.db.memories.update_one({"_id": mongomock.ObjectId(entry_id)}, {"$set": {"review_status": "approved"}})
        
        # Recall by category
        recalled = vault.recall(category="notes")
        self.assertTrue(len(recalled) > 0)
        self.assertEqual(recalled[0]["title"], "Important Server Configurations")
        
        # Recall by query (TF-IDF fallback under mongomock)
        searched = vault.recall(query="port", category="notes")
        self.assertTrue(len(searched) > 0)
        self.assertEqual(searched[0]["title"], "Important Server Configurations")
        
        # Recall by tags
        tagged = vault.recall(tags=["server"])
        self.assertTrue(len(tagged) > 0)
        self.assertEqual(tagged[0]["title"], "Important Server Configurations")
        
        # List entries
        entries = vault.list_entries(category="notes")
        self.assertTrue(len(entries) > 0)
        
        # Get stats
        stats = vault.get_stats()
        self.assertEqual(stats["total_entries"], 1)
        self.assertEqual(stats["by_category"]["notes"], 1)
        
        # Delete memory
        deleted = vault.delete(entry_id)
        self.assertTrue(deleted)
        self.assertEqual(self.db.memories.count_documents({}), 0)
        self.assertEqual(self.db.embeddings.count_documents({}), 0)
        self.assertEqual(self.db.memory_reviews.count_documents({}), 0)

    def test_conversation_memory_sessions(self):
        """Test session saving and resuming in ConversationMemory."""
        conv = ConversationMemory(persist=True)
        conv.clear()
        
        # Start new session
        conv.start_new_session()
        session_id = conv._session_id
        
        # Add turns
        conv.add_user("Hello Adele, please remember my project directory is ~/dev/project")
        conv.add_model("Got it! I will remember that.")
        conv._flush_save()
        
        # Check in DB
        session_doc = self.db.sessions.find_one({"session_id": session_id})
        self.assertIsNotNone(session_doc)
        self.assertEqual(len(session_doc["turns"]), 2)
        self.assertEqual(session_doc["turns"][0]["role"], "user")
        
        # Create a new ConversationMemory object and verify it resumes the session
        new_conv = ConversationMemory(persist=True)
        self.assertEqual(new_conv._session_id, session_id)
        self.assertEqual(len(new_conv._turns), 2)
        self.assertEqual(new_conv._turns[0]["parts"][0]["text"], "Hello Adele, please remember my project directory is ~/dev/project")

    def test_user_preferences_and_profile(self):
        """Test that UserPreferences, UserProfile, and TaskStore use MongoDB."""
        # Preferences
        prefs = UserPreferences()
        prefs.set("require_memory_approval", False)
        self.assertEqual(prefs.get("require_memory_approval"), False)
        
        # Check DB
        user_doc = self.db.users.find_one({"_id": "default_user"})
        self.assertIsNotNone(user_doc)
        self.assertEqual(user_doc["preferences"]["require_memory_approval"], False)
        
        # Profile / Fact extraction
        profile = UserProfile()
        profile.extract_facts("My name is Miles")
        self.assertEqual(profile.get_fact("name"), "miles")
        
        # Check DB
        user_doc_updated = self.db.users.find_one({"_id": "default_user"})
        self.assertEqual(user_doc_updated["profile"]["facts"]["name"]["value"], "miles")
        
        # TaskStore
        tasks = TaskStore()
        task = tasks.add("Check email", 3600)
        self.assertEqual(task.description, "Check email")
        self.assertEqual(len(tasks.list_active()), 1)
        
        # Check DB
        task_doc = self.db.tasks.find_one({"_id": task.id})
        self.assertIsNotNone(task_doc)
        self.assertEqual(task_doc["description"], "Check email")

    def test_agent_screen_event_and_action_logging(self):
        """Test logging of screen events and action execution traces to MongoDB."""
        agent = AdeleAgentV2(persist=True)
        
        # Mock ContextSnapshot
        context = perception.ContextSnapshot(
            active_app="Google Chrome",
            window_title="Adele PRD - Google Docs",
            browser_url="https://docs.google.com/document/d/123",
            page_title="Adele PRD",
            visible_text="Error: Connection failed in memory system.",
            timestamp=time.time()
        )
        
        # Log screen event
        agent.log_screen_event(context, "What is the status of the project?")
        
        # Verify in DB
        event = self.db.screen_events.find_one({"active_app": "Google Chrome"})
        self.assertIsNotNone(event)
        self.assertEqual(event["window_title"], "Adele PRD - Google Docs")
        self.assertIn("error", event["detected_problems"])
        self.assertEqual(event["source_session"], agent.conversation._session_id)
        
        # Log action via WorkingMemory
        agent.working_memory.log_action(
            tool="read_file",
            args={"path": "docs/PRD.md"},
            result="Success reading file.",
            success=True,
            session_id=agent.conversation._session_id
        )
        
        # Verify action in DB
        action = self.db.actions.find_one({"tool": "read_file"})
        self.assertIsNotNone(action)
        self.assertEqual(action["session_id"], agent.conversation._session_id)
        self.assertTrue(action["success"])


class TestWebSocketMemoryReview(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        # Reset globals
        import agent.memory as memory
        memory._mongo_client = None
        memory._mongo_db = None
        
        self.db = get_mongo_db()
        # Fresh db setup
        for col_name in self.db.list_collection_names():
            self.db[col_name].drop()
        _initialize_mongo_collections(self.db)
        
        # Setup mock WebSocket
        self.sent_messages = []
        
        class MockWebSocket:
            def __init__(self, test_case):
                self.test_case = test_case
            async def send(self, msg):
                self.test_case.sent_messages.append(json.loads(msg))
                
        self.ws = MockWebSocket(self)

    async def test_websocket_memory_review_flow(self):
        """Test the WebSocket interface handlers for memory reviews."""
        import json
        from servers.local_server import main_handler
        
        # Insert a pending memory candidate
        mem_doc = {
            "user_id": "default_user",
            "content": "Miles prefers dark mode for IDE.",
            "type": "document_fact",
            "category": "preferences",
            "title": "IDE Color Preference",
            "tags": ["ide", "theme"],
            "review_status": "pending_review",
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        mem_id = str(self.db.memories.insert_one(mem_doc).inserted_id)
        
        review_doc = {
            "memory_id": mem_id,
            "content": "Miles prefers dark mode for IDE.",
            "reason_for_saving": "Auto-curated fact from conversation",
            "status": "pending_review",
            "updated_at": time.time()
        }
        self.db.memory_reviews.insert_one(review_doc)
        
        # Mock the event loop list reader to handle these messages
        # We simulate messages processed by local_server.py main_handler loop.
        # To avoid blocking, we can test the handlers by mocking websocket loop or calling main_handler.
        # Alternatively, since main_handler is an async generator, we can mock messages in an async generator.
        
        messages = [
            # 1. list_pending_reviews
            json.dumps({"type": "list_pending_reviews"}),
            # 2. edit_memory
            json.dumps({
                "type": "edit_memory",
                "memory_id": mem_id,
                "title": "IDE Theme Preference",
                "content": "Miles prefers Obsidian Dark theme.",
                "tags": ["theme", "obsidian"]
            }),
            # 3. list_pending_reviews again to see edited values
            json.dumps({"type": "list_pending_reviews"}),
            # 4. approve_memory
            json.dumps({
                "type": "approve_memory",
                "memory_id": mem_id
            }),
            # 5. list_pending_reviews again to see it's cleared
            json.dumps({"type": "list_pending_reviews"}),
        ]
        
        class MockWSMessageIter:
            def __init__(self, msgs):
                self.msgs = msgs
                self.index = 0
            def __aiter__(self):
                return self
            async def __anext__(self):
                if self.index >= len(self.msgs):
                    raise StopAsyncIteration
                val = self.msgs[self.index]
                self.index += 1
                return val
                
        ws_mock = self.ws
        ws_mock.__class__.__aiter__ = lambda self: MockWSMessageIter(messages)
        
        # Run main_handler
        # We need to mock VoiceAssistant so it doesn't try to initialize speech engines/mic
        with patch('servers.local_server.VoiceAssistant') as mock_assistant_cls:
            mock_assistant = MagicMock()
            mock_assistant.tts_playing = False
            
            # Make agent.router.initialize an async dummy function to be awaitable
            async def dummy_init():
                pass
            mock_assistant.agent.router.initialize = dummy_init
            mock_assistant_cls.return_value = mock_assistant
            
            try:
                await main_handler(ws_mock)
            except Exception as e:
                # Disconnection errors or StopAsyncIteration are fine
                pass

        # Verify sent WebSocket responses
        # Let's filter response types
        response_types = [m.get("type") for m in self.sent_messages]
        self.assertIn("pending_reviews_list", response_types)
        self.assertIn("edit_memory_result", response_types)
        self.assertIn("approve_memory_result", response_types)
        
        # Verify first pending reviews list output
        list1 = next(m for m in self.sent_messages if m.get("type") == "pending_reviews_list")
        self.assertEqual(len(list1["reviews"]), 1)
        self.assertEqual(list1["reviews"][0]["title"], "IDE Color Preference")
        self.assertEqual(list1["reviews"][0]["content"], "Miles prefers dark mode for IDE.")
        
        # Verify edit memory result
        edit_res = next(m for m in self.sent_messages if m.get("type") == "edit_memory_result")
        self.assertTrue(edit_res["success"])
        
        # Verify second pending reviews list output (showing edits)
        list2 = [m for m in self.sent_messages if m.get("type") == "pending_reviews_list"][1]
        self.assertEqual(list2["reviews"][0]["title"], "IDE Theme Preference")
        self.assertEqual(list2["reviews"][0]["content"], "Miles prefers Obsidian Dark theme.")
        
        # Verify approve memory result
        app_res = next(m for m in self.sent_messages if m.get("type") == "approve_memory_result")
        self.assertTrue(app_res["success"])
        
        # Verify third pending reviews list output (showing empty list)
        list3 = [m for m in self.sent_messages if m.get("type") == "pending_reviews_list"][2]
        self.assertEqual(len(list3["reviews"]), 0)
        
        # Check DB states
        mem_final = self.db.memories.find_one({"_id": mongomock.ObjectId(mem_id)})
        self.assertEqual(mem_final["review_status"], "approved")
        self.assertEqual(mem_final["title"], "IDE Theme Preference")
        self.assertEqual(mem_final["content"], "Miles prefers Obsidian Dark theme.")
        
        # Check review doc is deleted
        review_final = self.db.memory_reviews.find_one({"memory_id": mem_id})
        self.assertIsNone(review_final)


if __name__ == "__main__":
    unittest.main()
