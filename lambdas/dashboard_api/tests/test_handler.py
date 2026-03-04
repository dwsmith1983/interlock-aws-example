"""Tests for dashboard API Lambda handler.

TDD: written before handler.py exists.
Uses unittest.mock to stub DynamoDB table interactions.
"""

import json
import time
import unittest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

# Environment must be set before import
import os

os.environ.setdefault("EVENTS_TABLE", "test-interlock-events")

from handler import handler, DecimalEncoder  # noqa: E402


def _api_event(method, path, qs=None, path_params=None):
    """Build a minimal API Gateway v2 HTTP API event."""
    return {
        "rawPath": path,
        "requestContext": {"http": {"method": method}},
        "queryStringParameters": qs or {},
        "pathParameters": path_params or {},
    }


def _body(response):
    return json.loads(response["body"])


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

NOW_MS = int(datetime(2026, 3, 4, 12, 0, 0, tzinfo=timezone.utc).timestamp() * 1000)
ONE_HOUR_MS = 3_600_000
ONE_DAY_MS = 86_400_000


def _event_item(pipeline, ts_ms, event_type, **extra):
    """Build a DynamoDB item as returned by boto3 Table resource (Decimal values)."""
    item = {
        "PK": f"PIPELINE#{pipeline}",
        "SK": f"{ts_ms}#{event_type}",
        "eventType": event_type,
        "timestamp": Decimal(str(ts_ms)),
        "pipelineId": pipeline,
        "scheduleId": extra.get("scheduleId", "daily"),
        "date": extra.get("date", "2026-03-04"),
        "message": extra.get("message", f"{event_type} for {pipeline}"),
    }
    if "ttl" in extra:
        item["ttl"] = Decimal(str(extra["ttl"]))
    return item


# Sample items used across tests
SAMPLE_ITEMS = [
    _event_item("bronze-ingest", NOW_MS - ONE_HOUR_MS, "JOB_TRIGGERED"),
    _event_item("bronze-ingest", NOW_MS - ONE_HOUR_MS + 60_000, "JOB_COMPLETED"),
    _event_item("bronze-ingest", NOW_MS - 2 * ONE_HOUR_MS, "SLA_MET"),
    _event_item("silver-transform", NOW_MS - 30 * 60_000, "SLA_WARNING"),
    _event_item("silver-transform", NOW_MS - 10 * 60_000, "SLA_BREACH"),
    _event_item("gold-publish", NOW_MS - 3 * ONE_HOUR_MS, "JOB_TRIGGERED"),
    _event_item("gold-publish", NOW_MS - 3 * ONE_HOUR_MS + 120_000, "JOB_FAILED"),
]


# ===================================================================
# CORS
# ===================================================================


class TestCORS(unittest.TestCase):
    """CORS headers must appear on every response."""

    @patch("handler.TABLE")
    def test_cors_on_success(self, mock_table):
        mock_table.scan.return_value = {"Items": [], "Count": 0}
        resp = handler(_api_event("GET", "/api/overview"), {})
        self.assertEqual(resp["headers"]["Access-Control-Allow-Origin"], "*")

    @patch("handler.TABLE")
    def test_cors_on_404(self, mock_table):
        resp = handler(_api_event("GET", "/api/nonexistent"), {})
        self.assertEqual(resp["headers"]["Access-Control-Allow-Origin"], "*")

    @patch("handler.TABLE")
    def test_options_preflight(self, mock_table):
        resp = handler(_api_event("OPTIONS", "/api/overview"), {})
        self.assertEqual(resp["statusCode"], 200)
        self.assertEqual(resp["headers"]["Access-Control-Allow-Origin"], "*")
        self.assertIn("Access-Control-Allow-Methods", resp["headers"])
        self.assertIn("Access-Control-Allow-Headers", resp["headers"])


# ===================================================================
# Routing
# ===================================================================


class TestRouting(unittest.TestCase):
    @patch("handler.TABLE")
    def test_unknown_path_returns_404(self, mock_table):
        resp = handler(_api_event("GET", "/api/nonexistent"), {})
        self.assertEqual(resp["statusCode"], 404)

    @patch("handler.TABLE")
    def test_root_path_returns_404(self, mock_table):
        resp = handler(_api_event("GET", "/"), {})
        self.assertEqual(resp["statusCode"], 404)


