#!/usr/bin/env bash

set -euo pipefail

: "${EXPECTED_ACCOUNT_ID:?EXPECTED_ACCOUNT_ID must be set}"
: "${STAGING_NAME_PREFIX:?STAGING_NAME_PREFIX must be set}"

account_id=$(aws sts get-caller-identity --query Account --output text)
if [[ "$account_id" != "$EXPECTED_ACCOUNT_ID" ]]; then
  echo "Refusing teardown in unexpected AWS account $account_id."
  exit 1
fi

db_status=$(aws rds describe-db-instances \
  --query "DBInstances[?DBInstanceIdentifier=='$STAGING_NAME_PREFIX'] | [0].DBInstanceStatus" \
  --output text)
if [[ -n "$db_status" && "$db_status" != "None" ]]; then
  aws rds modify-db-instance \
    --db-instance-identifier "$STAGING_NAME_PREFIX" \
    --no-deletion-protection \
    --apply-immediately >/dev/null
  aws rds wait db-instance-available \
    --db-instance-identifier "$STAGING_NAME_PREFIX"
else
  echo "RDS instance is already absent."
fi

lb_arn=$(aws elbv2 describe-load-balancers \
  --query "LoadBalancers[?LoadBalancerName=='${STAGING_NAME_PREFIX}-alb'] | [0].LoadBalancerArn" \
  --output text)
if [[ -n "$lb_arn" && "$lb_arn" != "None" ]]; then
  aws elbv2 modify-load-balancer-attributes \
    --load-balancer-arn "$lb_arn" \
    --attributes Key=deletion_protection.enabled,Value=false >/dev/null
  aws elbv2 delete-load-balancer --load-balancer-arn "$lb_arn"
  aws elbv2 wait load-balancers-deleted --load-balancer-arns "$lb_arn"
else
  echo "Application Load Balancer is already absent."
fi

for attempt in {1..60}; do
  eni_count=$(aws ec2 describe-network-interfaces \
    --filters "Name=description,Values=ELB app/${STAGING_NAME_PREFIX}-alb/*" \
    --query 'length(NetworkInterfaces)' \
    --output text)
  if [[ "$eni_count" == "0" ]]; then
    echo "Load balancer network interfaces have been removed."
    break
  fi
  if [[ "$attempt" == "60" ]]; then
    echo "Timed out waiting for $eni_count load balancer network interface(s)."
    aws ec2 describe-network-interfaces \
      --filters "Name=description,Values=ELB app/${STAGING_NAME_PREFIX}-alb/*" \
      --query 'NetworkInterfaces[].{Id:NetworkInterfaceId,Description:Description,Status:Status,Subnet:SubnetId}'
    exit 1
  fi
  sleep 10
done
