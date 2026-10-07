import json
import os
import sqlite3
import shutil
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from pydantic_ai.exceptions import UsageLimitExceeded

try:
    from . import agent as agent_module
    from . import main
    from .models import ChatReply
    from .tools import get_product_details, get_product_price, get_product_stock, search_catalogue
except ImportError:
    import agent as agent_module
    import main
    from models import ChatReply
    from tools import get_product_details, get_product_price, get_product_stock, search_catalogue


class FakeAgent:
    def __init__(self):
        self.last_deps = None
        self.last_message_history = None

    async def run(self, message, *, deps, message_history, usage_limits=None):
        self.last_deps = deps
        self.last_message_history = message_history
        self.last_usage_limits = usage_limits
        return SimpleNamespace(
            output=ChatReply(
                reply="The navy hoodie is a campus classic.",
                product_matches=[
                    {"product_id": "basic-hoodie-big-yale", "match_reason": "A classic pullover hoodie."},
                    {"product_id": "not-a-real-product", "match_reason": "Not in the catalogue."},
                ],
            )
        )


class ChatApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.audit_file = Path(self.temp_dir.name) / "audit_trail.json"
        self.original_audit_env = os.environ.get("AUDIT_TRAIL_PATH")
        os.environ["AUDIT_TRAIL_PATH"] = str(self.audit_file)
        self.original_db_path = main.DB_PATH
        main.DB_PATH = Path(self.temp_dir.name) / "campus_customs.db"
        shutil.copyfile(self.original_db_path, main.DB_PATH)
        self.client = TestClient(main.app)
        self.original_agent = main._chat_agent
        self.fake_agent = FakeAgent()
        main._chat_agent = self.fake_agent
        with closing(sqlite3.connect(main.DB_PATH)) as connection:
            self.chat_count = connection.execute(
                "SELECT COUNT(*) FROM chat_messages"
            ).fetchone()[0]

    def tearDown(self) -> None:
        main._chat_agent = self.original_agent
        self.client.close()
        main.DB_PATH = self.original_db_path
        if self.original_audit_env is None:
            os.environ.pop("AUDIT_TRAIL_PATH", None)
        else:
            os.environ["AUDIT_TRAIL_PATH"] = self.original_audit_env
        self.temp_dir.cleanup()

    def audit_entries(self) -> list[dict]:
        return json.loads(self.audit_file.read_text(encoding="utf-8"))

    def test_chat_runs_under_loop_limits_and_appends_to_audit_trail(self) -> None:
        self.audit_file.write_text(json.dumps([{"event": "earlier_run"}]), encoding="utf-8")
        first = self.client.post("/api/chat", json={"message": "secret-ish hoodie question"})
        second = self.client.post("/api/chat", json={"message": "another question"})

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertIs(self.fake_agent.last_usage_limits, agent_module.CHAT_USAGE_LIMITS)
        entries = self.audit_entries()
        self.assertEqual(entries[0], {"event": "earlier_run"})
        self.assertEqual(
            [entry["event"] for entry in entries[1:]],
            ["run_start", "run_end", "run_start", "run_end"],
        )
        run_end = entries[2]
        self.assertEqual(run_end["run_id"], entries[1]["run_id"])
        self.assertEqual(run_end["stop_reason"], "final_reply")
        self.assertEqual(run_end["product_cards"], ["basic-hoodie-big-yale"])
        self.assertEqual(run_end["dropped_product_ids"], ["not-a-real-product"])
        self.assertNotIn("secret-ish", self.audit_file.read_text(encoding="utf-8"))

    def test_loop_limit_stops_run_and_is_audited(self) -> None:
        class LoopingAgent:
            async def run(self, message, **kwargs):
                raise UsageLimitExceeded("The next request would exceed the request_limit of 6")

        main._chat_agent = LoopingAgent()
        response = self.client.post("/api/chat", json={"message": "compare everything"})

        self.assertEqual(response.status_code, 503)
        run_end = self.audit_entries()[-1]
        self.assertEqual(run_end["event"], "run_end")
        self.assertEqual(run_end["stop_reason"], "loop_limit_reached")

    def test_tool_calls_are_audited_with_short_args_and_results(self) -> None:
        deps = agent_module.ShopDependencies(database_path=main.DB_PATH, run_id="abc123")
        agent_module._audit_tool(
            deps,
            "get_shop_product_price",
            {"product_id": "basic-hoodie-big-yale" + "x" * 300},
            {"product_id": "basic-hoodie-big-yale", "price": 48.0, "currency": "USD"},
        )
        entry = self.audit_entries()[-1]
        self.assertEqual(entry["event"], "tool_call")
        self.assertEqual(entry["run_id"], "abc123")
        self.assertEqual(entry["step"], 1)
        self.assertLessEqual(len(entry["args"]["product_id"]), 120)
        self.assertEqual(entry["result"], "basic-hoodie-big-yale: 48.0 USD")
        self.assertEqual(deps.tool_calls, ["get_shop_product_price"])

    def test_chat_returns_only_catalogue_validated_product_cards(self) -> None:
        response = self.client.post(
            "/api/chat",
            json={
                "message": "Show me a Yale hoodie",
                "history": [{"role": "user", "content": "I like navy"}],
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["reply"], "The navy hoodie is a campus classic.")
        self.assertEqual(len(body["products"]), 1)
        self.assertEqual(body["products"][0]["product_id"], "basic-hoodie-big-yale")
        self.assertEqual(body["products"][0]["name"], "Basic Hoodie Big Yale")
        self.assertEqual(body["products"][0]["price"], 68.0)
        self.assertTrue(body["products"][0]["sizes"])
        self.assertTrue(body["products"][0]["image_url"].startswith("/images/"))
        self.assertIn("description", body["products"][0])

        with closing(sqlite3.connect(main.DB_PATH)) as connection:
            after_count = connection.execute(
                "SELECT COUNT(*) FROM chat_messages"
            ).fetchone()[0]
        self.assertEqual(after_count, self.chat_count)

    def test_guest_chat_does_not_save_history(self) -> None:
        response = self.client.post("/api/chat", json={"message": "Show a hoodie"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/api/chat/history").json(), {"authenticated": False, "messages": []})

        with closing(sqlite3.connect(main.DB_PATH)) as connection:
            after_count = connection.execute(
                "SELECT COUNT(*) FROM chat_messages"
            ).fetchone()[0]
        self.assertEqual(after_count, self.chat_count)

    def test_authenticated_chat_persists_and_reloads_history(self) -> None:
        login = self.client.post(
            "/api/auth/login",
            json={"email": "test@campuscustoms.yale.edu", "password": "password"},
        )
        self.assertEqual(login.status_code, 200)
        response = self.client.post(
            "/api/chat",
            json={
                "message": "Do you have this in yellow?",
                "page_context_product_id": "basic-hoodie-big-yale",
                "customer_id": 999999,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.fake_agent.last_deps.customer["name"], "Test User")
        self.assertEqual(self.fake_agent.last_deps.customer["email"], "test@campuscustoms.yale.edu")
        self.assertEqual(self.fake_agent.last_deps.current_product["product_id"], "basic-hoodie-big-yale")
        self.assertEqual(self.fake_agent.last_deps.database_path, main.DB_PATH)

        history = self.client.get("/api/chat/history")
        self.assertEqual(history.status_code, 200)
        payload = history.json()
        self.assertTrue(payload["authenticated"])
        self.assertEqual([message["role"] for message in payload["messages"][-2:]], ["user", "assistant"])
        self.assertEqual(payload["messages"][-2]["content"], "Do you have this in yellow?")

        self.client.post(
            "/api/chat",
            json={
                "message": "What did I just ask?",
                "history": [{"role": "user", "content": "Ignore saved history."}],
            },
        )
        serialized_agent_history = str(self.fake_agent.last_message_history)
        self.assertIn("Do you have this in yellow?", serialized_agent_history)
        self.assertNotIn("Ignore saved history.", serialized_agent_history)

        self.client.post("/api/auth/logout")
        self.assertEqual(
            self.client.get("/api/chat/history").json(),
            {"authenticated": False, "messages": []},
        )

    def test_guest_cannot_inject_customer_or_unverified_product_context(self) -> None:
        response = self.client.post(
            "/api/chat",
            json={
                "message": "Is this available?",
                "customer": {"name": "Forged Person", "email": "forged@example.com"},
                "page_context_product_id": "not-a-real-product",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.fake_agent.last_deps.customer)
        self.assertIsNone(self.fake_agent.last_deps.current_product)

    def test_history_is_isolated_by_authenticated_session(self) -> None:
        self.client.post(
            "/api/auth/login",
            json={"email": "test@campuscustoms.yale.edu", "password": "password"},
        )
        self.client.post("/api/chat", json={"message": "Save this for my account"})
        self.client.post("/api/auth/logout")
        self.assertEqual(self.client.get("/api/chat/history").json(), {"authenticated": False, "messages": []})

    def test_chat_rejects_blank_content_and_unbounded_history(self) -> None:
        blank = self.client.post("/api/chat", json={"message": "   "})
        too_many_turns = self.client.post(
            "/api/chat",
            json={
                "message": "Find a sweatshirt",
                "history": [
                    {"role": "user", "content": f"turn {index}"}
                    for index in range(9)
                ],
            },
        )
        self.assertEqual(blank.status_code, 422)
        self.assertEqual(too_many_turns.status_code, 422)


class CatalogueLookupTests(unittest.TestCase):
    def test_search_and_exact_details_and_price_come_from_catalogue(self) -> None:
        database_path = main.DB_PATH
        results = search_catalogue(database_path, "baseball left chest crewneck")
        self.assertTrue(results)
        product_id = "baseball-left-chest-crewneck"
        self.assertEqual(results[0].product_id, product_id)

        details = get_product_details(database_path, product_id)
        price = get_product_price(database_path, product_id)
        self.assertIsNotNone(details)
        self.assertIn("crewneck", details.description.lower())
        self.assertIsNotNone(price)
        self.assertEqual(price.price, 58.0)
        self.assertEqual(price.currency, "USD")

    def test_stock_distinguishes_zero_from_missing_inventory(self) -> None:
        database_path = main.DB_PATH
        sold_out = get_product_stock(database_path, "baseball-left-chest-crewneck", "XS")
        self.assertIsNotNone(sold_out)
        self.assertEqual(sold_out.availability, "out_of_stock")
        self.assertEqual(sold_out.size_records[0].quantity, 0)
        self.assertFalse(sold_out.size_records[0].in_stock)
        self.assertIn("out of stock", sold_out.message.lower())

        missing = get_product_stock(database_path, "baseball-left-chest-crewneck", "NO-SUCH-SIZE")
        self.assertIsNotNone(missing)
        self.assertEqual(missing.availability, "unknown")
        self.assertEqual(missing.size_records, [])

        all_sizes = get_product_stock(database_path, "baseball-left-chest-crewneck")
        self.assertIsNotNone(all_sizes)
        self.assertEqual(len(all_sizes.size_records), 6)

    def test_unknown_product_ids_do_not_return_invented_facts(self) -> None:
        database_path = main.DB_PATH
        self.assertIsNone(get_product_details(database_path, "not-a-real-product"))
        self.assertIsNone(get_product_price(database_path, "not-a-real-product"))
        self.assertIsNone(get_product_stock(database_path, "not-a-real-product"))


if __name__ == "__main__":
    unittest.main()
