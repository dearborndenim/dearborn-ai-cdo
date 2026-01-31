"""
Event Bus Client for CDO Module

Handles inter-module communication via Redis pub/sub.
Publishes analytics insights and receives data from other modules.
"""

import json
import os
import threading
from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum
import redis
from uuid import uuid4

from .db import SessionLocal, CDOEvent, CDOAlert, AlertSeverity
from .config import get_settings

settings = get_settings()


class CDOOutboundEvent(str, Enum):
    """Events the CDO module publishes"""
    TREND_ALERT = "trend_alert"
    PRODUCT_RECOMMENDATION = "product_recommendation"
    PERFORMANCE_REPORT = "performance_report"
    TECH_PACK_READY = "tech_pack_ready"
    PATTERN_READY = "pattern_ready"
    DEMAND_FORECAST = "demand_forecast"
    MARGIN_CHECK_REQUEST = "margin_check_request"
    CAPACITY_CHECK_REQUEST = "capacity_check_request"
    PRODUCT_APPROVAL_REQUEST = "product_approval_request"
    PRODUCT_APPROVED_FOR_PRODUCTION = "product_approved_for_production"
    PRODUCT_BUDGET_ALLOCATED = "product_budget_allocated"
    PRODUCT_LAUNCH_SCHEDULED = "product_launch_scheduled"
    PRODUCT_PIPELINE_UPDATED = "product_pipeline_updated"


class CDOInboundEvent(str, Enum):
    """Events the CDO module listens for"""
    APPROVAL_DECIDED = "approval_decided"
    SALES_DATA_UPDATED = "sales_data_updated"
    INVENTORY_UPDATED = "inventory_updated"
    CAMPAIGN_PERFORMANCE = "campaign_performance"
    FINANCIAL_REPORT = "financial_report"
    MARGIN_CHECK_RESPONSE = "margin_check_response"
    CAPACITY_CHECK_RESPONSE = "capacity_check_response"