# ===================================================================
# GET /api/overview
# ===================================================================


class TestOverview(unittest.TestCase):
    @patch("handler.TABLE")
    @patch("handler._now_ms")
    def test_overview_groups_by_pipeline(self, mock_now, mock_table):
        mock_now.return_value = NOW_MS
        mock_table.scan.return_value = {"Items": SAMPLE_ITEMS, "Count": len(SAMPLE_ITEMS)}
        resp = handler(_api_event("GET", "/api/overview"), {})

        self.assertEqual(resp["statusCode"], 200)
        body = _body(resp)
        pipelines = body["pipelines"]

        # 3 distinct pipelines
        self.assertEqual(len(pipelines), 3)

        # Check bronze-ingest
        bronze = next(p for p in pipelines if p["pipelineId"] == "bronze-ingest")
        self.assertEqual(bronze["eventCount"], 3)
        self.assertIn("JOB_TRIGGERED", bronze["typesBreakdown"])
        self.assertIn("JOB_COMPLETED", bronze["typesBreakdown"])
        self.assertIn("SLA_MET", bronze["typesBreakdown"])

        # Check silver-transform
        silver = next(p for p in pipelines if p["pipelineId"] == "silver-transform")
        self.assertEqual(silver["eventCount"], 2)

    @patch("handler.TABLE")
    @patch("handler._now_ms")
    def test_overview_empty(self, mock_now, mock_table):
        mock_now.return_value = NOW_MS
        mock_table.scan.return_value = {"Items": [], "Count": 0}
        resp = handler(_api_event("GET", "/api/overview"), {})

        self.assertEqual(resp["statusCode"], 200)
        body = _body(resp)
        self.assertEqual(body["pipelines"], [])

    @patch("handler.TABLE")
    @patch("handler._now_ms")
    def test_overview_last_event_is_most_recent(self, mock_now, mock_table):
        mock_now.return_value = NOW_MS
        mock_table.scan.return_value = {"Items": SAMPLE_ITEMS, "Count": len(SAMPLE_ITEMS)}
        resp = handler(_api_event("GET", "/api/overview"), {})

        body = _body(resp)
        bronze = next(p for p in body["pipelines"] if p["pipelineId"] == "bronze-ingest")
        # Most recent event for bronze-ingest is JOB_COMPLETED at NOW_MS - 1h + 60s
        self.assertEqual(bronze["lastEvent"]["eventType"], "JOB_COMPLETED")


# ===================================================================
# GET /api/pipelines/{id}/events
# ===================================================================


class TestPipelineEvents(unittest.TestCase):
    @patch("handler.TABLE")
    def test_requires_date_param(self, mock_table):
        resp = handler(_api_event("GET", "/api/pipelines/bronze-ingest/events"), {})
        self.assertEqual(resp["statusCode"], 400)
        body = _body(resp)
        self.assertIn("date", body["error"].lower())

    @patch("handler.TABLE")
    def test_returns_events_for_pipeline_and_date(self, mock_table):
        items = [
            _event_item("bronze-ingest", NOW_MS - ONE_HOUR_MS, "JOB_TRIGGERED"),
            _event_item("bronze-ingest", NOW_MS - ONE_HOUR_MS + 60_000, "JOB_COMPLETED"),
        ]
        mock_table.query.return_value = {"Items": items, "Count": 2}

        resp = handler(
            _api_event("GET", "/api/pipelines/bronze-ingest/events", qs={"date": "2026-03-04"}),
            {},
        )
        self.assertEqual(resp["statusCode"], 200)
        body = _body(resp)
        self.assertEqual(len(body["events"]), 2)
        self.assertEqual(body["pipelineId"], "bronze-ingest")

        # Verify query was called with correct PK
        call_kwargs = mock_table.query.call_args[1]
        self.assertIn("KeyConditionExpression", call_kwargs)

    @patch("handler.TABLE")
    def test_returns_events_with_hour_filter(self, mock_table):
        items = [
            _event_item("bronze-ingest", NOW_MS - ONE_HOUR_MS, "JOB_TRIGGERED"),
        ]
        mock_table.query.return_value = {"Items": items, "Count": 1}

        resp = handler(
            _api_event(
                "GET",
                "/api/pipelines/bronze-ingest/events",
                qs={"date": "2026-03-04", "hour": "11"},
            ),
            {},
        )
        self.assertEqual(resp["statusCode"], 200)
        body = _body(resp)
        self.assertEqual(len(body["events"]), 1)

    @patch("handler.TABLE")
    def test_empty_results(self, mock_table):
        mock_table.query.return_value = {"Items": [], "Count": 0}
        resp = handler(
            _api_event("GET", "/api/pipelines/bronze-ingest/events", qs={"date": "2026-03-04"}),
            {},
        )
        self.assertEqual(resp["statusCode"], 200)
        body = _body(resp)
        self.assertEqual(body["events"], [])


