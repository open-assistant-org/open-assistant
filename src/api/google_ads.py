"""Google Ads API endpoints."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException

from src.core.dependencies import get_credentials_repo, get_settings_repo
from src.core.repositories.credentials import CredentialsRepository
from src.core.repositories.settings import SettingsRepository
from src.models.google_ads import (
    AccountInfoResponse,
    AddKeywordRequest,
    AddKeywordResponse,
    AdGroupResponse,
    CampaignPerformanceResponse,
    AdGroupPerformanceResponse,
    CampaignResponse,
    CreateAdGroupRequest,
    CreateAdGroupResponse,
    CreateCampaignRequest,
    CreateCampaignResponse,
    GetAccountInfoRequest,
    GetAdGroupPerformanceRequest,
    GetCampaignPerformanceRequest,
    GetCampaignRequest,
    GoogleAdsConnectionTestResponse,
    KeywordResponse,
    ListAdGroupsRequest,
    ListCampaignsRequest,
    ListKeywordsRequest,
    UpdateCampaignBudgetRequest,
    UpdateCampaignResponse,
    UpdateCampaignStatusRequest,
)
from src.services.google_ads import GoogleAdsService
from src.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/google_ads", tags=["google_ads"])


# ----------------------------------------------------------------------------
# Dependency injection
# ----------------------------------------------------------------------------


def get_google_ads_service(
    settings_repo: SettingsRepository = Depends(get_settings_repo),
    credentials_repo: CredentialsRepository = Depends(get_credentials_repo),
) -> GoogleAdsService:
    return GoogleAdsService(settings_repo, credentials_repo)


# ----------------------------------------------------------------------------
# Connection test
# ----------------------------------------------------------------------------


@router.post("/test-connection", response_model=GoogleAdsConnectionTestResponse)
async def test_connection(
    service: GoogleAdsService = Depends(get_google_ads_service),
) -> GoogleAdsConnectionTestResponse:
    """Test the Google Ads connection."""
    result = service.test_connection()
    return GoogleAdsConnectionTestResponse(**result)


# ----------------------------------------------------------------------------
# Account
# ----------------------------------------------------------------------------


@router.post("/account")
async def get_account_info(
    request: GetAccountInfoRequest,
    service: GoogleAdsService = Depends(get_google_ads_service),
) -> AccountInfoResponse:
    """Get basic information about a Google Ads account."""
    try:
        result = service.get_account_info(request.customer_id)
        return AccountInfoResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get account info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ----------------------------------------------------------------------------
# Campaigns
# ----------------------------------------------------------------------------


@router.post("/campaigns/list")
async def list_campaigns(
    request: ListCampaignsRequest,
    service: GoogleAdsService = Depends(get_google_ads_service),
) -> List[CampaignResponse]:
    """List campaigns in a Google Ads account."""
    try:
        results = service.list_campaigns(
            customer_id=request.customer_id,
            status_filter=request.status_filter,
            limit=request.limit,
        )
        return [CampaignResponse(**c) for c in results]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to list campaigns: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/campaigns/get")
async def get_campaign(
    request: GetCampaignRequest,
    service: GoogleAdsService = Depends(get_google_ads_service),
) -> CampaignResponse:
    """Get details for a single campaign."""
    try:
        result = service.get_campaign(
            campaign_id=request.campaign_id,
            customer_id=request.customer_id,
        )
        return CampaignResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get campaign: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/campaigns/create")
async def create_campaign(
    request: CreateCampaignRequest,
    service: GoogleAdsService = Depends(get_google_ads_service),
) -> CreateCampaignResponse:
    """Create a new Google Ads campaign."""
    try:
        result = service.create_campaign(
            name=request.name,
            daily_budget=request.daily_budget,
            start_date=request.start_date,
            customer_id=request.customer_id,
            end_date=request.end_date,
            status=request.status,
            advertising_channel_type=request.advertising_channel_type,
        )
        return CreateCampaignResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create campaign: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/campaigns/update-status")
async def update_campaign_status(
    request: UpdateCampaignStatusRequest,
    service: GoogleAdsService = Depends(get_google_ads_service),
) -> UpdateCampaignResponse:
    """Update the status of a campaign (ENABLED, PAUSED, REMOVED)."""
    try:
        result = service.update_campaign_status(
            campaign_id=request.campaign_id,
            status=request.status,
            customer_id=request.customer_id,
        )
        return UpdateCampaignResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to update campaign status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/campaigns/update-budget")
async def update_campaign_budget(
    request: UpdateCampaignBudgetRequest,
    service: GoogleAdsService = Depends(get_google_ads_service),
) -> UpdateCampaignResponse:
    """Update the daily budget of a campaign."""
    try:
        result = service.update_campaign_budget(
            campaign_id=request.campaign_id,
            daily_budget=request.daily_budget,
            customer_id=request.customer_id,
        )
        return UpdateCampaignResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to update campaign budget: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ----------------------------------------------------------------------------
# Ad Groups
# ----------------------------------------------------------------------------


@router.post("/ad-groups/list")
async def list_ad_groups(
    request: ListAdGroupsRequest,
    service: GoogleAdsService = Depends(get_google_ads_service),
) -> List[AdGroupResponse]:
    """List ad groups, optionally filtered by campaign."""
    try:
        results = service.list_ad_groups(
            customer_id=request.customer_id,
            campaign_id=request.campaign_id,
            limit=request.limit,
        )
        return [AdGroupResponse(**ag) for ag in results]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to list ad groups: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ad-groups/create")
async def create_ad_group(
    request: CreateAdGroupRequest,
    service: GoogleAdsService = Depends(get_google_ads_service),
) -> CreateAdGroupResponse:
    """Create an ad group within a campaign."""
    try:
        result = service.create_ad_group(
            campaign_id=request.campaign_id,
            name=request.name,
            cpc_bid=request.cpc_bid,
            customer_id=request.customer_id,
            status=request.status,
        )
        return CreateAdGroupResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create ad group: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ----------------------------------------------------------------------------
# Keywords
# ----------------------------------------------------------------------------


@router.post("/keywords/list")
async def list_keywords(
    request: ListKeywordsRequest,
    service: GoogleAdsService = Depends(get_google_ads_service),
) -> List[KeywordResponse]:
    """List keywords, optionally filtered by ad group."""
    try:
        results = service.list_keywords(
            customer_id=request.customer_id,
            ad_group_id=request.ad_group_id,
            limit=request.limit,
        )
        return [KeywordResponse(**kw) for kw in results]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to list keywords: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/keywords/add")
async def add_keyword(
    request: AddKeywordRequest,
    service: GoogleAdsService = Depends(get_google_ads_service),
) -> AddKeywordResponse:
    """Add a keyword to an ad group."""
    try:
        result = service.add_keyword(
            ad_group_id=request.ad_group_id,
            keyword_text=request.keyword_text,
            customer_id=request.customer_id,
            match_type=request.match_type,
            cpc_bid=request.cpc_bid,
        )
        return AddKeywordResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to add keyword: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ----------------------------------------------------------------------------
# Performance reports
# ----------------------------------------------------------------------------


@router.post("/reports/campaigns")
async def get_campaign_performance(
    request: GetCampaignPerformanceRequest,
    service: GoogleAdsService = Depends(get_google_ads_service),
) -> List[CampaignPerformanceResponse]:
    """Get performance metrics for campaigns."""
    try:
        results = service.get_campaign_performance(
            customer_id=request.customer_id,
            campaign_id=request.campaign_id,
            date_range=request.date_range,
        )
        return [CampaignPerformanceResponse(**r) for r in results]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get campaign performance: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reports/ad-groups")
async def get_ad_group_performance(
    request: GetAdGroupPerformanceRequest,
    service: GoogleAdsService = Depends(get_google_ads_service),
) -> List[AdGroupPerformanceResponse]:
    """Get performance metrics for ad groups."""
    try:
        results = service.get_ad_group_performance(
            customer_id=request.customer_id,
            campaign_id=request.campaign_id,
            date_range=request.date_range,
        )
        return [AdGroupPerformanceResponse(**r) for r in results]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get ad group performance: {e}")
        raise HTTPException(status_code=500, detail=str(e))
