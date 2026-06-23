"""Google Ads service."""

from typing import Any, Dict, List, Optional

from src.core.repositories.audit import AuditLogRepository
from src.core.repositories.credentials import CredentialsRepository
from src.core.repositories.settings import SettingsRepository
from src.integrations.google_ads.auth import (
    GoogleAdsOAuthFlowRequired,
    get_google_ads_credentials_config,
)
from src.integrations.google_ads.client import GoogleAdsClient
from src.services.base import BaseService
from src.utils.logger import get_logger

logger = get_logger(__name__)


class GoogleAdsService(BaseService):
    """Service for Google Ads integration operations."""

    def __init__(
        self,
        settings_repo: SettingsRepository,
        credentials_repo: CredentialsRepository,
        audit_repo: Optional[AuditLogRepository] = None,
    ):
        super().__init__(settings_repo, credentials_repo, audit_repo)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_client(self) -> GoogleAdsClient:
        """
        Build and return a configured GoogleAdsClient.

        Raises:
            ValueError: If the integration is disabled or settings are missing.
            GoogleAdsOAuthFlowRequired: If no OAuth token has been stored yet.
        """
        enabled = self.settings_repo.get("google_ads.enabled")
        if not enabled:
            raise ValueError("Google Ads integration is not enabled")

        config = get_google_ads_credentials_config(
            credentials_repo=self.credentials_repo,
            settings_repo=self.settings_repo,
        )
        return GoogleAdsClient(config)

    def _default_customer_id(self) -> str:
        """Return the default customer ID from settings."""
        customer_id = self.settings_repo.get("google_ads.customer_id")
        if not customer_id:
            raise ValueError(
                "Google Ads customer ID not configured. "
                "Please add it in Settings under Google Ads integration."
            )
        return customer_id

    # ------------------------------------------------------------------
    # Account
    # ------------------------------------------------------------------

    def get_account_info(self, customer_id: Optional[str] = None) -> Dict[str, Any]:
        """Return basic information about a Google Ads account."""
        client = self._get_client()
        cid = customer_id or self._default_customer_id()
        result = client.get_account_info(cid)
        self._log_web_request(
            service_name="google_ads",
            action="get_account_info",
            endpoint="GoogleAdsService.search",
            method="GET",
            success=True,
            request_data={"customer_id": cid},
            response_data={"id": result.get("id")},
        )
        return result

    # ------------------------------------------------------------------
    # Campaigns
    # ------------------------------------------------------------------

    def list_campaigns(
        self,
        customer_id: Optional[str] = None,
        status_filter: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """List campaigns in a Google Ads account."""
        client = self._get_client()
        cid = customer_id or self._default_customer_id()
        result = client.list_campaigns(cid, status_filter=status_filter, limit=limit)
        self._log_web_request(
            service_name="google_ads",
            action="list_campaigns",
            endpoint="GoogleAdsService.search",
            method="GET",
            success=True,
            request_data={"customer_id": cid, "status_filter": status_filter, "limit": limit},
            response_data={"count": len(result)},
        )
        return result

    def get_campaign(self, campaign_id: str, customer_id: Optional[str] = None) -> Dict[str, Any]:
        """Get details for a single campaign."""
        client = self._get_client()
        cid = customer_id or self._default_customer_id()
        result = client.get_campaign(cid, campaign_id)
        self._log_web_request(
            service_name="google_ads",
            action="get_campaign",
            endpoint="GoogleAdsService.search",
            method="GET",
            success=True,
            request_data={"customer_id": cid, "campaign_id": campaign_id},
            response_data={"id": result.get("id")},
        )
        return result

    def create_campaign(
        self,
        name: str,
        daily_budget: float,
        start_date: str,
        customer_id: Optional[str] = None,
        end_date: Optional[str] = None,
        status: str = "PAUSED",
        advertising_channel_type: str = "SEARCH",
    ) -> Dict[str, Any]:
        """Create a new Google Ads campaign."""
        client = self._get_client()
        cid = customer_id or self._default_customer_id()
        result = client.create_campaign(
            customer_id=cid,
            name=name,
            daily_budget=daily_budget,
            start_date=start_date,
            end_date=end_date,
            status=status,
            advertising_channel_type=advertising_channel_type,
        )
        self._log_web_request(
            service_name="google_ads",
            action="create_campaign",
            endpoint="CampaignService.mutate_campaigns",
            method="POST",
            success=True,
            request_data={"customer_id": cid, "name": name, "daily_budget": daily_budget},
            response_data={"campaign_id": result.get("id")},
        )
        return result

    def update_campaign_status(
        self, campaign_id: str, status: str, customer_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update the status of a campaign (ENABLED, PAUSED, REMOVED)."""
        client = self._get_client()
        cid = customer_id or self._default_customer_id()
        result = client.update_campaign_status(cid, campaign_id, status)
        self._log_web_request(
            service_name="google_ads",
            action="update_campaign_status",
            endpoint="CampaignService.mutate_campaigns",
            method="POST",
            success=True,
            request_data={"customer_id": cid, "campaign_id": campaign_id, "status": status},
            response_data=result,
        )
        return result

    def update_campaign_budget(
        self, campaign_id: str, daily_budget: float, customer_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update the daily budget of a campaign."""
        client = self._get_client()
        cid = customer_id or self._default_customer_id()
        result = client.update_campaign_budget(cid, campaign_id, daily_budget)
        self._log_web_request(
            service_name="google_ads",
            action="update_campaign_budget",
            endpoint="CampaignBudgetService.mutate_campaign_budgets",
            method="POST",
            success=True,
            request_data={
                "customer_id": cid,
                "campaign_id": campaign_id,
                "daily_budget": daily_budget,
            },
            response_data=result,
        )
        return result

    # ------------------------------------------------------------------
    # Ad Groups
    # ------------------------------------------------------------------

    def list_ad_groups(
        self,
        customer_id: Optional[str] = None,
        campaign_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """List ad groups, optionally filtered by campaign."""
        client = self._get_client()
        cid = customer_id or self._default_customer_id()
        result = client.list_ad_groups(cid, campaign_id=campaign_id, limit=limit)
        self._log_web_request(
            service_name="google_ads",
            action="list_ad_groups",
            endpoint="GoogleAdsService.search",
            method="GET",
            success=True,
            request_data={"customer_id": cid, "campaign_id": campaign_id, "limit": limit},
            response_data={"count": len(result)},
        )
        return result

    def create_ad_group(
        self,
        campaign_id: str,
        name: str,
        cpc_bid: float,
        customer_id: Optional[str] = None,
        status: str = "ENABLED",
    ) -> Dict[str, Any]:
        """Create an ad group within a campaign."""
        client = self._get_client()
        cid = customer_id or self._default_customer_id()
        result = client.create_ad_group(
            customer_id=cid,
            campaign_id=campaign_id,
            name=name,
            cpc_bid=cpc_bid,
            status=status,
        )
        self._log_web_request(
            service_name="google_ads",
            action="create_ad_group",
            endpoint="AdGroupService.mutate_ad_groups",
            method="POST",
            success=True,
            request_data={
                "customer_id": cid,
                "campaign_id": campaign_id,
                "name": name,
                "cpc_bid": cpc_bid,
            },
            response_data={"ad_group_id": result.get("id")},
        )
        return result

    # ------------------------------------------------------------------
    # Keywords
    # ------------------------------------------------------------------

    def list_keywords(
        self,
        customer_id: Optional[str] = None,
        ad_group_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """List keywords, optionally filtered by ad group."""
        client = self._get_client()
        cid = customer_id or self._default_customer_id()
        result = client.list_keywords(cid, ad_group_id=ad_group_id, limit=limit)
        self._log_web_request(
            service_name="google_ads",
            action="list_keywords",
            endpoint="GoogleAdsService.search",
            method="GET",
            success=True,
            request_data={"customer_id": cid, "ad_group_id": ad_group_id, "limit": limit},
            response_data={"count": len(result)},
        )
        return result

    def add_keyword(
        self,
        ad_group_id: str,
        keyword_text: str,
        customer_id: Optional[str] = None,
        match_type: str = "BROAD",
        cpc_bid: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Add a keyword to an ad group."""
        client = self._get_client()
        cid = customer_id or self._default_customer_id()
        result = client.add_keyword(
            customer_id=cid,
            ad_group_id=ad_group_id,
            keyword_text=keyword_text,
            match_type=match_type,
            cpc_bid=cpc_bid,
        )
        self._log_web_request(
            service_name="google_ads",
            action="add_keyword",
            endpoint="AdGroupCriterionService.mutate_ad_group_criteria",
            method="POST",
            success=True,
            request_data={
                "customer_id": cid,
                "ad_group_id": ad_group_id,
                "keyword_text": keyword_text,
                "match_type": match_type,
            },
            response_data={"criterion_id": result.get("criterion_id")},
        )
        return result

    # ------------------------------------------------------------------
    # Performance reports
    # ------------------------------------------------------------------

    def get_campaign_performance(
        self,
        customer_id: Optional[str] = None,
        campaign_id: Optional[str] = None,
        date_range: str = "LAST_30_DAYS",
    ) -> List[Dict[str, Any]]:
        """Retrieve performance metrics for campaigns."""
        client = self._get_client()
        cid = customer_id or self._default_customer_id()
        result = client.get_campaign_performance(
            cid, campaign_id=campaign_id, date_range=date_range
        )
        self._log_web_request(
            service_name="google_ads",
            action="get_campaign_performance",
            endpoint="GoogleAdsService.search",
            method="GET",
            success=True,
            request_data={"customer_id": cid, "date_range": date_range},
            response_data={"count": len(result)},
        )
        return result

    def get_ad_group_performance(
        self,
        customer_id: Optional[str] = None,
        campaign_id: Optional[str] = None,
        date_range: str = "LAST_30_DAYS",
    ) -> List[Dict[str, Any]]:
        """Retrieve performance metrics for ad groups."""
        client = self._get_client()
        cid = customer_id or self._default_customer_id()
        result = client.get_ad_group_performance(
            cid, campaign_id=campaign_id, date_range=date_range
        )
        self._log_web_request(
            service_name="google_ads",
            action="get_ad_group_performance",
            endpoint="GoogleAdsService.search",
            method="GET",
            success=True,
            request_data={"customer_id": cid, "date_range": date_range},
            response_data={"count": len(result)},
        )
        return result

    # ------------------------------------------------------------------
    # Connection test
    # ------------------------------------------------------------------

    def test_connection(self) -> Dict[str, Any]:
        """Test Google Ads connection by fetching account info."""
        try:
            cid = self.settings_repo.get("google_ads.customer_id")
            if not cid:
                return {
                    "service_name": "google_ads",
                    "status": "error",
                    "message": "Google Ads customer ID not configured.",
                }
            info = self.get_account_info(cid)
            return {
                "service_name": "google_ads",
                "status": "success",
                "message": f"Connected to Google Ads account: {info.get('name', cid)}",
            }
        except GoogleAdsOAuthFlowRequired as e:
            return {
                "service_name": "google_ads",
                "status": "oauth_required",
                "message": "Google Ads OAuth not configured. Please complete the OAuth flow first.",
                "auth_url": e.auth_url or "",
            }
        except ValueError as e:
            return {"service_name": "google_ads", "status": "error", "message": str(e)}
        except Exception as e:
            logger.error(f"Google Ads connection test failed: {e}")
            return {
                "service_name": "google_ads",
                "status": "error",
                "message": f"Connection failed: {str(e)}",
            }
