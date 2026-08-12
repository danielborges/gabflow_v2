resource "aws_sqs_queue" "whatsapp_dlq" {
  name                              = "${var.name_prefix}-whatsapp-inbound-dlq.fifo"
  fifo_queue                        = true
  content_based_deduplication       = false
  message_retention_seconds         = 1209600
  kms_master_key_id                 = var.kms_key_arn
  kms_data_key_reuse_period_seconds = 300
}

resource "aws_sqs_queue" "whatsapp_inbound" {
  name                              = "${var.name_prefix}-whatsapp-inbound.fifo"
  fifo_queue                        = true
  content_based_deduplication       = false
  message_retention_seconds         = 345600
  visibility_timeout_seconds        = var.visibility_timeout_seconds
  receive_wait_time_seconds         = 20
  kms_master_key_id                 = var.kms_key_arn
  kms_data_key_reuse_period_seconds = 300
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.whatsapp_dlq.arn
    maxReceiveCount     = var.max_receive_count
  })
}

resource "aws_sqs_queue_redrive_allow_policy" "whatsapp_dlq" {
  queue_url = aws_sqs_queue.whatsapp_dlq.id
  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.whatsapp_inbound.arn]
  })
}

data "aws_iam_policy_document" "api_queue" {
  statement {
    sid       = "PublishWhatsAppInboundEvents"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.whatsapp_inbound.arn]
  }

  statement {
    sid       = "EncryptWhatsAppQueueMessages"
    actions   = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = [var.kms_key_arn]
  }
}

resource "aws_iam_role_policy" "api_queue" {
  name   = "${var.name_prefix}-api-whatsapp-queue"
  role   = var.api_task_role_name
  policy = data.aws_iam_policy_document.api_queue.json
}

data "aws_iam_policy_document" "worker_queue" {
  statement {
    sid = "ConsumeAndReconcileWhatsAppInboundEvents"
    actions = [
      "sqs:ChangeMessageVisibility",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
      "sqs:ReceiveMessage",
      "sqs:SendMessage",
    ]
    resources = [aws_sqs_queue.whatsapp_inbound.arn]
  }

  statement {
    sid       = "UseWhatsAppQueueKey"
    actions   = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = [var.kms_key_arn]
  }
}

resource "aws_iam_role_policy" "worker_queue" {
  name   = "${var.name_prefix}-worker-whatsapp-queue"
  role   = var.worker_task_role_name
  policy = data.aws_iam_policy_document.worker_queue.json
}

resource "aws_cloudwatch_metric_alarm" "whatsapp_dlq_not_empty" {
  alarm_name          = "${var.name_prefix}-whatsapp-dlq-not-empty"
  alarm_description   = "Eventos WhatsApp aguardando tratamento na DLQ"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 3
  datapoints_to_alarm = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = aws_sqs_queue.whatsapp_dlq.name
  }
}

resource "aws_cloudwatch_metric_alarm" "whatsapp_oldest_message" {
  alarm_name          = "${var.name_prefix}-whatsapp-oldest-message"
  alarm_description   = "Evento WhatsApp aguardando processamento por mais de cinco minutos"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateAgeOfOldestMessage"
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 3
  datapoints_to_alarm = 2
  threshold           = 300
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = aws_sqs_queue.whatsapp_inbound.name
  }
}

resource "aws_cloudwatch_dashboard" "whatsapp_operations" {
  dashboard_name = "${var.name_prefix}-whatsapp-operations"
  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "WhatsApp inbound queue"
          region = var.aws_region
          view   = "timeSeries"
          period = 60
          stat   = "Maximum"
          metrics = [
            ["AWS/SQS", "ApproximateAgeOfOldestMessage", "QueueName", aws_sqs_queue.whatsapp_inbound.name],
            [".", "ApproximateNumberOfMessagesVisible", ".", ".", { yAxis = "right" }],
            [".", "ApproximateNumberOfMessagesNotVisible", ".", ".", { yAxis = "right" }],
          ]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "WhatsApp DLQ"
          region = var.aws_region
          view   = "timeSeries"
          period = 60
          stat   = "Maximum"
          metrics = [
            ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", aws_sqs_queue.whatsapp_dlq.name],
          ]
        }
      },
      {
        type   = "alarm"
        x      = 0
        y      = 6
        width  = 24
        height = 5
        properties = {
          title = "WhatsApp operational alarms"
          alarms = [
            aws_cloudwatch_metric_alarm.whatsapp_dlq_not_empty.arn,
            aws_cloudwatch_metric_alarm.whatsapp_oldest_message.arn,
          ]
        }
      },
    ]
  })
}
