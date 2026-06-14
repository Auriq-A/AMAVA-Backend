"""Reports API (2021-06-30).

Request, poll and download reports. The typical flow:
    1. create_report(reportType=..., marketplaceIds=[...])  -> reportId
    2. poll get_report(reportId) until processingStatus == "DONE"
    3. get_report_document(reportDocumentId) -> a URL to download (+ optional
       compression). The actual download/decompress is left to the caller.
"""
from __future__ import annotations

from typing import Any

from ..client import SPAPIResponse
from .base import BaseSection


class ReportsAPI(BaseSection):
    path_prefix = "/reports/2021-06-30"

    def create_report(
        self,
        *,
        report_type: str,
        marketplace_ids: list[str] | None = None,
        data_start_time: str | None = None,
        data_end_time: str | None = None,
        report_options: dict[str, Any] | None = None,
    ) -> SPAPIResponse:
        """Request a new report. Operation: createReport."""
        body: dict[str, Any] = {
            "reportType": report_type,
            "marketplaceIds": self._default_marketplace_ids(marketplace_ids),
        }
        if data_start_time:
            body["dataStartTime"] = data_start_time
        if data_end_time:
            body["dataEndTime"] = data_end_time
        if report_options:
            body["reportOptions"] = report_options
        return self._post("/reports", operation="createReport", json_body=body)

    def get_report(self, report_id: str) -> SPAPIResponse:
        """Check a report's processing status. Operation: getReport."""
        return self._get(f"/reports/{report_id}", operation="getReport")

    def get_reports(
        self,
        *,
        report_types: list[str] | None = None,
        processing_statuses: list[str] | None = None,
        marketplace_ids: list[str] | None = None,
        page_size: int | None = None,
        created_since: str | None = None,
        created_until: str | None = None,
        next_token: str | None = None,
    ) -> SPAPIResponse:
        """List recent reports. Operation: getReports."""
        params = {
            "reportTypes": report_types,
            "processingStatuses": processing_statuses,
            "marketplaceIds": marketplace_ids,
            "pageSize": page_size,
            "createdSince": created_since,
            "createdUntil": created_until,
            "nextToken": next_token,
        }
        return self._get("/reports", operation="getReports", params=params)

    def cancel_report(self, report_id: str) -> SPAPIResponse:
        """Cancel a queued report. Operation: cancelReport."""
        return self._delete(f"/reports/{report_id}", operation="cancelReport")

    def get_report_document(self, report_document_id: str) -> SPAPIResponse:
        """Get the download URL + compression for a finished report.
        Operation: getReportDocument."""
        return self._get(
            f"/documents/{report_document_id}", operation="getReportDocument"
        )

    def create_report_schedule(
        self,
        *,
        report_type: str,
        period: str,
        marketplace_ids: list[str] | None = None,
        next_report_creation_time: str | None = None,
        report_options: dict[str, Any] | None = None,
    ) -> SPAPIResponse:
        """Schedule a recurring report. Operation: createReportSchedule."""
        body: dict[str, Any] = {
            "reportType": report_type,
            "marketplaceIds": self._default_marketplace_ids(marketplace_ids),
            "period": period,
        }
        if next_report_creation_time:
            body["nextReportCreationTime"] = next_report_creation_time
        if report_options:
            body["reportOptions"] = report_options
        return self._post(
            "/schedules", operation="createReportSchedule", json_body=body
        )
