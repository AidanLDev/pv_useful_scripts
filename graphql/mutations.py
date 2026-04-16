CREATE_SCORE_MUTATION = """
mutation CreateScore($input: CreateScoreInput!) {
	createScore(input: $input) {
		id
		locationID
		score
		dateTime
		published
	}
}
"""

CREATE_CUSTOMER_DATA_MUTATION = """
mutation CreateCustomerData($input: CreateCustomerDataInput!) {
	createCustomerData(input: $input) {
		id
		locationID
		siteID
		dateTime
		measureName
		tag
	}
}
"""
