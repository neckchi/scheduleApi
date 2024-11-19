import boto3
import os
import time

athena_client = boto3.client('athena')
cloudwatch_client = boto3.client('cloudwatch')


def lambda_handler(event, context):
    query = f""" SELECT client_ip, request_processing_time
            FROM {os.environ['ATHENA_TABLE']}
            WHERE from_iso8601_timestamp("time") BETWEEN date_add('minute', -5, current_timestamp) AND current_timestamp
            """

    # Execute Athena Query
    response = athena_client.start_query_execution(
        QueryString=query,
        QueryExecutionContext={'Database': os.environ['ATHENA_DATABASE']},
        ResultConfiguration={'OutputLocation': os.environ['ATHENA_OUTPUT_LOCATION']}
    )

    query_execution_id = response['QueryExecutionId']

    # Wait for Query Execution
    query_status = 'RUNNING'
    while query_status in ['RUNNING', 'QUEUED']:
        time.sleep(5)  # give time to query execute and update
        query_execution = athena_client.get_query_execution(QueryExecutionId=query_execution_id)
        query_status = query_execution['QueryExecution']['Status']['State']

    if query_status == 'SUCCEEDED':
        # Fetch results
        results = athena_client.get_query_results(QueryExecutionId=query_execution_id)

        for row in results["ResultSet"]["Rows"][1:]:
            client_ip = row["Data"][0]["VarCharValue"]

            # Push metric to CloudWatch
            cloudwatch_client.put_metric_data(
                Namespace='LoadBalancerMetricsP2P',
                MetricData=[
                    {
                        'MetricName': "RequestByIP",
                        'Dimensions': [
                            {
                                'Name': 'ClientIP',
                                'Value': client_ip
                            },
                            {
                                'Name': 'LoadBalancerName',
                                'Value': os.environ['ALB_NAME']
                            }
                        ],
                        'Value': 1,
                        'Unit': 'Count'
                    },
                ]
            )

            cloudwatch_client.put_metric_data(
                Namespace='LoadBalancerMetricsP2P',
                MetricData=[
                    {
                        'MetricName': "ProcessingTime",
                        'Dimensions': [
                            {
                                'Name': 'ClientIP',
                                'Value': client_ip
                            },
                            {
                                'Name': 'LoadBalancerName',
                                'Value': os.environ['ALB_NAME']
                            }
                        ],
                        'Value': float(row["Data"][1]["VarCharValue"]),
                        'Unit': 'Seconds'
                    },
                ]
            )
    else:
        print(f'Query failed: {query_status}')
