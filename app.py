# app.py (Final and Correct Boto3 Implementation)

import os
import uuid
import boto3
import botocore
import subprocess
import threading
import re
import json
from flask import Flask, render_template, request, jsonify, send_from_directory
from datetime import datetime, timedelta

# --- All setup code is unchanged ---
from dotenv import load_dotenv
load_dotenv()
app = Flask(__name__)
LOG_DIR = "slow_logs"
ANALYSIS_DIR = "analysis"
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(ANALYSIS_DIR, exist_ok=True)
JOBS = {}

def get_all_rds_instances():
    try:
        aws_region = os.getenv("AWS_REGION")
        if not aws_region: raise Exception("AWS_REGION environment variable is not set.")
        rds_client = boto3.client('rds', region_name=aws_region)
        paginator = rds_client.get_paginator('describe_db_instances')
        instances = [db['DBInstanceIdentifier'] for page in paginator.paginate() for db in page['DBInstances']]
        return sorted(instances), None
    except Exception as e:
        print(f"Error fetching RDS instances: {e}")
        return [], str(e)

# --- REWRITTEN Core Logic Function (Final Boto3 Version) ---
def run_analysis_task(job_id, db_instances, start_date_str, end_date_str):
    """
    The main function that downloads and analyzes logs.
    This version uses the robust "list-then-filter" approach entirely within Python.
    1. It lists ALL available log files from the server using a paginator.
    2. It filters this complete list locally to find files within the date range.
    3. It downloads only the matching files.
    """
    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        
        aws_region = os.getenv("AWS_REGION")
        if not aws_region: raise Exception("AWS_REGION environment variable is not set.")
            
        JOBS[job_id]['status'] = 'Initializing AWS client...'
        rds_client = boto3.client('rds', region_name=aws_region)
        all_reports = []

        # 1. Generate a set of all date strings we are interested in (e.g., {'2025-07-02', '2025-07-03'})
        # This is for efficient checking later.
        dates_to_find = set()
        current_date = start_date
        while current_date <= end_date:
            dates_to_find.add(current_date.strftime('%Y-%m-%d'))
            current_date += timedelta(days=1)

        for db_instance_id in db_instances:
            JOBS[job_id]['status'] = f'Processing: {db_instance_id}'
            print(f"Processing slow query logs for {db_instance_id}...")
            
            # 2. List ALL available log files for the instance by paginating through all results.
            # This is the most critical step to get the complete list.
            JOBS[job_id]['status'] = f'Fetching full log file list for {db_instance_id}...'
            print(f"Fetching full log file list for {db_instance_id}...")
            paginator = rds_client.get_paginator('describe_db_log_files')
            all_log_files_on_server = []
            # The paginator handles fetching page by page until the list is complete.
            for page in paginator.paginate(DBInstanceIdentifier=db_instance_id):
                all_log_files_on_server.extend(page['DescribeDBLogFiles'])
            
            print(f"Found {len(all_log_files_on_server)} total log files on the server.")

            # 3. Filter this full list to get only the ones that match our date range.
            files_to_download = []
            for log_file_data in all_log_files_on_server:
                filename = log_file_data.get('LogFileName', '')
                # Check if the filename contains our target prefix and any of our target date strings.
                if "slowquery/mysql-slowquery.log" in filename and any(d in filename for d in dates_to_find):
                    files_to_download.append(filename)
            
            print(f"Found {len(files_to_download)} log files in the date range to download.")
            print(f"Files to download: {files_to_download}") # Debug print

            # --- Download and Aggregate ---
            output_log_file = os.path.join(LOG_DIR, f"aggregated-slow-query-{db_instance_id}-{job_id}.log")
            with open(output_log_file, 'w') as agg_log:
                for log_file_name in files_to_download:
                    JOBS[job_id]['status'] = f'Downloading {log_file_name}...'
                    print(f"Downloading {log_file_name}...")
                    marker = '0'
                    while True:
                        try:
                            response = rds_client.download_db_log_file_portion(
                                DBInstanceIdentifier=db_instance_id,
                                LogFileName=log_file_name,
                                Marker=marker
                            )
                            agg_log.write(response.get('LogFileData', ''))
                            if response.get('AdditionalDataPending') and response.get('Marker'):
                                marker = response['Marker']
                            else:
                                break
                        except botocore.exceptions.ClientError as error:
                            # Handle cases where a file from the list might have been rotated out
                            # between the list and download calls.
                            if error.response['Error']['Code'] == 'DBLogFileNotFoundFault':
                                print(f"WARNING: Listed file {log_file_name} was not found for download. Skipping.")
                                break # Break the inner while loop and go to the next file
                            else:
                                raise error
            
            # --- The pt-query-digest part is unchanged ---
            analysis_file = os.path.join(ANALYSIS_DIR, f"analysis-{db_instance_id}-{job_id}.txt")
            if os.path.getsize(output_log_file) > 0:
                JOBS[job_id]['status'] = f'Running pt-query-digest for {db_instance_id}...'
                print(f"Running pt-query-digest for {db_instance_id}...")
                command = ["pt-query-digest", output_log_file]
                with open(analysis_file, "w") as af:
                    subprocess.run(command, stdout=af, stderr=subprocess.PIPE, text=True, check=True)
                os.remove(output_log_file)
                all_reports.append({'instance': db_instance_id, 'file': os.path.basename(analysis_file)})
            else:
                print(f"No slow logs found for {db_instance_id} in the specified date range.")
                os.remove(output_log_file)
                
        JOBS[job_id]['status'] = 'Completed'
        JOBS[job_id]['reports'] = all_reports
    except Exception as e:
        print(f"Error during analysis for job {job_id}: {e}")
        JOBS[job_id]['status'] = f'Error: {e}'


