# Google Navigator Integration

This guide covers integrating with Google Maps services: Places (search, details, nearby), Directions, and Geocoding.

## Overview

Google Navigator provides location and navigation features through Google Maps APIs. It is separate from the Google (Gmail/Calendar) integration.

**Services Covered**:
- **Places Search**: Text search for businesses, landmarks, and addresses
- **Place Details**: Detailed info including hours, reviews, phone, website
- **Nearby Search**: Find places within a radius of a location
- **Directions**: Turn-by-turn route planning (driving, walking, transit, bicycling)
- **Geocoding**: Convert addresses to coordinates and vice versa

## Prerequisites

- Google Cloud account
- A Google Cloud project with billing enabled

## Step 1: Create an API Key

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create or select a project
3. Enable the required APIs:
   - **Places API (New)**: For text search and nearby search
   - **Directions API**: For route planning
   - **Geocoding API**: For address/coordinates conversion
4. Go to **APIs & Services > Credentials**
5. Click **Create Credentials > API Key**
6. Copy the API key

## Step 2: Configure in Settings

1. Go to **Settings > Integrations > Google Navigator**
2. Enable the Google Navigator integration
3. Paste your API key
4. Click **Save**
5. Click **Test Connection** to verify

Or use environment variables:

```bash
GOOGLE_NAVIGATOR_ENABLED=true
GOOGLE_PLACES_API_KEY=AIzaSy...
```

## How It Works

The Google Navigator integration is used internally by the assistant for location-related queries. When you ask about places, directions, or geocoding, the assistant calls the Google Maps APIs.

### Example Conversations

```
You: Find Italian restaurants in San Francisco
Assistant: [Returns list of Italian restaurants with ratings, addresses, and hours]

You: How do I get from San Francisco to Los Angeles by car?
Assistant: [Returns driving directions with duration and distance]

You: What are the coordinates of 1600 Amphitheatre Parkway?
Assistant: [Returns latitude and longitude]
```

## Connection Test

To verify your API key is working:

```bash
POST /api/google_navigator/test-connection
```

Returns:
```json
{
  "status": "success",
  "message": "Google Navigator is configured. API key found."
}
```

Or `"error"` if the key is missing or invalid.

## Rate Limits

Google Maps APIs have the following limits per API key:

| API | Free Tier | Paid Tier |
|-----|-----------|-----------|
| Places (Text Search) | 1,000 req/day | Higher |
| Places (Nearby) | 1,000 req/day | Higher |
| Directions | 2,500 req/day | Higher |
| Geocoding | 40,000 req/day | Higher |

All APIs share a common quota pool. Monitor usage at [Google Cloud Console](https://console.cloud.google.com/apis/dashboard).

## Troubleshooting

### "Google Navigator integration is not enabled"

- Go to **Settings > Integrations > Google Navigator**
- Ensure the toggle is enabled
- Verify an API key is saved

### "Places API (New) is not enabled"

- Go to [Google Cloud Console](https://console.cloud.google.com/apis/library/places-backend.googleapis.com)
- Enable **Places API (New)**

### API returns no results

- Verify the API key has the correct permissions
- Check that the APIs (Places, Directions, Geocoding) are enabled
- Check Google Cloud Console for quota or billing issues

### Directions fails with "OVER_QUERY_LIMIT"

- You have exceeded your daily quota
- Check [Google Cloud Console](https://console.cloud.google.com/apis/dashboard) for usage
- Enable billing for higher quotas (free tier has limits)

### Geocoding returns "No results"

- The address may not be geocodable
- Try a more specific address
- Check for typos

## Security Considerations

- **API Key**: Keep it secure — it provides access to Google Maps services
- **Quota**: Monitor your API usage in Google Cloud Console
- **Billing**: Ensure billing is set up to avoid service interruption when quotas are exceeded

## API References

- [Places API (New)](https://developers.google.com/maps/documentation/places/web-service/search-text)
- [Directions API](https://developers.google.com/maps/documentation/directions/get-directions)
- [Geocoding API](https://developers.google.com/maps/documentation/geocoding/overview)

---

**Last Updated**: March 2026
