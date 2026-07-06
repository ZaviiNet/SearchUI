import os
from celery import Celery
from executor import GraphExecutor

# SQLite-based transport configuration
broker_db = "sqlite:///" + os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "celery_broker.sqlite"))
backend_db = "db+sqlite:///" + os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "celery_results.sqlite"))

celery_app = Celery(
    "searchui",
    broker=f"sqla+{broker_db}",
    backend=backend_db
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    result_expires=3600,
)

@celery_app.task(name="execute_graph_task")
def execute_graph_task(graph_json, origin=None):
    """
    Executes a node graph in a background Celery worker process.
    """
    try:
        executor = GraphExecutor(graph_json, origin=origin)
        result = executor.execute()
        return {
            "status": "success",
            "result": result,
            "node_outputs": executor.node_outputs
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }
