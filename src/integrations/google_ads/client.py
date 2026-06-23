"""Google Ads API client wrapper.

Uses the google-ads-python library (google-ads) to interact with the
Google Ads API via GAQL (Google Ads Query Language).
"""

from typing import Any, Dict, List, Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)


class GoogleAdsClient:
    """Thin wrapper around the google-ads library's GoogleAdsClient."""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialise the client.

        Args:
            config: Dict suitable for GoogleAdsClient.load_from_dict().
                    Must contain developer_token, client_id, client_secret,
                    refresh_token. Optionally login_customer_id.
        """
        from google.ads.googleads.client import GoogleAdsClient as _GAC

        self._client = _GAC.load_from_dict(config, version="v20")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ga_service(self):
        return self._client.get_service("GoogleAdsService")

    @staticmethod
    def _resource_name_id(resource_name: str) -> str:
        """Extract the numeric ID from a resource name like 'customers/123/campaigns/456'."""
        return resource_name.split("/")[-1]

    def _run_query(self, customer_id: str, query: str) -> List[Dict[str, Any]]:
        """Execute a GAQL query and return rows as plain dicts."""
        ga_service = self._ga_service()
        response = ga_service.search(customer_id=customer_id, query=query)
        rows = []
        for row in response:
            rows.append(row)
        return rows

    # ------------------------------------------------------------------
    # Account
    # ------------------------------------------------------------------

    def get_account_info(self, customer_id: str) -> Dict[str, Any]:
        """
        Return basic information about a Google Ads account.

        Args:
            customer_id: The 10-digit customer ID (dashes optional).

        Returns:
            Dict with id, name, currency_code, time_zone, status.
        """
        customer_id = customer_id.replace("-", "")
        query = """
            SELECT
                customer.id,
                customer.descriptive_name,
                customer.currency_code,
                customer.time_zone,
                customer.status
            FROM customer
            LIMIT 1
        """
        rows = self._run_query(customer_id, query)
        if not rows:
            return {}
        row = rows[0]
        c = row.customer
        return {
            "id": str(c.id),
            "name": c.descriptive_name,
            "currency_code": c.currency_code,
            "time_zone": c.time_zone,
            "status": c.status.name,
        }

    # ------------------------------------------------------------------
    # Campaigns
    # ------------------------------------------------------------------

    def list_campaigns(
        self,
        customer_id: str,
        status_filter: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        List campaigns in an account.

        Args:
            customer_id: Google Ads customer ID.
            status_filter: Optional status to filter on (ENABLED, PAUSED, REMOVED).
            limit: Maximum number of campaigns to return.

        Returns:
            List of campaign dicts.
        """
        customer_id = customer_id.replace("-", "")
        where_clause = "WHERE campaign.status != 'REMOVED'"
        if status_filter:
            where_clause = f"WHERE campaign.status = '{status_filter.upper()}'"

        query = f"""
            SELECT
                campaign.id,
                campaign.name,
                campaign.status,
                campaign.advertising_channel_type,
                campaign.start_date,
                campaign.end_date,
                campaign_budget.amount_micros,
                campaign_budget.name
            FROM campaign
            {where_clause}
            ORDER BY campaign.name
            LIMIT {limit}
        """
        rows = self._run_query(customer_id, query)
        campaigns = []
        for row in rows:
            c = row.campaign
            budget = row.campaign_budget
            campaigns.append(
                {
                    "id": str(c.id),
                    "name": c.name,
                    "status": c.status.name,
                    "advertising_channel_type": c.advertising_channel_type.name,
                    "start_date": c.start_date,
                    "end_date": c.end_date if c.end_date else None,
                    "daily_budget_micros": budget.amount_micros,
                    "daily_budget": budget.amount_micros / 1_000_000,
                    "budget_name": budget.name,
                }
            )
        return campaigns

    def get_campaign(self, customer_id: str, campaign_id: str) -> Dict[str, Any]:
        """
        Get details for a single campaign.

        Args:
            customer_id: Google Ads customer ID.
            campaign_id: Campaign ID.

        Returns:
            Campaign dict.

        Raises:
            ValueError: If campaign not found.
        """
        customer_id = customer_id.replace("-", "")
        query = f"""
            SELECT
                campaign.id,
                campaign.name,
                campaign.status,
                campaign.advertising_channel_type,
                campaign.start_date,
                campaign.end_date,
                campaign_budget.amount_micros,
                campaign_budget.name
            FROM campaign
            WHERE campaign.id = {campaign_id}
            LIMIT 1
        """
        rows = self._run_query(customer_id, query)
        if not rows:
            raise ValueError(f"Campaign {campaign_id} not found")
        row = rows[0]
        c = row.campaign
        budget = row.campaign_budget
        return {
            "id": str(c.id),
            "name": c.name,
            "status": c.status.name,
            "advertising_channel_type": c.advertising_channel_type.name,
            "start_date": c.start_date,
            "end_date": c.end_date if c.end_date else None,
            "daily_budget_micros": budget.amount_micros,
            "daily_budget": budget.amount_micros / 1_000_000,
            "budget_name": budget.name,
        }

    def create_campaign(
        self,
        customer_id: str,
        name: str,
        daily_budget: float,
        start_date: str,
        end_date: Optional[str] = None,
        status: str = "PAUSED",
        advertising_channel_type: str = "SEARCH",
    ) -> Dict[str, Any]:
        """
        Create a new campaign with a shared budget.

        The campaign is created as PAUSED by default so that ads are not
        served until the user explicitly enables it.

        Args:
            customer_id: Google Ads customer ID.
            name: Campaign name.
            daily_budget: Daily budget in account currency units (not micros).
            start_date: Start date in YYYYMMDD format.
            end_date: Optional end date in YYYYMMDD format.
            status: Initial campaign status (PAUSED or ENABLED).
            advertising_channel_type: Channel type (SEARCH, DISPLAY, etc.).

        Returns:
            Dict with created campaign id and resource_name.
        """
        customer_id = customer_id.replace("-", "")

        campaign_budget_service = self._client.get_service("CampaignBudgetService")
        campaign_service = self._client.get_service("CampaignService")

        # 1. Create campaign budget
        budget_op = self._client.get_type("CampaignBudgetOperation")
        budget = budget_op.create
        budget.name = f"Budget for {name}"
        budget.delivery_method = self._client.enums.BudgetDeliveryMethodEnum.STANDARD
        budget.amount_micros = int(daily_budget * 1_000_000)

        budget_response = campaign_budget_service.mutate_campaign_budgets(
            customer_id=customer_id, operations=[budget_op]
        )
        budget_resource_name = budget_response.results[0].resource_name

        # 2. Create campaign
        campaign_op = self._client.get_type("CampaignOperation")
        campaign = campaign_op.create
        campaign.name = name
        campaign.status = self._client.enums.CampaignStatusEnum[status]
        campaign.advertising_channel_type = self._client.enums.AdvertisingChannelTypeEnum[
            advertising_channel_type
        ]
        campaign.campaign_budget = budget_resource_name
        campaign.start_date = start_date
        if end_date:
            campaign.end_date = end_date

        # Manual CPC bidding strategy (simplest)
        campaign.manual_cpc.enhanced_cpc_enabled = False

        campaign_response = campaign_service.mutate_campaigns(
            customer_id=customer_id, operations=[campaign_op]
        )
        resource_name = campaign_response.results[0].resource_name
        campaign_id = self._resource_name_id(resource_name)

        return {
            "id": campaign_id,
            "resource_name": resource_name,
            "name": name,
            "status": status,
            "daily_budget": daily_budget,
            "start_date": start_date,
            "end_date": end_date,
        }

    def update_campaign_status(
        self, customer_id: str, campaign_id: str, status: str
    ) -> Dict[str, Any]:
        """
        Update the status of a campaign.

        Args:
            customer_id: Google Ads customer ID.
            campaign_id: Campaign ID.
            status: New status (ENABLED, PAUSED, REMOVED).

        Returns:
            Dict with updated campaign id and new status.
        """
        customer_id = customer_id.replace("-", "")
        campaign_service = self._client.get_service("CampaignService")

        campaign_op = self._client.get_type("CampaignOperation")
        campaign = campaign_op.update
        campaign.resource_name = campaign_service.campaign_path(customer_id, campaign_id)
        campaign.status = self._client.enums.CampaignStatusEnum[status]

        field_mask = self._client.get_type("FieldMask")
        field_mask.paths.append("status")
        campaign_op.update_mask.CopyFrom(field_mask)

        campaign_service.mutate_campaigns(customer_id=customer_id, operations=[campaign_op])
        return {"id": campaign_id, "status": status}

    def update_campaign_budget(
        self, customer_id: str, campaign_id: str, daily_budget: float
    ) -> Dict[str, Any]:
        """
        Update the daily budget of a campaign.

        Args:
            customer_id: Google Ads customer ID.
            campaign_id: Campaign ID.
            daily_budget: New daily budget in account currency units.

        Returns:
            Dict with campaign id and new budget.
        """
        customer_id = customer_id.replace("-", "")

        # Fetch the current budget resource name
        query = f"""
            SELECT campaign_budget.resource_name
            FROM campaign
            WHERE campaign.id = {campaign_id}
            LIMIT 1
        """
        rows = self._run_query(customer_id, query)
        if not rows:
            raise ValueError(f"Campaign {campaign_id} not found")
        budget_resource_name = rows[0].campaign_budget.resource_name

        budget_service = self._client.get_service("CampaignBudgetService")
        budget_op = self._client.get_type("CampaignBudgetOperation")
        budget = budget_op.update
        budget.resource_name = budget_resource_name
        budget.amount_micros = int(daily_budget * 1_000_000)

        field_mask = self._client.get_type("FieldMask")
        field_mask.paths.append("amount_micros")
        budget_op.update_mask.CopyFrom(field_mask)

        budget_service.mutate_campaign_budgets(customer_id=customer_id, operations=[budget_op])
        return {"id": campaign_id, "daily_budget": daily_budget}

    # ------------------------------------------------------------------
    # Ad Groups
    # ------------------------------------------------------------------

    def list_ad_groups(
        self,
        customer_id: str,
        campaign_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        List ad groups, optionally filtered by campaign.

        Args:
            customer_id: Google Ads customer ID.
            campaign_id: Optional campaign ID filter.
            limit: Maximum results.

        Returns:
            List of ad group dicts.
        """
        customer_id = customer_id.replace("-", "")
        where_clause = "WHERE ad_group.status != 'REMOVED'"
        if campaign_id:
            where_clause += f" AND campaign.id = {campaign_id}"

        query = f"""
            SELECT
                ad_group.id,
                ad_group.name,
                ad_group.status,
                ad_group.cpc_bid_micros,
                campaign.id,
                campaign.name
            FROM ad_group
            {where_clause}
            ORDER BY ad_group.name
            LIMIT {limit}
        """
        rows = self._run_query(customer_id, query)
        ad_groups = []
        for row in rows:
            ag = row.ad_group
            c = row.campaign
            ad_groups.append(
                {
                    "id": str(ag.id),
                    "name": ag.name,
                    "status": ag.status.name,
                    "cpc_bid_micros": ag.cpc_bid_micros,
                    "cpc_bid": ag.cpc_bid_micros / 1_000_000,
                    "campaign_id": str(c.id),
                    "campaign_name": c.name,
                }
            )
        return ad_groups

    def create_ad_group(
        self,
        customer_id: str,
        campaign_id: str,
        name: str,
        cpc_bid: float,
        status: str = "ENABLED",
    ) -> Dict[str, Any]:
        """
        Create an ad group within a campaign.

        Args:
            customer_id: Google Ads customer ID.
            campaign_id: Parent campaign ID.
            name: Ad group name.
            cpc_bid: Default CPC bid in account currency units.
            status: Initial status (ENABLED or PAUSED).

        Returns:
            Dict with created ad group id and resource_name.
        """
        customer_id = customer_id.replace("-", "")
        campaign_service = self._client.get_service("CampaignService")
        ad_group_service = self._client.get_service("AdGroupService")

        ag_op = self._client.get_type("AdGroupOperation")
        ag = ag_op.create
        ag.name = name
        ag.campaign = campaign_service.campaign_path(customer_id, campaign_id)
        ag.status = self._client.enums.AdGroupStatusEnum[status]
        ag.type_ = self._client.enums.AdGroupTypeEnum.SEARCH_STANDARD
        ag.cpc_bid_micros = int(cpc_bid * 1_000_000)

        response = ad_group_service.mutate_ad_groups(customer_id=customer_id, operations=[ag_op])
        resource_name = response.results[0].resource_name
        ad_group_id = self._resource_name_id(resource_name)

        return {
            "id": ad_group_id,
            "resource_name": resource_name,
            "name": name,
            "status": status,
            "cpc_bid": cpc_bid,
            "campaign_id": campaign_id,
        }

    # ------------------------------------------------------------------
    # Keywords
    # ------------------------------------------------------------------

    def list_keywords(
        self,
        customer_id: str,
        ad_group_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        List keywords, optionally filtered by ad group.

        Args:
            customer_id: Google Ads customer ID.
            ad_group_id: Optional ad group ID filter.
            limit: Maximum results.

        Returns:
            List of keyword dicts.
        """
        customer_id = customer_id.replace("-", "")
        where_clause = (
            "WHERE ad_group_criterion.status != 'REMOVED' AND ad_group_criterion.type = 'KEYWORD'"
        )
        if ad_group_id:
            where_clause += f" AND ad_group.id = {ad_group_id}"

        query = f"""
            SELECT
                ad_group_criterion.criterion_id,
                ad_group_criterion.keyword.text,
                ad_group_criterion.keyword.match_type,
                ad_group_criterion.status,
                ad_group_criterion.cpc_bid_micros,
                ad_group.id,
                ad_group.name
            FROM ad_group_criterion
            {where_clause}
            LIMIT {limit}
        """
        rows = self._run_query(customer_id, query)
        keywords = []
        for row in rows:
            criterion = row.ad_group_criterion
            ag = row.ad_group
            keywords.append(
                {
                    "criterion_id": str(criterion.criterion_id),
                    "text": criterion.keyword.text,
                    "match_type": criterion.keyword.match_type.name,
                    "status": criterion.status.name,
                    "cpc_bid_micros": criterion.cpc_bid_micros,
                    "cpc_bid": (
                        criterion.cpc_bid_micros / 1_000_000 if criterion.cpc_bid_micros else None
                    ),
                    "ad_group_id": str(ag.id),
                    "ad_group_name": ag.name,
                }
            )
        return keywords

    def add_keyword(
        self,
        customer_id: str,
        ad_group_id: str,
        keyword_text: str,
        match_type: str = "BROAD",
        cpc_bid: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Add a keyword to an ad group.

        Args:
            customer_id: Google Ads customer ID.
            ad_group_id: Ad group ID.
            keyword_text: The keyword text.
            match_type: BROAD, PHRASE, or EXACT.
            cpc_bid: Optional CPC bid override in account currency units.

        Returns:
            Dict with created criterion id and resource_name.
        """
        customer_id = customer_id.replace("-", "")
        ad_group_service = self._client.get_service("AdGroupService")
        criterion_service = self._client.get_service("AdGroupCriterionService")

        op = self._client.get_type("AdGroupCriterionOperation")
        criterion = op.create
        criterion.ad_group = ad_group_service.ad_group_path(customer_id, ad_group_id)
        criterion.status = self._client.enums.AdGroupCriterionStatusEnum.ENABLED
        criterion.keyword.text = keyword_text
        criterion.keyword.match_type = self._client.enums.KeywordMatchTypeEnum[match_type]

        if cpc_bid is not None:
            criterion.cpc_bid_micros = int(cpc_bid * 1_000_000)

        response = criterion_service.mutate_ad_group_criteria(
            customer_id=customer_id, operations=[op]
        )
        resource_name = response.results[0].resource_name
        criterion_id = self._resource_name_id(resource_name)

        return {
            "criterion_id": criterion_id,
            "resource_name": resource_name,
            "text": keyword_text,
            "match_type": match_type,
            "ad_group_id": ad_group_id,
        }

    # ------------------------------------------------------------------
    # Performance reports
    # ------------------------------------------------------------------

    def get_campaign_performance(
        self,
        customer_id: str,
        campaign_id: Optional[str] = None,
        date_range: str = "LAST_30_DAYS",
    ) -> List[Dict[str, Any]]:
        """
        Retrieve performance metrics for campaigns.

        Args:
            customer_id: Google Ads customer ID.
            campaign_id: Optional campaign ID to filter by.
            date_range: Named date range (e.g. LAST_7_DAYS, LAST_30_DAYS,
                        THIS_MONTH, LAST_MONTH).

        Returns:
            List of dicts with campaign metrics.
        """
        customer_id = customer_id.replace("-", "")
        where_clause = f"WHERE segments.date DURING {date_range}"
        if campaign_id:
            where_clause += f" AND campaign.id = {campaign_id}"

        query = f"""
            SELECT
                campaign.id,
                campaign.name,
                campaign.status,
                metrics.impressions,
                metrics.clicks,
                metrics.cost_micros,
                metrics.ctr,
                metrics.average_cpc,
                metrics.conversions,
                metrics.cost_per_conversion
            FROM campaign
            {where_clause}
            ORDER BY metrics.impressions DESC
        """
        rows = self._run_query(customer_id, query)
        results = []
        for row in rows:
            c = row.campaign
            m = row.metrics
            results.append(
                {
                    "campaign_id": str(c.id),
                    "campaign_name": c.name,
                    "campaign_status": c.status.name,
                    "impressions": m.impressions,
                    "clicks": m.clicks,
                    "cost_micros": m.cost_micros,
                    "cost": m.cost_micros / 1_000_000,
                    "ctr": round(m.ctr * 100, 2),
                    "average_cpc": m.average_cpc / 1_000_000 if m.average_cpc else 0,
                    "conversions": m.conversions,
                    "cost_per_conversion": (
                        m.cost_per_conversion / 1_000_000 if m.cost_per_conversion else 0
                    ),
                    "date_range": date_range,
                }
            )
        return results

    def get_ad_group_performance(
        self,
        customer_id: str,
        campaign_id: Optional[str] = None,
        date_range: str = "LAST_30_DAYS",
    ) -> List[Dict[str, Any]]:
        """
        Retrieve performance metrics for ad groups.

        Args:
            customer_id: Google Ads customer ID.
            campaign_id: Optional campaign ID to filter by.
            date_range: Named date range.

        Returns:
            List of dicts with ad group metrics.
        """
        customer_id = customer_id.replace("-", "")
        where_clause = f"WHERE segments.date DURING {date_range}"
        if campaign_id:
            where_clause += f" AND campaign.id = {campaign_id}"

        query = f"""
            SELECT
                ad_group.id,
                ad_group.name,
                ad_group.status,
                campaign.id,
                campaign.name,
                metrics.impressions,
                metrics.clicks,
                metrics.cost_micros,
                metrics.ctr,
                metrics.average_cpc,
                metrics.conversions
            FROM ad_group
            {where_clause}
            ORDER BY metrics.impressions DESC
        """
        rows = self._run_query(customer_id, query)
        results = []
        for row in rows:
            ag = row.ad_group
            c = row.campaign
            m = row.metrics
            results.append(
                {
                    "ad_group_id": str(ag.id),
                    "ad_group_name": ag.name,
                    "ad_group_status": ag.status.name,
                    "campaign_id": str(c.id),
                    "campaign_name": c.name,
                    "impressions": m.impressions,
                    "clicks": m.clicks,
                    "cost_micros": m.cost_micros,
                    "cost": m.cost_micros / 1_000_000,
                    "ctr": round(m.ctr * 100, 2),
                    "average_cpc": m.average_cpc / 1_000_000 if m.average_cpc else 0,
                    "conversions": m.conversions,
                    "date_range": date_range,
                }
            )
        return results