# ===================================================================
# GET /api/events
# ===================================================================


class TestEventsQuery(unittest.TestCase):
    @patch("handler.TABLE")
    @patch("handler._now_ms")
    def test_query_by_type(self, mock_now, mock_table):
        mock_now.return_value = NOW_MS
        items = [
            _event_item("bronze-ingest", NOW_MS - ONE_HOUR_MS, "SLA_BREACH"),
            _event_item("silver-transform", NOW_MS - 2 * ONE_HOUR_MS, "SLA_BREACH"),
        ]
        mock_table.query.return_value = {"Items": items, "Count": 2}

        from_ts = str(NOW_MS - ONE_DAY_MS)
        to_ts = str(NOW_MS)
        resp = handler(
            _api_event(
                "GET",
                "/api/events",
                qs={"type": "SLA_BREACH", "from": from_ts, "to": to_ts},
            ),
            {},
        )
        self.assertEqual(resp["statusCode"], 200)
        body = _body(resp)
        self.assertEqual(len(body["events"]), 2)

        # Should use GSI1 query
        call_kwargs = mock_table.query.call_args[1]
        self.assertEqual(call_kwargs.get("IndexName"), "GSI1")

    @patch("handler.TABLE")
    @patch("handler._now_ms")
    def test_scan_without_type(self, mock_now, mock_table):
        mock_now.return_value = NOW_MS
        mock_table.scan.return_value = {"Items": SAMPLE_ITEMS, "Count": len(SAMPLE_ITEMS)}

        from_ts = str(NOW_MS - ONE_DAY_MS)
        to_ts = str(NOW_MS)
        resp = handler(
            _api_event("GET", "/api/events", qs={"from": from_ts, "to": to_ts}),
            {},
        )
        self.assertEqual(resp["statusCode"], 200)
        body = _body(resp)
        self.assertIn("events", body)

    @patch("handler.TABLE")
    @patch("handler._now_ms")
    def test_defaults_to_24h_range(self, mock_now, mock_table):
        """When from/to are not provided, default to last 24 hours."""
        mock_now.return_value = NOW_MS
        mock_table.scan.return_value = {"Items": [], "Count": 0}

        resp = handler(_api_event("GET", "/api/events"), {})
        self.assertEqual(resp["statusCode"], 200)

    @patch("handler.TABLE")
    @patch("handler._now_ms")
    def test_empty_results(self, mock_now, mock_table):
        mock_now.return_value = NOW_MS
        mock_table.query.return_value = {"Items": [], "Count": 0}

        resp = handler(
            _api_event(
                "GET",
                "/api/events",
                qs={"type": "SCHEDULE_MISSED", "from": "0", "to": str(NOW_MS)},
            ),
            {},
        )
        self.assertEqual(resp["statusCode"], 200)
        body = _body(resp)
        self.assertEqual(body["events"], [])


# ===================================================================
# GET /api/metrics
# ===================================================================


