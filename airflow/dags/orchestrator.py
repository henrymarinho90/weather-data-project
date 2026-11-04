import os
import sys
from datetime import datetime, timedelta

from airflow.providers.docker.operators.docker import DockerOperator
from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import DAG
from docker.types import Mount

sys.path.append("/opt/airflow/api-request")


def ingest_weather_data():
    from insert_records import main

    return main()


def dbt_task(task_id, command):
    """Run a dbt command in the dbt image, on the compose network."""
    return DockerOperator(
        task_id=task_id,
        image=os.environ["DBT_IMAGE"],
        command=command,
        working_dir="/usr/app/weather",
        # Same uid/gid as the host user, so target/ and logs/ stay writable for them
        user=f"{os.environ.get('HOST_UID', '1000')}:{os.environ.get('HOST_GID', '1000')}",
        environment={
            "HOME": "/tmp",
            "DBT_PROFILES_DIR": "/usr/app",
            "DB_HOST": os.environ.get("DB_HOST", "db"),
            "DB_PORT": os.environ.get("DB_PORT", "5432"),
            "DB_USER": os.environ["DB_USER"],
            "DB_PASSWORD": os.environ["DB_PASSWORD"],
            "DB_NAME": os.environ["DB_NAME"],
        },
        # Must be a HOST path: DockerOperator talks to the host docker daemon
        mounts=[Mount(source=os.environ["DBT_HOST_PATH"], target="/usr/app", type="bind")],
        network_mode="weather_network",
        docker_url="unix:///var/run/docker.sock",
        auto_remove="success",
        mount_tmp_dir=False,
    )


with DAG(
    dag_id="api-dbt-orchestrator",
    description="Ingest weather data and transform it with dbt",
    start_date=datetime(2026, 10, 26),
    # Twice daily (08:00 and 20:00 UTC) = ~60 API calls/month, within the free tier
    schedule="0 8,20 * * *",
    catchup=False,
    max_active_runs=1,
    default_args={
        # One retry covers startup races; note an ingest retry can spend a second API call
        "retries": 1,
        "retry_delay": timedelta(minutes=2),
        # A hung API or dbt run must not block every later run (max_active_runs=1)
        "execution_timeout": timedelta(minutes=10),
    },
) as dag:
    ingest = PythonOperator(
        task_id="ingest_weather_data",
        python_callable=ingest_weather_data,
    )
    transform = dbt_task("transform_data_task", "build")
    # Fails when the newest observation is older than the source's error_after
    # (e.g. mock mode or a cached API response), even though dbt build passed
    freshness = dbt_task("check_source_freshness", "source freshness")

    ingest >> transform >> freshness
