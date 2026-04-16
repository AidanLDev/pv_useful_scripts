SCORES_BY_LOCATION_ID_QUERY = """
query ScoresByLocationID($locationID: ID!, $nextToken: String) {
	scoresByLocationID(locationID: $locationID, nextToken: $nextToken) {
		items {
			score
			dateTime
		}
		nextToken
	}
}
"""