class EventBus:
    """Redis pub/sub event bus for inter-module communication."""

    def __init__(self):
        self.redis_url = settings.redis_url
        self._client: Optional[redis.Redis] = None

    @property
    def client(self) -> Optional[redis.Redis]:
        """Lazy initialization of Redis client."""
        if not self.redis_url:
            return None

        if self._client is None:
            try:
                self._client = redis.from_url(
                    self.redis_url,
                    decode_responses=True,
                    socket_timeout=5,
                    socket_connect_timeout=5
                )
                self._client.ping()
            except Exception as e:
                print(f"Failed to connect to Redis: {e}")
                self._client = None

        return self._client

    def is_connected(self) -> bool:
        """Check if Redis is connected."""
        if not self.client:
            return False
        try:
            self.client.ping()
            return True
        except:
            return False

    def publish(
        self,
        event_type: CDOOutboundEvent,
        payload: Dict[str, Any],
        target_module: Optional[str] = None
    ) -> Optional[str]:
        """Publish an event to the event bus."""
        event_id = str(uuid4())

        event = {
            "event_id": event_id,
            "event_type": event_type.value if isinstance(event_type, CDOOutboundEvent) else event_type,
            "source_module": "cdo",
            "target_module": target_module,
            "payload": payload,
            "timestamp": datetime.utcnow().isoformat()
        }

        # Log to database
        self._log_event_to_db(event, direction="outbound")

        # Try Redis
        if self.client:
            try:
                channel = f"dearborn:events:{target_module}" if target_module else "dearborn:events:broadcast"
                receivers = self.client.publish(channel, json.dumps(event))
                print(f"Published event {event_type} to {channel} ({receivers} receivers)")
                if receivers > 0:
                    return event_id
            except Exception as e:
                print(f"Failed to publish to Redis: {e}")

        # HTTP fallback when Redis has no subscribers or is unavailable
        try:
            import httpx

            # CEO fallback
            if target_module == "ceo" and settings.ceo_api_url:
                response = httpx.post(
                    f"{settings.ceo_api_url}/ceo/approvals",
                    json={
                        "requesting_module": "cdo",
                        "request_type": event_type.value if isinstance(event_type, CDOOutboundEvent) else event_type,
                        "title": payload.get("title", f"CDO: {event_type}"),
                        "description": payload.get("message", ""),
                        "payload": payload,
                        "risk_level": payload.get("risk_level", "low")
                    },
                    timeout=10.0
                )
                if response.status_code == 200:
                    print(f"Published event {event_type} to CEO via HTTP fallback")

            # CFO fallback
            if target_module == "cfo" and settings.cfo_api_url:
                response = httpx.post(
                    f"{settings.cfo_api_url}/cfo/events/receive",
                    json=event,
                    timeout=10.0
                )
                if response.status_code == 200:
                    print(f"Published event {event_type} to CFO via HTTP fallback")

            # COO fallback
            if target_module == "coo" and settings.coo_api_url:
                response = httpx.post(
                    f"{settings.coo_api_url}/coo/events/receive",
                    json=event,
                    timeout=10.0
                )
                if response.status_code == 200:
                    print(f"Published event {event_type} to COO via HTTP fallback")

            # CMO fallback (serverless)
            if target_module == "cmo" and settings.cmo_api_url:
                response = httpx.post(
                    f"{settings.cmo_api_url}/api/events/webhook",
                    json=event,
                    timeout=10.0
                )
                if response.status_code == 200:
                    print(f"Published event {event_type} to CMO via HTTP webhook")

        except Exception as e:
            print(f"Failed to publish via HTTP fallback: {e}")

        return event_id

    def _log_event_to_db(self, event: Dict[str, Any], direction: str = "outbound"):
        """Log event to database for audit trail."""
        try:
            db = SessionLocal()
            db_event = CDOEvent(
                direction=direction,
                other_module=event.get("target_module") or event.get("source_module", "broadcast"),
                event_type=event["event_type"],
                payload=event,
                status="sent" if direction == "outbound" else "received"
            )
            db.add(db_event)
            db.commit()
            db.close()
        except Exception as e:
            print(f"Failed to log event to DB: {e}")

    def handle_incoming_event(self, event: Dict[str, Any]):
        """Process an incoming event."""
        event_type = event.get("event_type")
        source = event.get("source_module")
        payload = event.get("payload", {})

        print(f"Received event {event_type} from {source}")
        self._log_event_to_db(event, direction="inbound")

        try:
            if event_type == CDOInboundEvent.APPROVAL_DECIDED.value:
                self._handle_approval_decided(payload)
            elif event_type == CDOInboundEvent.SALES_DATA_UPDATED.value:
                self._handle_sales_data_updated(payload)
            elif event_type == CDOInboundEvent.INVENTORY_UPDATED.value:
                self._handle_inventory_updated(payload)
            elif event_type == CDOInboundEvent.CAMPAIGN_PERFORMANCE.value:
                self._handle_campaign_performance(payload)
            elif event_type == CDOInboundEvent.MARGIN_CHECK_RESPONSE.value:
                self._handle_margin_check_response(payload)
            elif event_type == CDOInboundEvent.CAPACITY_CHECK_RESPONSE.value:
                self._handle_capacity_check_response(payload)
            elif event_type == CDOInboundEvent.FINANCIAL_REPORT.value:
                self._handle_financial_report(payload)
            else:
                print(f"Unknown event type: {event_type}")
        except Exception as e:
            print(f"Error handling event {event_type}: {e}")

    def _handle_approval_decided(self, payload: Dict[str, Any]):
        """Handle approval decision from CEO."""
        status = payload.get("status")
        requesting_module = payload.get("requesting_module")

        if requesting_module != "cdo":
            return

        db = SessionLocal()
        try:
            alert = CDOAlert(
                severity=AlertSeverity.INFO if status == "approved" else AlertSeverity.WARNING,
                category="approval",
                title=f"Request {status.title()}",
                message=f"CEO has {status} the CDO request"
            )
            db.add(alert)
            db.commit()
        finally:
            db.close()

    def _handle_sales_data_updated(self, payload: Dict[str, Any]):
        """Handle sales data update - trigger analytics refresh."""
        print(f"Sales data updated: {payload}")
        db = SessionLocal()
        try:
            alert = CDOAlert(
                severity=AlertSeverity.INFO,
                category="analytics",
                title="Sales Data Updated",
                message=f"New sales data received — analytics may need refresh. Period: {payload.get('period', 'unknown')}"
            )
            db.add(alert)
            db.commit()
        finally:
            db.close()

    def _handle_inventory_updated(self, payload: Dict[str, Any]):
        """Handle inventory update from COO."""
        print(f"Inventory updated: {payload}")
        db = SessionLocal()
        try:
            item_name = payload.get("item_name", "Unknown")
            sku = payload.get("sku", "")
            quantity = payload.get("quantity", 0)
            alert = CDOAlert(
                severity=AlertSeverity.INFO,
                category="inventory",
                title="Inventory Updated",
                message=f"COO reports inventory change: {item_name} ({sku}) now at {quantity} units"
            )
            db.add(alert)
            db.commit()
        finally:
            db.close()

    def _handle_campaign_performance(self, payload: Dict[str, Any]):
        """Handle campaign performance from CMO."""
        print(f"Campaign performance: {payload}")
        db = SessionLocal()
        try:
            campaign_name = payload.get("campaign_name", "Unknown")
            roas = payload.get("roas", 0)
            alert = CDOAlert(
                severity=AlertSeverity.INFO,
                category="analytics",
                title="Campaign Performance Update",
                message=f"CMO campaign '{campaign_name}' ROAS: {roas:.2f}x"
            )
            db.add(alert)
            db.commit()
        finally:
            db.close()

    def _handle_financial_report(self, payload: Dict[str, Any]):
        """Handle financial report from CFO."""
        print(f"Financial report received: {payload}")
        db = SessionLocal()
        try:
            report_type = payload.get("report_type", "general")
            summary = payload.get("summary", "Financial report received from CFO")
            alert = CDOAlert(
                severity=AlertSeverity.INFO,
                category="finance",
                title=f"Financial Report: {report_type}",
                message=summary
            )
            db.add(alert)
            db.commit()
        finally:
            db.close()

    def _handle_margin_check_response(self, payload: Dict[str, Any]):
        """Handle margin check response from CFO."""
        validation_request_id = payload.get("validation_request_id")
        approved = payload.get("approved", False)
        summary = payload.get("summary", "")

        if not validation_request_id:
            print("Margin check response missing validation_request_id")
            return

        db = SessionLocal()
        try:
            from .cdo.validation import ValidationOrchestrator
            orchestrator = ValidationOrchestrator(db)
            result = orchestrator.handle_validation_response(
                validation_request_id=validation_request_id,
                approved=approved,
                response_data=payload,
                summary=summary or f"CFO margin check: {'approved' if approved else 'rejected'}",
            )
            print(f"Margin check response processed: {result}")

            alert = CDOAlert(
                severity=AlertSeverity.INFO if approved else AlertSeverity.WARNING,
                category="validation",
                title=f"Margin Check {'Approved' if approved else 'Rejected'}",
                message=summary or f"CFO has {'approved' if approved else 'rejected'} the margin check"
            )
            db.add(alert)
            db.commit()
        except Exception as e:
            print(f"Error processing margin check response: {e}")
        finally:
            db.close()

    def _handle_capacity_check_response(self, payload: Dict[str, Any]):
        """Handle capacity check response from COO."""
        validation_request_id = payload.get("validation_request_id")
        approved = payload.get("approved", False)
        summary = payload.get("summary", "")

        if not validation_request_id:
            print("Capacity check response missing validation_request_id")
            return

        db = SessionLocal()
        try:
            from .cdo.validation import ValidationOrchestrator
            orchestrator = ValidationOrchestrator(db)
            result = orchestrator.handle_validation_response(
                validation_request_id=validation_request_id,
                approved=approved,
                response_data=payload,
                summary=summary or f"COO capacity check: {'approved' if approved else 'rejected'}",
            )
            print(f"Capacity check response processed: {result}")

            alert = CDOAlert(
                severity=AlertSeverity.INFO if approved else AlertSeverity.WARNING,
                category="validation",
                title=f"Capacity Check {'Approved' if approved else 'Rejected'}",
                message=summary or f"COO has {'approved' if approved else 'rejected'} the capacity check"
            )
            db.add(alert)
            db.commit()
        except Exception as e:
            print(f"Error processing capacity check response: {e}")
        finally:
            db.close()

    def start_listener(self):
        """Start background Redis listener thread for incoming events."""
        if not self.client:
            print("Redis not connected - CDO listener not started")
            return

        def _listen():
            try:
                pubsub = self.client.pubsub()
                pubsub.subscribe("dearborn:events:cdo", "dearborn:events:broadcast")
                print("CDO Redis listener started on dearborn:events:cdo + broadcast")
                for message in pubsub.listen():
                    if message["type"] == "message":
                        try:
                            event = json.loads(message["data"])
                            if event.get("source_module") != "cdo":
                                self.handle_incoming_event(event)
                        except Exception as e:
                            print(f"CDO listener error: {e}")
            except Exception as e:
                print(f"CDO Redis listener failed: {e}")

        thread = threading.Thread(target=_listen, daemon=True)
        thread.start()

    def disconnect(self):
        """Disconnect from Redis."""
        if self._client:
            self._client.close()
            self._client = None


