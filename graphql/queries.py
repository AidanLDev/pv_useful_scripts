SCORES_BY_LOCATION_ID_QUERY = """
query ScoresByLocationID($locationID: ID!, $nextToken: String) {
	scoresByLocationID(locationID: $locationID, nextToken: $nextToken) {
		items {
			score
			dateTime
			published
		}
		nextToken
	}
}
"""

CUSTOMER_DATA_BY_LOCATION_ID_AND_DATE_TIME_QUERY = """
query CustomerDataByLocationIDAndDateTime($locationID: ID!, $nextToken: String) {
	customerDataByLocationIDAndDateTime(locationID: $locationID, nextToken: $nextToken) {
		items {
			measureName
			measureDataType
			measureUnit
			locationID
			id
			dateTime
			customerDataUserId
			createdAt
			_version
			measureValueBoolean
			measureValueNumber
			measureValueString
			siteID
			tag
			updatedAt
			_lastChangedAt
			_deleted
		}
		nextToken
	}
}
"""

# Backward-compatible alias if older code references the shorter constant name.
CUSTOMER_DATA_BY_LOCATION_ID_QUERY = CUSTOMER_DATA_BY_LOCATION_ID_AND_DATE_TIME_QUERY
