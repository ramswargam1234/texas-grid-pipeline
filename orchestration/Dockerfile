# Airflow image + an isolated virtualenv for the pipeline code (dbt, duckdb, pandas, boto3).
# Keeping them separate avoids dependency conflicts between Airflow and dbt.
FROM apache/airflow:3.2.2-python3.12

COPY requirements.txt /tmp/pipeline-requirements.txt
RUN python -m venv /opt/airflow/pipeline-venv \
 && /opt/airflow/pipeline-venv/bin/pip install --no-cache-dir -r /tmp/pipeline-requirements.txt

# Folder for Airflow's local metadata DB (mounted as a named volume so runs history survives restarts).
RUN mkdir -p /opt/airflow/db

ENV PIPELINE_PYTHON=/opt/airflow/pipeline-venv/bin/python
