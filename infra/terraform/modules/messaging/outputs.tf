output "whatsapp_inbound_queue_url" {
  value = aws_sqs_queue.whatsapp_inbound.url
}

output "whatsapp_inbound_queue_arn" {
  value = aws_sqs_queue.whatsapp_inbound.arn
}

output "whatsapp_dlq_arn" {
  value = aws_sqs_queue.whatsapp_dlq.arn
}

output "whatsapp_operations_dashboard_name" {
  value = aws_cloudwatch_dashboard.whatsapp_operations.dashboard_name
}
