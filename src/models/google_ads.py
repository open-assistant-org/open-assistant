"""Pydantic request/response models for the Google Ads integration."""

from typing import List, Optional

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Shared / base
# ---------------------------------------------------------------------------


class GoogleAdsConnectionTestResponse(BaseModel):
    service_name: str
    status: str
    message: str
    auth_url: Optional[str] = None


# ---------------------------------------------------------------------------
# Account
# ---------------------------------------------------------------------------


class GetAccountInfoRequest(BaseModel):
    customer_id: str = Field(..., description="Google Ads customer ID (e.g. '1234567890')")


class AccountInfoResponse(BaseModel):
    id: str
    name: str
    currency_code: str
    time_zone: str
    status: str


# ---------------------------------------------------------------------------
# Campaigns – requests
# ---------------------------------------------------------------------------


class ListCampaignsRequest(BaseModel):
    customer_id: str = Field(..., description="Google Ads customer ID")
    status_filter: Optional[str] = Field(
        None,
        description="Filter by status: ENABLED, PAUSED, or REMOVED. Omit for all non-removed.",
    )
    limit: int = Field(50, ge=1, le=500, description="Maximum number of campaigns to return")


class GetCampaignRequest(BaseModel):
    customer_id: str = Field(..., description="Google Ads customer ID")
    campaign_id: str = Field(..., description="Campaign ID")


class CreateCampaignRequest(BaseModel):
    customer_id: str = Field(..., description="Google Ads customer ID")
    name: str = Field(..., description="Campaign name")
    daily_budget: float = Field(..., gt=0, description="Daily budget in account currency units")
    start_date: str = Field(..., description="Start date in YYYYMMDD format (e.g. '20240101')")
    end_date: Optional[str] = Field(None, description="Optional end date in YYYYMMDD format")
    status: str = Field(
        "PAUSED",
        description="Initial campaign status: ENABLED or PAUSED (default PAUSED)",
    )
    advertising_channel_type: str = Field(
        "SEARCH",
        description="Advertising channel: SEARCH, DISPLAY, VIDEO, SHOPPING, etc.",
    )


class UpdateCampaignStatusRequest(BaseModel):
    customer_id: str = Field(..., description="Google Ads customer ID")
    campaign_id: str = Field(..., description="Campaign ID")
    status: str = Field(..., description="New status: ENABLED, PAUSED, or REMOVED")


class UpdateCampaignBudgetRequest(BaseModel):
    customer_id: str = Field(..., description="Google Ads customer ID")
    campaign_id: str = Field(..., description="Campaign ID")
    daily_budget: float = Field(..., gt=0, description="New daily budget in account currency units")


# ---------------------------------------------------------------------------
# Campaigns – responses
# ---------------------------------------------------------------------------


class CampaignResponse(BaseModel):
    id: str
    name: str
    status: str
    advertising_channel_type: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    daily_budget_micros: Optional[int] = None
    daily_budget: Optional[float] = None
    budget_name: Optional[str] = None


class CreateCampaignResponse(BaseModel):
    id: str
    resource_name: str
    name: str
    status: str
    daily_budget: float
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class UpdateCampaignResponse(BaseModel):
    id: str
    status: Optional[str] = None
    daily_budget: Optional[float] = None


# ---------------------------------------------------------------------------
# Ad Groups – requests
# ---------------------------------------------------------------------------


class ListAdGroupsRequest(BaseModel):
    customer_id: str = Field(..., description="Google Ads customer ID")
    campaign_id: Optional[str] = Field(None, description="Filter by campaign ID")
    limit: int = Field(50, ge=1, le=500, description="Maximum number of ad groups to return")


class CreateAdGroupRequest(BaseModel):
    customer_id: str = Field(..., description="Google Ads customer ID")
    campaign_id: str = Field(..., description="Parent campaign ID")
    name: str = Field(..., description="Ad group name")
    cpc_bid: float = Field(..., gt=0, description="Default CPC bid in account currency units")
    status: str = Field("ENABLED", description="Initial status: ENABLED or PAUSED")


# ---------------------------------------------------------------------------
# Ad Groups – responses
# ---------------------------------------------------------------------------


class AdGroupResponse(BaseModel):
    id: str
    name: str
    status: str
    cpc_bid_micros: Optional[int] = None
    cpc_bid: Optional[float] = None
    campaign_id: str
    campaign_name: Optional[str] = None


class CreateAdGroupResponse(BaseModel):
    id: str
    resource_name: str
    name: str
    status: str
    cpc_bid: float
    campaign_id: str


# ---------------------------------------------------------------------------
# Keywords – requests
# ---------------------------------------------------------------------------


class ListKeywordsRequest(BaseModel):
    customer_id: str = Field(..., description="Google Ads customer ID")
    ad_group_id: Optional[str] = Field(None, description="Filter by ad group ID")
    limit: int = Field(100, ge=1, le=1000, description="Maximum number of keywords to return")


class AddKeywordRequest(BaseModel):
    customer_id: str = Field(..., description="Google Ads customer ID")
    ad_group_id: str = Field(..., description="Ad group ID to add the keyword to")
    keyword_text: str = Field(..., description="The keyword text")
    match_type: str = Field(
        "BROAD",
        description="Keyword match type: BROAD, PHRASE, or EXACT",
    )
    cpc_bid: Optional[float] = Field(
        None,
        description="Optional CPC bid override in account currency units",
    )


# ---------------------------------------------------------------------------
# Keywords – responses
# ---------------------------------------------------------------------------


class KeywordResponse(BaseModel):
    criterion_id: str
    text: str
    match_type: str
    status: str
    cpc_bid_micros: Optional[int] = None
    cpc_bid: Optional[float] = None
    ad_group_id: str
    ad_group_name: Optional[str] = None


class AddKeywordResponse(BaseModel):
    criterion_id: str
    resource_name: str
    text: str
    match_type: str
    ad_group_id: str


# ---------------------------------------------------------------------------
# Performance reports – requests
# ---------------------------------------------------------------------------


class GetCampaignPerformanceRequest(BaseModel):
    customer_id: str = Field(..., description="Google Ads customer ID")
    campaign_id: Optional[str] = Field(None, description="Filter by campaign ID")
    date_range: str = Field(
        "LAST_30_DAYS",
        description=(
            "Named date range: LAST_7_DAYS, LAST_30_DAYS, THIS_MONTH, "
            "LAST_MONTH, LAST_14_DAYS, TODAY, YESTERDAY"
        ),
    )


class GetAdGroupPerformanceRequest(BaseModel):
    customer_id: str = Field(..., description="Google Ads customer ID")
    campaign_id: Optional[str] = Field(None, description="Filter by campaign ID")
    date_range: str = Field(
        "LAST_30_DAYS",
        description="Named date range (same options as GetCampaignPerformanceRequest)",
    )


# ---------------------------------------------------------------------------
# Performance reports – responses
# ---------------------------------------------------------------------------


class CampaignPerformanceResponse(BaseModel):
    campaign_id: str
    campaign_name: str
    campaign_status: str
    impressions: int
    clicks: int
    cost_micros: int
    cost: float
    ctr: float
    average_cpc: float
    conversions: float
    cost_per_conversion: float
    date_range: str


class AdGroupPerformanceResponse(BaseModel):
    ad_group_id: str
    ad_group_name: str
    ad_group_status: str
    campaign_id: str
    campaign_name: str
    impressions: int
    clicks: int
    cost_micros: int
    cost: float
    ctr: float
    average_cpc: float
    conversions: float
    date_range: str
