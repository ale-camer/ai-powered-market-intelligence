"""Airflow discovery entrypoint for market_intel_daily DAG."""

from market_intel.pipelines.market_intel_dag import market_intel_daily

# Expose 'dag' globally so that the Airflow scheduler discovers it
dag = market_intel_daily
