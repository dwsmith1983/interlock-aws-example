# =============================================================================
# Pipeline Monitor — DynamoDB Stream consumer for RUNLOG# records
# Updates CONTROL# pipeline health and writes JOBLOG# analytics records.
# =============================================================================

# DynamoDB Stream -> pipeline-monitor (filtered to RUNLOG# records only)
resource "aws_lambda_event_source_mapping" "pipeline_monitor" {
  event_source_arn  = aws_dynamodb_table.main.stream_arn
  function_name     = aws_lambda_function.python["pipeline-monitor"].arn
  starting_position = "LATEST"
  batch_size        = 10

  filter_criteria {
    filter {
      pattern = jsonencode({
        dynamodb = {
          NewImage = {
            SK = {
              S = [{ "prefix" : "RUNLOG#" }]
            }
          }
        }
      })
    }
  }
}