# --- ALL FLASK ROUTES ARE UNCHANGED ---
@app.route('/')
def index():
    db_instances, error_message = get_all_rds_instances()
    return render_template('index.html', db_instances=db_instances, error_message=error_message)

@app.route('/start-analysis', methods=['POST'])
def start_analysis():
    data = request.json
    db_instances = data.get('instances', []); start_date = data.get('startDate'); end_date = data.get('endDate')
    if not all([db_instances, start_date, end_date]): return jsonify({'error': 'Missing required parameters.'}), 400
    job_id = str(uuid.uuid4())
    JOBS[job_id] = {'status': 'Pending', 'reports': []}
    thread = threading.Thread(target=run_analysis_task, args=(job_id, db_instances, start_date, end_date))
    thread.daemon = True
    thread.start()
    return jsonify({'jobId': job_id})

@app.route('/ai-analyze', methods=['POST'])
def ai_analyze():
    aws_region = os.getenv("AWS_REGION")
    if not aws_region: return jsonify({'error': 'AWS_REGION is not configured in the .env file.'}), 500
    data = request.json
    report_text = data.get('report_text')
    if not report_text: return jsonify({'error': 'No report text provided.'}), 400
    prompt = f"""
You are an expert MySQL performance analyst... (rest of prompt)
---
{report_text}
---
"""
    try:
        bedrock_runtime = boto3.client(service_name='bedrock-runtime', region_name=aws_region)
        model_id = 'anthropic.claude-3-sonnet-20240229-v1:0'
        request_body = {"anthropic_version": "bedrock-2023-05-31","max_tokens": 4096,"messages": [{"role": "user","content": [{"type": "text", "text": prompt}]}]}
        response = bedrock_runtime.invoke_model(modelId=model_id,contentType='application/json',accept='application/json',body=json.dumps(request_body))
        response_body = json.loads(response['body'].read())
        analysis_text = response_body['content'][0]['text']
        return jsonify({'analysis': analysis_text})
    except botocore.exceptions.ClientError as error:
        if error.response['Error']['Code'] == 'AccessDeniedException':
            return jsonify({'error': f"Access denied. Please ensure you have enabled access to the '{model_id}' model in the AWS Bedrock console in the {aws_region} region."}), 500
        else:
            return jsonify({'error': f'An error occurred with the AWS Bedrock service: {error}'}), 500
    except Exception as e:
        return jsonify({'error': f'An unexpected error occurred: {e}'}), 500

@app.route('/analysis')
def analysis_page():
    return render_template('analysis.html')

@app.route('/status/<job_id>')
def job_status(job_id):
    job = JOBS.get(job_id); return jsonify(job) if job else (jsonify({'status': 'Not Found'}), 404)

@app.route('/report/<filename>')
def serve_report(filename):
    if '..' in filename or filename.startswith('/'): return "Invalid filename", 400
    return send_from_directory(ANALYSIS_DIR, filename, as_attachment=False)
