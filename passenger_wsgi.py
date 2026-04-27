from a2wsgi import ASGIMiddleware

from app.main import app
from app.services.jobs import ensure_background_job_runner_started

ensure_background_job_runner_started()
application = ASGIMiddleware(app)
