output "artifact_bucket_name" {
  description = "Bucket privado de artefatos efêmeros."
  value       = aws_s3_bucket.artifacts.id
}

output "processing_queue_url" {
  description = "Fila principal de processamento."
  value       = aws_sqs_queue.processing.url
}

output "processing_dead_letter_queue_url" {
  description = "Fila de mensagens que esgotaram as tentativas."
  value       = aws_sqs_queue.processing_dead_letter.url
}

output "application_kms_key_arn" {
  description = "Chave KMS usada pelos recursos do primeiro marco."
  value       = aws_kms_key.application.arn
}

