import os
import sys
from datetime import datetime, timedelta

from airflow.sdk import DAG
from airflow.providers.standard.operators.python import PythonOperator
from airflow.providers.docker.operators.docker import DockerOperator
from docker.types import Mount

sys.path.append('/opt/airflow/api-request')


def safe_main_callable():
    from insert_records import main
    return main()


with DAG(
    dag_id="api-dbt-orchestrator",
    description="Ingest weather data and transform it with dbt",
    start_date=datetime(2026, 10, 26),
    # Twice daily (08:00 and 20:00 UTC) = ~60 API calls/month, within the free tier
    schedule="0 8,20 * * *",
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 1, "retry_delay": timedelta(minutes=2)},
) as dag:
    ingest = PythonOperator(
        task_id="ingest_weather_data",
        python_callable=safe_main_callable,
    )

    transform = DockerOperator(
        task_id="transform_data_task",
        image="ghcr.io/dbt-labs/dbt-postgres:1.9.latest",
        command="build",
        working_dir="/usr/app/my_project",
        user="1000:1000",
        environment={
            "HOME": "/tmp",
            "DBT_PROFILES_DIR": "/usr/app",
            "DB_HOST": os.environ.get("DB_HOST", "db"),
            "DB_PORT": os.environ.get("DB_PORT", "5432"),
            "DB_USER": os.environ["DB_USER"],
            "DB_PASSWORD": os.environ["DB_PASSWORD"],
            "DB_NAME": os.environ["DB_NAME"],
        },
        mounts=[
            # Must be a HOST path: DockerOperator talks to the host docker daemon
            Mount(source=os.environ["DBT_HOST_PATH"],
                  target="/usr/app",
                  type="bind"),
        ],
        network_mode="weather_network",
        docker_url="unix://var/run/docker.sock",
        auto_remove="success",
        mount_tmp_dir=False,
    )

    ingest >> transform
