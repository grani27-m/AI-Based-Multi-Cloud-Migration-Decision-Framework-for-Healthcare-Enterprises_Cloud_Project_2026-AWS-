#!/bin/bash
# STAGE 1b - run ONCE by the account administrator (the same session that created hcf-bootstrap). Free (first budgets are free).
# Sends e-mail when the month's FORECAST exceeds 80 % or ACTUAL spend exceeds 100 % of the limit.
#   bash deploy/aws/scripts/admin_create_budget.sh you@example.com 15
set -euo pipefail
EMAIL=${1:?usage: admin_create_budget.sh <email> [monthly-usd]}; LIMIT=${2:-15}
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
aws budgets create-budget --account-id "$ACCOUNT_ID" \
  --budget "{\"BudgetName\":\"hcf-monthly\",\"BudgetType\":\"COST\",\"TimeUnit\":\"MONTHLY\",\"BudgetLimit\":{\"Amount\":\"$LIMIT\",\"Unit\":\"USD\"}}" \
  --notifications-with-subscribers \
  "[{\"Notification\":{\"NotificationType\":\"FORECASTED\",\"ComparisonOperator\":\"GREATER_THAN\",\"Threshold\":80,\"ThresholdType\":\"PERCENTAGE\"},\"Subscribers\":[{\"SubscriptionType\":\"EMAIL\",\"Address\":\"$EMAIL\"}]},
    {\"Notification\":{\"NotificationType\":\"ACTUAL\",\"ComparisonOperator\":\"GREATER_THAN\",\"Threshold\":100,\"ThresholdType\":\"PERCENTAGE\"},\"Subscribers\":[{\"SubscriptionType\":\"EMAIL\",\"Address\":\"$EMAIL\"}]}]"
aws budgets describe-budget --account-id "$ACCOUNT_ID" --budget-name hcf-monthly --query 'Budget.{Name:BudgetName,Limit:BudgetLimit}' --output table
