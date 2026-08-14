#!/bin/sh
set -eu

awslocal s3api create-bucket --bucket croquitodxf-local-artifacts \
  --create-bucket-configuration LocationConstraint=sa-east-1
cat >/tmp/artifact-cors.json <<'EOF'
{
  "CORSRules": [{
    "AllowedHeaders": ["Content-Type", "x-amz-checksum-sha256"],
    "AllowedMethods": ["PUT", "HEAD", "GET"],
    "AllowedOrigins": ["http://localhost:5173", "http://127.0.0.1:5173"],
    "ExposeHeaders": ["ETag"],
    "MaxAgeSeconds": 300
  }]
}
EOF
awslocal s3api put-bucket-cors --bucket croquitodxf-local-artifacts --cors-configuration file:///tmp/artifact-cors.json
awslocal sqs create-queue --queue-name croquitodxf-local-processing-dlq
DLQ_ARN=$(awslocal sqs get-queue-attributes \
  --queue-url http://localhost:4566/000000000000/croquitodxf-local-processing-dlq \
  --attribute-names QueueArn --query 'Attributes.QueueArn' --output text)
# Sem redrive a DLQ fica solta e uma mensagem venenosa reentrega para sempre.
awslocal sqs create-queue --queue-name croquitodxf-local-processing \
  --attributes "{\"RedrivePolicy\":\"{\\\"deadLetterTargetArn\\\":\\\"${DLQ_ARN}\\\",\\\"maxReceiveCount\\\":\\\"5\\\"}\"}"
awslocal secretsmanager create-secret --name croquitodxf/local/runtime --secret-string '{}'

cat >/tmp/extraction-state-machine.json <<'EOF'
{
  "Comment": "Contrato local da extração; o worker local consome a fila.",
  "StartAt": "QueueStage",
  "States": {
    "QueueStage": {
      "Type": "Pass",
      "Result": {"stage": "VALIDATING"},
      "End": true
    }
  }
}
EOF

awslocal stepfunctions create-state-machine \
  --name croquitodxf-local-extraction \
  --role-arn arn:aws:iam::000000000000:role/croquitodxf-local-workflow \
  --definition file:///tmp/extraction-state-machine.json
