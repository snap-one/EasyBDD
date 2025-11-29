"""
PagerDuty Service for Easy BDD Framework

Provides PagerDuty incident management operations including:
- Create incidents
- Resolve incidents
- Acknowledge incidents
- Get incident details
- List incidents
- Manage on-call schedules
"""

import os
import requests
from typing import Optional, Dict, Any, List
from datetime import datetime
import json


class PagerDutyService:
    """Service for PagerDuty incident management and on-call operations."""

    # Global PagerDuty configuration
    _global_config = {
        "api_key": None,
        "api_base_url": "https://api.pagerduty.com",
    }

    def __init__(self, logger=None, api_key: str = None, api_base_url: str = None):
        """
        Initialize PagerDuty Service.

        Args:
            logger: Logger instance for output
            api_key: PagerDuty API key (or use global config)
            api_base_url: PagerDuty API base URL (default: https://api.pagerduty.com)
        """
        self.logger = logger
        self.api_key = api_key or self._global_config.get("api_key") or os.environ.get("PAGERDUTY_API_KEY")
        self.api_base_url = api_base_url or self._global_config.get("api_base_url") or "https://api.pagerduty.com"
        
        if not self.api_key:
            raise ValueError(
                "PagerDuty API key not configured. Set PAGERDUTY_API_KEY environment variable "
                "or configure via PagerDutyService.configure_global_api_key()"
            )

    @classmethod
    def configure_global_api_key(cls, api_key: str, api_base_url: str = None):
        """
        Configure global PagerDuty API key.

        Args:
            api_key: PagerDuty API key
            api_base_url: PagerDuty API base URL (optional)
        """
        cls._global_config["api_key"] = api_key
        if api_base_url:
            cls._global_config["api_base_url"] = api_base_url

    def _log(self, message: str, level: str = "info"):
        """Log a message if logger is available."""
        if self.logger:
            if hasattr(self.logger, level):
                log_func = getattr(self.logger, level)
                log_func(message)
            else:
                self.logger(f"      {message}")
        else:
            print(f"      {message}")

    def _get_headers(self) -> Dict[str, str]:
        """Get headers for API requests."""
        return {
            "Authorization": f"Token token={self.api_key}",
            "Accept": "application/vnd.pagerduty+json;version=2",
            "Content-Type": "application/json",
        }

    def _make_request(
        self, method: str, endpoint: str, data: Dict[str, Any] = None, params: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Make an API request to PagerDuty.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint (e.g., '/incidents')
            data: Request body data
            params: Query parameters

        Returns:
            Response JSON as dictionary

        Raises:
            Exception: If request fails
        """
        url = f"{self.api_base_url}{endpoint}"
        headers = self._get_headers()

        try:
            if method.upper() == "GET":
                response = requests.get(url, headers=headers, params=params, timeout=30)
            elif method.upper() == "POST":
                response = requests.post(url, headers=headers, json=data, params=params, timeout=30)
            elif method.upper() == "PUT":
                response = requests.put(url, headers=headers, json=data, params=params, timeout=30)
            elif method.upper() == "DELETE":
                response = requests.delete(url, headers=headers, params=params, timeout=30)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            response.raise_for_status()
            return response.json() if response.content else {}

        except requests.exceptions.RequestException as e:
            error_msg = f"PagerDuty API request failed: {str(e)}"
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_detail = e.response.json()
                    error_msg += f" - {error_detail}"
                except:
                    error_msg += f" - Status: {e.response.status_code}"
            raise Exception(error_msg) from e

    def create_incident(
        self,
        service_id: str,
        title: str,
        description: str = None,
        severity: str = "error",
        urgency: str = None,
        priority_id: str = None,
        assignees: List[str] = None,
        escalation_policy_id: str = None,
        custom_details: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """
        Create a PagerDuty incident.

        Args:
            service_id: PagerDuty service ID
            title: Incident title
            description: Incident description
            severity: Severity level (critical, error, warning, info)
            urgency: Urgency level (high, low) - defaults based on severity
            priority_id: Priority ID (optional)
            assignees: List of user IDs to assign (optional)
            escalation_policy_id: Escalation policy ID (optional)
            custom_details: Custom details dictionary (optional)

        Returns:
            Created incident data
        """
        # Default urgency based on severity
        if urgency is None:
            urgency = "high" if severity in ["critical", "error"] else "low"

        incident_data = {
            "incident": {
                "type": "incident",
                "title": title,
                "service": {
                    "id": service_id,
                    "type": "service_reference",
                },
                "priority": {"id": priority_id, "type": "priority_reference"} if priority_id else None,
                "urgency": urgency,
                "body": {
                    "type": "incident_body",
                    "details": description or title,
                },
            }
        }

        # Remove None values
        if incident_data["incident"]["priority"] is None:
            del incident_data["incident"]["priority"]

        # Add assignees if provided
        if assignees:
            incident_data["incident"]["assignments"] = [
                {"assignee": {"id": user_id, "type": "user_reference"}} for user_id in assignees
            ]

        # Add escalation policy if provided
        if escalation_policy_id:
            incident_data["incident"]["escalation_policy"] = {
                "id": escalation_policy_id,
                "type": "escalation_policy_reference",
            }

        # Add custom details
        if custom_details:
            incident_data["incident"]["custom_details"] = custom_details

        self._log(f"Creating PagerDuty incident: {title}")
        response = self._make_request("POST", "/incidents", data=incident_data)
        incident = response.get("incident", {})
        self._log(f"Incident created: {incident.get('id')} - {incident.get('incident_number')}")
        return incident

    def resolve_incident(self, incident_id: str, resolution: str = None) -> Dict[str, Any]:
        """
        Resolve a PagerDuty incident.

        Args:
            incident_id: Incident ID
            resolution: Resolution notes (optional)

        Returns:
            Updated incident data
        """
        update_data = {
            "incident": {
                "type": "incident",
                "status": "resolved",
            }
        }

        if resolution:
            update_data["incident"]["resolution"] = resolution

        self._log(f"Resolving incident: {incident_id}")
        response = self._make_request("PUT", f"/incidents/{incident_id}", data=update_data)
        incident = response.get("incident", {})
        self._log(f"Incident resolved: {incident.get('id')}")
        return incident

    def acknowledge_incident(self, incident_id: str, acknowledger_id: str = None) -> Dict[str, Any]:
        """
        Acknowledge a PagerDuty incident.

        Args:
            incident_id: Incident ID
            acknowledger_id: User ID acknowledging (optional, uses API key user if not provided)

        Returns:
            Updated incident data
        """
        update_data = {
            "incident": {
                "type": "incident",
                "status": "acknowledged",
            }
        }

        if acknowledger_id:
            update_data["incident"]["acknowledgers"] = [
                {"acknowledger": {"id": acknowledger_id, "type": "user_reference"}}
            ]

        self._log(f"Acknowledging incident: {incident_id}")
        response = self._make_request("PUT", f"/incidents/{incident_id}", data=update_data)
        incident = response.get("incident", {})
        self._log(f"Incident acknowledged: {incident.get('id')}")
        return incident

    def get_incident(self, incident_id: str) -> Dict[str, Any]:
        """
        Get incident details.

        Args:
            incident_id: Incident ID

        Returns:
            Incident data
        """
        self._log(f"Getting incident: {incident_id}")
        response = self._make_request("GET", f"/incidents/{incident_id}")
        return response.get("incident", {})

    def list_incidents(
        self,
        service_ids: List[str] = None,
        statuses: List[str] = None,
        since: str = None,
        until: str = None,
        limit: int = 25,
    ) -> List[Dict[str, Any]]:
        """
        List incidents.

        Args:
            service_ids: Filter by service IDs (optional)
            statuses: Filter by statuses (triggered, acknowledged, resolved) (optional)
            since: Start date (ISO 8601 format) (optional)
            until: End date (ISO 8601 format) (optional)
            limit: Maximum number of results (default: 25, max: 100)

        Returns:
            List of incidents
        """
        params = {"limit": min(limit, 100)}

        if service_ids:
            params["service_ids[]"] = service_ids
        if statuses:
            params["statuses[]"] = statuses
        if since:
            params["since"] = since
        if until:
            params["until"] = until

        self._log("Listing incidents")
        response = self._make_request("GET", "/incidents", params=params)
        return response.get("incidents", [])

    def update_incident(
        self,
        incident_id: str,
        title: str = None,
        description: str = None,
        severity: str = None,
        urgency: str = None,
        priority_id: str = None,
        status: str = None,
        custom_details: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """
        Update an incident.

        Args:
            incident_id: Incident ID
            title: New title (optional)
            description: New description (optional)
            severity: New severity (optional)
            urgency: New urgency (optional)
            priority_id: New priority ID (optional)
            status: New status (triggered, acknowledged, resolved) (optional)
            custom_details: Custom details to update (optional)

        Returns:
            Updated incident data
        """
        update_data = {"incident": {"type": "incident"}}

        if title:
            update_data["incident"]["title"] = title
        if description:
            update_data["incident"]["body"] = {
                "type": "incident_body",
                "details": description,
            }
        if severity:
            update_data["incident"]["severity"] = severity
        if urgency:
            update_data["incident"]["urgency"] = urgency
        if priority_id:
            update_data["incident"]["priority"] = {
                "id": priority_id,
                "type": "priority_reference",
            }
        if status:
            update_data["incident"]["status"] = status
        if custom_details:
            update_data["incident"]["custom_details"] = custom_details

        self._log(f"Updating incident: {incident_id}")
        response = self._make_request("PUT", f"/incidents/{incident_id}", data=update_data)
        incident = response.get("incident", {})
        self._log(f"Incident updated: {incident.get('id')}")
        return incident

    def get_oncall_users(self, schedule_ids: List[str] = None, escalation_policy_ids: List[str] = None) -> List[Dict[str, Any]]:
        """
        Get users currently on-call.

        Args:
            schedule_ids: Filter by schedule IDs (optional)
            escalation_policy_ids: Filter by escalation policy IDs (optional)

        Returns:
            List of on-call users
        """
        params = {}
        if schedule_ids:
            params["schedule_ids[]"] = schedule_ids
        if escalation_policy_ids:
            params["escalation_policy_ids[]"] = escalation_policy_ids

        self._log("Getting on-call users")
        response = self._make_request("GET", "/oncalls", params=params)
        return response.get("oncalls", [])

    def get_services(self, query: str = None, limit: int = 25) -> List[Dict[str, Any]]:
        """
        List services.

        Args:
            query: Search query (optional)
            limit: Maximum number of results (default: 25)

        Returns:
            List of services
        """
        params = {"limit": min(limit, 100)}
        if query:
            params["query"] = query

        self._log("Listing services")
        response = self._make_request("GET", "/services", params=params)
        return response.get("services", [])

    def get_service(self, service_id: str) -> Dict[str, Any]:
        """
        Get service details.

        Args:
            service_id: Service ID

        Returns:
            Service data
        """
        self._log(f"Getting service: {service_id}")
        response = self._make_request("GET", f"/services/{service_id}")
        return response.get("service", {})

