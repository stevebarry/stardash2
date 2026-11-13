# Gunicorn configuration for the BI Dashboard
bind = "127.0.0.1:8000"
workers = 3
threads = 2
timeout = 120          # long-running dashboard queries / exports
accesslog = "-"
errorlog = "-"