# Singleton instance
event_bus = EventBus()


# Convenience functions

def publish_trend_alert(
    trend_name: str,
    trend_score: float,
    description: str,
    recommended_actions: list
) -> Optional[str]:
    """Publish trend alert to CEO."""
    return event_bus.publish(
        CDOOutboundEvent.TREND_ALERT,
        {
            "trend_name": trend_name,
            "trend_score": trend_score,
            "description": description,
            "recommended_actions": recommended_actions,
            "title": f"Trend Alert: {trend_name}",
            "message": description
        },
        target_module="ceo"
    )


def publish_product_recommendation(
    product_idea_id: int,
    title: str,
    category: str,
    estimated_revenue: float,
    priority_score: float,
    justification: str
) -> Optional[str]:
    """Publish product recommendation to CEO for approval."""
    return event_bus.publish(
        CDOOutboundEvent.PRODUCT_RECOMMENDATION,
        {
            "product_idea_id": product_idea_id,
            "title": title,
            "category": category,
            "estimated_revenue": estimated_revenue,
            "priority_score": priority_score,
            "justification": justification,
            "risk_level": "medium"
        },
        target_module="ceo"
    )


def publish_demand_forecast(
    sku: str,
    product_name: str,
    forecast_period_days: int,
    forecasted_units: int,
    confidence: float
) -> Optional[str]:
    """Publish demand forecast to COO for production planning."""
    return event_bus.publish(
        CDOOutboundEvent.DEMAND_FORECAST,
        {
            "sku": sku,
            "product_name": product_name,
            "forecast_period_days": forecast_period_days,
            "forecasted_units": forecasted_units,
            "confidence": confidence,
            "title": f"Demand Forecast: {product_name}",
            "message": f"Forecasted {forecasted_units} units over {forecast_period_days} days"
        },
        target_module="coo"
    )


def publish_tech_pack_ready(
    tech_pack_id: int,
    tech_pack_number: str,
    style_name: str,
    status: str
) -> Optional[str]:
    """Notify COO that tech pack is ready for production."""
    return event_bus.publish(
        CDOOutboundEvent.TECH_PACK_READY,
        {
            "tech_pack_id": tech_pack_id,
            "tech_pack_number": tech_pack_number,
            "style_name": style_name,
            "status": status,
            "title": f"Tech Pack Ready: {style_name}",
            "message": f"Tech pack {tech_pack_number} is ready for production"
        },
        target_module="coo"
    )