class TestMetrics(unittest.TestCase):
    @patch("handler.TABLE")
    @patch("handler._now_ms")
    def test_metrics_aggregation(self, mock_now, mock_table):
        mock_now.return_value = NOW_MS
        mock_table.scan.return_value = {"Items": SAMPLE_ITEMS, "Count": len(SAMPLE_ITEMS)}

        resp = handler(_api_event("GET", "/api/metrics"), {})
        self.assertEqual(resp["statusCode"], 200)
        body = _body(resp)

        # Total events
        self.assertEqual(body["totalEvents"], 7)

        # byType
        self.assertIn("byType", body)
        self.assertEqual(body["byType"]["JOB_TRIGGERED"], 2)
        self.assertEqual(body["byType"]["SLA_BREACH"], 1)

        # byPipeline
        self.assertIn("byPipeline", body)
        self.assertEqual(body["byPipeline"]["bronze-ingest"], 3)
        self.assertEqual(body["byPipeline"]["silver-transform"], 2)
        self.assertEqual(body["byPipeline"]["gold-publish"], 2)

        # byHour — dict keyed by ISO hour strings
        self.assertIn("byHour", body)
        self.assertIsInstance(body["byHour"], dict)

        # sla
        self.assertIn("sla", body)
        self.assertEqual(body["sla"]["SLA_MET"], 1)
        self.assertEqual(body["sla"]["SLA_WARNING"], 1)
        self.assertEqual(body["sla"]["SLA_BREACH"], 1)

    @patch("handler.TABLE")
    @patch("handler._now_ms")
    def test_metrics_custom_range(self, mock_now, mock_table):
        mock_now.return_value = NOW_MS
        mock_table.scan.return_value = {"Items": SAMPLE_ITEMS[:3], "Count": 3}

        from_ts = str(NOW_MS - ONE_DAY_MS)
        to_ts = str(NOW_MS)
        resp = handler(
            _api_event("GET", "/api/metrics", qs={"from": from_ts, "to": to_ts}),
            {},
        )
        self.assertEqual(resp["statusCode"], 200)
        body = _body(resp)
        self.assertEqual(body["totalEvents"], 3)

    @patch("handler.TABLE")
    @patch("handler._now_ms")
    def test_metrics_empty(self, mock_now, mock_table):
        mock_now.return_value = NOW_MS
        mock_table.scan.return_value = {"Items": [], "Count": 0}

        resp = handler(_api_event("GET", "/api/metrics"), {})
        self.assertEqual(resp["statusCode"], 200)
        body = _body(resp)
        self.assertEqual(body["totalEvents"], 0)
        self.assertEqual(body["byType"], {})
        self.assertEqual(body["byPipeline"], {})
        self.assertEqual(body["byHour"], {})
        self.assertEqual(body["sla"], {"SLA_MET": 0, "SLA_WARNING": 0, "SLA_BREACH": 0})

    @patch("handler.TABLE")
    @patch("handler._now_ms")
    def test_metrics_defaults_to_7_days(self, mock_now, mock_table):
        """When no from/to, should scan last 7 days."""
        mock_now.return_value = NOW_MS
        mock_table.scan.return_value = {"Items": [], "Count": 0}

        resp = handler(_api_event("GET", "/api/metrics"), {})
        self.assertEqual(resp["statusCode"], 200)

        # Verify scan was called with appropriate filter
        call_kwargs = mock_table.scan.call_args[1]
        self.assertIn("FilterExpression", call_kwargs)


# ===================================================================
# DecimalEncoder
# ===================================================================


class TestDecimalEncoder(unittest.TestCase):
    def test_decimal_int(self):
        result = json.dumps({"val": Decimal("42")}, cls=DecimalEncoder)
        self.assertEqual(json.loads(result)["val"], 42)

    def test_decimal_float(self):
        result = json.dumps({"val": Decimal("3.14")}, cls=DecimalEncoder)
        self.assertAlmostEqual(json.loads(result)["val"], 3.14)

    def test_nested_decimal(self):
        data = {"items": [{"ts": Decimal("1709510400000")}]}
        result = json.dumps(data, cls=DecimalEncoder)
        parsed = json.loads(result)
        self.assertEqual(parsed["items"][0]["ts"], 1709510400000)


if __name__ == "__main__":
    unittest.main()
